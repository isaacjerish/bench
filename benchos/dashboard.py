"""Loopback-only web dashboard for live BenchOS measurements."""

from __future__ import annotations

import argparse
import json
import math
import re
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, urlsplit

import serial

from .client import BenchClient
from .light import read_light_report
from .ports import available_ports, candidate_ports
from .protocol import BenchError
from .serial_lock import SerialPortLock

MODES = {"light", "led", "servo", "imu"}
IMU_LINE = re.compile(r"IMU_ACCEL_G x=(-?\d+\.\d+) y=(-?\d+\.\d+) z=(-?\d+\.\d+)(?: id=0x([0-9A-Fa-f]{2}))?\Z")
WHO_LINE = re.compile(r"IMU_FOUND addr=0x([0-9A-Fa-f]{2}) who_am_i=0x([0-9A-Fa-f]{2})\Z")
ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.css": ("app.css", "text/css; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8")}


def diagnose(mode: str, physical: dict | None, dut: dict | None) -> dict:
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
        if dut is None:
            return {"state": "unknown", "title": "Awaiting IMU stream",
                    "detail": "Connect the C6 and flash the IMU demo."}
        return {"state": "unverified", "title": "Motion stream detected",
                "detail": "These values come from the DUT. Move P1 to an isolated I²C line for independent electrical evidence."}
    raise ValueError(f"Unknown mode: {mode}")


def read_imu_report(port: str, timeout_s: float = 2.5) -> dict:
    """Read one C6 motion line; a fresh session may miss the one-time ID line."""
    import time

    found = None
    try:
        with SerialPortLock(port), serial.Serial(port, 115200, timeout=0.25, write_timeout=0.25) as dut:
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                line = dut.readline().decode("ascii", errors="replace").strip()
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
        self._lock = threading.Lock()

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
        with self._lock:
            if lab_port and mode != "imu":
                try:
                    # Release serial after each sample so MCP/CLI may use the S3.
                    with BenchClient(lab_port) as client:
                        if mode == "light":
                            result["physical"] = client.measure_voltage("P1")
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
                        result["dut"] = read_imu_report(dut_port)
                except (BenchError, OSError, ValueError) as exc:
                    result["errors"].append({"device": "C6", "message": str(exc)})
        result["diagnosis"] = diagnose(mode, result["physical"], result["dut"])
        return result


class DashboardHandler(BaseHTTPRequestHandler):
    server: "DashboardServer"

    def log_message(self, _format: str, *_args: object) -> None:
        # Frequent dashboard polls would otherwise flood the terminal.
        pass

    def do_GET(self) -> None:
        route = urlsplit(self.path)
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

    def _json(self, value: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


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
    print(f"BenchOS dashboard: http://127.0.0.1:{args.web_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        state.close()


if __name__ == "__main__":
    main()
