"""Read the user-declared physical harness; never infer wiring from firmware."""

from pathlib import Path
from datetime import date
import math
import os
import re
import tempfile

import yaml


HARNESS_FILE = Path(__file__).resolve().parent.parent / "harness" / "current.yaml"
PROBE_STATES = {"connected", "wired_unverified", "pending", "disconnected"}
NET_RE = re.compile(r"[A-Z][A-Z0-9_]{0,31}\Z")


def describe_harness(path: Path = HARNESS_FILE) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Unsupported harness declaration")
    probes = data.get("probes")
    if not isinstance(probes, dict) or set(probes) != {"P1", "P2", "P3"}:
        raise ValueError("Harness must declare P1, P2, and P3")
    for name, probe in probes.items():
        if not isinstance(probe, dict) or probe.get("state") not in PROBE_STATES:
            raise ValueError(f"Invalid state for {name}")
        if probe["state"] == "connected" and not probe.get("net"):
            raise ValueError(f"Connected {name} needs a declared net")
        lo, hi = probe.get("expected_min_v"), probe.get("expected_max_v")
        if (lo is None) != (hi is None):
            raise ValueError(f"{name} needs both expected voltage bounds or neither")
        if lo is not None and (isinstance(lo, bool) or isinstance(hi, bool)
                               or not isinstance(lo, (int, float)) or not isinstance(hi, (int, float))
                               or not 0 <= lo <= hi <= 3.3):
            raise ValueError(f"{name} expected voltage must stay within 0–3.3 V")
    monitor = data.get("bus_monitor")
    if not isinstance(monitor, dict) or monitor.get("state") not in {"pending", "connected", "disconnected"}:
        raise ValueError("Harness must declare bus_monitor state")
    if monitor["state"] == "connected" and not all(
        isinstance(monitor.get(key), str) and monitor[key]
        for key in ("sda_net", "scl_net", "sda_input", "scl_input")
    ):
        raise ValueError("Connected bus monitor needs declared nets and inputs")
    telemetry_checks = data.get("telemetry_checks", [])
    taps = data.get("digital_taps", {})
    if not isinstance(taps, dict) or not set(taps) <= {"D1", "D2", "D3", "D4", "D5"}:
        raise ValueError("Digital taps must be named D1–D5")
    for name, tap in taps.items():
        if not isinstance(tap, dict) or tap.get("state") not in PROBE_STATES:
            raise ValueError(f"Invalid state for {name}")
        if tap.get("gpio") != int(name[1:]) + 7:
            raise ValueError(f"{name} GPIO must match the fixed S3 input firmware")
        if not all(isinstance(tap.get(key), str) and tap[key].strip() for key in ("net", "endpoint")):
            raise ValueError(f"{name} needs a declared net and physical endpoint")
        if (isinstance(tap.get("series_resistor_ohm"), bool)
                or not isinstance(tap.get("series_resistor_ohm"), int)
                or not 1000 <= tap["series_resistor_ohm"] <= 10000):
            raise ValueError(f"{name} needs a 1–10 kΩ series sense resistor")
        maximum = tap.get("max_transitions_per_s")
        if maximum is not None and (isinstance(maximum, bool) or not isinstance(maximum, (int, float))
                                    or not math.isfinite(maximum) or not 0 <= maximum <= 10000000):
            raise ValueError(f"{name} transition upper bound must be a finite nonnegative number")
    if not isinstance(telemetry_checks, list) or len(telemetry_checks) > 8:
        raise ValueError("telemetry_checks must be a list of at most eight rules")
    for rule in telemetry_checks:
        if not isinstance(rule, dict) or set(rule) != {"probe", "field", "scale_to_v", "max_delta_v"}:
            raise ValueError("Invalid telemetry comparison rule")
        if rule["probe"] not in probes or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", str(rule["field"])):
            raise ValueError("Telemetry rule needs a known probe and key=value field")
        if any(isinstance(rule[key], bool) or not isinstance(rule[key], (int, float))
               for key in ("scale_to_v", "max_delta_v")):
            raise ValueError("Telemetry rule needs numeric scale and tolerance")
        if not 0 < rule["scale_to_v"] <= 1 or not 0 <= rule["max_delta_v"] <= 3.3:
            raise ValueError("Telemetry comparison scale or tolerance is out of range")
        if not math.isfinite(rule["scale_to_v"]) or not math.isfinite(rule["max_delta_v"]):
            raise ValueError("Telemetry comparison values must be finite")
    if data.get("voltage_limit_v") != 3.3:
        raise ValueError("Harness voltage limit must be 3.3 V")
    return {**data, "source": "user_declared", "physically_verified": False}


def update_probe_declarations(changes: dict, path: Path = HARNESS_FILE) -> dict:
    """Save only user-declared P1/P2 state and net labels, never measured facts."""
    if not isinstance(changes, dict) or not changes or not set(changes) <= {"P1", "P2", "P3"}:
        raise ValueError("Submit declarations for known probes P1, P2, or P3")
    for name, item in changes.items():
        if not isinstance(item, dict) or not {"state", "net"} <= set(item) or not set(item) <= {
            "state", "net", "expected_min_v", "expected_max_v"}:
            raise ValueError(f"{name} needs state, net, and optional expected voltage bounds")
        if item["state"] not in PROBE_STATES:
            raise ValueError(f"Invalid state for {name}")
        if not isinstance(item["net"], str) or not NET_RE.fullmatch(item["net"]):
            raise ValueError(f"{name} net must be an uppercase name of at most 32 characters")
        lo, hi = item.get("expected_min_v"), item.get("expected_max_v")
        if (lo is None) != (hi is None):
            raise ValueError(f"{name} needs both expected voltage bounds or neither")
        if lo is not None and (isinstance(lo, bool) or isinstance(hi, bool)
                               or not isinstance(lo, (int, float)) or not isinstance(hi, (int, float))
                               or not 0 <= lo <= hi <= 3.3):
            raise ValueError(f"{name} expected voltage must stay within 0–3.3 V")
    original = describe_harness(path)
    data = {key: value for key, value in original.items()
            if key not in {"source", "physically_verified"}}
    for name, item in changes.items():
        data["probes"][name].update(item)
    data["declared_on"] = date.today().isoformat()
    content = "# User-declared wiring. Update after physically moving probes.\n" + yaml.safe_dump(data, sort_keys=False)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".harness-", delete=False) as stream:
            temp_name = stream.name
            stream.write(content)
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    return describe_harness(path)
