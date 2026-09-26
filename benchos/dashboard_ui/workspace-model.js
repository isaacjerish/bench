(function (root) {
  'use strict';
  function ageMs(timestamp, now = Date.now()) {
    const value = Date.parse(timestamp);
    return Number.isFinite(value) ? now - value : Infinity;
  }
  function isFresh(timestamp, limit = 15000, now = Date.now()) {
    const age = ageMs(timestamp, now);
    return age >= -1000 && age <= limit;
  }
  function coverage(harness) {
    return Object.entries(harness && harness.dut_pins || {}).map(([pin, declaration]) => {
      const channels = [];
      for (const [name, probe] of Object.entries(harness.probes || {}))
        if (probe.net === declaration.net) channels.push({name, state:probe.state, kind:'voltage + level'});
      for (const [name, tap] of Object.entries(harness.digital_taps || {}))
        if (tap.net === declaration.net) channels.push({name, state:tap.state, kind:'digital activity'});
      return {pin, ...declaration, channels, covered:channels.some(channel => channel.state === 'connected')};
    });
  }
  function compareObservations(before, after) {
    const key = row => JSON.stringify([row.channel, row.net, row.metric, row.unit]);
    const left = new Map((before || []).map(row => [key(row), row]));
    const right = new Map((after || []).map(row => [key(row), row]));
    return [...new Set([...left.keys(), ...right.keys()])].map(id => {
      const a = left.get(id), b = right.get(id), exemplar = a || b;
      const comparable = a && b && a.net && b.net &&
        typeof a.value === 'number' && typeof b.value === 'number' &&
        Number.isFinite(a.value) && Number.isFinite(b.value);
      return {...exemplar, before:a || null, after:b || null,
        delta:comparable ? Math.round((b.value - a.value) * 1000000) / 1000000 : null};
    });
  }
  function compareTelemetry(sample, events, rules) {
    const comparisons = [], missing = [], changing = [];
    for (const rule of rules || []) {
      const physical = sample.readings.find(row => row.probe === rule.probe && row.declared_state === 'connected');
      const time = physical && Date.parse(physical.timestamp || sample.timestamp);
      const pattern = new RegExp('(?:^|\\s)' + rule.field + '=(\\S+)');
      const reports = (events || []).map(event => ({event, match:event.line.match(pattern)}))
        .filter(row => row.match && Math.abs(Date.parse(row.event.timestamp) - time) <= 5000);
      if (!physical || !Number.isFinite(Number(physical.voltage_v)) || !reports.length) {
        missing.push(rule.field); continue;
      }
      // Do not compare a moving input to a different moment in its motion.
      // Invalid nearby reports are not hidden by an older valid value.
      const values = reports.map(row => Number(row.match[1]) * Number(rule.scale_to_v));
      if (reports.some(row => !/^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?$/.test(row.match[1])) ||
          values.some(value => !Number.isFinite(value))) { missing.push(rule.field); continue; }
      if (Math.max(...values) - Math.min(...values) > Number(rule.max_delta_v)) {
        changing.push(rule.field); continue;
      }
      const nearest = reports.reduce((best, row) =>
        Math.abs(Date.parse(row.event.timestamp) - time) < Math.abs(Date.parse(best.event.timestamp) - time) ? row : best);
      const claimed = Number(nearest.match[1]) * Number(rule.scale_to_v);
      comparisons.push({rule, physical:Number(physical.voltage_v), claimed,
        delta:Math.abs(claimed - Number(physical.voltage_v))});
    }
    return {comparisons, missing, changing};
  }
  function activityVerdict(harness, capture, now = Date.now()) {
    const rules = harness && harness.activity_checks || [];
    if (!rules.length) return null;
    const result = capture && capture.activity_checks;
    if (!capture || !isFresh(capture.timestamp, 15000, now) || !result ||
        JSON.stringify(result.rules) !== JSON.stringify(rules))
      return {state:'unverified', detail:'A fresh output capture with the current declared conditions is needed.'};
    const expected = [...new Set(rules.map(rule => rule.tap + ':' + rule.field))];
    const checks = result.checks || [];
    const failed = checks.find(item => item.state === 'fail');
    if (failed) return {state:'fail', detail:failed.detail};
    const uncertain = checks.find(item => item.state !== 'pass');
    if (uncertain || expected.some(key => !checks.some(item => item.tap + ':' + item.field === key)))
      return {state:'unverified', detail:uncertain ? uncertain.detail : 'Some declared output checks are missing.'};
    return {state:'pass', detail:checks.map(item => item.detail).join(' ')};
  }
  const api = {ageMs, isFresh, coverage, compareObservations, compareTelemetry, activityVerdict};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.BenchyModel = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
