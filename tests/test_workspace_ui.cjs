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
