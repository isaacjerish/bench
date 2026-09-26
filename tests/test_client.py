from collections import deque

import pytest

from benchos.client import BenchClient
from benchos.protocol import BenchError, BenchProtocolError


class FakeSerial:
    replies = []
    instances = []

    def __init__(self, port, baudrate, **_kwargs):
        self.port = port
        self.baudrate = baudrate
        self.is_open = True
        self.writes = []
        self.queue = deque(self.replies)
        self.instances.append(self)

    def reset_input_buffer(self):
        pass

    def write(self, payload):
        self.writes.append(payload)

    def flush(self):
        pass

    def readline(self):
        return self.queue.popleft() if self.queue else b""

    def close(self):
        self.is_open = False


def test_client_ignores_boot_output_and_uses_physical_reply(monkeypatch):
    FakeSerial.replies = [b"ESP-ROM: booting\n", b"OK PONG\n",
                          b"OK VOLTAGE P1 3.271 RAW 2030 SAMPLES 32\n"]
    FakeSerial.instances = []
    monkeypatch.setattr("benchos.client.serial.Serial", FakeSerial)
    with BenchClient("/dev/fake", startup_delay=0) as client:
        result = client.measure_voltage("p1")
    assert result["voltage_v"] == 3.271
    assert FakeSerial.instances[0].writes == [b"PING\n", b"READ_ADC P1\n"]


def test_mismatched_probe_cannot_be_misattributed(monkeypatch):
    FakeSerial.replies = [b"OK PONG\n", b"OK DIGITAL P2 HIGH\n"]
    monkeypatch.setattr("benchos.client.serial.Serial", FakeSerial)
    with BenchClient("/dev/fake", startup_delay=0) as client:
        with pytest.raises(BenchProtocolError, match="mismatch"):
            client.read_digital("P1")


def test_voltage_pair_has_order_and_reports_non_simultaneity(monkeypatch):
    FakeSerial.replies = [b"OK PONG\n",
                          b"OK VOLTAGE P1 3.250 RAW 2010 SAMPLES 32\n",
                          b"OK VOLTAGE P2 0.025 RAW 18 SAMPLES 32\n"]
    FakeSerial.instances = []
    monkeypatch.setattr("benchos.client.serial.Serial", FakeSerial)
    with BenchClient("/dev/fake", startup_delay=0) as client:
        result = client.measure_voltage_pair()
    assert result["simultaneous"] is False
    assert [item["probe"] for item in result["readings"]] == ["P1", "P2"]
    assert [item["declared_net"] for item in result["readings"]] == ["LIGHT_SENSE", "MPU_VCC"]
    assert result["wiring_source"] == "user_declared"
    assert [item["voltage_v"] for item in result["readings"]] == [3.25, 0.025]
    assert FakeSerial.instances[0].writes == [b"PING\n", b"READ_ADC P1\n", b"READ_ADC P2\n"]


def test_auto_discovery_rescans_after_connection_loss(monkeypatch):
    from benchos.protocol import BenchError

    FakeSerial.replies = [b"OK PONG\n"]
    FakeSerial.instances = []
    discovered = iter([["/dev/old"], ["/dev/new"]])
    monkeypatch.setattr("benchos.client.serial.Serial", FakeSerial)
    monkeypatch.setattr("benchos.client.ports.candidate_ports", lambda: next(discovered))
    client = BenchClient(startup_delay=0, timeout=0.01)
    client.connect()
    with pytest.raises(BenchError, match="Timed out"):
        client.read_digital("P1")
    FakeSerial.replies = [b"OK PONG\n", b"OK DIGITAL P1 LOW\n"]
    assert client.read_digital("P1")["state"] == "LOW"
    assert [instance.port for instance in FakeSerial.instances] == ["/dev/old", "/dev/new"]
    client.close()


def test_bus_monitor_refuses_unwired_inputs(monkeypatch):
    monkeypatch.setattr("benchos.client.describe_harness", lambda: {"bus_monitor": {"state": "pending"}})
    client = BenchClient("/dev/fake", startup_delay=0)
    with pytest.raises(BenchError, match="not declared connected"):
        client.measure_bus_activity()
