import json

import pytest

from benchos.records import list_records, read_record


def test_saved_channels_keep_original_nets_and_missing_values(tmp_path):
    path = tmp_path / "capture.json"
    path.write_text(json.dumps({"timestamp": "2026-09-26T19:00:00+00:00",
        "physical": {"readings": [{"probe": "P1", "declared_net": "ORIGINAL_NET", "voltage_v": 1.2}]},
        "capture": {"window_ms": 2000, "taps": {
            "D1": {"usable_for_diagnosis": True, "declared_net": "DATA", "end": "HIGH", "edges": 20},
            "D3": {"usable_for_diagnosis": False, "edges": 99999}}}}))
    record = read_record("capture.json", tmp_path)
    assert record["id"] == "capture.json"
    assert list_records(tmp_path)["records"][0]["id"] == "capture.json"
    assert record["is_live"] is False
    assert record["observations"][0]["net"] == "ORIGINAL_NET"
    assert record["observations"][-1]["value"] == 10
    assert not any(row["channel"] == "D3" for row in record["observations"])
    assert record["harness_snapshot_available"] is False


def test_capture_viewer_refuses_outside_paths_and_symlinks(tmp_path):
    root = tmp_path / "records"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text('{"private": true}')
    (root / "link.json").symlink_to(outside)
    for name in ("../outside.json", str(outside), "link.json", ".hidden.json"):
        with pytest.raises(ValueError):
            read_record(name, root)


def test_invalid_files_do_not_break_inventory(tmp_path):
    (tmp_path / "bad.json").write_text("not JSON")
    (tmp_path / "huge.json").write_text(" " * 512001)
    result = list_records(tmp_path)
    assert result["records"] == []
    assert result["skipped"] == 2
