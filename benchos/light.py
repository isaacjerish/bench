"""Compare a DUT light-sensor claim with the S3's physical P1 voltage."""

from __future__ import annotations

import re
import time

import serial

from .protocol import BenchError, BenchProtocolError

LIGHT_LINE = re.compile(r"LIGHT_MV ([0-9]{1,5})\Z")


def parse_light_line(line: str) -> float | None:
    match = LIGHT_LINE.fullmatch(line.strip())
    if not match:
        return None
    millivolts = int(match.group(1))
    if millivolts > 3300:
        raise BenchProtocolError(f"DUT reported impossible 3.3 V reading: {millivolts} mV")
    return millivolts / 1000.0


def read_light_report(port: str, timeout_s: float = 6.0) -> float:
    if not port:
        raise ValueError("A separate C6 --dut-port is required")
    try:
        with serial.Serial(port, 115200, timeout=0.5, write_timeout=0.5) as dut:
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                line = dut.readline().decode("ascii", errors="replace")
                value = parse_light_line(line)
                if value is not None:
                    return value
    except (serial.SerialException, OSError) as exc:
        raise BenchError(f"Cannot read C6 light report on {port}: {exc}") from exc
    raise BenchError(f"No LIGHT_MV report from C6 on {port} within {timeout_s:g} s")


def compare_light(client, dut_port: str, *, tolerance_v: float = 0.45,
                  min_physical_v: float = 0.3) -> dict:
    if tolerance_v < 0 or min_physical_v < 0:
        raise ValueError("Thresholds cannot be negative")
    if dut_port == client.port:
        raise ValueError("The C6 DUT port must differ from the S3 lab port")
    reported = read_light_report(dut_port)
    physical = client.measure_voltage("P1")["voltage_v"]
    difference = abs(reported - physical)
    enough_signal = physical >= min_physical_v
    return {"test": "light_sensor_agreement", "probe": "P1", "dut_port": dut_port,
            "physical_voltage_v": physical, "reported_voltage_v": reported,
            "difference_v": round(difference, 3), "tolerance_v": tolerance_v,
            "min_physical_v": min_physical_v, "enough_signal": enough_signal,
            "pass": enough_signal and difference <= tolerance_v}
