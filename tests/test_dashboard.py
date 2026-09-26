"""Dashboard verdicts and loopback API must distinguish evidence from claims."""

import json
import threading
from urllib.request import urlopen

import pytest

from benchos.dashboard import DashboardServer, DashboardState, IMU_LINE, diagnose, read_imu_report
from benchos.protocol import BenchError


def test_light_disagreement_uses_physical_reading():
    result = diagnose("light", {"voltage_v": 2.207}, {"reported_voltage_v": 0.0})
    assert result["state"] == "fail"
    assert "2.21 V" in result["detail"]


def test_servo_wrong_frequency_is_a_fault():
    result = diagnose("servo", {"frequency_hz": 312, "edges": 312, "pulse_us": 1500}, None)
    assert result["state"] == "fail"
    assert "Frequency" in result["title"]


def test_imu_dut_report_is_not_physical_pass():
    result = diagnose("imu", None, {"magnitude_g": 1.0})
    assert result["state"] == "unverified"


def test_imu_power_fault_is_physical_but_motion_is_not():
    failed = diagnose("imu", {"voltage_v": 0.02}, None)
    assert failed["state"] == "fail"
    assert failed["evidence"] == "physical"
    healthy = diagnose("imu", {"voltage_v": 3.23}, {"magnitude_g": 1.0})
    assert healthy["state"] == "unverified"
    assert healthy["evidence"] == "mixed"


def test_imu_link_failure_keeps_power_and_dut_error_separate():
    result = diagnose("imu", {"voltage_v": 3.23}, None,
                      [{"device": "C6", "message": "C6 reported IMU_ERROR no_device_at_0x68_or_0x69"}])
    assert result["state"] == "fail"
    assert result["evidence"] == "mixed"
    assert "3.23 V" in result["detail"]
    assert "no_device" in result["detail"]


def test_imu_saturated_axis_is_flagged():
    result = diagnose("imu", None, {"magnitude_g": 2.2, "saturated_axes": ["z"]})
    assert result["state"] == "fail"
    assert "z" in result["detail"]


def test_imu_stream_line_carries_chip_id():
    match = IMU_LINE.fullmatch("IMU_ACCEL_G x=0.120 y=-0.080 z=0.990 id=0x71")
    assert match is not None
    assert match.group(4) == "71"


def test_imu_read_error_is_reported_explicitly(monkeypatch):
    from contextlib import nullcontext

    class FakeSerial:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def readline(self):
            return b"IMU_ERROR read_failed\n"

    monkeypatch.setattr("benchos.dashboard.SerialPortLock", lambda _port: nullcontext())
    monkeypatch.setattr("benchos.dashboard.serial.Serial", FakeSerial)
    with pytest.raises(BenchError, match="read_failed"):
        read_imu_report("/dev/fake", timeout_s=0.1)


def test_dashboard_serves_assets_and_snapshot_without_hardware():
    state = DashboardState()
    try:
        server = DashboardServer(("127.0.0.1", 0), state)
    except PermissionError:
        pytest.skip("Local socket binding is disabled by this sandbox")
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(base + "/") as response:
            assert b"Benchy" in response.read()
        with urlopen(base + "/app.js") as response:
            assert b"const MODES" in response.read()
        with urlopen(base + "/scene-light.png") as response:
            assert response.headers["Content-Type"] == "image/png"
            assert response.read(8) == b"\x89PNG\r\n\x1a\n"
        with urlopen(base + "/api/harness") as response:
            declaration = json.load(response)
            assert declaration["source"] == "user_declared"
            assert declaration["probes"]["P2"]["net"] == "MPU_VCC"
        with urlopen(base + "/api/snapshot?mode=light") as response:
            data = json.load(response)
            assert data["diagnosis"]["state"] == "unknown"
            assert data["physical"] is None
    finally:
        server.shutdown()
        server.server_close()
        state.close()
        worker.join(timeout=2)
