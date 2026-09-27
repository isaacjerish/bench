"""Temporary visual inspection: phone photo in, hypotheses out, probes decide.

The camera session never stores a photo on disk. Model output is a hypothesis
until an allowlisted BenchClient measurement records a physical fact.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import math
import os
import re
import secrets
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import escape
from http import HTTPStatus
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

import segno

SESSION_TTL = timedelta(minutes=10)
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_GEMINI_INLINE_BYTES = 12 * 1024 * 1024
# A full schema answer runs past 10 kB, and reasoning models spend this budget first.
MAX_OUTPUT_TOKENS = 8192
DEFAULT_MODEL = "gemini-robotics-er-2-preview"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = REPO_ROOT / "physical_tests"
PROBES = frozenset({"P1", "P2", "P3"})
CHECK_PROFILES = frozenset({"rail_3v3", "ground", "led_blink", "servo_signal", "imu_vcc"})
WINDOW_MS = 1000
CAPTURE_PATH = re.compile(r"^/capture/(?P<token>[A-Za-z0-9_-]{20,120})(?P<tail>/status)?$")
STATUS_LABELS = {
    "ready": "READY",
    "waiting": "WAITING FOR IMAGE",
    "uploaded": "IMAGE RECEIVED",
    "analyzing": "ANALYZING",
    "complete": "COMPLETE",
    "error": "ERROR",
    "expired": "EXPIRED",
}
PUBLIC_URL_HELP = (
    "Set BENCHY_PUBLIC_BASE_URL to an address your phone can open, "
    "such as http://192.168.x.x:8765 or a tunnel URL. "
    "Benchy will not put localhost in a QR code. "
    "Set BENCHY_BIND_HOST=0.0.0.0 when the phone is on the same network."
)
SYSTEM_PROMPT = (
    "You are the visual inspection subsystem for Benchy, an embedded hardware "
    "debugging and verification instrument.\n\n"
    "You analyze photographs of development boards, breadboards, sensors, "
    "modules, connectors, jumper wires, actuators, electronic components, and "
    "physical devices under test.\n\n"
    "Your job is to produce visually grounded debugging evidence.\n\n"
    "Pay particular attention to visible board and module identity, GPIO and "
    "pin labels, jumper-wire routing, breadboard row placement, power rail "
    "usage, missing wires, loose or disconnected wires, shifted connections, "
    "incorrectly seated components, reversed connectors, polarity issues when "
    "visually evident, switch and jumper positions, visible component markings, "
    "burned, damaged, or bent components, and mismatch between visible wiring "
    "and the expected Benchy harness.\n\n"
    "You may also receive context describing DUT identity, expected pin "
    "assignments, expected harness, expected electrical behavior, and Benchy "
    "measurement results.\n\n"
    "Always distinguish between:\n"
    "1. VISUAL OBSERVATION\n"
    "2. HYPOTHESIS\n"
    "3. RECOMMENDED PHYSICAL CHECK\n\n"
    "Never infer voltage, frequency, current, continuity, signal integrity, or "
    "electrical correctness from appearance alone.\n\n"
    "Never claim that an internal electronic component has electrically failed "
    "solely because of appearance unless there is clear visible physical damage, "
    "and even then describe the visible damage rather than asserting electrical "
    "failure.\n\n"
    "If labels, wires, or components are ambiguous, explicitly state the "
    "uncertainty.\n\n"
    "Prefer useful, conservative observations over confident hallucinations.\n\n"
    "Your purpose is to tell Benchy where to investigate next. Benchy’s physical "
    "probes determine what is electrically true.\n\n"
    "Confidence must be LOW, MEDIUM, or HIGH. Recommended checks may use only "
    "measure_voltage, read_digital, or measure_frequency with target P1, P2, or "
    "P3; measure_voltage_pair; measure_bus_activity; measure_digital_taps; or "
    "check_circuit with target rail_3v3, ground, led_blink, servo_signal, or "
    "imu_vcc. Do not recommend flashing, rewiring, or any other command."
)
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "observed_hardware": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "item": {"type": "STRING"},
            "confidence": {"type": "STRING", "enum": ["LOW", "MEDIUM", "HIGH"]},
        }, "required": ["item", "confidence"]}},
        "observations": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "observation": {"type": "STRING"},
            "confidence": {"type": "STRING", "enum": ["LOW", "MEDIUM", "HIGH"]},
        }, "required": ["observation", "confidence"]}},
        "possible_issues": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "issue": {"type": "STRING"},
            "evidence": {"type": "ARRAY", "items": {"type": "STRING"}},
            "confidence": {"type": "STRING", "enum": ["LOW", "MEDIUM", "HIGH"]},
        }, "required": ["issue", "evidence", "confidence"]}},
        "recommended_checks": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "measurement": {"type": "STRING"},
            "target": {"type": "STRING"},
            "reason": {"type": "STRING"},
        }, "required": ["measurement", "reason"]}},
        "limitations": {"type": "ARRAY", "items": {"type": "STRING"}},
        "regions": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "label": {"type": "STRING"},
            "box": {"type": "OBJECT", "properties": {
                "x": {"type": "NUMBER"}, "y": {"type": "NUMBER"},
                "width": {"type": "NUMBER"}, "height": {"type": "NUMBER"},
            }, "required": ["x", "y", "width", "height"]},
        }, "required": ["label", "box"]}},
    },
    "required": ["observed_hardware", "observations", "possible_issues",
                 "recommended_checks", "limitations"],
}


class VisualError(Exception):
    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = status


class VisionProvider(Protocol):
    def analyze(self, image: bytes, mime_type: str, context: dict) -> dict:
        """Return unvalidated structured model JSON."""


def header_hostname(host_header: str) -> str:
    value = (host_header or "").strip().lower()
    if value.startswith("["):
        end = value.find("]")
        return value[1:end] if end != -1 else value
    return value.split(":")[0]


def local_dashboard_allowed(client_host: str, host_header: str) -> bool:
    """Dashboard routes stay on the laptop, including when a tunnel forwards them."""
    peer = (client_host or "").lower()
    if peer not in {"127.0.0.1", "::1"}:
        return False
    return header_hostname(host_header) in {"127.0.0.1", "localhost", "::1"}


def is_phone_capture_path(path: str) -> bool:
    return path == "/app.css" or CAPTURE_PATH.match(path) is not None


def parse_capture_path(path: str) -> tuple[str, str] | None:
    match = CAPTURE_PATH.match(path)
    if not match:
        return None
    return match.group("token"), match.group("tail") or ""


def public_base_url() -> str | None:
    """Return a phone-reachable origin, never a loopback address."""
    raw = os.environ.get("BENCHY_PUBLIC_BASE_URL", "").strip()
    if not raw:
        return None
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower().rstrip(".")
    if (parts.scheme not in {"http", "https"} or not host or parts.username
            or parts.password or parts.query or parts.fragment
            or parts.path not in {"", "/"}):
        return None
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return None
    formatted = f"[{host}]" if ":" in host else host
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{formatted}{port}"


def local_ipv4_addresses() -> set[str]:
    try:
        return {info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except (OSError, UnicodeError):
        return set()


def unreachable_host_warning(base: str) -> str | None:
    """A literal IP that is not ours cannot reach this laptop. A tunnel name still can."""
    host = urlsplit(base).hostname or ""
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        return None
    if parsed.version != 4:
        return None
    local = local_ipv4_addresses()
    if not local or host in local:
        return None
    return (f"BENCHY_PUBLIC_BASE_URL points at {host}, which is not an address of this computer "
            f"({', '.join(sorted(local))}). The phone will not reach that QR code.")


def availability() -> dict:
    base = public_base_url()
    if base:
        return {"available": True, "public_base_url": base, "message": None,
                "warning": unreachable_host_warning(base)}
    return {"available": False, "public_base_url": None, "message": PUBLIC_URL_HELP, "warning": None}


def make_qr_svg(url: str) -> str:
    svg = segno.make(url, error="m").svg_inline(scale=4, border=2, dark="#111111", light="#f4f4f2").strip()
    if not svg.startswith("<svg") or "<script" in svg.lower():
        raise VisualError("QR code could not be created.")
    return svg


def sniff_image(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_image(data: bytes, content_type: str) -> str:
    if len(data) > MAX_IMAGE_BYTES:
        raise VisualError("Image is larger than 5 MB.")
    if len(data) < 16:
        raise VisualError("Image file is empty or incomplete.")
    declared = (content_type or "").split(";")[0].strip().lower()
    detected = sniff_image(data)
    if declared not in {"image/jpeg", "image/png", "image/webp"} or detected is None:
        raise VisualError("Use a JPEG, PNG, or WEBP photo.")
    if detected != declared:
        raise VisualError("File contents do not match the declared image type.")
    return detected


def _clip(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text:
        return None
    return text[:limit]


def _confidence(value: object) -> str | None:
    if isinstance(value, str) and value.strip().upper() in {"LOW", "MEDIUM", "HIGH"}:
        return value.strip().upper()
    return None


def resolve_check(measurement: object, target: object) -> dict:
    """Map a recommendation onto a fixed BenchClient call. Never eval names."""
    if not isinstance(measurement, str):
        raise VisualError("Benchy cannot run that check.")
    name = measurement.strip()
    chosen = target.strip() if isinstance(target, str) else ""
    chosen = chosen or None
    if name in {"measure_voltage", "read_digital", "measure_frequency"}:
        if chosen not in PROBES:
            raise VisualError("Choose probe P1, P2, or P3.")
        spec = {"measurement": name, "probe": chosen}
        if name == "measure_frequency":
            spec["duration_ms"] = WINDOW_MS
        return spec
    if name == "check_circuit":
        if chosen not in CHECK_PROFILES:
            raise VisualError("Benchy cannot run that circuit check.")
        return {"measurement": name, "profile": chosen}
    if name == "measure_voltage_pair":
        return {"measurement": name}
    if name in {"measure_bus_activity", "measure_digital_taps"}:
        return {"measurement": name, "duration_ms": WINDOW_MS}
    raise VisualError("Benchy cannot run that check.")


def check_label(measurement: str, target: str | None) -> str:
    if measurement == "measure_voltage":
        return f"Measure voltage on {target}"
    if measurement == "read_digital":
        return f"Read digital level on {target}"
    if measurement == "measure_frequency":
        return f"Measure frequency on {target}"
    if measurement == "measure_voltage_pair":
        return "Measure P1 and P2 voltage"
    if measurement == "measure_bus_activity":
        return "Sample bus activity"
    if measurement == "measure_digital_taps":
        return "Sample digital taps"
    if measurement == "check_circuit":
        return f"Run {target} physical check"
    return "Benchy cannot run this check"


def classify_recommendation(item: object) -> dict | None:
    if not isinstance(item, dict):
        return None
    reason = _clip(item.get("reason"), 240) or "No reason was given."
    measurement = item.get("measurement")
    try:
        spec = resolve_check(measurement, item.get("target"))
    except VisualError:
        label = measurement.strip() if isinstance(measurement, str) and measurement.strip() else "suggestion"
        return {"measurement": label[:80], "target": _clip(item.get("target"), 40),
                "reason": reason, "supported": False, "label": "Benchy cannot run this check"}
    stored = spec.get("probe") or spec.get("profile")
    return {"measurement": spec["measurement"], "target": stored, "reason": reason,
            "supported": True, "label": check_label(spec["measurement"], stored)}


def _region(item: object) -> dict | None:
    if not isinstance(item, dict):
        return None
    label = _clip(item.get("label"), 160)
    box = item.get("box")
    if not label or not isinstance(box, dict):
        return None
    try:
        values = [float(box[key]) for key in ("x", "y", "width", "height")]
    except (KeyError, TypeError, ValueError):
        return None
    x, y, width, height = values
    if not all(math.isfinite(number) for number in values):
        return None
    if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < width <= 1 and 0 < height <= 1):
        return None
    if x + width > 1.001 or y + height > 1.001:
        return None
    return {"label": label, "box": {"x": round(x, 4), "y": round(y, 4),
                                    "width": round(width, 4), "height": round(height, 4)}}


def validate_analysis(payload: object) -> dict:
    """Keep only visually scoped fields. Electrical claims are not accepted."""
    required = ("observed_hardware", "observations", "possible_issues",
                "recommended_checks", "limitations")
    if not isinstance(payload, dict) or any(not isinstance(payload.get(key), list) for key in required):
        raise VisualError("The vision model returned a response Benchy could not validate.")
    hardware = []
    for item in payload["observed_hardware"][:12]:
        if not isinstance(item, dict):
            continue
        name = _clip(item.get("item"), 160)
        confidence = _confidence(item.get("confidence"))
        if name and confidence:
            hardware.append({"item": name, "confidence": confidence})
    observations = []
    for item in payload["observations"][:12]:
        if not isinstance(item, dict):
            continue
        text = _clip(item.get("observation"), 400)
        confidence = _confidence(item.get("confidence"))
        if text and confidence:
            observations.append({"observation": text, "confidence": confidence})
    issues = []
    for item in payload["possible_issues"][:8]:
        if not isinstance(item, dict):
            continue
        text = _clip(item.get("issue"), 400)
        confidence = _confidence(item.get("confidence"))
        evidence = item.get("evidence")
        if not text or not confidence or not isinstance(evidence, list):
            continue
        notes = [note for note in (_clip(entry, 240) for entry in evidence[:6]) if note]
        issues.append({"issue": text, "evidence": notes, "confidence": confidence,
                       "kind": "hypothesis", "electrically_verified": False})
    checks = [item for item in (classify_recommendation(entry) for entry in payload["recommended_checks"][:8]) if item]
    limitations = [note for note in (_clip(entry, 240) for entry in payload["limitations"][:8]) if note]
    regions = [item for item in (_region(entry) for entry in payload.get("regions", [])[:8]) if item] if isinstance(payload.get("regions", []), list) else []
    return {"observed_hardware": hardware, "observations": observations, "possible_issues": issues,
            "recommended_checks": checks, "limitations": limitations, "regions": regions,
            "evidence_class": "visual_hypothesis"}


def _probe_summary(sample: dict | None) -> dict | None:
    if not isinstance(sample, dict):
        return None
    readings = []
    for item in sample.get("readings") or []:
        if not isinstance(item, dict):
            continue
        readings.append({"probe": item.get("probe"), "voltage_v": item.get("voltage_v"),
                         "declared_net": item.get("declared_net"), "declared_state": item.get("declared_state")})
    return {"timestamp": sample.get("timestamp"), "source": "s3_physical",
            "digital_states": sample.get("digital_states"), "readings": readings[:6]}


def _capture_summary(capture: dict | None) -> dict | None:
    if not isinstance(capture, dict):
        return None
    if isinstance(capture.get("taps"), dict):
        taps = []
        for name, tap in list(capture["taps"].items())[:8]:
            if isinstance(tap, dict):
                taps.append({"tap": name, "edges": tap.get("edges"), "declared_net": tap.get("declared_net")})
        return {"kind": "digital_taps", "window_ms": capture.get("window_ms"), "taps": taps,
                "source": "s3_physical"}
    if isinstance(capture.get("sda"), dict) and isinstance(capture.get("scl"), dict):
        return {"kind": "bus_activity", "window_ms": capture.get("window_ms"),
                "sda_edges": capture["sda"].get("edges"), "scl_edges": capture["scl"].get("edges"),
                "source": "s3_physical"}
    return None


def _declared_identity(section: object) -> dict:
    if not isinstance(section, dict):
        return {}
    hidden = {"usb_serial_number", "serial_port_hint"}
    return {key: value for key, value in section.items() if key not in hidden}


def _declared_probes(probes: object) -> dict:
    kept = {}
    if not isinstance(probes, dict):
        return kept
    fields = ("state", "net", "tip", "note", "expected_min_v", "expected_max_v")
    for name, probe in probes.items():
        if isinstance(probe, dict):
            kept[name] = {key: probe[key] for key in fields if key in probe}
    return kept


def _declared_taps(taps: object) -> dict:
    kept = {}
    if not isinstance(taps, dict):
        return kept
    for name, tap in taps.items():
        if isinstance(tap, dict):
            kept[name] = {key: tap[key] for key in ("state", "net", "endpoint") if key in tap}
    return kept


def build_inspection_context(harness: dict | None, probes: dict | None, capture: dict | None,
                             serial_lines: list[str], harness_error: str | None = None) -> dict:
    """Context for the photo. Declarations stay labeled as declarations."""
    source = harness if isinstance(harness, dict) else {}
    dut = _declared_identity(source.get("dut"))
    lines = [line[:180] for line in serial_lines[:12] if isinstance(line, str) and line.strip()]
    context = {
        "dut": {"board": dut.get("board"), "firmware": dut.get("firmware")},
        "lab_board": _declared_identity(source.get("lab")).get("board"),
        "profile": dut.get("firmware"),
        "source": "user_declared",
        "physically_verified": False,
        "dut_pins": source.get("dut_pins") if isinstance(source.get("dut_pins"), dict) else {},
        "expected_harness": {"probes": _declared_probes(source.get("probes")),
                             "digital_taps": _declared_taps(source.get("digital_taps")),
                             "bus_monitor": source.get("bus_monitor") if isinstance(source.get("bus_monitor"), dict) else {}},
        "expected_behavior": {"telemetry_checks": source.get("telemetry_checks") or [],
                              "activity_checks": source.get("activity_checks") or []},
        "latest_measurements": {"probes": _probe_summary(probes), "capture": _capture_summary(capture),
                                "recent_serial_lines": lines},
    }
    if harness_error:
        context["harness_error"] = harness_error[:240]
    return context


def user_prompt(context: dict) -> str:
    return (
        "Here is the expected wiring and behavior from Benchy, and the latest "
        "physical measurements when they exist. The attached photograph shows "
        "the device under test. Report visually supported observations that "
        "could explain a mismatch. Do not state electrical facts.\n\n"
        + json.dumps(context, indent=2, default=str)
    )


def configured_model_name() -> str:
    model = os.environ.get("BENCHY_VISION_MODEL", DEFAULT_MODEL).strip()
    return model or DEFAULT_MODEL


def get_provider() -> VisionProvider:
    name = os.environ.get("BENCHY_VISION_PROVIDER", "gemini").strip().lower() or "gemini"
    if name != "gemini":
        raise VisualError(
            "BENCHY_VISION_PROVIDER must be gemini. Benchy will not switch vision providers automatically.",
            HTTPStatus.SERVICE_UNAVAILABLE)
    return GeminiRestProvider(os.environ.get("GEMINI_API_KEY", "").strip(), configured_model_name())


def _model_text(payload: dict) -> str:
    if not isinstance(payload, dict):
        raise VisualError("The vision model returned a response Benchy could not validate.")
    feedback = payload.get("promptFeedback")
    if isinstance(feedback, dict) and feedback.get("blockReason"):
        raise VisualError("The vision model could not analyze this photo.")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        raise VisualError("The vision model returned no answer for this photo.")
    finish = candidates[0].get("finishReason")
    if finish == "MAX_TOKENS":
        raise VisualError(
            f"The vision model reached its {MAX_OUTPUT_TOKENS} token output limit before it "
            "finished answering. Try again, or use a model that answers more briefly.")
    if finish in {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "RECITATION", "SPII"}:
        raise VisualError("The vision model declined to analyze this photo.")
    parts = (candidates[0].get("content") or {}).get("parts") if isinstance(candidates[0].get("content"), dict) else None
    texts = [part.get("text") for part in parts or [] if isinstance(part, dict) and isinstance(part.get("text"), str)]
    if not texts:
        detail = f" It stopped with {finish}." if isinstance(finish, str) and finish else ""
        raise VisualError(f"The vision model returned no text to read.{detail}")
    return "\n".join(texts).strip()


def _parse_model_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise VisualError("The vision model did not answer with valid JSON.") from exc
    if not isinstance(value, dict):
        raise VisualError("The vision model did not answer with valid JSON.")
    return value


class GeminiRestProvider:
    """Gemini Robotics ER calls over the public REST API. The UI never sees the key."""

    def __init__(self, api_key: str, model: str, urlopen=urllib.request.urlopen):
        self.api_key = api_key
        self.model = model
        self._urlopen = urlopen

    def describe_images(self, images: list[tuple[bytes, str]]) -> str:
        """Turn multiple photos into a neutral visual description for Codex context."""
        if not self.api_key:
            raise VisualError("Set GEMINI_API_KEY in .env to use photo context.",
                              HTTPStatus.SERVICE_UNAVAILABLE)
        if not self.model:
            raise VisualError("BENCHY_VISION_MODEL is empty.", HTTPStatus.SERVICE_UNAVAILABLE)
        if not images or len(images) > 4:
            raise VisualError("Attach between one and four photos.")
        if sum(len(image) for image, _mime in images) > MAX_GEMINI_INLINE_BYTES:
            raise VisualError("The selected photos exceed Gemini's 12 MB combined limit. Use fewer or smaller photos.",
                              HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        parts = [{"text": (
            "Describe these photos as one visual-context note for a hardware debugging conversation. "
            "Inventory visible boards, modules, components, connectors, and physical controls. "
            "Transcribe legible printed labels and markings. Describe visible wire paths and where they "
            "appear to meet pins, breadboard rows, or power rails; say when a route or label is uncertain. "
            "Mention image-to-image differences if the views show different angles or states. Be concise but "
            "include useful details and spatial relationships. Do not diagnose a fault, propose a fix or test, "
            "infer voltage/current/continuity/signal behavior, or treat appearance as electrical evidence. "
            "Output only the descriptive note, with uncertainties clearly marked."
        )}]
        for index, (image, mime_type) in enumerate(images, 1):
            parts.append({"text": f"Photo {index}:"})
            parts.append({"inlineData": {"mimeType": mime_type,
                                          "data": base64.b64encode(image).decode("ascii")}})
        body = {
            "systemInstruction": {"parts": [{"text": (
                "You are a visual note-taking stage for an electronics debugging assistant. "
                "Your only job is to convert visible image content into a careful text description. "
                "Do not infer electrical or functional correctness, diagnose problems, recommend measurements, "
                "or make decisions for the debugger. Distinguish clear observations from uncertain visual guesses."
            )}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096},
        }
        url = GEMINI_ENDPOINT.format(model=urllib.parse.quote(self.model, safe=""))
        request = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            method="POST")
        try:
            with self._urlopen(request, timeout=45) as response:
                raw = response.read(1_000_000)
        except urllib.error.HTTPError as exc:
            self._raise_http(exc)
        except TimeoutError as exc:
            raise VisualError("Gemini photo description timed out.", HTTPStatus.GATEWAY_TIMEOUT) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise VisualError("Could not reach Gemini to describe the photos.",
                              HTTPStatus.SERVICE_UNAVAILABLE) from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VisualError("Gemini returned an unreadable photo description.") from exc
        return _model_text(payload)

    def analyze(self, image: bytes, mime_type: str, context: dict) -> dict:
        if not self.api_key:
            raise VisualError("GEMINI_API_KEY is not set for the dashboard process.",
                              HTTPStatus.SERVICE_UNAVAILABLE)
        if not self.model:
            raise VisualError("BENCHY_VISION_MODEL is empty.", HTTPStatus.SERVICE_UNAVAILABLE)
        body = {"systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": [
                    {"text": user_prompt(context)},
                    {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(image).decode("ascii")}},
                ]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": MAX_OUTPUT_TOKENS,
                                     "responseMimeType": "application/json",
                                     "responseSchema": RESPONSE_SCHEMA}}
        url = GEMINI_ENDPOINT.format(model=urllib.parse.quote(self.model, safe=""))
        request = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            method="POST")
        try:
            with self._urlopen(request, timeout=30) as response:
                raw = response.read(1_000_000)
        except urllib.error.HTTPError as exc:
            self._raise_http(exc)
        except TimeoutError as exc:
            raise VisualError("Visual analysis timed out.", HTTPStatus.GATEWAY_TIMEOUT) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise VisualError("Could not reach the vision model.", HTTPStatus.SERVICE_UNAVAILABLE) from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VisualError("The vision model returned a response Benchy could not validate.") from exc
        return _parse_model_json(_model_text(payload))

    def _raise_http(self, exc: urllib.error.HTTPError) -> None:
        message = ""
        try:
            raw = exc.read(4096)
            parsed = json.loads(raw.decode("utf-8", errors="replace") or "{}")
            extracted = parsed.get("error", {}).get("message", "") if isinstance(parsed, dict) else ""
            if isinstance(extracted, str):
                message = " ".join(extracted.split())[:240]
        except (OSError, json.JSONDecodeError, AttributeError):
            message = ""
        lowered = message.lower()
        unavailable = exc.code == 404 or (
            "model" in lowered and any(word in lowered for word in ("not found", "not available", "unsupported", "does not exist")))
        if unavailable:
            raise VisualError(
                f"Configured vision model {self.model} is not available to this API key. "
                "Benchy will not switch models.",
                HTTPStatus.SERVICE_UNAVAILABLE) from None
        if exc.code == 429:
            raise VisualError("Vision model quota or rate limit was reached. Try again shortly.",
                              HTTPStatus.SERVICE_UNAVAILABLE) from None
        raise VisualError("Visual analysis failed.", HTTPStatus.SERVICE_UNAVAILABLE) from None


def describe_images_for_context(images: list[tuple[bytes, str]]) -> str:
    provider = GeminiRestProvider(
        os.environ.get("GEMINI_API_KEY", "").strip(), configured_model_name())
    return provider.describe_images(images)


def analyze_dut_image(image: bytes, mime_type: str, context: dict,
                      provider: VisionProvider | None = None) -> dict:
    raw = (provider or get_provider()).analyze(image, mime_type, context)
    return validate_analysis(raw)


def execute_check(client, spec: dict) -> dict:
    """Run one already-resolved measurement. The spec comes from resolve_check."""
    measurement = spec["measurement"]
    if measurement == "measure_voltage":
        return client.measure_voltage(spec["probe"])
    if measurement == "read_digital":
        return client.read_digital(spec["probe"])
    if measurement == "measure_frequency":
        return client.measure_frequency(spec["probe"], spec["duration_ms"])
    if measurement == "measure_voltage_pair":
        return client.measure_voltage_pair()
    if measurement == "measure_bus_activity":
        return client.measure_bus_activity(spec["duration_ms"])
    if measurement == "measure_digital_taps":
        return client.measure_digital_taps(spec["duration_ms"])
    if measurement == "check_circuit":
        from .checks import run_suite
        return run_suite(client, PROFILE_DIR / f"{spec['profile']}.yaml")
    raise VisualError("Benchy cannot run that check.")


def summarize_physical(spec: dict, reading: dict) -> str:
    try:
        measurement = spec["measurement"]
        if measurement == "measure_voltage":
            return f"{reading['probe']} measured {float(reading['voltage_v']):.3f} V"
        if measurement == "read_digital":
            return f"{reading['probe']} is {reading['state']}"
        if measurement == "measure_frequency":
            pulse = reading.get("pulse_us")
            width = f", {int(pulse)} µs" if isinstance(pulse, (int, float)) and not isinstance(pulse, bool) else ""
            return f"{reading['probe']} measured {float(reading['frequency_hz']):.2f} Hz{width}"
        if measurement == "measure_voltage_pair":
            parts = [f"{item['probe']} {float(item['voltage_v']):.3f} V" for item in reading.get("readings", [])]
            return ", ".join(parts) or "P1 and P2 were read"
        if measurement == "measure_bus_activity":
            return f"SDA {int(reading['sda']['edges'])} edges, SCL {int(reading['scl']['edges'])} edges"
        if measurement == "measure_digital_taps":
            parts = [f"{name} {int(tap.get('edges'))} edges" for name, tap in (reading.get("taps") or {}).items()
                     if isinstance(tap, dict)]
            return "Digital taps: " + ", ".join(parts)
        if measurement == "check_circuit":
            outcome = "passed" if reading.get("pass") else "did not pass"
            return f"{reading.get('test', spec.get('profile'))} {outcome}"
    except (KeyError, TypeError, ValueError):
        return "Physical reading recorded"
    return "Physical reading recorded"


def findings_path() -> Path:
    override = os.environ.get("BENCHY_VISUAL_FINDINGS", "").strip()
    if override:
        return Path(override)
    return REPO_ROOT / ".benchos" / "latest_visual_inspection.json"


def write_latest_findings(document: dict) -> None:
    path = findings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(document, indent=2), encoding="utf-8")
    temporary.replace(path)


def read_latest_findings() -> dict:
    path = findings_path()
    if not path.is_file():
        return {"ok": False, "error": "No visual inspection has completed yet."}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "error": "Latest visual inspection record could not be read."}
    if not isinstance(document, dict) or not isinstance(document.get("analysis"), dict):
        return {"ok": False, "error": "Latest visual inspection record could not be read."}
    document["ok"] = True
    document["physically_verified"] = False
    document.pop("image", None)
    return document


def findings_document(analysis: dict, context: dict, model: str) -> dict:
    return {"ok": True, "source": "visual_hypothesis", "physically_verified": False,
            "completed_at": datetime.now(timezone.utc).isoformat(), "model": model,
            "analysis": analysis, "context": context}


def message_page(title: str, detail: str) -> bytes:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Benchy — Visual Inspection</title><link rel="stylesheet" href="/app.css"></head>
<body class="capture-page"><main class="capture-card"><p class="capture-kicker">BENCHY</p>
<h1>{escape(title)}</h1><p>{escape(detail)}</p></main></body></html>""".encode("utf-8")


