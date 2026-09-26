"""A saved capture must preserve instrument evidence and its original context."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from benchos.dashboard import DashboardState
from benchos.protocol import BenchError
from benchos.records import read_record, write_record


def rig(monkeypatch, tmp_path):
    state = DashboardState()
    harness = {"probes": {"P1": {"net": "ORIGINAL", "state": "connected"}},
               "digital_taps": {"D1": {"state": "connected", "net": "DATA"}}}
    monkeypatch.setattr("benchos.dashboard.candidate_ports", lambda: ["lab", "dut"])
    monkeypatch.setattr("benchos.dashboard.describe_harness", lambda: deepcopy(harness))
    monkeypatch.setattr("benchos.dashboard.code_inventory", lambda: {
        "commit": "abc", "short_commit": "abc", "dirty": False,
        "files": [{"path": "config.h", "sha256_short": "original"}], "modified_files": []})
    monkeypatch.setattr("benchos.dashboard.write_record", lambda document: write_record(document, tmp_path))

    def probes(port, *, harness):
        assert port == "lab"
        assert harness["probes"]["P1"]["net"] == "ORIGINAL"
        return {"timestamp": datetime.now(timezone.utc).isoformat(), "source": "s3_physical",
                "readings": [{"probe": "P1", "declared_net": "ORIGINAL", "voltage_v": 1.23}]}

    def taps(port, duration, dut, *, digital_taps, harness):
        assert port == "lab" and dut == "dut" and digital_taps
        state._record_serial("value=1.23", "dut")
        state._record_serial("wrong_device=99", "other")
        return {"timestamp": datetime.now(timezone.utc).isoformat(), "window_ms": 1000,
                "taps": {"D1": {"usable_for_diagnosis": True, "declared_net": "DATA", "end": "HIGH", "edges": 12}}}

    monkeypatch.setattr(state, "probe_sample", probes)
    monkeypatch.setattr(state, "bus_sample", taps)
    return state, harness


def test_fresh_capture_persists_physical_data_and_selected_device_context(monkeypatch, tmp_path):
    state, _ = rig(monkeypatch, tmp_path)
    record = state.capture_record({"lab_port": "lab", "dut_port": "dut", "label": "Before repair", "note": "Wire untouched"})
    saved = read_record(record["id"], tmp_path)
    assert saved["title"] == "Before repair"
    assert saved["observations"][0]["value"] == 1.23
    assert saved["observations"][-1]["value"] == 12
    assert saved["harness"]["probes"]["P1"]["net"] == "ORIGINAL"
    assert saved["dut_lines"] == ["value=1.23"]
    assert saved["source_context"]["after"]["files"][0]["sha256_short"] == "original"
    assert saved["source_context"]["flashed_firmware_verified"] is False
    assert saved["harness_changed_during_capture"] is False
    assert saved["note"] == "Wire untouched"
    assert saved["is_live"] is False


def test_capture_rejects_browser_supplied_measurements(monkeypatch, tmp_path):
    state, _ = rig(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="port choices"):
        state.capture_record({"lab_port": "lab", "label": "Fake", "physical": {"voltage_v": 3.3}})
    with pytest.raises(ValueError, match="distinct"):
        state.capture_record({"lab_port": "lab", "dut_port": "lab", "label": "Bad port"})
    assert not list(tmp_path.rglob("*.json"))


def test_capture_keeps_original_harness_and_flags_changes(monkeypatch, tmp_path):
    state, harness = rig(monkeypatch, tmp_path)
    original = state.probe_sample

    def changing_probes(port, **kwargs):
        result = original(port, **kwargs)
        harness["probes"]["P1"]["net"] = "CHANGED"
        return result

    monkeypatch.setattr(state, "probe_sample", changing_probes)
    saved = state.capture_record({"lab_port": "lab", "dut_port": "dut", "label": "Changing design"})
    assert saved["harness_changed_during_capture"] is True
    assert saved["harness"]["probes"]["P1"]["net"] == "ORIGINAL"
    assert saved["observations"][0]["net"] == "ORIGINAL"


def test_partial_digital_failure_cannot_reuse_an_older_capture(monkeypatch, tmp_path):
    state, _ = rig(monkeypatch, tmp_path)

    def unavailable(*_args, **_kwargs):
        raise BenchError("Lab disconnected")

    monkeypatch.setattr(state, "bus_sample", unavailable)
    saved = state.capture_record({"lab_port": "lab", "dut_port": "dut", "label": "Interrupted"})
    assert len(saved["observations"]) == 1
    assert saved["capture_errors"] == [{"stage": "digital_capture", "message": "Lab disconnected"}]
    assert saved["dut_lines"] == []
    assert state._capture_lock.acquire(blocking=False)
    state._capture_lock.release()


def test_failed_physical_capture_writes_nothing_and_releases_lock(monkeypatch, tmp_path):
    state, _ = rig(monkeypatch, tmp_path)

    def unavailable(*_args, **_kwargs):
        raise BenchError("No measurement")

    monkeypatch.setattr(state, "probe_sample", unavailable)
    with pytest.raises(BenchError, match="No measurement"):
        state.capture_record({"lab_port": "lab", "label": "Unplugged"})
    assert not list(tmp_path.rglob("*.json"))
    assert state._capture_lock.acquire(blocking=False)
    state._capture_lock.release()


def test_source_changes_are_recorded_without_claiming_firmware_identity(monkeypatch, tmp_path):
    state, _ = rig(monkeypatch, tmp_path)
    inventories = iter([
        {"commit": "abc", "files": [{"path": "config.h", "sha256_short": "old"}]},
        {"commit": "abc", "files": [{"path": "config.h", "sha256_short": "new"}]},
    ])
    monkeypatch.setattr("benchos.dashboard.code_inventory", lambda: next(inventories))
    saved = state.capture_record({"lab_port": "lab", "dut_port": "dut", "label": "Edited source"})
    assert saved["source_context"]["changed_during_capture"] is True
    assert saved["source_context"]["before"]["files"][0]["sha256_short"] == "old"
    assert saved["source_context"]["after"]["files"][0]["sha256_short"] == "new"
    assert saved["source_context"]["flashed_firmware_verified"] is False


def test_distant_windows_are_saved_with_a_timing_warning(monkeypatch, tmp_path):
    state, _ = rig(monkeypatch, tmp_path)
    original = state.probe_sample

    def older_voltage(port, **kwargs):
        result = original(port, **kwargs)
        result['timestamp'] = '2026-01-01T00:00:00+00:00'
        return result

    monkeypatch.setattr(state, 'probe_sample', older_voltage)
    saved = state.capture_record({'lab_port': 'lab', 'dut_port': 'dut', 'label': 'Separated windows'})
    assert any(error['stage'] == 'timing' for error in saved['capture_errors'])
    assert saved['observations'][0]['timestamp'] == '2026-01-01T00:00:00+00:00'
    assert saved['capture_span_s'] is not None


def test_saved_capture_reservation_prevents_polling_from_jumping_queue():
    import threading
    state = DashboardState()
    reserved = threading.Event()
    release = threading.Event()

    def owner():
        state._capture_owner = threading.get_ident()
        reserved.set()
        release.wait(2)
        state._capture_owner = None

    worker = threading.Thread(target=owner)
    worker.start()
    assert reserved.wait(1)
    try:
        with pytest.raises(BenchError, match='reserved'):
            with state.instrument_access():
                pytest.fail('Poll acquired a reserved instrument')
    finally:
        release.set()
        worker.join(2)
    with state.instrument_access():
        pass
