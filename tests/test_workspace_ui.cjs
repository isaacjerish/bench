const test = require('node:test');
const assert = require('node:assert/strict');
const model = require('../benchos/dashboard_ui/workspace-model.js');

test('old matched readings cannot remain fresh indefinitely', () => {
  const now = Date.parse('2026-09-26T20:00:00Z');
  assert.equal(model.isFresh('2026-09-26T19:59:50Z', 15000, now), true);
  assert.equal(model.isFresh('2026-09-26T19:59:40Z', 15000, now), false);
  assert.equal(model.isFresh('invalid', 15000, now), false);
  assert.equal(model.isFresh('2026-09-26T20:02:00Z', 15000, now), false);
});

test('missing or differently assigned channels do not turn into numeric deltas', () => {
  const a = [{channel:'P1', net:'OLD', metric:'voltage', unit:'V', value:1}];
  const b = [{channel:'P1', net:'NEW', metric:'voltage', unit:'V', value:3}];
  const result = model.compareObservations(a, b);
  assert.equal(result.length, 2);
  assert.ok(result.every(row => row.delta === null));
  assert.ok(result.some(row => row.after === null));
});

test('comparable saved observations retain zero as an actual measurement', () => {
  const a = [{channel:'D5', net:'OUTPUT', metric:'transitions', unit:'/s', value:5000}];
  const b = [{channel:'D5', net:'OUTPUT', metric:'transitions', unit:'/s', value:0}];
  assert.equal(model.compareObservations(a, b)[0].delta, -5000);
});

test('coverage counts only declared pins and confirmed probe assignments', () => {
  assert.deepEqual(model.coverage({probes:{P1:{state:'connected', net:'A'}}}), []);
  const rows = model.coverage({dut_pins:{IO1:{net:'A'}, IO2:{net:'B'}},
    probes:{P1:{state:'connected', net:'A'}}, digital_taps:{D1:{state:'pending', net:'B'}}});
  assert.deepEqual(rows.map(row => row.covered), [true, false]);
});

const voltageRule = {probe:'P1', field:'light_mv', scale_to_v:0.001, max_delta_v:0.45};
const sampleTime = '2026-09-26T20:00:05Z';
const voltageSample = {timestamp:sampleTime, readings:[{probe:'P1', voltage_v:2.7, declared_state:'connected'}]};
test('stable incorrect sensor reports still produce a mismatch', () => {
  const result = model.compareTelemetry(voltageSample, [{timestamp:sampleTime, line:'light_mv=0'}], [voltageRule]);
  assert.equal(result.comparisons[0].delta, 2.7);
});
test('moving sensor input does not become a false report disagreement', () => {
  const result = model.compareTelemetry(voltageSample, [
    {timestamp:'2026-09-26T20:00:04Z', line:'light_mv=2700'},
    {timestamp:'2026-09-26T20:00:06Z', line:'light_mv=500'}], [voltageRule]);
  assert.deepEqual(result.changing, ['light_mv']);
  assert.equal(result.comparisons.length, 0);
});
test('missing and malformed serial evidence cannot fall back to a passing value', () => {
  const good = {timestamp:sampleTime, line:'light_mv=2700'};
  for (const line of ['light_mv=nan', 'light_mv=0xA8C']) {
    const result = model.compareTelemetry(voltageSample, [good, {timestamp:sampleTime, line}], [voltageRule]);
    assert.deepEqual(result.missing, ['light_mv']);
  }
  const stale = model.compareTelemetry(voltageSample, [{timestamp:'2026-09-26T19:00:00Z', line:'light_mv=2700'}], [voltageRule]);
  assert.deepEqual(stale.missing, ['light_mv']);
});
const outputRules = [{tap:'D3', field:'alert', equals:1, min_transitions_per_s:3, max_transitions_per_s:5}];
test('output verdict requires every current rule and a fresh capture', () => {
  const harness = {activity_checks:outputRules}, now = Date.parse(sampleTime);
  const capture = {timestamp:sampleTime, activity_checks:{rules:outputRules,
    checks:[{tap:'D3', field:'alert', state:'pass', detail:'Matched'}]}};
  assert.equal(model.activityVerdict(harness, capture, now).state, 'pass');
  assert.equal(model.activityVerdict(harness, capture, now + 16000).state, 'unverified');
  assert.equal(model.activityVerdict(harness, null, now).state, 'unverified');
  capture.activity_checks.checks = [];
  assert.equal(model.activityVerdict(harness, capture, now).state, 'unverified');
});
test('silent requested output is a failure and changed rules invalidate the verdict', () => {
  const capture = {timestamp:sampleTime, activity_checks:{rules:outputRules,
    checks:[{tap:'D3', field:'alert', state:'fail', detail:'Requested alert but zero edges'}]}};
  const now = Date.parse(sampleTime);
  assert.equal(model.activityVerdict({activity_checks:outputRules}, capture, now).state, 'fail');
  assert.equal(model.activityVerdict({activity_checks:[{...outputRules[0], equals:0}]}, capture, now).state, 'unverified');
});
