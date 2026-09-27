"""Local web dashboard for live BenchOS measurements.

The dashboard itself stays on localhost. Phone capture is a separate,
token-limited route and is reachable only when a public base URL is configured.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import subprocess
import threading
import time
import urllib.error
import urllib.request
from importlib.util import find_spec
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import serial
import yaml

from .client import BenchClient
from .light import read_light_report
from .harness import describe_harness, update_probe_declarations
from .ports import available_ports, candidate_ports
from .protocol import BenchError
from .serial_lock import SerialPortLock
from .records import list_records, read_record, write_record
from .activity import compare_activity
from .visual_inspection import (
    SessionStore, VisualError, build_inspection_context,
    describe_images_for_context, execute_check, is_phone_capture_path, local_dashboard_allowed,
    message_page, parse_capture_path, resolve_check, summarize_physical, validate_image,
)

MODES = {"light", "led", "servo", "imu"}
REPO_ROOT = Path(__file__).resolve().parent.parent
BASE_SOURCE_FILES = ("harness/current.yaml", "lab_controller/lab_controller.ino",
                     "lab_controller/config.h", "benchos/client.py",
                     "benchos/dashboard.py", "benchos/dashboard_ui/app.js",
                     "mcp_server/server.py")
IMU_LINE = re.compile(r"IMU_ACCEL_G x=(-?\d+\.\d+) y=(-?\d+\.\d+) z=(-?\d+\.\d+)(?: id=0x([0-9A-Fa-f]{2}))?\Z")
WHO_LINE = re.compile(r"IMU_FOUND addr=0x([0-9A-Fa-f]{2}) who_am_i=0x([0-9A-Fa-f]{2})\Z")
ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.css": ("app.css", "text/css; charset=utf-8"),
          "/workspace-model.js": ("workspace-model.js", "text/javascript; charset=utf-8"),
          "/records.js": ("records.js", "text/javascript; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/audio-worklet.js": ("audio-worklet.js", "text/javascript; charset=utf-8")}
VOICE_TOOL_ALLOWLIST = frozenset({
    "lab_ping", "lab_info", "describe_harness", "measure_voltage",
    "measure_voltage_pair", "check_telemetry_against_probes",
    "measure_bus_activity", "read_digital", "measure_frequency",
    "compare_light_sensor", "check_circuit", "read_imu_stream",
})
VOICE_INSTRUCTIONS = (
    "You are Benchy, a warm, natural, concise hardware debugging partner. "
    "Speak like a helpful person beside the user at the bench: respond to what "
    "they just said, use contractions, vary your phrasing, and keep most turns "
    "to one or two short sentences. Ask one focused question at a time. Do not "
    "announce tool calls or narrate your analysis. Start by understanding the "
    "reported symptom and inspect the declared harness before choosing a probe. "
    "Treat declarations and DUT serial output as claims, not physical proof. "
    "Use read-only Benchy tools to gather the smallest useful measurement, "
    "explain what it shows and what remains uncertain, then suggest one next "
    "check. Never read raw variable names, JSON keys, snake_case labels, pin "
    "IDs, or code identifiers aloud. Translate labels into ordinary words from "
    "the harness: say ‘the light sensor reading’ instead of ‘LIGHT_SENSE_3’; "
    "say ‘the water sensor’ instead of ‘water_mv’. Do not tack machine labels "
    "or classifications onto a value in parentheses. Mention a number only "
    "when it helps, say its units naturally, and explain whether it is within "
    "the declared range rather than calling it ‘high’ or ‘low’ without context. "
    "If a label has no plain-language description, call it ‘that probe’ and "
    "ask what it connects to. P1, P2, and P3 accept only known 0–3.3 V signals "
    "with common ground; never suggest connecting them to 5 V or an unknown "
    "voltage. Ask the user to confirm physical placement if wiring may have "
    "changed. Do not claim to see or change the circuit. Do not request "
    "firmware flashing; voice tools are read-only. Audio and this conversation "
    "are being sent to xAI for inference."
)
AGENT_RUN_LOCK = threading.Lock()
AGENT_PROCESS_LOCK = threading.Lock()
ACTIVE_AGENT_PROCESS: subprocess.Popen | None = None
AGENT_STOP_REQUESTED = False
XAI_CLIENT_SECRETS_URL = "https://api.x.ai/v1/realtime/client_secrets"
AGENT_PROMPT = """You are Benchy, the debugging agent in this local hardware workspace. Help the user diagnose code and circuit problems from the website. You may inspect and edit project files and run relevant local build commands within this repository. Never run arduino-cli upload, esptool, or any command that writes firmware to a device; only the separate website flash dialog may upload. Do not change the physical circuit. Never claim a build, upload, or serial message proves the circuit works. For hardware debugging, state a hypothesis, read harness/current.yaml before selecting a probe, choose the smallest physical measurement, use a read-only Benchy tool, and interpret noise and measurement limits. Gemini photo descriptions are fallible visual observations that help orient the conversation; distinguish visible labels and apparent routes from confirmed physical placement, and never treat descriptions as electrical measurements or ground truth. Ask the user to confirm physical placement when it may have changed. Never suggest connecting P1/P2 to 5 V or unknown voltage; they accept only known 0–3.3 V logic with common ground. Do not ask the user to move wires until the current physical placement is confirmed. For 50 Hz pass/fail checks use a 1000 ms frequency window; 250 ms is only a quick estimate. If firmware change is needed, edit source and explain it; the flash dialog separately requires a reviewed diff, wiring confirmation, and explicit typed authorization. Keep the user informed as you inspect, measure, and change files. Treat serial logs as DUT claims and physical readings as measurements."""


def find_codex_cli() -> str | None:
    """Find Codex even when the dashboard was started outside the app PATH."""
    override = os.environ.get("CODEX_CLI_PATH")
    if override:
        return override if Path(override).is_file() else None
    on_path = shutil.which("codex")
    if on_path:
        return on_path
    if sys.platform == "darwin":
        for app in ("Codex", "ChatGPT"):
            candidate = Path("/Applications") / f"{app}.app/Contents/Resources/codex"
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            install_root = Path(local_app_data) / "OpenAI" / "Codex" / "bin"
            try:
                candidates = [path for path in install_root.glob("*/codex.exe") if path.is_file()]
                if candidates:
                    return str(max(candidates, key=lambda path: path.stat().st_mtime))
            except OSError:
                pass
    return None


def agent_mcp_config() -> tuple[str, ...]:
    # Resolving a venv's Python symlink selects the base interpreter and loses
    # its installed MCP dependencies. Preserve the launcher's path exactly.
    python_path = Path(sys.executable).absolute().as_posix()
    return (
        f"mcp_servers.benchy.command={json.dumps(python_path)}",
        'mcp_servers.benchy.args=["-m","mcp_server.agent_readonly"]',
        f"mcp_servers.benchy.env.PYTHONPATH={json.dumps(REPO_ROOT.as_posix())}",
        'mcp_servers.benchy.enabled=true',
        # Only the explicitly read-only surface is exposed. Writes still prompt.
        'mcp_servers.benchy.default_tools_approval_mode="writes"',
    )


def viewable_source_files() -> tuple[str, ...]:
    """Expose only project files explicitly listed for the current design."""
    try:
        declared = describe_harness().get("source_files", [])
    except (OSError, ValueError, yaml.YAMLError):
        declared = []
    names = list(BASE_SOURCE_FILES)
    for name in declared[:16] if isinstance(declared, list) else []:
        if not isinstance(name, str):
            continue
        relative = Path(name)
        if (relative.is_absolute() or ".." in relative.parts
                or any(part.startswith(".") for part in relative.parts)
                or relative.suffix.lower() not in {".ino", ".h", ".cpp", ".c", ".py", ".js", ".ts", ".yaml", ".md"}):
            continue
        candidate = (REPO_ROOT / relative).resolve()
        if name not in names and candidate.is_relative_to(REPO_ROOT) and candidate.is_file():
            names.append(name)
    return tuple(names)


def code_inventory() -> dict:
    """Describe local source, without claiming it matches flashed firmware."""
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=2, check=True).stdout.strip()
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                                cwd=REPO_ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=2,
                                check=True).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        commit, status = None, []
    entries = []
    for name in viewable_source_files():
        path = REPO_ROOT / name
        if path.is_file():
            data = path.read_bytes()
            entries.append({"path": name, "bytes": len(data),
                            "sha256_short": hashlib.sha256(data).hexdigest()[:12]})
    try:
        harness = describe_harness()
        declared_firmware = harness.get("dut", {}).get("firmware")
    except (OSError, ValueError, yaml.YAMLError):
        declared_firmware = None
    return {"source": "local_files", "commit": commit, "short_commit": commit[:8] if commit else None,
            "dirty": bool(status) if commit else None,
            "modified_files": [line[3:] for line in status],
            "declared_dut_firmware": declared_firmware,
            "flashed_firmware_verified": False, "files": entries}


def source_file(name: str) -> dict:
    if name not in viewable_source_files():
        raise ValueError("File is not in the source viewer allowlist")
    path = REPO_ROOT / name
    data = path.read_bytes()
    if len(data) > 150_000:
        raise ValueError("Source file is too large for the viewer")
    return {"path": name, "source": "local_file", "text": data.decode("utf-8", errors="replace"),
            "sha256_short": hashlib.sha256(data).hexdigest()[:12]}


def voice_tool_specs() -> list[dict]:
    """Return only read-only instrument tools plus the source viewer."""
    try:
        from mcp_server.server import mcp
    except ImportError as exc:
        raise RuntimeError("Install the MCP extra to use Grok voice debugging") from exc
    listed = asyncio.run(mcp.list_tools())
    specs = []
    for tool in listed:
        if tool.name not in VOICE_TOOL_ALLOWLIST:
            continue
        item = tool.model_dump(mode="json", by_alias=True, exclude_none=True)
        specs.append({"type": "function", "name": item["name"],
                      "description": item.get("description") or item["name"],
                      "parameters": item.get("inputSchema") or
                                    {"type": "object", "properties": {}}})
    source_paths = viewable_source_files()
    specs.append({"type": "function", "name": "read_source_file",
                  "description": "Read a local Benchy source file from the declared source viewer allowlist.",
                  "parameters": {"type": "object",
                                 "properties": {"path": {"type": "string", "enum": list(source_paths)}},
                                 "required": ["path"], "additionalProperties": False}})
    return specs


def invoke_voice_tool(name: str, arguments: dict) -> dict:
    """Invoke a validated read-only voice tool, enforcing the allowlist locally."""
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a JSON object")
    if name == "read_source_file":
        path = arguments.get("path")
        if set(arguments) != {"path"} or path not in viewable_source_files():
            raise ValueError("Source path is not in the declared source viewer allowlist")
        return source_file(path)
    if name not in VOICE_TOOL_ALLOWLIST:
        raise ValueError("Tool is not enabled in voice mode")
    from mcp_server.server import mcp

    result = asyncio.run(mcp.call_tool(name, arguments))
    structured = result.structured_content
    if structured is not None:
        data = structured
    else:
        data = [item.model_dump(mode="json", by_alias=True, exclude_none=True)
                for item in getattr(result, "content", [])]
        if len(data) == 1 and data[0].get("type") == "text":
            try:
                data = json.loads(data[0].get("text", ""))
            except json.JSONDecodeError:
                pass
    return {"ok": not result.is_error, "result": data}


def create_voice_token() -> dict:
    """Mint a short-lived browser credential without disclosing the xAI key."""
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        raise RuntimeError("XAI_API_KEY is not set for the dashboard process")
    body = json.dumps({"expires_after": {"seconds": 300}}).encode("utf-8")
    request = urllib.request.Request(
        XAI_CLIENT_SECRETS_URL,
        data=body,
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read(16_384))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"xAI token request failed with HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        raise RuntimeError("Could not reach xAI to create a voice session") from None
    value = data.get("value") if isinstance(data, dict) else None
    expires_at = data.get("expires_at") if isinstance(data, dict) else None
    if not isinstance(value, str) or not value or not isinstance(expires_at, int):
        raise RuntimeError("xAI returned an invalid voice session token response")
    return {"value": value, "expires_at": expires_at}


def diagnose(mode: str, physical: dict | None, dut: dict | None,
             errors: list[dict] | None = None) -> dict:
    """Keep the verdict grounded in measurements, not DUT claims alone."""
    if mode == "light":
        if physical is None or dut is None:
            return {"state": "unknown", "title": "Awaiting both readings",
                    "detail": "Connect the S3 probe and C6 light demo to compare them."}
        volts = physical["voltage_v"]
        delta = abs(volts - dut["reported_voltage_v"])
        if volts < 0.3:
            return {"state": "unknown", "title": "Too little signal",
                    "detail": "Brighten the photoresistor before checking agreement."}
        if delta > 0.45:
            return {"state": "fail", "title": "Sensor report disagrees",
                    "detail": f"The DUT is {delta:.2f} V away from the independent probe (>0.45 V)."}
        return {"state": "pass", "title": "Sensor report agrees",
                "detail": f"The DUT and probe differ by {delta:.2f} V (limit 0.45 V)."}
    if mode in {"servo", "led"}:
        if physical is None:
            return {"state": "unknown", "title": "Awaiting P1 signal",
                    "detail": "Place P1 on the 3.3 V control signal and connect the S3."}
        hz = physical["frequency_hz"]
        edges = physical["edges"]
        if edges == 0:
            return {"state": "fail", "title": "No physical transitions",
                    "detail": "Check the DUT output pin, wire to P1, and shared ground."}
        low, high = (45, 55) if mode == "servo" else (1.5, 2.5)
        if not low <= hz <= high:
            return {"state": "fail", "title": "Frequency outside target",
                    "detail": f"P1 measured {hz:.1f} Hz; expected {low:g}–{high:g} Hz."}
        if mode == "servo" and not 900 <= physical["pulse_us"] <= 2100:
            return {"state": "fail", "title": "Servo pulse width outside target",
                    "detail": f"P1 measured {physical['pulse_us']} µs; expected 900–2100 µs."}
        return {"state": "pass", "title": "Physical signal matches",
                "detail": "The S3 probe measured the expected timing at P1."}
    if mode == "imu":
        if physical is not None:
            volts = physical["voltage_v"]
            if not 3.0 <= volts <= 3.4:
                return {"state": "fail", "evidence": "physical",
                        "title": "Sensor supply outside target",
                        "detail": f"S3 P2 reads {volts:.2f} V on the declared MPU VCC net; expected 3.0–3.4 V."}
        if dut is None:
            imu_error = next((item["message"] for item in (errors or [])
                              if item.get("device") == "C6" and "IMU_ERROR" in item.get("message", "")), None)
            if physical is not None and imu_error:
                return {"state": "fail", "evidence": "mixed",
                        "title": "Power present; IMU link failed",
                        "detail": f"S3 P2 reads {physical['voltage_v']:.2f} V at MPU VCC. {imu_error}. Check SCL/SDA and sensor configuration."}
            return {"state": "unknown", "title": "Awaiting IMU stream",
                    "detail": "Connect the C6 and flash the IMU demo; inspect C6 serial errors."}
        if dut.get("saturated_axes"):
            axes = ", ".join(dut["saturated_axes"])
            return {"state": "fail", "evidence": "dut", "title": "Accelerometer axis clipped",
                    "detail": f"The DUT reports {axes} at the ±2 g limit. Check raw registers and repeat with the board still."}
        if physical is not None:
            return {"state": "unverified", "evidence": "mixed",
                    "title": "Power verified; motion stream detected",
                    "detail": f"S3 P2 measured {physical['voltage_v']:.2f} V at MPU VCC. Motion values are from C6; the I²C bus is not independently decoded."}
        return {"state": "unverified", "title": "Motion stream detected",
                "detail": "These values come from the DUT. Connect S3 P2 to the known MPU VCC net to verify sensor power."}
    raise ValueError(f"Unknown mode: {mode}")


def read_imu_report(port: str, timeout_s: float = 2.5, line_sink=None) -> dict:
    """Read one C6 motion line; a fresh session may miss the one-time ID line."""
    import time

    found = None
    try:
        with SerialPortLock(port), serial.Serial(port, 115200, timeout=0.25, write_timeout=0.25) as dut:
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                line = dut.readline().decode("ascii", errors="replace").strip()
                if line and line_sink:
                    line_sink(line)
                if line.startswith("IMU_ERROR "):
                    raise BenchError(f"C6 reported {line}")
                identity = WHO_LINE.fullmatch(line)
                if identity:
                    found = {"address": "0x" + identity.group(1).upper(),
                             "who_am_i": "0x" + identity.group(2).upper()}
                match = IMU_LINE.fullmatch(line)
                if match:
                    axes = tuple(float(x) for x in match.groups()[:3])
                    if not all(math.isfinite(x) and abs(x) <= 16 for x in axes):
                        raise BenchError("Invalid IMU acceleration report")
                    return {"x_g": axes[0], "y_g": axes[1], "z_g": axes[2],
                            "magnitude_g": round(math.sqrt(sum(x * x for x in axes)), 3),
                            "saturated_axes": [axis for axis, value in zip("xyz", axes)
                                               if abs(value) >= 1.999],
                            **(found or {}),
                            **({"who_am_i": "0x" + match.group(4).upper()}
                               if match.group(4) else {})}
    except (serial.SerialException, OSError) as exc:
        raise BenchError(f"Cannot read C6 IMU report on {port}: {exc}") from exc
    raise BenchError(f"No IMU_ACCEL_G report on {port} within {timeout_s:g} s")


class DashboardState:
    def __init__(self, lab_port: str | None = None, dut_port: str | None = None):
        self.lab_port = lab_port
        self.dut_port = dut_port
        self._lock = threading.RLock()
        self._capture_lock = threading.Lock()
        self._capture_owner: int | None = None
        self._serial_events = deque(maxlen=400)
        self._serial_seq = 0
        self.last_probes: dict | None = None
        self.last_capture: dict | None = None
        self.visual = SessionStore()

    @contextmanager
    def instrument_access(self):
        if self._capture_owner not in (None, threading.get_ident()):
            raise BenchError("A saved capture has reserved the instrument; retry shortly")
        if not self._lock.acquire(timeout=3):
            raise BenchError("Instrument is busy with another capture; retry shortly")
        try:
            if self._capture_owner not in (None, threading.get_ident()):
                raise BenchError("A saved capture has reserved the instrument; retry shortly")
            yield
        finally:
            self._lock.release()

    def _record_serial(self, line: str, port: str = "") -> None:
        self._serial_seq += 1
        self._serial_events.append({"seq": self._serial_seq,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                    "source": "serial_observed", "port": port, "line": line[:512]})

    def serial_sample(self, port: str, duration_ms: int, after_seq: int = 0) -> dict:
        if port not in set(candidate_ports()):
            raise ValueError("Serial port is not currently available")
        if not 100 <= duration_ms <= 1200 or after_seq < 0:
            raise ValueError("Invalid serial sample window or sequence")
        with self.instrument_access():
            try:
                with SerialPortLock(port), serial.Serial(port, 115200, timeout=0.1, write_timeout=0.25) as device:
                    deadline = time.monotonic() + duration_ms / 1000
                    while time.monotonic() < deadline:
                        line = device.readline().decode("utf-8", errors="replace").strip()
                        if line:
                            self._record_serial(line, port)
            except (serial.SerialException, OSError) as exc:
                raise BenchError(f"Cannot sample serial port {port}: {exc}") from exc
            if after_seq > self._serial_seq:
                after_seq = 0
            return {"port": port, "sample_window_ms": duration_ms,
                    "continuous": False, "latest_seq": self._serial_seq,
                    "events": [item for item in self._serial_events if item["seq"] > after_seq and item["port"] == port]}

    def recent_serial_lines(self, limit: int = 12) -> list[str]:
        return [str(event.get("line", ""))[:180] for event in list(self._serial_events)[-limit:]]

    def inspection_context(self) -> dict:
        harness = None
        error = None
        try:
            harness = describe_harness()
        except (OSError, ValueError, yaml.YAMLError) as exc:
            error = str(exc)
        return build_inspection_context(harness, self.last_probes, self.last_capture,
                                        self.recent_serial_lines(), error)

    def probe_sample(self, port: str, harness: dict | None = None) -> dict:
        if port not in set(candidate_ports()):
            raise ValueError("S3 port is not currently available")
        probes = (describe_harness() if harness is None else harness)["probes"]
        with self.instrument_access():
            with BenchClient(port) as client:
                started = time.monotonic()
                pair = client.measure_voltage_pair(probe_declarations=probes)
                if probes["P3"]["state"] == "connected":
                    reading = client.measure_voltage("P3")
                    pair["readings"].append({"timestamp": datetime.now(timezone.utc).isoformat(),
                                             "declared_state": "connected", "declared_net": probes["P3"]["net"],
                                             **reading})
                    pair["elapsed_ms"] = round((time.monotonic() - started) * 1000, 1)
                digital = {name: client.read_digital(name)["state"]
                           for name in ("P1", "P2", "P3")
                           if probes[name]["state"] == "connected"}
        pair["digital_states"] = digital
        pair["timestamp"] = datetime.now(timezone.utc).isoformat()
        pair["source"] = "s3_physical"
        pair["voltage_limit_v"] = 3.3
        self.last_probes = pair
        return pair

    def bus_sample(self, port: str, duration_ms: int, dut_port: str = "", *, digital_taps: bool = False,
                   harness: dict | None = None) -> dict:
        known = set(candidate_ports())
        if port not in known:
            raise ValueError("S3 port is not currently available")
        if dut_port and (dut_port not in known or dut_port == port):
            raise ValueError("DUT serial port is not a distinct available device")
        if isinstance(duration_ms, bool) or not 100 <= duration_ms <= 2000:
            raise ValueError("Bus sample window must be 100–2000 ms")
        stream_error = []
        declared = describe_harness() if harness is None else harness
        activity_rules = declared.get("activity_checks", []) if digital_taps else []
        stream_ready = threading.Event()
        stream_stop = threading.Event()

        def drain_dut() -> None:
            try:
                with SerialPortLock(dut_port), serial.Serial(dut_port, 115200, timeout=0.1,
                                                            write_timeout=0.25) as dut:
                    dut.reset_input_buffer()
                    stream_ready.set()
                    pending = bytearray()
                    while not stream_stop.is_set():
                        pending.extend(dut.read_until(b"\n", 512))
                        while b"\n" in pending:
                            line, _, pending = pending.partition(b"\n")
                            line = line.decode("utf-8", errors="replace").strip()
                            if line:
                                self._record_serial(line, dut_port)
                        if len(pending) > 4096:
                            raise BenchError("DUT serial line exceeded the capture limit")
            except (BenchError, serial.SerialException, OSError) as exc:
                stream_error.append(str(exc))
                stream_ready.set()

        with self.instrument_access():
            first_seq = self._serial_seq
            # Some DUT sketches pause their serial logging (and therefore their
            # I/O loop) when USB CDC has no reader. Keep the DUT stream drained
            # while the independent S3 samples the physical bus.
            reader = threading.Thread(target=drain_dut, daemon=True) if dut_port else None
            if reader:
                reader.start()
                stream_ready.wait(1.5)
            try:
                with BenchClient(port, timeout=4.0) as client:
                    command_started = datetime.now(timezone.utc).isoformat()
                    if digital_taps:
                        result = client.measure_digital_taps(duration_ms, tap_declarations=declared.get("digital_taps", {}))
                    else:
                        result = client.measure_bus_activity(duration_ms, monitor_declaration=declared.get("bus_monitor", {}))
                    command_ended = datetime.now(timezone.utc).isoformat()
                if reader and activity_rules:
                    # Preserve a report after the counter window as well as
                    # those observed while the lab connection was opening.
                    stream_stop.wait(0.65)
            finally:
                stream_stop.set()
                if reader:
                    reader.join(timeout=1.0)
                    if reader.is_alive():
                        stream_error.append("DUT serial reader did not stop within its deadline")
            events = [dict(event) for event in self._serial_events
                      if event["port"] == dut_port and event["seq"] > first_seq]
        observed = {**result, "timestamp": command_ended,
                "command_started_at": command_started, "command_ended_at": command_ended,
                "source": "s3_physical", "decoded_transactions": False,
                "dut_stream_open_during_capture": bool(reader and stream_ready.is_set() and not stream_error),
                **({"dut_stream_error": stream_error[0]} if stream_error else {})}
        if activity_rules:
            observed["activity_checks"] = compare_activity(observed, events, activity_rules)
            observed["condition_serial_events"] = events
        self.last_capture = observed
        return observed

    def capture_record(self, payload: dict) -> dict:
        """Collect fresh server-side evidence; accept only labels and port choices."""
        allowed = {"lab_port", "dut_port", "label", "note"}
        if not isinstance(payload, dict) or set(payload) - allowed:
            raise ValueError("Capture accepts port choices, label, and note only")
        lab, dut = payload.get("lab_port", ""), payload.get("dut_port", "")
        label, note = payload.get("label", ""), payload.get("note", "")
        if (not isinstance(lab, str) or not isinstance(dut, str)
                or not isinstance(label, str) or not 1 <= len(label.strip()) <= 100
                or not isinstance(note, str) or len(note) > 2000):
            raise ValueError("Choose the S3 and a label of 1–100 characters; notes allow 2000 characters")
        known = set(candidate_ports())
        if lab not in known or (dut and (dut not in known or dut == lab)):
            raise ValueError("Choose currently available, distinct lab and DUT ports")
        if not self._capture_lock.acquire(blocking=False):
            raise BenchError("A capture is already in progress")
        acquired = False
        try:
            self._capture_owner = threading.get_ident()
            # Reserve this dashboard's instrument queue across the complete
            # saved capture. Each window still acquires the cross-process USB
            # lock separately; these measurements are not simultaneous.
            acquired = self._lock.acquire(timeout=10)
            if not acquired:
                raise BenchError("Instrument is busy with another capture; retry shortly")
            # Pin labels and scale declarations must stay fixed across both
            # measurement windows, even if another browser edits the harness.
            declared = describe_harness()
            source_before = {**code_inventory(), "recorded_at": datetime.now(timezone.utc).isoformat()}
            started = datetime.now(timezone.utc).isoformat()
            physical = self.probe_sample(lab, harness=declared)
            capture, errors = None, []
            has_taps = any(tap.get("state") == "connected" for tap in declared.get("digital_taps", {}).values())
            if has_taps or declared.get("bus_monitor", {}).get("state") == "connected":
                try:
                    window_ms = 2000 if declared.get("activity_checks") else 1000
                    capture = self.bus_sample(lab, window_ms, dut, digital_taps=has_taps, harness=declared)
                    if capture.get("dut_stream_error"):
                        errors.append({"stage": "dut_serial", "message": capture["dut_stream_error"]})
                except (ValueError, BenchError, OSError) as exc:
                    errors.append({"stage": "digital_capture", "message": str(exc)})
            elif dut:
                try:
                    self.serial_sample(dut, 700)
                except (ValueError, BenchError, OSError) as exc:
                    errors.append({"stage": "dut_serial", "message": str(exc)})
            ended = datetime.now(timezone.utc).isoformat()
            if capture:
                gap = (datetime.fromisoformat(capture["timestamp"]) -
                       datetime.fromisoformat(physical["timestamp"])).total_seconds()
                if gap > 15:
                    errors.append({"stage": "timing", "message":
                        f"Digital window ended {gap:.1f} s after the voltage reading; do not treat these as concurrent observations"})
            with self._lock:
                events = [dict(event) for event in self._serial_events
                          if event["port"] == dut and started <= event["timestamp"] <= ended]
            source_after = {**code_inventory(), "recorded_at": datetime.now(timezone.utc).isoformat()}
            try:
                harness_changed = describe_harness() != declared
            except (ValueError, OSError, yaml.YAMLError):
                harness_changed = True
            document = {
                "schema_version": 1, "kind": "benchy_capture", "source": "dashboard_instrument_capture",
                "label": label.strip(), "note": note, "timestamp": started,
                "saved_at": datetime.now(timezone.utc).isoformat(), "capture_ended_at": ended,
                "simultaneous": False, "lab_port": lab, "dut_port": dut,
                "harness": declared, "harness_changed_during_capture": harness_changed,
                "physical": physical, "capture": capture, "errors": errors,
                "serial": {"port": dut, "continuous": False, "events": events},
                "source_context": {"before": source_before, "after": source_after,
                    "changed_during_capture": any(source_before.get(key) != source_after.get(key)
                        for key in ("commit", "files", "dirty", "modified_files")),
                    "flashed_firmware_verified": False}}
            return write_record(document)
        finally:
            if acquired:
                self._lock.release()
            self._capture_owner = None
            self._capture_lock.release()

    def close(self) -> None:
        pass

    def accept_visual_image(self, token: str, data: bytes, content_type: str) -> dict:
        mime = validate_image(data, content_type)
        return self.visual.store_image(token, data, mime)

    def run_visual_check(self, lab_port: str, measurement: str, target: str) -> dict:
        spec = resolve_check(measurement, target)
        if lab_port not in set(candidate_ports()):
            raise ValueError("S3 port is not currently available")
        with self.instrument_access():
            with BenchClient(lab_port) as client:
                reading = execute_check(client, spec)
        record = {"measurement": spec["measurement"],
                  "target": spec.get("probe") or spec.get("profile"),
                  "summary": summarize_physical(spec, reading), "reading": reading,
                  "timestamp": datetime.now(timezone.utc).isoformat(),
                  "source": "s3_physical", "evidence": "physical"}
        return {"check": record, "session": self.visual.add_physical_check(record)}

    def snapshot(self, mode: str, lab_port: str, dut_port: str) -> dict:
        if mode not in MODES:
            raise ValueError("Unknown demo mode")
        known = set(candidate_ports())
        if lab_port and lab_port not in known:
            raise ValueError("S3 port is not a currently available serial device")
        if dut_port and dut_port not in known:
            raise ValueError("C6 port is not a currently available serial device")
        if lab_port and dut_port and lab_port == dut_port:
            raise ValueError("S3 and C6 must use different serial ports")
        result = {"mode": mode, "timestamp": datetime.now(timezone.utc).isoformat(),
                  "lab_port": lab_port, "dut_port": dut_port,
                  "physical": None, "dut": None, "errors": []}
        imu_vcc_declared = False
        if mode == "imu":
            try:
                probe = describe_harness()["probes"]["P2"]
                imu_vcc_declared = probe["state"] == "connected" and probe["net"] == "MPU_VCC"
            except (OSError, ValueError, yaml.YAMLError) as exc:
                result["errors"].append({"device": "Harness", "message": str(exc)})
            if not imu_vcc_declared:
                result["errors"].append({"device": "Harness", "message": "P2 is not declared on MPU_VCC; power check omitted"})
        with self._lock:
            if lab_port and (mode != "imu" or imu_vcc_declared):
                try:
                    # Release serial after each sample so MCP/CLI may use the S3.
                    with BenchClient(lab_port) as client:
                        if mode in {"light", "imu"}:
                            result["physical"] = client.measure_voltage("P2" if mode == "imu" else "P1")
                        else:
                            duration = 1000 if mode == "servo" else 2000
                            result["physical"] = client.measure_frequency("P1", duration)
                except (BenchError, OSError, ValueError) as exc:
                    result["errors"].append({"device": "S3", "message": str(exc)})
            if dut_port and mode in {"light", "imu"}:
                try:
                    if mode == "light":
                        result["dut"] = {"reported_voltage_v": read_light_report(dut_port)}
                    else:
                        result["dut"] = read_imu_report(dut_port, line_sink=lambda line: self._record_serial(line, dut_port))
                except (BenchError, OSError, ValueError) as exc:
                    result["errors"].append({"device": "C6", "message": str(exc)})
        result["diagnosis"] = diagnose(mode, result["physical"], result["dut"], result["errors"])
        return result


class DashboardHandler(BaseHTTPRequestHandler):
    server: "DashboardServer"

    def log_message(self, _format: str, *_args: object) -> None:
        # Frequent dashboard polls would otherwise flood the terminal.
        pass

    def _remote_dashboard_blocked(self, path: str) -> bool:
        if is_phone_capture_path(path):
            return False
        if local_dashboard_allowed(self.client_address[0], self.headers.get("Host", "")):
            return False
        self._json({"error": "This Benchy dashboard is only available on the local computer."},
                   HTTPStatus.FORBIDDEN)
        return True

    def _local_json_post(self) -> bool:
        origin = self.headers.get("Origin")
        expected_origin = f"http://127.0.0.1:{self.server.server_address[1]}"
        return (self.headers.get("X-Benchy-Local") == "1"
                and self.headers.get_content_type() == "application/json"
                and (not origin or origin == expected_origin))

    def do_GET(self) -> None:
        route = urlsplit(self.path)
        if self._remote_dashboard_blocked(route.path):
            return
        capture = parse_capture_path(route.path)
        if capture:
            self._get_capture(capture[0], capture[1] == "/status")
            return
        if route.path == "/api/visual/session/image":
            self._get_visual_image()
            return
        if route.path == "/api/visual/session":
            self._json(self.server.state.visual.current_view())
            return
        if route.path == "/api/voice/status":
            self._json({"configured": bool(os.environ.get("XAI_API_KEY")),
                        "model": "grok-voice-latest",
                        "instructions": VOICE_INSTRUCTIONS})
            return
        if route.path == "/api/voice/tools":
            self._json({"tools": [{
                "type": "function", "name": "ask_codex",
                "description": "Hand the user's debugging problem to the local Codex engineer. Use this when code inspection, a physical measurement, or a concrete diagnosis is needed. Include what the user observed, relevant conversation context, and what you want Codex to investigate. Codex will inspect the local project and may take read-only physical measurements.",
                "parameters": {
                    "type": "object", "properties": {
                        "problem": {"type": "string", "description": "The user's symptom and expected behavior."},
                        "context": {"type": "string", "description": "Relevant details established in the conversation, including what has already been tried."},
                        "investigation": {"type": "string", "description": "The specific question or next investigation for Codex."}
                    }, "required": ["problem", "context", "investigation"], "additionalProperties": False
                }
            }]})
            return
        if route.path == "/api/agent/status":
            binary = find_codex_cli()
            try:
                mcp_available = find_spec("mcp") is not None
            except (ImportError, ValueError):
                mcp_available = False
            self._json({"configured": bool(binary and mcp_available),
                        "codex_cli": bool(binary), "benchy_tools": mcp_available,
                        "gemini_configured": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
                        "codex_cli_source": "configured path" if os.environ.get("CODEX_CLI_PATH") else
                            "PATH" if shutil.which("codex") else "Codex desktop install" if binary else None,
                        "model": "Codex · local workspace"})
            return
        if route.path == "/api/code":
            self._json(code_inventory())
            return
        if route.path == "/api/agent/diff":
            try:
                result = subprocess.run(["git", "diff", "--no-ext-diff", "--unified=3"],
                    cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=5, check=True)
                parts = [result.stdout]
                additions = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "--exclude=**/node_modules/**"],
                    cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=5, check=True)
                reviewable = {".py", ".ino", ".h", ".cpp", ".c", ".js", ".ts", ".json",
                              ".md", ".yaml", ".yml", ".html", ".css", ".txt", ".toml", ".sh", ".ps1"}
                for relative in additions.stdout.splitlines():
                    candidate = (REPO_ROOT / relative).resolve()
                    try:
                        safe_path = candidate.is_relative_to(REPO_ROOT)
                    except (OSError, ValueError):
                        safe_path = False
                    if (not safe_path or Path(relative).suffix.lower() not in reviewable
                            or any(part.startswith(".") for part in Path(relative).parts)
                            or not candidate.is_file() or candidate.stat().st_size > 100_000):
                        continue
                    content = candidate.read_text(encoding="utf-8", errors="replace")
                    parts.append(f"--- /dev/null\n+++ b/{relative}\n" +
                                 "@@ new file @@\n" + "\n".join("+" + line for line in content.splitlines()))
                diff = "\n".join(part for part in parts if part)
                self._json({"source": "local_git_diff", "diff": diff[:200_000],
                            "truncated": len(diff) > 200_000,
                            "empty": not bool(diff)})
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                self._json({"error": f"Could not read the project diff: {exc}"},
                           HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if route.path == "/api/agent/flash-plan":
            try:
                from benchos.flash import plan_dut_flash
                self._json({"ok": True, **plan_dut_flash()})
            except (OSError, ValueError, yaml.YAMLError) as exc:
                self._json({"ok": False, "error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
            except Exception as exc:
                self._json({"ok": False, "error": f"Flash planning failed: {exc}"},
                           HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if route.path == "/api/source":
            name = parse_qs(route.query).get("path", [""])[0]
            try:
                self._json(source_file(name))
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except OSError as exc:
                self._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
            return
        if route.path == "/api/serial":
            query = parse_qs(route.query)
            try:
                port = query.get("port", [""])[0]
                duration_ms = int(query.get("duration_ms", ["700"])[0])
                after_seq = int(query.get("after", ["0"])[0])
                self._json(self.server.state.serial_sample(port, duration_ms, after_seq))
            except (ValueError, BenchError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route.path == "/api/probes":
            port = parse_qs(route.query).get("lab_port", [""])[0]
            try:
                self._json(self.server.state.probe_sample(port))
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except (BenchError, OSError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if route.path in {"/api/bus", "/api/taps"}:
            query = parse_qs(route.query)
            port = query.get("lab_port", [""])[0]
            dut_port = query.get("dut_port", [""])[0]
            try:
                duration_ms = int(query.get("duration_ms", ["1000"])[0])
                self._json(self.server.state.bus_sample(port, duration_ms, dut_port,
                                                       digital_taps=route.path == "/api/taps"))
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except (BenchError, OSError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if route.path == "/api/records":
            query = parse_qs(route.query)
            try:
                name = query.get("id", [""])[0]
                self._json(read_record(name) if name else list_records())
            except (OSError, ValueError, TypeError, RecursionError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route.path == "/api/harness":
            try:
                self._json(describe_harness())
            except (OSError, ValueError, yaml.YAMLError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if route.path == "/api/config":
            candidates = set(candidate_ports())
            self._json({"lab_port": self.server.state.lab_port,
                        "dut_port": self.server.state.dut_port,
                        "ports": [port for port in available_ports()
                                  if port["device"] in candidates]})
            return
        if route.path == "/api/snapshot":
            query = parse_qs(route.query)
            mode = query.get("mode", ["light"])[0]
            lab_port = query.get("lab_port", [""])[0]
            dut_port = query.get("dut_port", [""])[0]
            try:
                self._json(self.server.state.snapshot(mode, lab_port, dut_port))
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route.path in ASSETS:
            name, content_type = ASSETS[route.path]
            data = files("benchos.dashboard_ui").joinpath(name).read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _get_capture(self, token: str, status_only: bool) -> None:
        try:
            state = self.server.state.visual.phone_state(token)
        except VisualError as exc:
            if status_only:
                self._json({"error": str(exc)}, exc.status)
            else:
                self._html(message_page("Capture link", str(exc)), exc.status)
            return
        if status_only:
            self._json(state)
            return
        if state["status"] == "expired":
            self._html(message_page("Capture link expired", "Ask Benchy for a new QR code."), HTTPStatus.GONE)
            return
        page = files("benchos.dashboard_ui").joinpath("capture.html").read_text(encoding="utf-8")
        self._html(page.replace("__BENCHY_TOKEN__", token).encode("utf-8"))

    def _get_visual_image(self) -> None:
        try:
            data, mime = self.server.state.visual.image()
        except VisualError as exc:
            self._json({"error": str(exc)}, exc.status)
            return
        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _html(self, data: bytes, status: HTTPStatus = HTTPStatus.OK) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _read_limited(self, limit: int) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise VisualError("Invalid upload size.") from exc
        if length < 1 or length > limit:
            raise VisualError("Image must be between 1 byte and 5 MB.")
        data = self.rfile.read(length)
        if len(data) != length:
            raise VisualError("Upload ended early.")
        return data

    def do_POST(self) -> None:
        route = urlsplit(self.path).path
        if self._remote_dashboard_blocked(route):
            return
        capture = parse_capture_path(route)
        if capture and capture[1] == "":
            self._post_capture(capture[0])
            return
        if capture:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if route == "/api/visual/session":
            self._post_visual_session()
            return
        if route == "/api/visual/verify":
            self._post_visual_verify()
            return
        if route in {"/api/voice/session", "/api/voice/tool"}:
            self._do_voice_post(route)
            return
        if route == "/api/agent/chat":
            self._do_agent_chat()
            return
        if route == "/api/agent/flash":
            self._do_agent_flash()
            return
        if route == "/api/agent/stop":
            self._do_agent_stop()
            return
        if route not in {"/api/harness/probes", "/api/records"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        origin = self.headers.get("Origin")
        expected_origin = f"http://127.0.0.1:{self.server.server_address[1]}"
        if (self.headers.get("X-Benchy-Local") != "1"
                or self.headers.get_content_type() != "application/json"
                or (origin and origin != expected_origin)):
            self._json({"error": "Local JSON request required"}, HTTPStatus.FORBIDDEN)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= (12_000 if route == "/api/records" else 2048):
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length))
            if route == "/api/records":
                self._json(self.server.state.capture_record(payload), HTTPStatus.CREATED)
            else:
                self._json(update_probe_declarations(payload))
        except BenchError as exc:
            self._json({"error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _post_capture(self, token: str) -> None:
        try:
            data = self._read_limited(5 * 1024 * 1024)
            view = self.server.state.accept_visual_image(token, data, self.headers.get_content_type())
            self._json(view, HTTPStatus.ACCEPTED)
        except VisualError as exc:
            self._json({"error": str(exc)}, exc.status)

    def _post_visual_session(self) -> None:
        if not self._local_json_post():
            self._json({"error": "Local JSON request required"}, HTTPStatus.FORBIDDEN)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 2048:
                raise ValueError("Invalid request size")
            if length:
                json.loads(self.rfile.read(length))
            self._json(self.server.state.visual.start(), HTTPStatus.CREATED)
        except VisualError as exc:
            self._json({"error": str(exc)}, exc.status)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _post_visual_verify(self) -> None:
        if not self._local_json_post():
            self._json({"error": "Local JSON request required"}, HTTPStatus.FORBIDDEN)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 4096:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")
            measurement = payload.get("measurement")
            target = payload.get("target") or ""
            lab_port = payload.get("lab_port") or self.server.state.lab_port or ""
            if not isinstance(measurement, str) or not isinstance(target, str) or not isinstance(lab_port, str):
                raise ValueError("Measurement, target, and lab port must be text")
            self._json(self.server.state.run_visual_check(lab_port, measurement, target))
        except VisualError as exc:
            self._json({"error": str(exc)}, exc.status)
        except BenchError as exc:
            self._json({"error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _do_voice_post(self, path: str) -> None:
        expected_origins = {
            f"http://127.0.0.1:{self.server.server_address[1]}",
            f"http://localhost:{self.server.server_address[1]}",
        }
        if (path != "/api/voice/session"
                or self.headers.get("X-Benchy-Local") != "1"
                or self.headers.get_content_type() != "application/json"
                or self.headers.get("Origin") not in expected_origins):
            self._json({"error": "Local dashboard request required"}, HTTPStatus.FORBIDDEN)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 1024:
                raise ValueError("Invalid request size")
            json.loads(self.rfile.read(length))
            self._json(create_voice_token())
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except RuntimeError as exc:
            self._json({"error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
    def _do_agent_chat(self) -> None:
        global ACTIVE_AGENT_PROCESS, AGENT_STOP_REQUESTED
        expected_origins = {
            f"http://127.0.0.1:{self.server.server_address[1]}",
            f"http://localhost:{self.server.server_address[1]}",
        }
        if (self.headers.get("X-Benchy-Local") != "1"
                or self.headers.get_content_type() != "application/json"
                or self.headers.get("Origin") not in expected_origins):
            self._json({"error": "Local dashboard request required"}, HTTPStatus.FORBIDDEN)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 28_000_000:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")
            message = payload.get("message")
            thread_id = payload.get("thread_id")
            photos = payload.get("photos", [])
            if not isinstance(message, str) or not message.strip() or len(message) > 8000:
                raise ValueError("Message must contain 1–8000 characters")
            if not isinstance(photos, list) or len(photos) > 4:
                raise ValueError("Attach no more than four photos at once")
            photo_bytes = []
            for photo in photos:
                if not isinstance(photo, str) or len(photo) > 7_000_000:
                    raise ValueError("Each photo must be 5 MB or smaller")
                match = re.fullmatch(r"data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)", photo)
                if not match:
                    raise ValueError("Photos must be JPEG, PNG, or WEBP images")
                data = base64.b64decode(match.group(2), validate=True)
                validate_image(data, match.group(1))
                photo_bytes.append((data, match.group(1)))
            for phone_photo in self.server.state.visual.images():
                if len(photo_bytes) == 4:
                    break
                photo_bytes.append(phone_photo)
            if thread_id is not None and (not isinstance(thread_id, str)
                    or not re.fullmatch(r"[0-9a-fA-F-]{36}", thread_id)):
                raise ValueError("Invalid conversation id")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        codex = find_codex_cli()
        if not codex:
            self._json({"error": "Codex CLI was not found. Start the dashboard from the signed-in Codex app, or set CODEX_CLI_PATH to the full path of the Codex executable and restart it."},
                       HTTPStatus.SERVICE_UNAVAILABLE)
            return
        try:
            if find_spec("mcp") is None:
                raise ImportError
        except (ImportError, ValueError):
            self._json({"error": "Install the project MCP extra in this Python environment, then restart the dashboard."},
                       HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if not AGENT_RUN_LOCK.acquire(blocking=False):
            self._json({"error": "Benchy is already working on another request. Wait for it to finish, then retry."},
                       HTTPStatus.CONFLICT)
            return

        with AGENT_PROCESS_LOCK:
            AGENT_STOP_REQUESTED = False

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def emit(value: dict) -> None:
            encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            self.wfile.write(f"data: {encoded}\n\n".encode("utf-8"))
            self.wfile.flush()

        process = None
        try:
            photo_description = ""
            if photo_bytes:
                emit({"kind": "status", "message": "Gemini is describing the attached photos for Codex…"})
                photo_description = describe_images_for_context(photo_bytes)
            emit({"kind": "status", "message": "Starting local Codex agent…"})
            args = [codex, "exec"]
            if thread_id:
                # `exec resume` accepts JSON/config options before its session id,
                # but does not support `--cd` or `--sandbox`. Resume restores the
                # original workspace and policy from the saved session.
                args += ["resume", "--json", "--ignore-user-config"]
            else:
                args += ["--json", "--cd", str(REPO_ROOT), "--sandbox", "workspace-write",
                         "--ignore-user-config"]
            mcp_config = agent_mcp_config()
            for item in mcp_config:
                args += ["--config", item]
            if thread_id:
                args.append(thread_id)
            args.append("-")
            environment = os.environ.copy()
            profile = environment.get("USERPROFILE")
            if profile:
                if not environment.get("HOME"):
                    environment["HOME"] = profile
                if not environment.get("CODEX_HOME"):
                    environment["CODEX_HOME"] = str(Path(profile) / ".codex")
            with tempfile.TemporaryFile() as error_file:
                process = subprocess.Popen(args, cwd=REPO_ROOT, env=environment,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=error_file,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                with AGENT_PROCESS_LOCK:
                    ACTIVE_AGENT_PROCESS = process
                    if AGENT_STOP_REQUESTED:
                        process.terminate()
                photo_context = ("\n\nGemini photo description (visual context only; not a diagnosis or electrical measurement):\n"
                                 + photo_description
                                 + "\nTreat uncertain labels and wire routes as uncertain visual observations. Confirm physical placement with the user before using it to choose a probe or change the circuit.") if photo_description else ""
                prompt = AGENT_PROMPT + "\n\nUser message:\n" + message.strip() + photo_context
                assert process.stdin is not None
                process.stdin.write(prompt)
                process.stdin.close()
                assert process.stdout is not None
                actual_thread_id = thread_id
                for line in process.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        emit({"kind": "status", "message": line[:1000]})
                        continue
                    if isinstance(event, dict):
                        if event.get("type") == "thread.started":
                            actual_thread_id = event.get("thread_id") or actual_thread_id
                        emit({"kind": "codex_event", "event": event,
                              "thread_id": actual_thread_id})
                return_code = process.wait()
                if return_code:
                    error_file.seek(0)
                    diagnostic = error_file.read(16_384).decode("utf-8", errors="replace")
                    emit({"kind": "error", "message": diagnostic.strip() or
                          f"Codex exited with status {return_code}.",
                          "thread_id": actual_thread_id})
                else:
                    emit({"kind": "complete", "thread_id": actual_thread_id})
        except (BrokenPipeError, ConnectionResetError):
            if process and process.poll() is None:
                process.terminate()
        except VisualError as exc:
            try:
                emit({"kind": "error", "message": str(exc), "thread_id": thread_id})
            except (BrokenPipeError, ConnectionResetError):
                pass
        except (OSError, RuntimeError, ValueError) as exc:
            try:
                emit({"kind": "error", "message": str(exc)[:2000], "thread_id": thread_id})
            except (BrokenPipeError, ConnectionResetError):
                pass
        finally:
            with AGENT_PROCESS_LOCK:
                if ACTIVE_AGENT_PROCESS is process:
                    ACTIVE_AGENT_PROCESS = None
                AGENT_STOP_REQUESTED = False
            if process and process.poll() is None:
                process.terminate()
            AGENT_RUN_LOCK.release()

    def _do_agent_flash(self) -> None:
        expected_origins = {
            f"http://127.0.0.1:{self.server.server_address[1]}",
            f"http://localhost:{self.server.server_address[1]}",
        }
        if (self.headers.get("X-Benchy-Local") != "1"
                or self.headers.get_content_type() != "application/json"
                or self.headers.get("Origin") not in expected_origins):
            self._json({"error": "Local dashboard request required"}, HTTPStatus.FORBIDDEN)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 2048:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length))
            if (not isinstance(payload, dict)
                    or payload.get("confirmation") != "FLASH_DECLARED_DUT"
                    or payload.get("wiring_confirmed") is not True):
                raise ValueError("Confirm the declared DUT target and current physical wiring before flashing")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if not AGENT_RUN_LOCK.acquire(blocking=False):
            self._json({"error": "Benchy is already working on another request. Wait for it to finish, then retry."},
                       HTTPStatus.CONFLICT)
            return
        try:
            from benchos.flash import build_dut_firmware, flash_result_ok
            result = build_dut_firmware(flash=True)
            response = {"ok": flash_result_ok(result), **result}
            self._json(response, HTTPStatus.OK if response["ok"] else HTTPStatus.CONFLICT)
        except (OSError, ValueError) as exc:
            self._json({"ok": False, "error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
        except Exception as exc:
            self._json({"ok": False, "error": f"Build or flash failed: {exc}"},
                       HTTPStatus.SERVICE_UNAVAILABLE)
        finally:
            AGENT_RUN_LOCK.release()

    def _do_agent_stop(self) -> None:
        expected_origins = {
            f"http://127.0.0.1:{self.server.server_address[1]}",
            f"http://localhost:{self.server.server_address[1]}",
        }
        if (self.headers.get("X-Benchy-Local") != "1"
                or self.headers.get("Origin") not in expected_origins):
            self._json({"error": "Local dashboard request required"}, HTTPStatus.FORBIDDEN)
            return
        with AGENT_PROCESS_LOCK:
            if AGENT_RUN_LOCK.locked():
                global AGENT_STOP_REQUESTED
                AGENT_STOP_REQUESTED = True
                if ACTIVE_AGENT_PROCESS and ACTIVE_AGENT_PROCESS.poll() is None:
                    ACTIVE_AGENT_PROCESS.terminate()
        self._json({"ok": True})

    def _json(self, value: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(value).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            # A reload can close an in-flight polling request. There is no
            # client left to receive a second error response.
            return


class DashboardServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], state: DashboardState):
        super().__init__(address, DashboardHandler)
        self.state = state


def load_env_file(path: Path) -> list[str]:
    """Fill unset variables from a local .env. A real environment variable always wins."""
    try:
        # Notepad and PowerShell write a BOM, which would otherwise become part
        # of the first variable's name.
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return []
    loaded = []
    for line in text.splitlines():
        entry = line.strip()
        if entry.startswith("export "):
            entry = entry[7:].lstrip()
        if not entry or entry.startswith("#") or "=" not in entry:
            continue
        name, _, value = entry.partition("=")
        name, value = name.strip(), value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not name or name in os.environ:
            continue
        os.environ[name] = value
        loaded.append(name)
    return loaded


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="BenchOS local dashboard")
    parser.add_argument("--lab-port", help="ESP32-S3 serial port")
    parser.add_argument("--dut-port", help="ESP32-C6 serial port")
    parser.add_argument("--web-port", type=int, default=8765)
    args = parser.parse_args(argv)
    if not 1 <= args.web_port <= 65535:
        parser.error("--web-port must be 1–65535")
    loaded = load_env_file(REPO_ROOT / ".env")
    if loaded:
        print(f"Loaded from .env: {', '.join(loaded)}", flush=True)
    bind = os.environ.get("BENCHY_BIND_HOST", "127.0.0.1").strip() or "127.0.0.1"
    if any(character in bind for character in " /\\?#"):
        parser.error("BENCHY_BIND_HOST must be a host address such as 127.0.0.1 or 0.0.0.0")
    state = DashboardState(args.lab_port, args.dut_port)
    server = DashboardServer((bind, args.web_port), state)
    print(f"Benchy dashboard: http://127.0.0.1:{args.web_port}", flush=True)
    if bind not in {"127.0.0.1", "localhost", "::1"}:
        print("Phone capture listens on this bind address. Open the dashboard at "
              f"http://127.0.0.1:{args.web_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        state.close()


if __name__ == "__main__":
    main()
