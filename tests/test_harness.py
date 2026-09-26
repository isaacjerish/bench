"""A declared connection must never be misrepresented as observed wiring."""

import pytest

from benchos.harness import HARNESS_FILE, describe_harness, update_probe_declarations


def test_harness_separates_declared_from_measured():
    result = describe_harness()
    assert result["source"] == "user_declared"
    assert result["physically_verified"] is False
    assert result["probes"]["P1"]["net"] == "LIGHT_SENSE"
    assert result["probes"]["P2"]["state"] == "connected"
    assert result["probes"]["P2"]["net"] == "MPU_VCC"
    assert result["bus_monitor"]["state"] == "connected"


def test_probe_declaration_updates_only_selected_fields(tmp_path):
    path = tmp_path / "current.yaml"
    path.write_text(HARNESS_FILE.read_text())
    result = update_probe_declarations({"P1": {"state": "connected", "net": "NEW_SENSOR"},
                                        "P2": {"state": "disconnected", "net": "MPU_VCC"}}, path)
    assert result["probes"]["P1"]["net"] == "NEW_SENSOR"
    assert result["probes"]["P1"]["adc"] == "S3 IO1 via 10k/10k divider"
    assert result["probes"]["P2"]["state"] == "disconnected"
    assert result["bus_monitor"]["state"] == "connected"
    assert result["source"] == "user_declared"


def test_invalid_declaration_cannot_change_file(tmp_path):
    path = tmp_path / "current.yaml"
    original = HARNESS_FILE.read_text()
    path.write_text(original)
    with pytest.raises(ValueError, match="uppercase"):
        update_probe_declarations({"P1": {"state": "connected", "net": "bad label"},
                                   "P2": {"state": "connected", "net": "MPU_VCC"}}, path)
    assert path.read_text() == original
