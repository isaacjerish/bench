import pytest

from benchos.digital import describe_capture


def capture(first, second, state="connected"):
    raw = {"taps": {"D1": {"start": "HIGH", "end": "HIGH", "edges": first},
                    "D3": {"start": "HIGH", "end": "HIGH", "edges": second}}}
    declared = {"D1": {"state": "connected", "net": "DATA", "endpoint": "receiver"},
                "D3": {"state": state, "net": "DATA", "endpoint": "source"}}
    return describe_capture(raw, declared)


@pytest.mark.parametrize("first,second,expected", [
    (10, 0, "activity_mismatch"), (0, 10, "activity_mismatch"),
    (0, 0, "static"), (10, 9, "activity_at_both")])
def test_endpoint_activity_is_not_continuity(first, second, expected):
    result = capture(first, second)
    assert result["comparisons"][0]["assessment"] == expected
    assert result["comparisons"][0]["continuity_verified"] is False
    assert result["continuity_verified"] is False


@pytest.mark.parametrize("state", ["pending", "wired_unverified", "disconnected"])
def test_floating_unconfirmed_inputs_cannot_create_fault_or_pass(state):
    result = capture(10, 0, state)
    assert result["comparisons"][0]["assessment"] == "unverified"
    assert result["taps"]["D3"]["usable_for_diagnosis"] is False
    assert result["taps"]["D3"]["declared_net"] is None
