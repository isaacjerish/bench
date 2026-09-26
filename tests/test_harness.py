"""A declared connection must never be misrepresented as observed wiring."""

from benchos.harness import describe_harness


def test_harness_separates_declared_from_measured():
    result = describe_harness()
    assert result["source"] == "user_declared"
    assert result["physically_verified"] is False
    assert result["probes"]["P1"]["net"] == "LIGHT_SENSE"
    assert result["probes"]["P2"]["state"] == "connected"
    assert result["probes"]["P2"]["net"] == "MPU_VCC"
