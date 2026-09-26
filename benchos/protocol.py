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
INFO_RE = re.compile(r"([A-Za-z0-9_-]+)\s+(v\d+(?:\.\d+)*)\s+PROBES\s+(\d+)\s+ADC_SAMPLES\s+(\d+)(?:\s+PROFILE\s+([A-Za-z0-9_-]+))?\Z")


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
    if kind == "INFO":
        detail = " ".join(parts[2:])
        match = INFO_RE.fullmatch(detail)
        if not match:
            raise BenchProtocolError(f"Malformed INFO response: {line!r}")
        return {"kind": "info", "device": match.group(1), "version": match.group(2),
                "probe_count": _nonnegative_int(match.group(3)),
                "adc_samples": _nonnegative_int(match.group(4)), "text": detail,
                **({"profile": match.group(5)} if match.group(5) else {})}
    if kind == "HELP":
        return {"kind": "help", "text": " ".join(parts[2:])}
    if kind == "VOLTAGE" and len(parts) == 8 and parts[4] == "RAW" and parts[6] == "SAMPLES":
        return {"kind": "voltage", "probe": parts[2], "voltage_v": _finite_float(parts[3]),
                "raw": _nonnegative_int(parts[5]), "samples": _nonnegative_int(parts[7])}
    if kind == "DIGITAL" and len(parts) == 4 and parts[3] in ("HIGH", "LOW"):
        return {"kind": "digital", "probe": parts[2], "state": parts[3]}
    if kind == "TAPS" and len(parts) >= 8 and parts[2] == "WINDOW_MS" and (len(parts) - 4) % 4 == 0:
        window = _nonnegative_int(parts[3])
        if not window or len(parts) > 68:
            raise BenchProtocolError("Invalid digital tap capture window or channel count")
        taps = {}
        for offset in range(4, len(parts), 4):
            name, start, end, edges = parts[offset:offset + 4]
            if (not re.fullmatch(r"D[1-9][0-9]?", name) or name in taps
                    or start not in {"HIGH", "LOW"} or end not in {"HIGH", "LOW"}):
                raise BenchProtocolError("Invalid or duplicate digital tap")
            taps[name] = {"start": start, "end": end, "edges": _nonnegative_int(edges)}
        return {"kind": "digital_taps", "window_ms": window,
                "edge_counts_approximate": True, "capture_windows_overlap": True,
                "decoded_transactions": False, "taps": taps}
    if (kind == "FREQUENCY" and len(parts) == 10 and parts[4] == "EDGES"
            and parts[6] == "WINDOW_MS" and parts[8] == "PULSE_US"):
        return {"kind": "frequency", "probe": parts[2], "frequency_hz": _finite_float(parts[3]),
                "edges": _nonnegative_int(parts[5]), "window_ms": _nonnegative_int(parts[7]),
                "pulse_us": _nonnegative_int(parts[9])}
    if (kind == "BUS" and len(parts) == 14 and parts[2] == "SDA"
            and parts[5] == "EDGES" and parts[7] == "SCL"
            and parts[10] == "EDGES" and parts[12] == "WINDOW_MS"
            and all(parts[i] in {"HIGH", "LOW"} for i in (3, 4, 8, 9))):
        return {"kind": "bus_activity", "window_ms": _nonnegative_int(parts[13]),
                "edge_counts_approximate": True,
                "sda": {"start": parts[3], "end": parts[4], "edges": _nonnegative_int(parts[6])},
                "scl": {"start": parts[8], "end": parts[9], "edges": _nonnegative_int(parts[11])}}
    raise BenchProtocolError(f"Malformed response: {line!r}")
