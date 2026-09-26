"""Strict parsing of the line-oriented BenchOS protocol."""

import math
import re


class BenchError(Exception):
    """Base error from transport or protocol."""


class BenchProtocolError(BenchError):
    pass


class BenchDeviceError(BenchError):
    pass


PROBE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,15}\Z")


def validate_probe(probe: str) -> str:
    if not isinstance(probe, str) or not PROBE_RE.fullmatch(probe):
        raise ValueError("Probe must be a name such as P1, with no spaces")
    return probe.upper()


def _finite_float(value: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise BenchProtocolError(f"Invalid numeric value: {value!r}") from exc
    if not math.isfinite(result):
        raise BenchProtocolError("Non-finite measurement")
    return result


def _nonnegative_int(value: str) -> int:
    if not value.isdigit():
        raise BenchProtocolError(f"Invalid nonnegative integer: {value!r}")
    return int(value)


def parse_response(line: str) -> dict:
    parts = line.strip().split()
    if not parts:
        raise BenchProtocolError("Empty response")
    if parts[0] == "ERR":
        raise BenchDeviceError(" ".join(parts[1:]) or "UNKNOWN_ERROR")
    if parts[0] != "OK" or len(parts) < 2:
        raise BenchProtocolError(f"Unexpected response: {line!r}")
    kind = parts[1]
    if kind == "PONG" and len(parts) == 2:
        return {"kind": "pong"}
    if kind in ("INFO", "HELP"):
        return {"kind": kind.lower(), "text": " ".join(parts[2:])}
    if kind == "VOLTAGE" and len(parts) == 8 and parts[4] == "RAW" and parts[6] == "SAMPLES":
        return {"kind": "voltage", "probe": parts[2], "voltage_v": _finite_float(parts[3]),
                "raw": _nonnegative_int(parts[5]), "samples": _nonnegative_int(parts[7])}
    if kind == "DIGITAL" and len(parts) == 4 and parts[3] in ("HIGH", "LOW"):
        return {"kind": "digital", "probe": parts[2], "state": parts[3]}
    if (kind == "FREQUENCY" and len(parts) == 10 and parts[4] == "EDGES"
            and parts[6] == "WINDOW_MS" and parts[8] == "PULSE_US"):
        return {"kind": "frequency", "probe": parts[2], "frequency_hz": _finite_float(parts[3]),
                "edges": _nonnegative_int(parts[5]), "window_ms": _nonnegative_int(parts[7]),
                "pulse_us": _nonnegative_int(parts[9])}
    raise BenchProtocolError(f"Malformed response: {line!r}")
