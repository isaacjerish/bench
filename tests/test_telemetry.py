"""Cross-source checks must catch a false DUT claim without inventing evidence."""

from benchos.telemetry import compare_declared_fields


def test_independent_water_probe_catches_false_zero():
    probes = {"timestamp": "2026-09-26T18:00:00+00:00",
              "readings": [{"probe": "P3", "voltage_v": 0.83,
                            "declared_state": "connected", "declared_net": "WATER_SENSE"}]}
    rule = [{"probe": "P3", "field": "water_mv", "scale_to_v": 0.001,
             "max_delta_v": 0.45}]
    events = [{"timestamp": "2026-09-26T18:00:01+00:00",
               "line": "SENTINEL water_mv=0 alert=1"}]
    result = compare_declared_fields(probes, events, rule)
    assert result["state"] == "fail"
    assert result["checks"][0]["physical_v"] == 0.83
    assert result["checks"][0]["dut_claim_v"] == 0
    assert result["checks"][0]["pass"] is False


def test_stale_report_is_unverified():
    probes = {"timestamp": "2026-09-26T18:00:20+00:00",
              "readings": [{"probe": "P3", "voltage_v": 0.83,
                            "declared_state": "connected"}]}
    events = [{"timestamp": "2026-09-26T18:00:01+00:00", "line": "water_mv=0"}]
    result = compare_declared_fields(probes, events,
                                     [{"probe": "P3", "field": "water_mv",
                                       "scale_to_v": 0.001, "max_delta_v": 0.45}])
    assert result["state"] == "unverified"
