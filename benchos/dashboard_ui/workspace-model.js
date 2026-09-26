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
  const api = {ageMs, isFresh, coverage, compareObservations};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.BenchyModel = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
