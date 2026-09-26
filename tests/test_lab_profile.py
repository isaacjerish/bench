import pytest

from benchos.client import BenchClient
from benchos.harness import describe_harness
from benchos.protocol import BenchError, parse_response
from pathlib import Path


def test_info_identifies_series_profile_without_breaking_legacy():
    result = parse_response('OK INFO BenchOS-S3 v0.3 PROBES 3 ADC_SAMPLES 32 PROFILE series-taps-v1')
    assert result['profile'] == 'series-taps-v1'
    assert 'profile' not in parse_response('OK INFO BenchOS-S3 v0.2 PROBES 3 ADC_SAMPLES 32')


def test_new_harness_is_pending_and_uses_no_i2c():
    root = Path(__file__).resolve().parents[1]
    profile = describe_harness(root / 'harness/profiles/parcel_guard.yaml')
    assert profile['lab']['required_profile'] == 'series-taps-v1'
    assert all(item['state'] == 'pending' for item in profile['probes'].values())
    assert profile['bus_monitor']['state'] == 'disconnected'
    assert set(profile['dut_pins']) == {'IO1', 'IO2', 'IO20'}


@pytest.mark.parametrize('reported', [None, 'legacy-dividers-v1'])
def test_wrong_lab_profile_refuses_measurement_before_adc(monkeypatch, reported):
    class Serial:
        is_open = True
        def reset_input_buffer(self): pass
        def close(self): self.is_open = False

    monkeypatch.setattr('benchos.client.describe_harness', lambda: {'lab': {'required_profile': 'series-taps-v1'}})
    monkeypatch.setattr('benchos.client.SerialPortLock', lambda *_a, **_k: type('Lock', (), {'acquire': lambda self: None, 'release': lambda self: None})())
    monkeypatch.setattr('benchos.client.serial.Serial', lambda *_a, **_k: Serial())
    commands = []
    client = BenchClient('/dev/fake', startup_delay=0)

    def exchange(command):
        commands.append(command)
        return {'kind': 'pong'} if command == 'PING' else {'kind': 'info', 'profile': reported}

    monkeypatch.setattr(client, '_exchange', exchange)
    with pytest.raises(BenchError, match='profile mismatch'):
        client.measure_voltage('P1')
    assert commands == ['PING', 'INFO']
