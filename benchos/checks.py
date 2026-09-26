"""Small, deterministic pass/fail checks for real physical measurements."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .client import BenchClient
from .harness import describe_harness


@dataclass(frozen=True)
class VoltageRangeCheck:
    probe: str
    minimum: float
    maximum: float

    def run(self, client: BenchClient) -> dict:
        reading = client.measure_voltage(self.probe)
        value = reading["voltage_v"]
        return {"type": "voltage_range", "probe": self.probe, "value": value,
                "unit": "V", "minimum": self.minimum, "maximum": self.maximum,
                "pass": self.minimum <= value <= self.maximum}


@dataclass(frozen=True)
class DigitalStateCheck:
    probe: str
    expected: str

    def run(self, client: BenchClient) -> dict:
        reading = client.read_digital(self.probe)
        value = reading["state"]
        return {"type": "digital_state", "probe": self.probe, "value": value,
                "expected": self.expected, "pass": value == self.expected}


@dataclass(frozen=True)
class FrequencyRangeCheck:
    probe: str
    minimum: float
    maximum: float
    duration_ms: int = 1000
    pulse_min_us: int | None = None
    pulse_max_us: int | None = None

    def run(self, client: BenchClient) -> dict:
        reading = client.measure_frequency(self.probe, self.duration_ms)
        hz = reading["frequency_hz"]
        pulse = reading["pulse_us"]
        passed = self.minimum <= hz <= self.maximum and reading["edges"] > 0
        if self.pulse_min_us is not None:
            passed = passed and pulse >= self.pulse_min_us
        if self.pulse_max_us is not None:
            passed = passed and pulse <= self.pulse_max_us
        return {"type": "frequency_range", "probe": self.probe, "value": hz,
                "unit": "Hz", "edges": reading["edges"], "pulse_us": pulse,
                "minimum": self.minimum, "maximum": self.maximum, "pass": passed}


CHECK_TYPES = {
    "voltage_range": VoltageRangeCheck,
    "digital_state": DigitalStateCheck,
    "frequency_range": FrequencyRangeCheck,
}


def load_suite(path: str | Path) -> tuple[str, list, dict[str, str]]:
    source = Path(path)
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("checks"), list):
        raise ValueError("Test file needs a 'checks' list")
    expected_nets = data.get("expected_nets", {})
    if not isinstance(expected_nets, dict) or not all(
        key in {"P1", "P2", "P3"} and isinstance(value, str) and value
        for key, value in expected_nets.items()
    ):
        raise ValueError("expected_nets must map probe names to nonempty net names")
    checks = []
    for item in data["checks"]:
        if not isinstance(item, dict) or item.get("type") not in CHECK_TYPES:
            raise ValueError(f"Unknown check: {item!r}")
        check_type = item["type"]
        checks.append(CHECK_TYPES[check_type](**{key: value for key, value in item.items()
                                                   if key != "type"}))
    return str(data.get("name") or source.stem), checks, expected_nets


def run_suite(client: BenchClient, path: str | Path, log_path: str | None = None) -> dict:
    name, checks, expected_nets = load_suite(path)
    if expected_nets:
        declared = describe_harness()["probes"]
        for probe, net in expected_nets.items():
            actual = declared[probe]
            if actual["state"] != "connected" or actual["net"] != net:
                raise ValueError(f"{name} requires declared {probe} on {net}; check wiring and harness/current.yaml")
    results = []
    for check in checks:
        result = check.run(client)
        results.append(result)
        if log_path:
            record = {"timestamp": datetime.now(timezone.utc).isoformat(),
                      "test": name, **result}
            with Path(log_path).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record) + "\n")
    return {"test": name, "expected_nets_source": "user_declared", "pass": bool(results) and all(r["pass"] for r in results),
            "checks": results}
