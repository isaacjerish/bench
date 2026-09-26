"""Compare physical edge counts with a stable, bracketed DUT state report."""
from __future__ import annotations

import math
import re
from datetime import datetime

FIELD_RE = re.compile(r'(?:^|\s)([A-Za-z][A-Za-z0-9_]{0,31})=(\S+)')


def validate_activity_rules(rules, taps: dict) -> list[dict]:
    if not isinstance(rules, list) or len(rules) > 16:
        raise ValueError('activity_checks must contain at most 16 rules')
    seen = set()
    for rule in rules:
        required = {'tap', 'field', 'equals', 'min_transitions_per_s', 'max_transitions_per_s'}
        if not isinstance(rule, dict) or set(rule) != required:
            raise ValueError('Activity rule needs tap, field, equals, and transition bounds')
        if not isinstance(rule['tap'], str) or rule['tap'] not in taps or not isinstance(rule['field'], str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,31}', rule['field']):
            raise ValueError('Activity rule needs a declared tap and valid serial field')
        for key in ('equals', 'min_transitions_per_s', 'max_transitions_per_s'):
            value = rule[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('Activity rule values must be finite numbers')
        if not 0 <= rule['min_transitions_per_s'] <= rule['max_transitions_per_s'] <= 10000000:
            raise ValueError('Invalid activity transition bounds')
        key = (rule['tap'], rule['field'], rule['equals'])
        if key in seen:
            raise ValueError('Duplicate activity condition')
        seen.add(key)
    return rules


def _time(value) -> float:
    if not isinstance(value, str):
        raise ValueError('Timestamp must be text')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamp needs a timezone')
    return parsed.timestamp()


def compare_activity(capture: dict, events: list[dict], rules: list[dict], max_gap_s: float = 1.5) -> dict:
    """A changed/missing/stale condition is unverified, never a passing skip.

    Host timestamps bracket the command interval, which encloses the physical
    counter window. Reports cannot establish unobserved transitions between
    serial messages, or prove that the requested state is itself correct.
    """
    groups = {}
    for rule in rules:
        groups.setdefault((rule['tap'], rule['field']), []).append(rule)
    checks = []
    for (name, field), alternatives in groups.items():
        tap = capture.get('taps', {}).get(name, {})
        item = {'tap': name, 'field': field, 'net': tap.get('declared_net'), 'state': 'unverified'}
        checks.append(item)
        if not tap.get('usable_for_diagnosis'):
            item['detail'] = 'Tap connection is unconfirmed or was not captured.'
            continue
        if capture.get('dut_stream_error'):
            item['detail'] = 'DUT serial observation failed: ' + capture['dut_stream_error']
            continue
        try:
            start = _time(capture['command_started_at'])
            end = _time(capture['command_ended_at'])
            window_ms = capture['window_ms']
            if isinstance(window_ms, bool) or not isinstance(window_ms, int) or not 100 <= window_ms <= 2100:
                raise ValueError('Invalid or delayed capture interval')
            # A response that returned substantially later than its advertised
            # counter window cannot establish when that window actually ran.
            if not window_ms / 1000 - 0.05 <= end - start <= window_ms / 1000 + 1.0:
                raise ValueError('Digital response timing does not match the counter window')
            reports = []
            for event in events:
                fields = dict(FIELD_RE.findall(event.get('line', '')))
                if field not in fields:
                    continue
                when = _time(event['timestamp'])
                if start - max_gap_s <= when <= end + max_gap_s:
                    value = float(fields[field])
                    if not math.isfinite(value):
                        raise ValueError('Malformed condition report near the capture')
                    reports.append((when, value, event['line']))
            reports.sort(key=lambda row: row[0])
            before = [row for row in reports if row[0] <= start]
            after = [row for row in reports if row[0] >= end]
            if not before or not after:
                raise ValueError('Need fresh condition reports before and after the counter window')
            bracket = [row for row in reports if before[-1][0] <= row[0] <= after[0][0]]
            if any(b[0] - a[0] > max_gap_s for a, b in zip(bracket, bracket[1:])):
                raise ValueError('Condition reports have a gap across the capture')
            state_value = bracket[0][1]
            if any(row[1] != state_value for row in bracket):
                raise ValueError('DUT state changed during capture; hold the condition steady and repeat')
            rule = next((rule for rule in alternatives if rule['equals'] == state_value), None)
            if rule is None:
                raise ValueError('No expectation is declared for this reported state')
            edges = tap['edges']
            if isinstance(edges, bool) or not isinstance(edges, int) or edges < 0:
                raise ValueError('Invalid physical edge count')
            rate = edges * 1000 / window_ms
            lo, hi = rule['min_transitions_per_s'], rule['max_transitions_per_s']
            item.update(state='pass' if lo <= rate <= hi else 'fail',
                        reported_state=state_value, observed_transitions_per_s=round(rate, 3),
                        minimum=lo, maximum=hi, reports=[row[2] for row in bracket],
                        detail=f'DUT reported {field}={state_value:g}; {name} observed {rate:.2f} transitions/s, expected {lo:g}–{hi:g}/s.')
        except (KeyError, ValueError, TypeError, OverflowError) as exc:
            item['detail'] = str(exc)
    state = ('fail' if any(item['state'] == 'fail' for item in checks) else
             'unverified' if not checks or any(item['state'] == 'unverified' for item in checks) else 'pass')
    return {'state': state, 'checks': checks, 'rules': rules,
            'scope': 'Physical transitions conditioned on bracketed DUT claims. Does not prove the load works or that the requested state is correct.'}
