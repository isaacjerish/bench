"""Read bounded saved instrument records without presenting them as live data."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

RECORDS_ROOT = Path(__file__).resolve().parent.parent / "validation_runs"
MAX_BYTES = 512_000


def write_record(document: dict, root: Path = RECORDS_ROOT) -> dict:
    """Persist a server-built capture atomically, under a generated filename."""
    raw = json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise ValueError("Capture exceeds the storage limit")
    folder = root / "dashboard"
    folder.mkdir(parents=True, exist_ok=True)
    if folder.is_symlink() or not folder.resolve().is_relative_to(root.resolve()):
        raise ValueError("Capture directory must remain inside validation_runs")
    name = "dashboard/" + uuid.uuid4().hex + ".json"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".capture-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
        os.replace(temporary, root / name)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return read_record(name, root)


def _timestamp(value) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value if parsed.tzinfo is not None else None
    except ValueError:
        return None


def _record_path(name: str, root: Path) -> Path:
    relative = Path(name)
    if (not name or len(name) > 240 or relative.is_absolute() or relative.suffix != ".json"
            or any(part.startswith(".") for part in relative.parts)):
        raise ValueError("Choose a JSON capture inside validation_runs")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Capture is unavailable")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Capture is too large for the viewer")
    return path


def read_record(name: str, root: Path = RECORDS_ROOT) -> dict:
    path = _record_path(name, root)
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError("Capture is too large for the viewer")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Capture must contain an object")
    telemetry = data.get("telemetry") if isinstance(data.get("telemetry"), dict) else {}
    physical = telemetry.get("physical", data.get("physical", data))
    physical = physical if isinstance(physical, dict) else {}
    capture = data.get("capture", data)
    if isinstance(data.get("captures"), list) and data["captures"]:
        # Multi-window records display the last recorded window, not an average.
        capture = data["captures"][-1]
    capture = capture if isinstance(capture, dict) else {}
    observed_at = _timestamp(data.get("timestamp")) or _timestamp(capture.get("timestamp")) or _timestamp(physical.get("timestamp"))
    ended_at = _timestamp(data.get("capture_ended_at"))
    span_s = round((datetime.fromisoformat(ended_at.replace("Z", "+00:00")) -
                    datetime.fromisoformat(observed_at.replace("Z", "+00:00"))).total_seconds(), 3) if ended_at and observed_at else None
    observations = []

    def add(channel, net, metric, value, unit, timestamp=None, detail=None):
        if not isinstance(channel, str) or len(channel) > 32:
            return
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            return
        if isinstance(value, str) and value not in {"HIGH", "LOW"}:
            return
        if isinstance(value, (int, float)):
            try:
                if not math.isfinite(value):
                    return
            except OverflowError:
                return
        observations.append({"channel": channel, "net": net if isinstance(net, str) else None,
                             "metric": metric, "value": value, "unit": unit,
                             "timestamp": _timestamp(timestamp), "detail": detail})

    readings = physical.get("readings", [])
    for row in readings[:16] if isinstance(readings, list) else []:
        if isinstance(row, dict):
            add(row.get("probe"), row.get("declared_net"), "voltage", row.get("voltage_v"), "V",
                row.get("timestamp", physical.get("timestamp")))
    taps = capture.get("taps", {})
    window = capture.get("window_ms")
    for tap_name, tap in list(taps.items())[:16] if isinstance(taps, dict) else []:
        if not isinstance(tap, dict) or not tap.get("usable_for_diagnosis"):
            continue
        net = tap.get("declared_net")
        add(tap_name, net, "digital_end", tap.get("end"), "", capture.get("timestamp"), tap.get("endpoint"))
        edges = tap.get("edges")
        if (isinstance(edges, int) and not isinstance(edges, bool) and 0 <= edges <= 2**32
                and isinstance(window, (int, float)) and not isinstance(window, bool)
                and math.isfinite(window) and window > 0):
            add(tap_name, net, "transitions", round(edges * 1000 / window, 3), "/s", capture.get("timestamp"),
                f"{edges} observed edges in {window:g} ms; approximate")
    for item in data.values():
        if isinstance(item, dict) and item.get("kind") == "frequency":
            probe = item.get("probe")
            tap = taps.get(probe, {}) if isinstance(taps, dict) else {}
            add(probe, tap.get("declared_net"), "frequency", item.get("frequency_hz"), "Hz",
                detail="Separate frequency window; timestamp not saved with this reading")
    lines = telemetry.get("serial_lines", [])
    if not isinstance(lines, list):
        lines = []
    if isinstance(data.get("serial"), dict) and isinstance(data["serial"].get("events"), list):
        lines = [event.get("line") for event in data["serial"]["events"][-30:] if isinstance(event, dict)]
    label = data.get("label")
    title = label[:100] if isinstance(label, str) and label.strip() else path.stem.replace("-", " ").replace("_", " ").capitalize()
    return {"id": name, "title": title,
            "timestamp": observed_at, "source": "recorded_file", "is_live": False,
            "capture_ended_at": ended_at, "capture_span_s": span_s,
            "sha256": hashlib.sha256(raw).hexdigest(), "observations": observations,
            "dut_lines": [line[:512] for line in lines[-30:] if isinstance(line, str)],
            "harness_snapshot_available": isinstance(data.get("harness"), dict),
            "harness": data.get("harness") if isinstance(data.get("harness"), dict) else None,
            "source_context": data.get("source_context") if isinstance(data.get("source_context"), dict) else None,
            "note": data.get("note", "")[:2000] if isinstance(data.get("note", ""), str) else "",
            "capture_errors": data.get("errors", []) if isinstance(data.get("errors", []), list) else [],
            "saved_at": _timestamp(data.get("saved_at")),
            "harness_changed_during_capture": data.get("harness_changed_during_capture"),
            "notes": ["Saved observations, not the present state of the circuit.",
                      "Net names come from the saved declaration; no physical connectivity is inferred.",
                      "Channels can have different capture windows. Missing values are not zero."]}


def list_records(root: Path = RECORDS_ROOT) -> dict:
    entries, skipped = [], 0
    if root.is_dir():
        for index, path in enumerate(sorted(root.rglob("*.json"))):
            if index >= 300:
                break
            name = str(path.relative_to(root))
            try:
                record = read_record(name, root)
                if not record["observations"]:
                    continue
                entries.append({key: record[key] for key in ("id", "title", "timestamp", "sha256")}
                               | {"observation_count": len(record["observations"])})
            except (OSError, ValueError, TypeError, RecursionError):
                skipped += 1
    # Checked-in copies and their original runtime captures have identical
    # bytes. Keep one menu choice while retaining every file and readable ID.
    unique = {}
    for entry in entries:
        if entry['sha256'] in unique:
            unique[entry['sha256']]['aliases'].append(entry['id'])
        else:
            unique[entry['sha256']] = {**entry, 'aliases': []}
    return {"source": "recorded_files", "is_live": False, "skipped": skipped,
            "records": sorted(unique.values(), key=lambda item: item["timestamp"] or "", reverse=True)[:100]}
