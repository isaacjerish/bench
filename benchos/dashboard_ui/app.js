const el = (id) => document.getElementById(id);
const names = ['P1', 'P2'];
let harness = null, latestSample = null, inventory = null;
let preview = false, auto = false, probeBusy = false, serialBusy = false, serialPaused = false;
let serialSeq = 0, serialEvents = [], session = [];
try {
  const saved = JSON.parse(localStorage.getItem('benchos-workspace-session-v2') || '[]');
  if (Array.isArray(saved)) session = saved.slice(-100);
} catch {}

function timeLabel(date) { return new Date(date).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}); }
function setText(id, value) { el(id).textContent = value == null ? '—' : String(value); }
function download(name, value) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type:'application/json'}));
  const link = document.createElement('a');
  link.href = url; link.download = name; document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function saveSession() {
  try { localStorage.setItem('benchos-workspace-session-v2', JSON.stringify(session.slice(-100))); } catch {}
}
function resetProbeDisplay() {
  latestSample = null;
  for (const name of names) {
    const key = name.toLowerCase();
    setText('probe-' + key + '-value', '—');
    setText('probe-' + key + '-level', '—');
    el('probe-' + key + '-fill').style.width = '0%';
  }
  setText('probe-status', 'No paired sample yet.');
  el('export-probes').disabled = true;
  renderAssessment();
}
function compactNet(value) {
  if (!value) return 'UNDECLARED';
  return value.length > 15 ? value.slice(0, 13) + '…' : value;
}
function renderHarness() {
  if (!harness) return;
  const board = harness.dut && harness.dut.board ? harness.dut.board : 'DUT';
  setText('board-dut', compactNet(board));
  setText('dut-port-label', board);
  setText('harness-state', 'USER DECLARED · ' + (harness.declared_on || 'DATE UNKNOWN'));
  for (const name of names) {
    const item = harness.probes[name], key = name.toLowerCase();
    setText('board-' + key + '-net', compactNet(item.state === 'connected' ? item.net : item.state.toUpperCase()));
    setText('legend-' + key, (item.net || 'UNASSIGNED') + ' · ' + item.state.replaceAll('_', ' '));
    setText('probe-' + key + '-net', item.net || 'UNASSIGNED');
    setText('probe-' + key + '-state', item.state.replaceAll('_', ' ').toUpperCase() + ' · USER DECLARED');
    const range = item.expected_min_v == null ? 'NO TARGET RANGE' : Number(item.expected_min_v).toFixed(2) + '–' + Number(item.expected_max_v).toFixed(2) + ' V TARGET';
    setText('probe-' + key + '-target', range);
    el('declare-' + key + '-net').value = item.net || '';
    el('declare-' + key + '-state').value = item.state;
    el('declare-' + key + '-min').value = item.expected_min_v == null ? '' : item.expected_min_v;
    el('declare-' + key + '-max').value = item.expected_max_v == null ? '' : item.expected_max_v;
  }
  renderAssessment();
}
async function loadHarness() {
  try {
    const response = await fetch('/api/harness', {cache:'no-store'});
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Harness unavailable');
    harness = data; renderHarness();
  } catch (error) { setText('harness-state', 'Harness unavailable: ' + error.message); }
}
async function loadPorts() {
  try {
    const response = await fetch('/api/config', {cache:'no-store'});
    const data = await response.json();
    for (const kind of ['lab', 'dut']) {
      const select = el(kind + '-port');
      const previous = select.value;
      const preferred = localStorage.getItem('benchos-' + kind + '-port') || data[kind + '_port'] || '';
      select.replaceChildren(new Option(kind === 'lab' ? 'Choose S3 port' : 'Choose DUT port', ''));
      for (const port of data.ports) select.add(new Option(port.device + ' · ' + (port.description || 'USB serial'), port.device));
      select.value = [previous, preferred].find(value => value && [...select.options].some(option => option.value === value)) || '';
    }
    setText('connection-label', data.ports.length ? data.ports.length + ' serial port' + (data.ports.length === 1 ? '' : 's') + ' found' : 'No serial ports found');
    el('connection-dot').classList.toggle('active', data.ports.length > 0);
  } catch (error) { setText('connection-label', 'Port discovery unavailable'); }
}
function previewSample() {
  const readings = names.map((name, index) => {
    const item = harness && harness.probes ? harness.probes[name] : null;
    const min = item && item.expected_min_v;
    const max = item && item.expected_max_v;
    const volts = min == null ? (index === 0 ? 1.42 : 2.18) : (Number(min) + Number(max)) / 2;
    return {probe:name, voltage_v:Number(volts.toFixed(3)), declared_net:item && item.state === 'connected' ? item.net : null, declared_state:item ? item.state : 'pending'};
  });
  return {source:'preview', simultaneous:false, timestamp:new Date().toISOString(),
    wiring_source:'user_declared', elapsed_ms:28.4, voltage_limit_v:3.3,
    digital_states:{P1:'HIGH',P2:'HIGH'}, readings};
}
function evaluate(sample) {
  if (!sample) return {state:'unknown', label:'AWAITING EVIDENCE', title:'Ready when you are.', detail:'Select the S3 port and take a paired probe reading.', next:'Take a paired reading on known safe nodes.'};
  const disconnected = sample.readings.filter(row => row.declared_state !== 'connected');
  const checks = sample.readings.map(row => {
    const declared = harness && harness.probes ? harness.probes[row.probe] : null;
    if (!declared || declared.expected_min_v == null || row.declared_state !== 'connected') return null;
    const min = Number(declared.expected_min_v), max = Number(declared.expected_max_v);
    return {probe:row.probe, net:declared.net, min, max, value:Number(row.voltage_v), pass:Number(row.voltage_v) >= min && Number(row.voltage_v) <= max};
  }).filter(Boolean);
  const failed = checks.find(item => !item.pass);
  if (disconnected.length) return {state:'unknown', label:'WIRING NOT CONFIRMED', title:'Probe assignment unclear.', detail:disconnected.map(row => row.probe).join(' and ') + ' has no confirmed net in the declaration. Its voltage is real, but the node identity is unknown.', next:'Confirm the probe tip and shared ground, then update the declared connection.'};
  if (failed) return {state:'fail', label:'MEASURED TARGET MISSED', title:failed.net + ' is outside target.', detail:failed.probe + ' measured ' + failed.value.toFixed(3) + ' V; the declared range is ' + failed.min.toFixed(2) + '–' + failed.max.toFixed(2) + ' V.', next:'Check the power source, ground path, and load at ' + failed.net + ', then sample again.'};
  if (checks.length) return {state:'pass', label:'PHYSICAL TARGETS MET', title:'Checked nodes are in range.', detail:checks.length + ' declared target' + (checks.length === 1 ? '' : 's') + ' matched the S3 readings. This says nothing about unprobed parts of the design.', next:'Sample during the failing behavior, then inspect the device serial output or move a probe to a discriminating node.'};
  return {state:'observed', label:'PHYSICAL VALUES CAPTURED', title:'Two nodes measured.', detail:'The S3 recorded both voltages. Add expected ranges to get a bounded pass/fail check for this design.', next:'Declare a target voltage range or compare readings before and after a controlled stimulus.'};
}
function renderAssessment() {
  const verdict = evaluate(latestSample);
  el('assessment').dataset.state = verdict.state;
  setText('assessment-label', preview && latestSample ? 'PREVIEW · SAMPLE DATA' : verdict.label);
  setText('assessment-title', verdict.title);
  setText('assessment-detail', verdict.detail);
  setText('assessment-symbol', verdict.state === 'pass' ? '✓' : verdict.state === 'fail' ? '!' : verdict.state === 'observed' ? '·' : '—');
  setText('assessment-source', latestSample ? (preview ? 'SAMPLE DATA' : 'S3 / PHYSICAL') : '—');
  setText('assessment-time', latestSample ? timeLabel(latestSample.timestamp) : '—');
  const evidence = [];
  if (latestSample) {
    for (const row of latestSample.readings) {
      evidence.push((preview ? 'Preview ' : 'S3 ') + row.probe + ' ' + (preview ? 'sampled ' : 'measured ') + Number(row.voltage_v).toFixed(3) + ' V. Net ' + (row.declared_net || 'unassigned') + ' is user-declared.');
    }
    evidence.push('P1 and P2 were read in order, ' + (latestSample.elapsed_ms == null ? 'not simultaneously.' : Number(latestSample.elapsed_ms).toFixed(1) + ' ms apart overall.'));
  } else evidence.push('Waiting for an S3 probe measurement.');
  const recentError = [...serialEvents].reverse().find(item => /ERROR|FAIL/i.test(item.line));
  if (recentError) evidence.push('DUT serial reported: ' + recentError.line);
  const list = el('evidence-list'); list.replaceChildren();
  for (const line of evidence) { const item = document.createElement('li'); item.textContent = line; list.append(item); }
  setText('next-check', verdict.next);
  setText('uncertainty', 'The map is a declaration. Benchy has not discovered connectivity, decoded the bus, or measured nodes outside its probe tips.');
}
function storeReading(sample, manual) {
  if (preview) return;
  const now = Date.now(), last = session.at(-1), verdict = evaluate(sample);
  if (!manual && last && last.state === verdict.state && now - last.time < 30000) return;
  session.push({time:now, state:verdict.state, title:verdict.title, manual, sample});
  session = session.slice(-100); saveSession(); renderTimeline();
}
function renderTimeline() {
  const target = el('timeline'); target.replaceChildren();
  if (!session.length) { const p = document.createElement('p'); p.className = 'empty-state'; p.textContent = 'Measurements will appear here as they arrive.'; target.append(p); return; }
  for (const item of [...session].reverse().slice(0, 25)) {
    const row = document.createElement('div'); row.className = 'timeline-row'; row.dataset.state = item.state;
    const time = document.createElement('time'); time.textContent = timeLabel(item.time);
    const title = document.createElement('strong'); title.textContent = (item.manual ? 'CAPTURE · ' : '') + item.title;
    const probes = document.createElement('span'); probes.className = 'timeline-probe'; probes.textContent = 'P1 + P2';
    const mark = document.createElement('span'); mark.className = 'timeline-mark'; mark.textContent = item.state === 'pass' ? '✓' : item.state === 'fail' ? '!' : '·';
    row.append(time, title, probes, mark); target.append(row);
  }
}
function renderProbeSample(sample) {
  latestSample = sample;
  for (const row of sample.readings) {
    const key = row.probe.toLowerCase(), value = Number(row.voltage_v);
    setText('probe-' + key + '-value', value.toFixed(3));
    setText('probe-' + key + '-level', sample.digital_states && sample.digital_states[row.probe] || '—');
    el('probe-' + key + '-fill').style.width = Math.min(100, Math.max(0, value / 3.3 * 100)) + '%';
  }
  setText('probe-status', (preview ? 'PREVIEW · sample data' : 'S3 physical · ordered reads') + ' · ' + timeLabel(sample.timestamp));
  el('export-probes').disabled = false;
  setText('footer-status', (preview ? 'Preview sample' : 'Physical sample') + ' at ' + timeLabel(sample.timestamp));
  renderAssessment(); storeReading(sample, false);
}
async function sampleProbes() {
  if (probeBusy) return;
  if (preview) { renderProbeSample(previewSample()); return; }
  const port = el('lab-port').value;
  if (!port) { setText('probe-status', 'Choose an S3 port before sampling.'); return; }
  probeBusy = true; el('sample-probes').disabled = true; setText('probe-status', 'Sampling P1, then P2…');
  try {
    const response = await fetch('/api/probes?' + new URLSearchParams({lab_port:port}), {cache:'no-store'});
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Probe sample failed');
    if (port === el('lab-port').value) renderProbeSample(data);
  } catch (error) { setText('probe-status', 'Probe unavailable: ' + error.message); }
  finally { probeBusy = false; el('sample-probes').disabled = false; }
}
function declarationPayload() {
  const result = {};
  for (const name of names) {
    const key = name.toLowerCase(), min = el('declare-' + key + '-min').value, max = el('declare-' + key + '-max').value;
    if ((min === '') !== (max === '')) throw Error(name + ' needs both target bounds or neither.');
    const item = {state:el('declare-' + key + '-state').value, net:el('declare-' + key + '-net').value.trim().toUpperCase(),
      expected_min_v:min === '' ? null : Number(min), expected_max_v:max === '' ? null : Number(max)};
    if (item.expected_min_v != null && !(0 <= item.expected_min_v && item.expected_min_v <= item.expected_max_v && item.expected_max_v <= 3.3)) throw Error(name + ' target must fit 0–3.3 V.');
    result[name] = item;
  }
  return result;
}
async function saveDeclaration(event) {
  event.preventDefault();
  if (preview) { setText('declaration-status', 'Leave Preview before saving.'); return; }
  try {
    const payload = declarationPayload();
    const response = await fetch('/api/harness/probes', {method:'POST', headers:{'Content-Type':'application/json','X-Benchy-Local':'1'}, body:JSON.stringify(payload)});
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Save failed');
    harness = data; renderHarness(); resetProbeDisplay(); await loadCode();
    setText('declaration-status', 'Saved locally · user-declared, not physically verified');
  } catch (error) { setText('declaration-status', 'Not saved: ' + error.message); }
}
function renderSerial() {
  const target = el('serial-lines'), filter = el('serial-filter').value.trim().toLowerCase();
  target.replaceChildren();
  const matches = serialEvents.filter(item => item.line.toLowerCase().includes(filter)).slice(-160);
  if (!matches.length) { const p = document.createElement('p'); p.className = 'empty-state'; p.textContent = filter ? 'No matching lines.' : 'Raw device output will appear here.'; target.append(p); return; }
  for (const item of matches) {
    const row = document.createElement('div'); row.className = 'serial-line' + (/ERROR|FAIL|WARN/i.test(item.line) ? ' error' : '');
    const time = document.createElement('time'); time.textContent = timeLabel(item.timestamp);
    const line = document.createElement('span'); line.textContent = item.line;
    row.append(time, line); target.append(row);
  }
  target.scrollTop = target.scrollHeight;
}
async function pollSerial() {
  if (serialBusy || serialPaused) return;
  if (preview) {
    if (!serialEvents.length) { serialEvents = ['BOOT: device ready', 'READING value=1.42'].map((line, index) => ({seq:index + 1, timestamp:new Date().toISOString(), line})); renderSerial(); }
    setText('serial-status', 'PREVIEW · sample output'); el('serial-live-dot').classList.remove('active'); return;
  }
  const port = el('dut-port').value;
  if (!port) { setText('serial-status', 'Choose a DUT port'); el('serial-live-dot').classList.remove('active'); return; }
  serialBusy = true;
  try {
    const query = new URLSearchParams({port, duration_ms:'700', after:String(serialSeq)});
    const response = await fetch('/api/serial?' + query, {cache:'no-store'});
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Serial sample failed');
    if (port !== el('dut-port').value) return;
    serialSeq = data.latest_seq;
    if (data.events.length) { serialEvents.push(...data.events); serialEvents = serialEvents.slice(-400); renderSerial(); renderAssessment(); }
    setText('serial-status', port.split('/').at(-1) + ' · ' + data.sample_window_ms + ' ms window · ' + serialEvents.length + ' lines');
    el('serial-live-dot').classList.add('active');
  } catch (error) { setText('serial-status', 'Serial unavailable: ' + error.message); el('serial-live-dot').classList.remove('active'); }
  finally { serialBusy = false; }
}
async function loadCode() {
  try {
    const response = await fetch('/api/code', {cache:'no-store'}), data = await response.json();
    if (!response.ok) throw Error(data.error || 'Source inventory failed');
    inventory = data; setText('source-revision', data.short_commit || 'LOCAL');
    setText('source-state', data.commit ? data.short_commit + (data.dirty ? ' · modified' : ' · clean') : 'Git revision unavailable');
    setText('firmware-state', data.declared_dut_firmware ? data.declared_dut_firmware + ' · declared' : 'Unspecified');
    const select = el('source-select'), previous = select.value;
    select.replaceChildren(new Option('Choose source file', ''));
    for (const file of data.files) select.add(new Option(file.path, file.path));
    const suggested = data.declared_dut_firmware ? 'dut_examples/' + data.declared_dut_firmware + '/' + data.declared_dut_firmware + '.ino' : '';
    select.value = data.files.some(file => file.path === previous) ? previous : data.files.some(file => file.path === suggested) ? suggested : '';
    if (select.value) await loadSource();
  } catch (error) { setText('source-state', 'Unavailable: ' + error.message); setText('source-revision', 'OFFLINE'); }
}
async function loadSource() {
  const path = el('source-select').value, target = el('source-code');
  target.replaceChildren();
  if (!path) { const p = document.createElement('p'); p.className = 'empty-state'; p.textContent = 'Select a file to inspect local code.'; target.append(p); return; }
  try {
    const response = await fetch('/api/source?' + new URLSearchParams({path}), {cache:'no-store'}), data = await response.json();
    if (!response.ok) throw Error(data.error || 'Source unavailable');
    if (path !== el('source-select').value) return;
    const modified = inventory && inventory.modified_files && inventory.modified_files.includes(path);
    setText('source-meta', path + ' · SHA-256 ' + data.sha256_short + '… · ' + (modified ? 'modified locally' : 'matches checked-out file') + ' · local source only');
    const fragment = document.createDocumentFragment();
    for (const [index, line] of data.text.split('\n').entries()) {
      const row = document.createElement('div'); row.className = 'source-row' + (/^\s*(\/\/|#)/.test(line) ? ' comment' : '');
      const number = document.createElement('span'); number.className = 'number'; number.textContent = String(index + 1);
      const code = document.createElement('span'); code.className = 'code'; code.textContent = line || ' ';
      row.append(number, code); fragment.append(row);
    }
    target.append(fragment);
  } catch (error) { setText('source-meta', 'Source unavailable: ' + error.message); }
}
function togglePreview() {
  preview = !preview; document.body.classList.toggle('preview', preview);
  el('preview-toggle').setAttribute('aria-pressed', String(preview));
  setText('session-badge', preview ? 'PREVIEW DATA' : 'LIVE SESSION');
  el('probe-declaration-form').querySelector('button[type=submit]').disabled = preview;
  serialSeq = 0; serialEvents = []; renderSerial(); resetProbeDisplay(); pollSerial();
}

el('preview-toggle').addEventListener('click', togglePreview);
el('refresh-button').addEventListener('click', async () => { await Promise.all([loadPorts(), loadHarness(), loadCode()]); pollSerial(); });
for (const kind of ['lab', 'dut']) el(kind + '-port').addEventListener('change', event => {
  localStorage.setItem('benchos-' + kind + '-port', event.target.value);
  if (kind === 'dut') { serialSeq = 0; serialEvents = []; renderSerial(); pollSerial(); }
  if (kind === 'lab') resetProbeDisplay();
});
el('sample-probes').addEventListener('click', sampleProbes);
el('auto-sample').addEventListener('click', () => { auto = !auto; el('auto-sample').setAttribute('aria-pressed', String(auto)); setText('auto-sample', auto ? 'Auto: on' : 'Auto: off'); if (auto) sampleProbes(); });
el('export-probes').addEventListener('click', () => { if (latestSample) download('benchy-probes.json', latestSample); });
el('probe-declaration-form').addEventListener('submit', saveDeclaration);
for (const name of names) el('declare-' + name.toLowerCase() + '-net').addEventListener('input', event => { event.target.value = event.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ''); });
el('capture-button').addEventListener('click', () => { if (latestSample && !preview) storeReading(latestSample, true); });
el('export-session').addEventListener('click', () => download('benchy-session.json', {source:'local_dashboard', exported_at:new Date().toISOString(), entries:session}));
el('clear-session').addEventListener('click', () => { session = []; saveSession(); renderTimeline(); });
el('serial-pause').addEventListener('click', () => { serialPaused = !serialPaused; setText('serial-pause', serialPaused ? 'Resume' : 'Pause'); el('serial-pause').setAttribute('aria-pressed', String(serialPaused)); if (!serialPaused) pollSerial(); });
el('serial-clear').addEventListener('click', () => { serialEvents = []; renderSerial(); renderAssessment(); });
el('serial-export').addEventListener('click', () => download('benchy-serial.json', {source:preview ? 'preview' : 'serial_observed', continuous:false, port:el('dut-port').value, events:serialEvents}));
el('serial-filter').addEventListener('input', renderSerial);
el('source-select').addEventListener('change', loadSource);
el('source-refresh').addEventListener('click', loadCode);
renderTimeline();
Promise.all([loadPorts(), loadHarness(), loadCode()]).then(() => { renderAssessment(); pollSerial(); setInterval(() => { if (auto) sampleProbes(); }, 4500); setInterval(pollSerial, 2400); });
