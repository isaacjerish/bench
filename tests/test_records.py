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


def test_identical_copies_share_one_choice_but_both_remain_readable(tmp_path):
    contents = json.dumps({'physical': {'readings': [{'probe': 'P1', 'voltage_v': 1.2}]}})
    (tmp_path / 'saved.json').write_text(contents)
    (tmp_path / 'dashboard').mkdir()
    (tmp_path / 'dashboard' / 'original.json').write_text(contents)
    result = list_records(tmp_path)
    assert len(result['records']) == 1
    entry = result['records'][0]
    assert set([entry['id'], *entry['aliases']]) == {'saved.json', 'dashboard/original.json'}
    assert read_record('saved.json', tmp_path)['observations'] == read_record('dashboard/original.json', tmp_path)['observations']
