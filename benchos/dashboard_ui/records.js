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
        if ([...select.options].some(option => option.value === old)) select.value = old;
      }
      $('records-status').textContent = data.records.length + ' saved capture' + (data.records.length === 1 ? '' : 's') + ' · recorded evidence, never live';
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
    $('record-summary').textContent = 'Opening recorded evidence…';
    try {
      const [before, after] = await Promise.all([readSelected('before'), readSelected('after')]);
      if (generation !== selectionGeneration) return;
      for (const [side, record] of [['before', before], ['after', after]]) {
        $('record-' + side + '-meta').textContent = record ? date(record.timestamp) + ' · SHA ' + record.sha256.slice(0, 10) : 'No capture selected';
        $('record-' + side + '-serial').textContent = record && record.dut_lines.length ? record.dut_lines.join('\n') : 'No device output saved in this capture.';
      }
      const rows = window.BenchyModel.compareObservations(before && before.observations, after && after.observations);
      for (const row of rows) {
        const tr = document.createElement('tr'); tr.dataset.changed = String(row.delta != null && row.delta !== 0);
        const name = document.createElement('td'), title = document.createElement('strong'), subtitle = document.createElement('small');
        title.textContent = row.channel + ' · ' + (row.net || 'Unassigned'); subtitle.textContent = metric(row.metric);
        name.append(title, subtitle); tr.append(name);
        for (const value of [format(row.before), format(row.after), row.delta == null ? '—' :
          (row.delta > 0 ? '+' : '') + row.delta.toLocaleString(undefined, {maximumFractionDigits:3}) + (row.unit ? ' ' + row.unit : '')]) {
          const cell = document.createElement('td'); cell.textContent = value; tr.append(cell);
        }
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

  window.BenchyRecords = {
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
  $('refresh-records').addEventListener('click', loadInventory);
  loadInventory();
})();
