"""Dashboard verdicts and loopback API must distinguish evidence from claims."""

import json
import threading
from urllib.request import urlopen

import pytest

from benchos.dashboard import DashboardServer, DashboardState, IMU_LINE, diagnose


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


def test_imu_stream_line_carries_chip_id():
    match = IMU_LINE.fullmatch("IMU_ACCEL_G x=0.120 y=-0.080 z=0.990 id=0x71")
    assert match is not None
    assert match.group(4) == "71"


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
            assert b"BenchOS" in response.read()
        with urlopen(base + "/app.js") as response:
            assert b"const MODES" in response.read()
        with urlopen(base + "/api/snapshot?mode=light") as response:
            data = json.load(response)
            assert data["diagnosis"]["state"] == "unknown"
            assert data["physical"] is None
    finally:
        server.shutdown()
        server.server_close()
        state.close()
        worker.join(timeout=2)