@dataclass
class InspectionSession:
    token: str
    created_at: datetime
    expires_at: datetime
    capture_url: str
    qr_svg: str
    status: str = "waiting"
    image: bytes | None = None
    mime_type: str | None = None
    images: list[tuple[bytes, str]] = field(default_factory=list)
    analysis: dict | None = None
    context: dict | None = None
    error: str | None = None
    model: str | None = None
    revision: int = 0
    physical_checks: list = field(default_factory=list)


class SessionStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: dict[str, InspectionSession] = {}
        self._current: str | None = None

    def start(self, now: datetime | None = None) -> dict:
        base = public_base_url()
        if not base:
            raise VisualError(PUBLIC_URL_HELP)
        moment = now or datetime.now(timezone.utc)
        token = secrets.token_urlsafe(24)
        url = f"{base}/capture/{token}"
        session = InspectionSession(token, moment, moment + SESSION_TTL, url, make_qr_svg(url))
        with self._lock:
            for previous in self._sessions.values():
                previous.image = None
                previous.mime_type = None
                previous.images.clear()
                previous.qr_svg = ""
                previous.status = "expired"
                previous.error = "This capture link has expired."
            self._sessions[token] = session
            self._current = token
            overflow = [key for key in self._sessions if key != token]
            for key in overflow[:-7]:
                self._sessions.pop(key, None)
            return self._view(session)

    def _live(self, session: InspectionSession, now: datetime) -> bool:
        if session.status == "expired":
            return False
        if now < session.expires_at:
            return True
        session.image = None
        session.mime_type = None
        session.images.clear()
        session.status = "expired"
        session.error = "This capture link has expired."
        return False

    def _get(self, token: str, now: datetime) -> InspectionSession:
        session = self._sessions.get(token)
        if session is None:
            raise VisualError("This capture link is not valid.", HTTPStatus.NOT_FOUND)
        self._live(session, now)
        return session

    def phone_state(self, token: str, now: datetime | None = None) -> dict:
        moment = now or datetime.now(timezone.utc)
        with self._lock:
            session = self._get(token, moment)
            return {"status": session.status, "status_label": STATUS_LABELS[session.status],
                    "error": session.error, "photo_count": len(session.images)}

    def store_image(self, token: str, data: bytes, mime_type: str, now: datetime | None = None) -> dict:
        moment = now or datetime.now(timezone.utc)
        with self._lock:
            session = self._get(token, moment)
            if session.status == "expired":
                raise VisualError("This capture link has expired.", HTTPStatus.GONE)
            if session.status not in {"waiting", "error", "complete"}:
                raise VisualError("This capture session is no longer waiting for a photo.")
            if len(session.images) >= 4:
                raise VisualError("This capture session already has four photos.", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            session.image = data
            session.mime_type = mime_type
            session.images.append((data, mime_type))
            session.revision += 1
            session.status = "complete"
            session.error = None
            session.analysis = None
            session.context = {"purpose": "secondary conversation context", "electrical_analysis": False}
            return self._phone(session)

    def images(self, now: datetime | None = None) -> list[tuple[bytes, str]]:
        moment = now or datetime.now(timezone.utc)
        with self._lock:
            if self._current is None:
                return []
            session = self._get(self._current, moment)
            return list(session.images)

    def begin_analysis(self, token: str) -> tuple[bytes, str]:
        with self._lock:
            session = self._get(token, datetime.now(timezone.utc))
            if session.status == "expired":
                raise VisualError("This capture link has expired.", HTTPStatus.GONE)
            if session.status != "uploaded" or session.image is None or session.mime_type is None:
                raise VisualError("No photo is waiting for analysis.")
            session.status = "analyzing"
            return session.image, session.mime_type

    def complete(self, token: str, analysis: dict, context: dict, model: str) -> bool:
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return False
            if not self._live(session, datetime.now(timezone.utc)):
                return False
            session.analysis = analysis
            session.context = context
            session.model = model
            session.status = "complete"
            session.error = None
            return True

    def fail(self, token: str, message: str) -> None:
        with self._lock:
            session = self._sessions.get(token)
            if session is None or session.status in {"expired", "complete"}:
                return
            session.status = "error"
            session.error = message

    def image(self, now: datetime | None = None) -> tuple[bytes, str]:
        moment = now or datetime.now(timezone.utc)
        with self._lock:
            if self._current is None:
                raise VisualError("No visual inspection photo is available.", HTTPStatus.NOT_FOUND)
            session = self._get(self._current, moment)
            if session.image is None or session.mime_type is None or session.status == "expired":
                raise VisualError("No visual inspection photo is available.", HTTPStatus.NOT_FOUND)
            return session.image, session.mime_type

    def add_physical_check(self, record: dict) -> dict:
        with self._lock:
            if self._current is None:
                raise VisualError("Start a visual inspection before running a recommended check.")
            session = self._get(self._current, datetime.now(timezone.utc))
            if session.status == "expired":
                raise VisualError("This capture link has expired.", HTTPStatus.GONE)
            session.physical_checks.append(record)
            return self._view(session)

    def current_view(self) -> dict:
        with self._lock:
            if self._current is None:
                return self._idle()
            session = self._get(self._current, datetime.now(timezone.utc))
            return self._view(session)

    def _idle(self) -> dict:
        return {"active": False, "status": "ready", "status_label": STATUS_LABELS["ready"],
                "availability": availability(), "image_ready": False, "analysis": None,
                "context": None, "physical_checks": [], "error": None, "qr_svg": None}

    def _phone(self, session: InspectionSession) -> dict:
        return {"status": session.status, "status_label": STATUS_LABELS[session.status],
                "error": session.error, "photo_count": len(session.images)}

    def _view(self, session: InspectionSession) -> dict:
        ready = session.image is not None and session.status in {"uploaded", "analyzing", "complete", "error"}
        return {"active": session.status != "expired", "status": session.status,
                "status_label": STATUS_LABELS[session.status],
                "started_at": session.created_at.isoformat(),
                "expires_at": session.expires_at.isoformat(),
                "availability": availability(),
                "capture_url": session.capture_url if session.status == "waiting" else None,
                "qr_svg": session.qr_svg if session.status == "waiting" else None,
                "image_ready": ready, "revision": session.revision, "photo_count": len(session.images),
                "analysis": None, "context": session.context,
                "physical_checks": list(session.physical_checks), "error": session.error,
                "model": session.model}
