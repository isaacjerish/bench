"""Cross-check declared DUT serial fields against nearby physical S3 readings."""

from __future__ import annotations

import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from .dashboard import DashboardState
from .harness import describe_harness
from .ports import available_ports

FIELD_RE = re.compile(r"(?:^|\s)([A-Za-z][A-Za-z0-9_]{0,31})=(-?\d+(?:\.\d+)?)(?=\s|$)")


def compare_declared_fields(probes: dict, serial_events: list[dict], rules: list[dict],
                            max_age_s: float = 5.0) -> dict:
    """Return bounded evidence; a missing or stale serial report is unverified."""
    measured_at = datetime.fromisoformat(probes["timestamp"])
    readings = {row["probe"]: row for row in probes["readings"]
                if row.get("declared_state") == "connected"}
    for event in reversed(serial_events):
        try:
            age = abs((measured_at - datetime.fromisoformat(event["timestamp"])).total_seconds())
        except (KeyError, TypeError, ValueError):
            continue
        if age > max_age_s:
            continue
        fields = {key: float(value) for key, value in FIELD_RE.findall(event.get("line", ""))}
        if not fields:
            continue
        checks = []
        for rule in rules:
            row = readings.get(rule["probe"])
            if row is None or rule["field"] not in fields:
                continue
            claimed = fields[rule["field"]] * rule["scale_to_v"]
            actual = float(row["voltage_v"])
            if not math.isfinite(claimed) or not math.isfinite(actual):
                continue
            delta = abs(actual - claimed)
            checks.append({"probe": rule["probe"], "field": rule["field"],
                           "declared_net": row.get("declared_net"),
                           "physical_v": actual, "dut_claim_v": round(claimed, 4),
                           "delta_v": round(delta, 4), "max_delta_v": rule["max_delta_v"],
                           "pass": delta <= rule["max_delta_v"]})
        if checks:
            return {"state": "pass" if all(item["pass"] for item in checks) else "fail",
                    "source": "s3_physical_plus_dut_serial", "sample_age_s": round(age, 3),
                    "serial_line": event["line"], "checks": checks,
                    "scope": "Only declared probe nodes and fields; serial contents are DUT claims."}
    return {"state": "unverified", "source": "s3_physical_plus_dut_serial",
            "checks": [], "reason": "No fresh numeric serial fields matched connected probe declarations"}


def check_live_declared_telemetry() -> dict:
    """Read enrolled S3/C6 in overlapping windows, then compare declared fields."""
    harness = describe_harness()
    ports = available_ports()

    def enrolled(serial: str) -> str:
        matches = [item["device"] for item in ports if item.get("serial_number")
                   and item["serial_number"].casefold() == serial.casefold()]
        if len(matches) != 1:
            raise ValueError(f"Expected one connected USB board with serial {serial}; found {len(matches)}")
        return matches[0]

    lab_port = enrolled(harness["lab"]["usb_serial_number"])
    dut_port = enrolled(harness["dut"]["usb_serial_number"])
    if lab_port == dut_port:
        raise ValueError("Lab and DUT ports must be distinct")
    with ThreadPoolExecutor(max_workers=2) as pool:
        serial_future = pool.submit(DashboardState().serial_sample, dut_port, 1200)
        probes_future = pool.submit(DashboardState().probe_sample, lab_port)
        serial_result = serial_future.result()
        probe_result = probes_future.result()
    verdict = compare_declared_fields(probe_result, serial_result["events"],
                                      harness.get("telemetry_checks", []))
    return {"lab_port": lab_port, "dut_port": dut_port,
            "physical": probe_result, "serial_window_ms": serial_result["sample_window_ms"],
            **verdict}
