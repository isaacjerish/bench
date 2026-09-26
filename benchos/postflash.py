"""Bounded observations after upload; a marker is not binary attestation."""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone

import serial

from .protocol import BenchError
from .serial_lock import SerialPortLock


def validate_postflash(spec: dict | None) -> dict | None:
    if spec is None:
        return None
    if not isinstance(spec, dict) or not set(spec) <= {"serial_marker", "timeout_s", "check_telemetry"}:
        raise ValueError("Invalid postflash declaration")
    marker = spec.get("serial_marker")
    if not isinstance(marker, str) or not 1 <= len(marker) <= 128 or any(
        not 33 <= ord(char) <= 126 for char in marker
    ):
        raise ValueError("Postflash serial_marker must be one printable ASCII token")
    timeout = spec.get("timeout_s", 8)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 15:
        raise ValueError("Postflash timeout_s must be 1–15 seconds")
    if not isinstance(spec.get("check_telemetry", False), bool):
        raise ValueError("Postflash check_telemetry must be boolean")
    return {"serial_marker": marker, "timeout_s": timeout,
            "check_telemetry": spec.get("check_telemetry", False)}


def observe_marker(usb_serial_number: str, spec: dict, ports_provider) -> dict:
    deadline = time.monotonic() + spec["timeout_s"]
    error = None
    while time.monotonic() < deadline:
        matches = [port for port in ports_provider() if str(port.get("serial_number", "")).casefold()
                   == usb_serial_number.casefold()]
        if len(matches) > 1:
            return {"state": "unverified", "error": "DUT USB identity is ambiguous after upload"}
        if not matches:
            time.sleep(0.1)
            continue
        port = matches[0]["device"]
        try:
            remaining = max(0.01, deadline - time.monotonic())
            with SerialPortLock(port, timeout_s=min(2, remaining)), serial.Serial(
                port, 115200, timeout=0.1, write_timeout=0.25
            ) as device:
                while time.monotonic() < deadline:
                    line = device.readline().decode("utf-8", errors="replace").strip()
                    if spec["serial_marker"] in line.split():
                        return {"state": "observed", "port": port,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "expected_marker": spec["serial_marker"], "line": line[:512],
                                "source": "dut_serial", "binary_identity_verified": False}
        except (BenchError, serial.SerialException, OSError) as exc:
            error = str(exc)
        time.sleep(0.1)
    return {"state": "unverified", "expected_marker": spec["serial_marker"],
            "error": error or "Expected marker was not observed before timeout"}


def verify_postflash(harness: dict, spec: dict, ports_provider) -> dict:
    marker = observe_marker(harness["dut"]["usb_serial_number"], spec, ports_provider)
    result = {"state": "pass" if marker["state"] == "observed" else "unverified",
              "marker": marker, "telemetry": None, "probe_ranges": [],
              "scope": "Declared marker, telemetry comparisons, and voltage ranges only; other behavior is unverified."}
    if not spec["check_telemetry"]:
        return result
    from .telemetry import check_live_declared_telemetry
    try:
        evidence = check_live_declared_telemetry(harness)
        result["telemetry"] = evidence
        readings = {row["probe"]: row for row in evidence["physical"]["readings"]}
        for name, declaration in harness["probes"].items():
            if declaration.get("expected_min_v") is None:
                continue
            row = readings.get(name)
            if row is None or row.get("declared_state") != "connected":
                result["probe_ranges"].append({"probe": name, "state": "unverified"})
                continue
            value = row["voltage_v"]
            lo, hi = declaration["expected_min_v"], declaration["expected_max_v"]
            passed = math.isfinite(value) and lo <= value <= hi
            result["probe_ranges"].append({"probe": name, "state": "pass" if passed else "fail",
                                            "voltage_v": value, "min_v": lo, "max_v": hi})
        states = [result["state"], evidence["state"], *[row["state"] for row in result["probe_ranges"]]]
        result["state"] = "fail" if "fail" in states else "unverified" if "unverified" in states else "pass"
    except (BenchError, OSError, ValueError, KeyError) as exc:
        result.update(state="unverified", error=str(exc))
    return result
