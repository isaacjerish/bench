"""Loopback-only web dashboard for live BenchOS measurements."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import threading
import time
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
          "/app.js": ("app.js", "text/javascript; charset=utf-8")}


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
                                capture_output=True, text=True, timeout=2, check=True).stdout.strip()
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                                cwd=REPO_ROOT, capture_output=True, text=True, timeout=2,
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
        stream_ready = threading.Event()
        stream_stop = threading.Event()

        def drain_dut() -> None:
            try:
                with SerialPortLock(dut_port), serial.Serial(dut_port, 115200, timeout=0.1,
                                                            write_timeout=0.25) as dut:
                    stream_ready.set()
                    while not stream_stop.is_set():
                        line = dut.readline().decode("utf-8", errors="replace").strip()
                        if line:
                            self._record_serial(line, dut_port)
            except (BenchError, serial.SerialException, OSError) as exc:
                stream_error.append(str(exc))
                stream_ready.set()

        with self.instrument_access():
            # Some DUT sketches pause their serial logging (and therefore their
            # I/O loop) when USB CDC has no reader. Keep the DUT stream drained
            # while the independent S3 samples the physical bus.
            reader = threading.Thread(target=drain_dut, daemon=True) if dut_port else None
            if reader:
                reader.start()
                stream_ready.wait(1.5)
            try:
                with BenchClient(port, timeout=4.0) as client:
                    if harness is None:
                        result = (client.measure_digital_taps(duration_ms) if digital_taps
                                  else client.measure_bus_activity(duration_ms))
                    elif digital_taps:
                        result = client.measure_digital_taps(duration_ms, tap_declarations=harness.get("digital_taps", {}))
                    else:
                        result = client.measure_bus_activity(duration_ms, monitor_declaration=harness.get("bus_monitor", {}))
            finally:
                stream_stop.set()
                if reader:
                    reader.join(timeout=1.0)
        return {**result, "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "s3_physical", "decoded_transactions": False,
                "dut_stream_open_during_capture": bool(reader and stream_ready.is_set() and not stream_error),
                **({"dut_stream_error": stream_error[0]} if stream_error else {})}

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
                    capture = self.bus_sample(lab, 1000, dut, digital_taps=has_taps, harness=declared)
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

    def do_GET(self) -> None:
        route = urlsplit(self.path)
        if route.path == "/api/code":
            self._json(code_inventory())
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

    def do_POST(self) -> None:
        route = urlsplit(self.path).path
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="BenchOS local dashboard")
    parser.add_argument("--lab-port", help="ESP32-S3 serial port")
    parser.add_argument("--dut-port", help="ESP32-C6 serial port")
    parser.add_argument("--web-port", type=int, default=8765)
    args = parser.parse_args(argv)
    if not 1 <= args.web_port <= 65535:
        parser.error("--web-port must be 1–65535")
    state = DashboardState(args.lab_port, args.dut_port)
    server = DashboardServer(("127.0.0.1", args.web_port), state)
    print(f"Benchy dashboard: http://127.0.0.1:{args.web_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        state.close()


if __name__ == "__main__":
    main()
