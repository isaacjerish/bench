from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from benchos.activity import compare_activity, validate_activity_rules

BASE = datetime(2026, 9, 26, 20, tzinfo=timezone.utc)
RULES = [dict(tap='D3', field='alert', equals=1, min_transitions_per_s=3, max_transitions_per_s=5),
         dict(tap='D3', field='alert', equals=0, min_transitions_per_s=0, max_transitions_per_s=0)]


def stamp(offset):
    return (BASE + timedelta(seconds=offset)).isoformat()


def capture(edges=8):
    return dict(command_started_at=stamp(1), command_ended_at=stamp(3.01), window_ms=2000,
                taps={'D3': dict(edges=edges, usable_for_diagnosis=True, declared_net='ALARM')})


def reports(state=1):
    return [dict(timestamp=stamp(t), line=f'alert={state}') for t in (.7, 1.2, 1.7, 2.2, 2.7, 3.2)]


@pytest.mark.parametrize('state,edges,expected', [(1,8,'pass'), (1,0,'fail'), (1,40,'fail'),
                                                (0,0,'pass'), (0,8,'fail')])
def test_output_must_match_the_reported_condition(state, edges, expected):
    result = compare_activity(capture(edges), reports(state), RULES)
    assert result['state'] == expected
    assert result['checks'][0]['observed_transitions_per_s'] == edges / 2


@pytest.mark.parametrize('issue', ['changed', 'no_before', 'no_after', 'gap', 'nan', 'bad_time',
                                   'late_response', 'short_response', 'disconnected', 'serial_error', 'unknown_state'])
def test_uncertain_or_changed_conditions_never_pass(issue):
    sample, events = capture(), reports()
    if issue == 'changed': events[2]['line'] = 'alert=0'
    if issue == 'no_before': events = events[1:]
    if issue == 'no_after': events = events[:-1]
    if issue == 'gap': events = [events[0], events[-1]]
    if issue == 'nan': events[-1]['line'] = 'alert=nan'
    if issue == 'bad_time': sample['command_started_at'] = None
    if issue == 'late_response': sample['command_ended_at'] = stamp(5)
    if issue == 'short_response': sample['command_ended_at'] = stamp(1.2)
    if issue == 'disconnected': sample['taps']['D3']['usable_for_diagnosis'] = False
    if issue == 'serial_error': sample['dut_stream_error'] = 'Disconnected'
    if issue == 'unknown_state': events = reports(2)
    assert compare_activity(sample, events, RULES)['state'] == 'unverified'


def test_rules_reject_ambiguous_conditions_and_bad_bounds():
    validate_activity_rules(RULES, {'D3': {}})
    with pytest.raises(ValueError, match='Duplicate'):
        validate_activity_rules([RULES[0], RULES[0]], {'D3': {}})
    for key, value in [('tap', []), ('equals', float('nan')), ('min_transitions_per_s', 6),
                       ('max_transitions_per_s', True)]:
        rules = deepcopy(RULES)
        rules[0][key] = value
        with pytest.raises(ValueError): validate_activity_rules(rules, {'D3': {}})


def test_capture_uses_frozen_rules_and_marks_missing_serial_unverified(monkeypatch):
    from benchos.dashboard import DashboardState
    frozen = {'digital_taps': {'D3': {'state': 'connected'}}, 'activity_checks': RULES}

    class Client:
        def __init__(self, *_args, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def measure_digital_taps(self, duration, *, tap_declarations):
            assert tap_declarations == frozen['digital_taps']
            return capture()

    monkeypatch.setattr('benchos.dashboard.candidate_ports', lambda: ['lab'])
    monkeypatch.setattr('benchos.dashboard.BenchClient', Client)
    result = DashboardState().bus_sample('lab', 2000, digital_taps=True, harness=frozen)
    assert result['activity_checks']['state'] == 'unverified'
    assert result['activity_checks']['rules'] == RULES
    assert result['condition_serial_events'] == []


def test_serial_fragments_are_joined_and_bracket_the_physical_window(monkeypatch):
    import time
    from contextlib import nullcontext
    from benchos.dashboard import DashboardState

    class Device:
        def __init__(self, *_args, **_kwargs): self.index = 0
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def reset_input_buffer(self): pass
        def read_until(self, *_args):
            time.sleep(0.02)
            self.index += 1
            return b'PARCEL alert=' if self.index % 2 else b'0\n'

    class Client:
        def __init__(self, *_args, **_kwargs): pass
        def __enter__(self):
            time.sleep(0.15)
            return self
        def __exit__(self, *_args): pass
        def measure_digital_taps(self, duration, **_kwargs):
            time.sleep(duration / 1000)
            return {'window_ms': duration, 'taps': {'D3': {'edges': 0, 'usable_for_diagnosis': True}}}

    monkeypatch.setattr('benchos.dashboard.candidate_ports', lambda: ['lab', 'dut'])
    monkeypatch.setattr('benchos.dashboard.BenchClient', Client)
    monkeypatch.setattr('benchos.dashboard.serial.Serial', Device)
    monkeypatch.setattr('benchos.dashboard.SerialPortLock', lambda *_: nullcontext())
    result = DashboardState().bus_sample('lab', 100, 'dut', digital_taps=True,
        harness={'digital_taps': {}, 'activity_checks': RULES})
    assert result['dut_stream_open_during_capture'] is True
    assert result['activity_checks']['state'] == 'pass'
    assert all(event['line'] == 'PARCEL alert=0' for event in result['condition_serial_events'])
    assert result['condition_serial_events'][0]['timestamp'] < result['command_started_at']
    assert result['condition_serial_events'][-1]['timestamp'] > result['command_ended_at']
