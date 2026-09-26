"""Read the user-declared physical harness; never infer wiring from firmware."""

from pathlib import Path

import yaml


HARNESS_FILE = Path(__file__).resolve().parent.parent / "harness" / "current.yaml"
PROBE_STATES = {"connected", "wired_unverified", "pending", "disconnected"}


def describe_harness(path: Path = HARNESS_FILE) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Unsupported harness declaration")
    probes = data.get("probes")
    if not isinstance(probes, dict) or set(probes) != {"P1", "P2"}:
        raise ValueError("Harness must declare P1 and P2")
    for name, probe in probes.items():
        if not isinstance(probe, dict) or probe.get("state") not in PROBE_STATES:
            raise ValueError(f"Invalid state for {name}")
        if probe["state"] == "connected" and not probe.get("net"):
            raise ValueError(f"Connected {name} needs a declared net")
    if data.get("voltage_limit_v") != 3.3:
        raise ValueError("Harness voltage limit must be 3.3 V")
    return {**data, "source": "user_declared", "physically_verified": False}
