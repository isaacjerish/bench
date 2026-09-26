(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let selectionGeneration = 0;
  const format = row => !row ? '—' : typeof row.value === 'number'
    ? row.value.toLocaleString(undefined, {maximumFractionDigits:3}) + (row.unit ? ' ' + row.unit : '')
    : row.value;
  const date = timestamp => timestamp ? new Date(timestamp).toLocaleString() : 'Capture time not recorded';
  const metric = value => ({voltage:'Voltage', digital_end:'End level', transitions:'Transitions', frequency:'Frequency'}[value] || value);

  async function loadInventory() {
    $('records-status').textContent = 'Loading saved observations…';
    try {
      const response = await fetch('/api/records', {cache:'no-store'});
      const data = await response.json();
      if (!response.ok) throw Error(data.error || 'Saved captures unavailable');
      for (const side of ['before', 'after']) {
        const select = $('record-' + side), old = select.value;
        select.replaceChildren(new Option('Choose a capture…', ''));
        for (const record of data.records) select.add(new Option(record.title + ' · ' + date(record.timestamp), record.id));
        const kept = data.records.find(record => record.id === old || (record.aliases || []).includes(old));
        if (kept) select.value = kept.id;
      }
      $('records-status').textContent = data.records.length + ' saved capture' + (data.records.length === 1 ? '' : 's') + ' · recorded evidence, never live';
      return data.records;
    } catch (error) { $('records-status').textContent = error.message; }
  }

  async function readSelected(side) {
    const name = $('record-' + side).value;
    if (!name) return null;
    const response = await fetch('/api/records?' + new URLSearchParams({id:name}), {cache:'no-store'});
    const record = await response.json();
    if (!response.ok) throw Error(record.error || 'Cannot open capture');
    return record;
  }

  async function compare() {
    const generation = ++selectionGeneration;
    $('record-comparison').replaceChildren();
    $('record-context').replaceChildren();
    for (const side of ['before', 'after']) {
      $('record-' + side + '-meta').textContent = 'Opening…';
      $('record-' + side + '-serial').textContent = 'Opening…';
    }
    $('record-summary').textContent = 'Opening recorded evidence…';
    try {
      const [before, after] = await Promise.all([readSelected('before'), readSelected('after')]);
      if (generation !== selectionGeneration) return;
      for (const [side, record] of [['before', before], ['after', after]]) {
        $('record-' + side + '-meta').textContent = record ? date(record.timestamp) + ' · SHA ' + record.sha256.slice(0, 10) : 'No capture selected';
        $('record-' + side + '-serial').textContent = record && record.dut_lines.length ? record.dut_lines.join('\n') : 'No device output saved in this capture.';
        if (record) renderContext(side, record);
      }
      const rows = window.BenchyModel.compareObservations(before && before.observations, after && after.observations);
      for (const row of rows) {
        const tr = document.createElement('tr'); tr.dataset.changed = String(row.delta != null && row.delta !== 0);
        const name = document.createElement('td'), title = document.createElement('strong'), subtitle = document.createElement('small');
        title.textContent = row.channel + ' · ' + (row.net || 'Unassigned'); subtitle.textContent = metric(row.metric);
        name.append(title, subtitle); tr.append(name);
        for (const observation of [row.before, row.after]) {
          const cell = document.createElement('td'); cell.textContent = format(observation);
          if (observation) {
            const when = document.createElement('small');
            when.textContent = observation.timestamp ? new Date(observation.timestamp).toLocaleTimeString() : 'Time not saved';
            when.title = observation.timestamp || 'This individual observation has no saved timestamp';
            cell.append(when);
          }
          tr.append(cell);
        }
        const delta = document.createElement('td');
        delta.textContent = row.delta == null ? '—' : (row.delta > 0 ? '+' : '') + row.delta.toLocaleString(undefined, {maximumFractionDigits:3}) + (row.unit ? ' ' + row.unit : '');
        tr.append(delta);
        tr.title = [row.before && row.before.detail, row.after && row.after.detail].filter(Boolean).join(' / ');
        $('record-comparison').append(tr);
      }
      const paired = rows.filter(row => row.before && row.after).length;
      $('record-summary').textContent = rows.length
        ? rows.length + ' observed fields · ' + paired + ' present in both captures. Deltas require the same channel, metric, and declared net.'
        : 'Choose one or two captures to inspect their original readings.';
      $('record-context-note').textContent = [before, after].filter(Boolean).some(record => !record.harness_snapshot_available)
        ? 'These legacy records retain net labels but lack a full wiring snapshot. Differences alone cannot prove what was repaired.'
        : 'These are past observations. Different capture windows and wiring changes can affect comparisons.';
    } catch (error) { if (generation === selectionGeneration) $('record-summary').textContent = error.message; }
  }

  function renderContext(side, record) {
    const section = document.createElement('article'), title = document.createElement('strong');
    title.textContent = side.toUpperCase() + ' · ' + record.title; section.append(title);
    const context = record.source_context, source = context && context.after;
    const lines = [record.note || 'No note saved.',
      record.harness_snapshot_available ? 'Wiring declaration preserved with this capture.' : 'Full wiring declaration was not saved.',
      source ? 'Local source: ' + (source.short_commit || 'revision unavailable') + (source.dirty ? ' · modified' : '') +
        ' · ' + (source.files || []).length + ' file hashes. Recorded ' + date(source.recorded_at) + '.' : 'Local source hashes were not saved.'];
    if (record.capture_span_s != null) lines.push('Capture span: ' + record.capture_span_s.toFixed(1) + ' s · sequential windows.' +
      (record.capture_span_s > 15 ? ' Long capture: use the individual reading times below.' : ''));
    if (source) lines.push('Local file state; flashed firmware identity is not verified.');
    if (context && context.changed_during_capture) lines.push('Source changed during capture. Inspect both source inventories.');
    if (record.harness_changed_during_capture) lines.push('Wiring declaration changed during capture. Measurements retain the original declaration.');
    for (const error of record.capture_errors || []) lines.push('Partial capture · ' + error.stage + ': ' + error.message);
    for (const line of lines) { const text = document.createElement('p'); text.textContent = line; section.append(text); }
    const inspect = document.createElement('button'); inspect.type = 'button'; inspect.className = 'text-button';
    inspect.textContent = 'Inspect saved context ↗';
    inspect.addEventListener('click', () => {
      $('capture-dialog-title').textContent = record.title;
      $('capture-dialog-verdict').textContent = 'Recorded ' + date(record.timestamp);
      $('capture-dialog-body').textContent = JSON.stringify(record, null, 2);
      $('capture-dialog').showModal();
    });
    section.append(inspect); $('record-context').append(section);
  }

  window.BenchyRecords = {
    async selectSaved(id) {
      const records = await loadInventory();
      const selected = (records || []).find(record => record.id === id || (record.aliases || []).includes(id));
      $('record-after').value = selected ? selected.id : id;
      await compare();
    },
    inspectSnapshot(item) {
      $('capture-dialog-title').textContent = 'Saved at ' + new Date(item.time).toLocaleString();
      $('capture-dialog-verdict').textContent = item.title + ' · assessment at capture time';
      $('capture-dialog-body').textContent = JSON.stringify(item, null, 2);
      $('capture-dialog').showModal();
    }
  };
  $('capture-dialog-close').addEventListener('click', () => $('capture-dialog').close());
  $('record-before').addEventListener('change', compare);
  $('record-after').addEventListener('change', compare);
  $('refresh-records').addEventListener('click', async () => { await loadInventory(); await compare(); });
  loadInventory();
})();
