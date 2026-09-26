"""Dashboard verdicts and loopback API must distinguish evidence from claims."""

import json
import threading
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

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


def test_probe_explorer_preserves_order_and_declared_source(monkeypatch):
    class FakeClient:
        def __init__(self, _port):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def measure_voltage_pair(self, **_kwargs):
            return {"simultaneous": False, "wiring_source": "user_declared",
                    "readings": [{"probe": "P1", "voltage_v": 2.1, "declared_net": "LIGHT_SENSE"},
                                 {"probe": "P2", "voltage_v": 3.2, "declared_net": "MPU_VCC"}]}

        def measure_voltage(self, probe):
            assert probe == "P3"
            return {"probe": probe, "voltage_v": 0.4}

        def read_digital(self, probe):
            return {"state": "HIGH" if probe == "P2" else "LOW"}

    monkeypatch.setattr("benchos.dashboard.candidate_ports", lambda: ["/dev/fake"])
    monkeypatch.setattr("benchos.dashboard.BenchClient", FakeClient)
    sample = DashboardState().probe_sample("/dev/fake")
    assert sample["source"] == "s3_physical"
    assert sample["simultaneous"] is False
    assert [row["probe"] for row in sample["readings"]] == ["P1", "P2", "P3"]
    assert sample["readings"][2]["declared_net"] == "WATER_SENSE"
    assert sample["digital_states"] == {"P1": "LOW", "P2": "HIGH", "P3": "LOW"}


def test_bus_sample_reports_raw_activity_without_claiming_decode(monkeypatch):
    class FakeClient:
        def __init__(self, _port, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def measure_bus_activity(self, duration_ms):
            return {"window_ms": duration_ms, "sda": {"edges": 12}, "scl": {"edges": 48},
                    "edge_counts_approximate": True}

    monkeypatch.setattr("benchos.dashboard.candidate_ports", lambda: ["/dev/fake"])
    monkeypatch.setattr("benchos.dashboard.BenchClient", FakeClient)
    result = DashboardState().bus_sample("/dev/fake", 1000)
    assert result["scl"]["edges"] == 48
    assert result["source"] == "s3_physical"
    assert result["decoded_transactions"] is False


def test_dashboard_selects_five_input_capture_without_dut(monkeypatch):
    class FakeClient:
        def __init__(self, _port, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def measure_digital_taps(self, duration_ms):
            return {"kind": "digital_taps", "window_ms": duration_ms,
                    "taps": {"D5": {"edges": 4}}, "comparisons": []}

    monkeypatch.setattr("benchos.dashboard.candidate_ports", lambda: ["/dev/fake"])
    monkeypatch.setattr("benchos.dashboard.BenchClient", FakeClient)
    result = DashboardState().bus_sample("/dev/fake", 1000, digital_taps=True)
    assert result["kind"] == "digital_taps"
    assert result["taps"]["D5"]["edges"] == 4
    assert result["source"] == "s3_physical"
    assert result["decoded_transactions"] is False
    assert result["dut_stream_open_during_capture"] is False


def test_dashboard_serves_assets_and_snapshot_without_hardware(monkeypatch):
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
            assert b"const names = ['P1', 'P2', 'P3']" in response.read()
        with urlopen(base + "/workspace-model.js") as response:
            assert b"compareObservations" in response.read()
        with urlopen(base + "/records.js") as response:
            assert b"/api/records" in response.read()
        with urlopen(base + "/api/records") as response:
            records = json.load(response)
            assert records["is_live"] is False
            assert records["records"]
            record_id = records["records"][0]["id"]
        with urlopen(base + "/api/records?id=" + quote(record_id)) as response:
            record = json.load(response)
            assert record["id"] == record_id
            assert record["is_live"] is False
        with pytest.raises(HTTPError) as blocked:
            urlopen(base + "/api/records?id=../.env")
        assert blocked.value.code == 400
        capture_body = json.dumps({"lab_port": "/dev/not-a-device", "label": "Check"}).encode()
        with pytest.raises(HTTPError) as blocked:
            urlopen(Request(base + "/api/records", data=capture_body,
                            headers={"Content-Type": "application/json"}, method="POST"))
        assert blocked.value.code == 403
        with pytest.raises(HTTPError) as blocked:
            urlopen(Request(base + "/api/records", data=capture_body,
                            headers={"Content-Type": "application/json", "X-Benchy-Local": "1"}, method="POST"))
        assert blocked.value.code == 400
        monkeypatch.setattr(state, "capture_record", lambda _data: {"id": "dashboard/test.json", "is_live": False})
        with urlopen(Request(base + "/api/records", data=capture_body,
                             headers={"Content-Type": "application/json", "X-Benchy-Local": "1"}, method="POST")) as response:
            assert response.status == 201
            assert json.load(response)["is_live"] is False
        with urlopen(base + "/api/harness") as response:
            declaration = json.load(response)
            assert declaration["source"] == "user_declared"
            assert declaration["probes"]["P2"]["net"] == "MPU_VCC"
        with urlopen(base + "/api/code") as response:
            inventory = json.load(response)
            assert inventory["source"] == "local_files"
            assert inventory["flashed_firmware_verified"] is False
            assert any(item["path"] == "dut_examples/plant_sentinel/plant_sentinel.ino" for item in inventory["files"])
            assert not any(item["path"] == "dut_examples/led_demo/led_demo.ino" for item in inventory["files"])
        with urlopen(base + "/api/source?path=" + quote("dut_examples/plant_sentinel/plant_sentinel.ino")) as response:
            source = json.load(response)
            assert "SENTINEL build=" in source["text"]
        with pytest.raises(HTTPError) as blocked:
            urlopen(base + "/api/source?path=../.env")
        assert blocked.value.code == 400
        with pytest.raises(HTTPError) as blocked:
            urlopen(base + "/api/source?path=" + quote("dut_examples/led_demo/led_demo.ino"))
        assert blocked.value.code == 400
        with pytest.raises(HTTPError) as blocked:
            urlopen(base + "/api/serial?port=/dev/not-a-device")
        assert blocked.value.code == 400
        with pytest.raises(HTTPError) as blocked:
            urlopen(base + "/api/taps?lab_port=/dev/not-a-device")
        assert blocked.value.code == 400
        with pytest.raises(HTTPError) as blocked:
            urlopen(base + "/api/probes?lab_port=/dev/not-a-device")
        assert blocked.value.code == 400
        with pytest.raises(HTTPError) as blocked:
            urlopen(base + "/api/bus?lab_port=/dev/not-a-device")
        assert blocked.value.code == 400
        declaration_body = json.dumps({"P1": {"state": "connected", "net": "LIGHT_SENSE"},
                                       "P2": {"state": "connected", "net": "MPU_VCC"}}).encode()
        request = Request(base + "/api/harness/probes", data=declaration_body,
                          headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(HTTPError) as blocked:
            urlopen(request)
        assert blocked.value.code == 403
        monkeypatch.setattr("benchos.dashboard.update_probe_declarations",
                            lambda _data: {"source": "user_declared", "probes": {}})
        request = Request(base + "/api/harness/probes", data=declaration_body,
                          headers={"Content-Type": "application/json", "X-Benchy-Local": "1"}, method="POST")
        with urlopen(request) as response:
            assert json.load(response)["source"] == "user_declared"
        with urlopen(base + "/api/snapshot?mode=light") as response:
            data = json.load(response)
            assert data["diagnosis"]["state"] == "unknown"
            assert data["physical"] is None
    finally:
        server.shutdown()
        server.server_close()
        state.close()
        worker.join(timeout=2)
