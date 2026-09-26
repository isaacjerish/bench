import pytest

from benchos.postflash import validate_postflash, observe_marker, verify_postflash


def test_marker_requires_exact_token_and_follows_enrolled_usb(tmp_path, monkeypatch):
    lines = iter([b"build=test-wrong\n", b"REPORT build=test value=2\n"])
    class Device:
        def __init__(self, port, *_args, **_kwargs):
            assert port == "/dev/renumbered"
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            pass
        def readline(self):
            return next(lines)
    monkeypatch.setattr("benchos.postflash.serial.Serial", Device)
    monkeypatch.setattr("benchos.serial_lock.tempfile.gettempdir", lambda: str(tmp_path))
    result = observe_marker("DUT", validate_postflash({"serial_marker": "build=test"}),
                            lambda: [{"device": "/dev/renumbered", "serial_number": "DUT"}])
    assert result["state"] == "observed"
    assert result["line"] == "REPORT build=test value=2"
    assert result["binary_identity_verified"] is False


def test_invalid_postflash_spec_rejected_before_upload():
    with pytest.raises(ValueError, match="token"):
        validate_postflash({"serial_marker": "build=test\n"})
    with pytest.raises(ValueError, match="1–15"):
        validate_postflash({"serial_marker": "build=test", "timeout_s": 1000})


def test_present_marker_cannot_hide_bad_supply(monkeypatch):
    monkeypatch.setattr("benchos.postflash.observe_marker", lambda *_: {"state": "observed"})
    monkeypatch.setattr("benchos.telemetry.check_live_declared_telemetry", lambda *_: {
        "state": "pass", "physical": {"readings": [
            {"probe": "P2", "declared_state": "connected", "voltage_v": 0.2}]}})
    harness = {"dut": {"usb_serial_number": "DUT"}, "probes": {
        "P2": {"expected_min_v": 3.0, "expected_max_v": 3.3}}}
    result = verify_postflash(harness, {"check_telemetry": True}, lambda: [])
    assert result["state"] == "fail"
    assert result["probe_ranges"][0]["voltage_v"] == 0.2
