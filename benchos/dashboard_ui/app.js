const el = (id) => document.getElementById(id);
const names = ['P1', 'P2', 'P3'];
const model = window.BenchyModel;
let probeHistory = {};
let harness = null, latestSample = null, latestBus = null, latestTaps = null, inventory = null;
let preview = false, auto = true, probeBusy = false, busBusy = false, serialBusy = false, serialPaused = false;
let captureBusy = false;
let serialSeq = 0, serialEvents = [], session = [];
const voice = {active:false, ready:false, socket:null, stream:null, audio:null, source:null,
  processor:null, mute:null, playbackAt:0, playbackTimer:null, players:new Set(), pendingTools:[], toolRun:false,
  userDraft:null, assistantDraft:null, aborter:null, generation:0, audioQueue:[], tools:[]};
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
  probeHistory = {};
  for (const name of names) {
    const key = name.toLowerCase();
    setText('probe-' + key + '-value', '—');
    setText('probe-' + key + '-level', '—');
    el('probe-' + key + '-fill').style.width = '0%';
    renderSpark(name);
  }
  setText('probe-status', 'No paired sample yet.');
  el('export-probes').disabled = true;
  renderAssessment();
}
function compactNet(value) {
  if (!value) return 'UNDECLARED';
  return value.length > 15 ? value.slice(0, 13) + '…' : value;
}
function renderSpark(name) {
  const key = name.toLowerCase(), now = Date.now();
  const points = (probeHistory[name] || []).filter(point => point.time >= now - 120000);
  probeHistory[name] = points;
  let previous = null;
  const path = points.map(point => {
    const x = Math.min(296, Math.max(4, 4 + (point.time - (now - 120000)) / 120000 * 292));
    const y = 54 - Math.min(3.3, Math.max(0, point.value)) / 3.3 * 48;
    const command = !previous || point.time - previous.time > 12000 ? 'M' : 'L';
    previous = point; return command + x.toFixed(1) + ' ' + y.toFixed(1);
  }).join(' ');
  el('spark-' + key).setAttribute('d', path);
  setText('spark-' + key + '-meta', points.length ?
    Math.min(...points.map(point => point.value)).toFixed(2) + '–' + Math.max(...points.map(point => point.value)).toFixed(2) + ' V · ' + points.length + ' samples' : 'Awaiting samples');
}
function renderCoverage() {
  const rows = model.coverage(harness), target = el('coverage-rows'); target.replaceChildren();
  const connected = rows.filter(row => row.covered).length;
  setText('coverage-summary', rows.length ? connected + ' / ' + rows.length : '—');
  setText('coverage-description', rows.length ? 'declared DUT pins have connected probes' : 'Declare used DUT pins in the harness to see coverage');
  for (const row of rows) {
    const element = document.createElement('tr');
    let evidence = 'Awaiting fresh sample';
    const analog = latestSample && model.isFresh(latestSample.timestamp) && latestSample.readings.find(item => item.declared_net === row.net && item.declared_state === 'connected');
    const digital = latestTaps && model.isFresh(latestTaps.timestamp) && Object.entries(latestTaps.taps).filter(([, item]) => item.declared_net === row.net && item.usable_for_diagnosis);
    if (analog) evidence = (preview ? 'PREVIEW · ' : '') + analog.voltage_v.toFixed(3) + ' V · ' + analog.probe;
    else if (digital && digital.length) evidence = digital.map(([name, item]) => name + ' ' + (item.edges * 1000 / latestTaps.window_ms).toFixed(1) + '/s').join(' · ');
    if (!row.covered) evidence = 'No declared connected probe';
    const values = [row.pin, row.net, row.function,
      row.channels.map(channel => channel.name + (channel.state !== 'connected' ? ' (' + channel.state.replaceAll('_', ' ') + ')' : '')).join(' · ') || 'Unobserved', evidence];
    for (const value of values) { const cell = document.createElement('td'); cell.textContent = value; element.append(cell); }
    target.append(element);
  }
}
function renderFreshness() {
  el('save-capture').disabled = preview || captureBusy || !el('lab-port').value;
  setText('capture-availability', preview ? 'Leave Preview to save physical evidence.' :
    !el('lab-port').value ? 'Connect the S3 to save a new capture. Saved captures remain available below.' : '');
  const stale = latestSample && !preview && !model.isFresh(latestSample.timestamp);
  for (const name of names) {
    el('probe-' + name.toLowerCase() + '-value').closest('.probe-card').dataset.stale = String(Boolean(stale));
    renderSpark(name);
  }
  if (latestSample && !probeBusy) setText('probe-status', preview ? 'PREVIEW · sample data' :
    (stale ? 'STALE · last recorded ' : 'S3 physical · ') + Math.max(0, Math.floor(model.ageMs(latestSample.timestamp) / 1000)) + ' s ago · reads are sequential');
  el('digital-taps').dataset.stale = String(Boolean(latestTaps && !model.isFresh(latestTaps.timestamp)));
  el('bus').dataset.stale = String(Boolean(latestBus && !preview && !model.isFresh(latestBus.timestamp)));
  if (latestBus && !busBusy) setText('bus-status', preview ? 'PREVIEW · sample data' :
    (model.isFresh(latestBus.timestamp) ? 'S3 PHYSICAL' : 'STALE · LAST CAPTURE') + ' · ' +
    Math.max(0, Math.floor(model.ageMs(latestBus.timestamp) / 1000)) + ' s ago · approximate edge counts');
  if (latestTaps && !busBusy) setText('digital-tap-status', (model.isFresh(latestTaps.timestamp) ? 'S3 PHYSICAL' : 'STALE · LAST CAPTURE') +
    ' · ' + Math.max(0, Math.floor(model.ageMs(latestTaps.timestamp) / 1000)) + ' s ago · ' + latestTaps.window_ms + ' ms window · approximate counts');
  setText('session-badge', preview ? 'PREVIEW DATA' : !el('lab-port').value && !el('dut-port').value ? 'OFFLINE' : auto ? 'LIVE SESSION' : 'SAMPLING PAUSED');
  renderAssessment(); renderTelemetry(); renderCoverage();
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
  const monitor = harness.bus_monitor || {};
  el('bus').hidden = monitor.state !== 'connected';
  setText('bus-sda-net', monitor.sda_net || 'UNDECLARED');
  setText('bus-scl-net', monitor.scl_net || 'UNDECLARED');
  if (monitor.state !== 'connected') setText('bus-status', 'Sense inputs ' + (monitor.state || 'undeclared') + ' · user declaration');
  renderTaps(null);
  renderCoverage();
  renderAssessment();
}
async function loadHarness() {
  try {
    const response = await fetch('/api/harness', {cache:'no-store'});
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Harness unavailable');
    if (harness && JSON.stringify(harness) !== JSON.stringify(data)) { resetProbeDisplay(); renderBus(null); }
    harness = data; renderHarness();
  } catch (error) { setText('harness-state', 'Harness unavailable: ' + error.message); }
}
async function loadPorts() {
  try {
    const response = await fetch('/api/config', {cache:'no-store'});
    const data = await response.json();
    for (const kind of ['lab', 'dut']) {
      const select = el(kind + '-port');
      const expected = kind === 'lab' ? harness && harness.lab && harness.lab.usb_serial_number : harness && harness.dut && harness.dut.usb_serial_number;
      const enrolled = expected && data.ports.find(port => port.serial_number && port.serial_number.toLowerCase() === expected.toLowerCase());
      const previous = select.value;
      const preferred = localStorage.getItem('benchos-' + kind + '-port') || data[kind + '_port'] || '';
      select.replaceChildren(new Option(kind === 'lab' ? 'Choose S3 port' : 'Choose DUT port', ''));
      for (const port of data.ports) select.add(new Option(port.device + ' · ' + (port.serial_number || port.description || 'USB serial'), port.device));
      select.value = expected ? (enrolled ? enrolled.device : '') : ([previous, preferred].find(value => value && [...select.options].some(option => option.value === value)) || '');
    }
    const count = ['lab', 'dut'].filter(kind => el(kind + '-port').value).length;
    setText('connection-label', count === 2 ? 'S3 + DUT identified' : count === 1 ? 'One board identified' : 'Boards unavailable');
    el('connection-dot').classList.toggle('active', count === 2);
    renderAssessment();
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
    digital_states:{P1:'HIGH',P2:'HIGH',P3:'HIGH'}, readings};
}
function evaluate(sample) {
  if (!sample) return {state:'unknown', label:'AWAITING EVIDENCE', title:'Ready when you are.', detail:'Select the S3 port and take a paired probe reading.', next:'Take a paired reading on known safe nodes.'};
  if (!preview && (!el('lab-port').value || !model.isFresh(sample.timestamp))) return {
    state:'unknown', label:'LAST SAMPLE · NOT CURRENT', title:'Fresh evidence needed.',
    detail:'The last physical reading was captured at ' + timeLabel(sample.timestamp) + '. Values remain visible as history; they do not establish the circuit’s current state.',
    next:'Reconnect the identified S3 or resume sampling to obtain a fresh observation.'};
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
  const comparisons = [], missingComparisons = [];
  if (!preview && harness && Array.isArray(harness.telemetry_checks)) {
    for (const rule of harness.telemetry_checks) {
      const physical = sample.readings.find(row => row.probe === rule.probe && row.declared_state === 'connected');
      const pattern = new RegExp('(?:^|\\s)' + rule.field + '=(\\S+)');
      const recent = [...serialEvents].reverse().find(item => pattern.test(item.line));
      const match = recent && recent.line.match(pattern);
      const fresh = physical && recent && Math.abs(Date.parse(recent.timestamp) - Date.parse(physical.timestamp || sample.timestamp)) <= 5000;
      if (!fresh || !match || !/^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?$/.test(match[1])) {
        missingComparisons.push(rule.field); continue;
      }
      const claimed = Number(match[1]) * Number(rule.scale_to_v);
      if (Number.isFinite(claimed)) comparisons.push({rule, physical:Number(physical.voltage_v), claimed, delta:Math.abs(claimed - Number(physical.voltage_v))});
      else missingComparisons.push(rule.field);
    }
  }
  const disagreement = comparisons.find(item => item.delta > Number(item.rule.max_delta_v));
  if (disagreement) return {state:'fail', label:'DUT REPORT DISAGREES', title:disagreement.rule.field + ' differs from ' + disagreement.rule.probe + '.',
    detail:'DUT serial claims ' + disagreement.claimed.toFixed(3) + ' V; S3 measured ' + disagreement.physical.toFixed(3) + ' V at the declared net. Difference ' + disagreement.delta.toFixed(3) + ' V exceeds ' + Number(disagreement.rule.max_delta_v).toFixed(3) + ' V.',
    next:'Check ADC scaling, selected pin, and report logic. Repeat with a controlled change at the sensor.'};
  const busIsFresh = latestBus && !preview && model.isFresh(latestBus.timestamp) && Math.abs(Date.parse(latestBus.timestamp) - Date.parse(sample.timestamp)) < 15000;
  const tapsAreFresh = latestTaps && !preview && model.isFresh(latestTaps.timestamp) && Math.abs(Date.parse(latestTaps.timestamp) - Date.parse(sample.timestamp)) < 15000;
  const tapTargetMissed = tapsAreFresh && (latestTaps.expectations || []).find(item => item.state === 'fail');
  if (tapTargetMissed) return {state:'fail', label:'DIGITAL TARGET MISSED', title:tapTargetMissed.net + ' has unexpected activity.',
    detail:tapTargetMissed.detail, next:'Check the declared signal node and the sense branch, then capture again. This observation alone does not identify a faulty component.'};
  const endpointMismatch = tapsAreFresh && latestTaps.comparisons.find(item => item.assessment === 'activity_mismatch');
  if (endpointMismatch) return {state:'unknown', label:'ENDPOINT ACTIVITY DIFFERS', title:endpointMismatch.net + ' needs a closer look.',
    detail:endpointMismatch.detail, next:'Check the declared connection and both probe branches. Repeat during sustained traffic; edge counts cannot identify the exact broken contact.'};
  if (busIsFresh && latestBus.sda.edges > 0 && latestBus.scl.edges === 0) {
    const recentError = [...serialEvents].reverse().find(item => /ERROR|FAIL/i.test(item.line) && Math.abs(Date.parse(item.timestamp) - Date.parse(latestBus.timestamp)) < 15000);
    return {state:'fail', label:'CLOCK PATH NEEDS CHECK', title:'Data moved; clock stayed static.',
      detail:'The S3 counted ' + latestBus.sda.edges + ' data transitions and zero clock transitions at the declared monitor points.' + (recentError ? ' DUT serial also reported: ' + recentError.line : ''),
      next:'Check the declared clock row, its probe branch, and the DUT-to-device clock jumper. Then capture again.'};
  }
  if (busIsFresh && latestBus.scl.edges > 0 && latestBus.sda.edges === 0) return {
    state:'fail', label:'DATA PATH NEEDS CHECK', title:'Clock moved; data stayed static.',
    detail:'The S3 counted ' + latestBus.scl.edges + ' clock transitions and zero data transitions at the declared monitor points.',
    next:'Check the declared data row and its sense branch, then capture again.'};
  const freshError = !preview && [...serialEvents].reverse().find(item =>
    /(?:^|[\s_])(ERROR|FAIL)(?:[\s_:]|$)/i.test(item.line) &&
    Math.abs(Date.parse(item.timestamp) - Date.parse(sample.timestamp)) <= 10000);
  if (freshError) return {state:'fail', label:'DUT REPORTED ERROR', title:'The device reports a fault.',
    detail:'Fresh DUT serial output: ' + freshError.line + '. The S3 values above describe only the probed nodes.',
    next:'Use probe and bus readings to narrow the physical cause, then repeat after the repair.'};
  if (missingComparisons.length) return {state:'unknown', label:'COMPARISON INCOMPLETE', title:'Awaiting all declared fields.',
    detail:'Fresh paired evidence is missing for ' + missingComparisons.join(', ') + '. ' + comparisons.length + ' other comparison(s) matched within tolerance.',
    next:'Keep the device stream running and the input steady, then repeat the sample.'};
  if (comparisons.length) return {state:'pass', label:'REPORTS AGREE WITH PROBES', title:'Independent readings agree.', detail:comparisons.length + ' declared serial field' + (comparisons.length === 1 ? '' : 's') + ' matched fresh S3 probe readings within configured tolerance.', next:'Change one input or introduce a reversible fault, then capture both sources again.'};
  if (checks.length) return {state:'pass', label:'PHYSICAL TARGETS MET', title:'Checked nodes are in range.', detail:checks.length + ' declared target' + (checks.length === 1 ? '' : 's') + ' matched the S3 readings. This says nothing about unprobed parts of the design.', next:'Sample during the failing behavior, then inspect the device serial output or move a probe to a discriminating node.'};
  return {state:'observed', label:'PHYSICAL VALUES CAPTURED', title:sample.readings.length + ' nodes measured.', detail:'The S3 recorded the connected probe voltages. Add expected ranges to get a bounded pass/fail check for this design.', next:'Declare a target voltage range or compare readings before and after a controlled stimulus.'};
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
    evidence.push(latestSample.readings.map(row => row.probe).join(', ') + ' were read in order, ' + (latestSample.elapsed_ms == null ? 'not simultaneously.' : Number(latestSample.elapsed_ms).toFixed(1) + ' ms overall.'));
  } else evidence.push('Waiting for an S3 probe measurement.');
  if (latestBus) evidence.push((preview ? 'Preview bus sample: ' : 'S3 bus inputs: ') +
    'SDA ' + latestBus.sda.edges + ' edges, SCL ' + latestBus.scl.edges + ' edges in ' + latestBus.window_ms + ' ms; transactions not decoded.');
  const recentError = latestSample && [...serialEvents].reverse().find(item =>
    /ERROR|FAIL/i.test(item.line) && Math.abs(Date.parse(item.timestamp) - Date.parse(latestSample.timestamp)) <= 10000);
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
  session.push({time:now, state:verdict.state, title:verdict.title, manual, sample,
    harness:structuredClone(harness),
    taps:latestTaps && model.isFresh(latestTaps.timestamp) ? latestTaps : null,
    serial:serialEvents.filter(event => Math.abs(Date.parse(event.timestamp) - Date.parse(sample.timestamp)) <= 10000)});
  session = session.slice(-100); saveSession(); renderTimeline();
}
function renderTimeline() {
  const target = el('timeline'); target.replaceChildren();
  if (!session.length) { const p = document.createElement('p'); p.className = 'empty-state'; p.textContent = 'Measurements will appear here as they arrive.'; target.append(p); return; }
  for (const item of [...session].reverse().slice(0, 25)) {
    const row = document.createElement('button'); row.type = 'button'; row.className = 'timeline-row'; row.dataset.state = item.state;
    row.setAttribute('aria-label', 'Inspect saved capture at ' + timeLabel(item.time));
    row.addEventListener('click', () => window.BenchyRecords.inspectSnapshot(item));
    const time = document.createElement('time'); time.textContent = timeLabel(item.time);
    const title = document.createElement('strong'); title.textContent = (item.manual ? 'CAPTURE · ' : '') + item.title;
    const probes = document.createElement('span'); probes.className = 'timeline-probe'; probes.textContent = item.sample.readings.map(row => row.probe).join(' + ');
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
    if (row.declared_state === 'connected' && Number.isFinite(value)) {
      const points = probeHistory[row.probe] || [];
      points.push({time:Date.parse(row.timestamp || sample.timestamp), value});
      probeHistory[row.probe] = points.filter(point => point.time >= Date.now() - 120000).slice(-40);
      renderSpark(row.probe);
    }
  }
  setText('probe-status', (preview ? 'PREVIEW · sample data' : 'S3 physical · ordered reads') + ' · ' + timeLabel(sample.timestamp));
  el('export-probes').disabled = false;
  setText('footer-status', (preview ? 'Preview sample' : 'Physical sample') + ' at ' + timeLabel(sample.timestamp));
  renderAssessment(); storeReading(sample, false);
  renderCoverage();
}
async function sampleProbes() {
  if (probeBusy || captureBusy) return;
  if (preview) { renderProbeSample(previewSample()); return; }
  const port = el('lab-port').value;
  if (!port) { setText('probe-status', 'Choose an S3 port before sampling.'); return; }
  probeBusy = true; el('sample-probes').disabled = true; setText('probe-status', 'Sampling connected probes…');
  try {
    const response = await fetch('/api/probes?' + new URLSearchParams({lab_port:port}), {cache:'no-store'});
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Probe sample failed');
    if (port === el('lab-port').value && !preview) renderProbeSample(data);
  } catch (error) { setText('probe-status', 'Probe unavailable: ' + error.message); }
  finally { probeBusy = false; el('sample-probes').disabled = false; }
}
function previewBus() {
  return {source:'preview', timestamp:new Date().toISOString(), window_ms:1000,
    edge_counts_approximate:true, decoded_transactions:false,
    sda:{start:'HIGH',end:'HIGH',edges:16}, scl:{start:'HIGH',end:'HIGH',edges:64}};
}
function renderBus(sample) {
  latestBus = sample;
  if (!sample) {
    renderTaps(null);
    for (const line of ['sda', 'scl']) { setText('bus-' + line + '-edges', '—'); setText('bus-' + line + '-level', 'Awaiting sample'); }
    setText('bus-title', 'No bus evidence yet.');
    setText('bus-detail', 'Bench can count transitions on declared read-only inputs. Edge counts do not decode transactions or prove which wire is faulty.');
    return;
  }
  for (const line of ['sda', 'scl']) {
    const item = sample[line];
    setText('bus-' + line + '-edges', item.edges);
    setText('bus-' + line + '-level', item.start + ' → ' + item.end + ' · ' + sample.window_ms + ' ms');
  }
  const sda = sample.sda.edges, scl = sample.scl.edges;
  if (sda === 0 && scl === 0) {
    setText('bus-title', 'No transitions observed.');
    setText('bus-detail', 'Both sense inputs were static during this window. The bus may be idle, the leads may miss the active rows, or capture may have missed traffic. Check the DUT output and repeat.');
  } else if (scl === 0) {
    setText('bus-title', 'Data line moved; clock stayed static.');
    setText('bus-detail', 'Check the declared clock connection and sample while the DUT is communicating. This edge count does not identify a specific broken contact.');
  } else if (sda === 0) {
    setText('bus-title', 'Clock line moved; data stayed static.');
    setText('bus-detail', 'Check the declared data connection and sample while the DUT is communicating. This edge count does not decode an address or ACK.');
  } else {
    setText('bus-title', 'Both lines show activity.');
    setText('bus-detail', 'The S3 observed transitions on both declared inputs. Transaction contents and ACK/NACK remain unverified until timed capture is built.');
  }
  const stream = sample.dut_stream_open_during_capture ? ' · DUT STREAM HELD OPEN' : '';
  setText('bus-status', (sample.source === 'preview' ? 'PREVIEW · SAMPLE DATA' : 'S3 PHYSICAL · APPROXIMATE COUNT') + stream + ' · ' + timeLabel(sample.timestamp));
  renderAssessment();
}
function renderTaps(sample) {
  latestTaps = sample;
  const target = el('digital-tap-rows');
  target.replaceChildren();
  const declared = harness && harness.digital_taps || {};
  for (const [name, tap] of Object.entries(declared)) {
    const reading = sample && sample.taps[name];
    const usable = tap.state === 'connected' && reading && reading.usable_for_diagnosis;
    const row = document.createElement('tr');
    for (const value of [name + ' · IO' + tap.gpio, tap.net, tap.endpoint,
      usable ? reading.start + ' → ' + reading.end : tap.state.replaceAll('_', ' '),
      usable ? String(reading.edges) : '—']) {
      const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
    }
    target.append(row);
  }
  const comparisons = el('digital-tap-comparisons'); comparisons.replaceChildren();
  for (const item of sample && sample.comparisons || []) {
    const row = document.createElement('p');
    const label = document.createElement('strong'); label.textContent = item.net + ' · ' + item.taps.join(' / ') + ': ';
    row.append(label, document.createTextNode(item.detail)); comparisons.append(row);
  }
  for (const item of sample && sample.expectations || []) {
    const row = document.createElement('p');
    const label = document.createElement('strong'); label.textContent = item.tap + ' · ' + item.state.toUpperCase() + ': ';
    row.append(label, document.createTextNode(item.detail)); comparisons.append(row);
  }
  setText('digital-tap-status', sample
    ? 'S3 PHYSICAL · ' + sample.window_ms + ' ms · ' + timeLabel(sample.timestamp) + ' · counts are approximate'
    : 'Awaiting capture. Pending connections are excluded from diagnosis.');
  el('export-taps').disabled = !sample;
  renderCoverage();
}
async function sampleBus() {
  if (busBusy || captureBusy) return;
  if (preview) { renderBus(previewBus()); return; }
  const hasTaps = harness && Object.values(harness.digital_taps || {}).some(tap => tap.state === 'connected');
  if (!hasTaps && (!harness || !harness.bus_monitor || harness.bus_monitor.state !== 'connected')) return;
  const port = el('lab-port').value;
  if (!port) { setText('bus-status', 'Choose the identified S3 port.'); return; }
  busBusy = true; el('sample-bus').disabled = true; el('sample-taps').disabled = true; setText('bus-status', 'Counting read-only transitions…');
  setText('digital-tap-status', 'Counting read-only transitions…');
  try {
    const response = await fetch((hasTaps ? '/api/taps?' : '/api/bus?') + new URLSearchParams({lab_port:port,dut_port:el('dut-port').value,duration_ms:'1000'}), {cache:'no-store'});
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Bus sample failed');
    if (port === el('lab-port').value && !preview) {
      if (hasTaps) {
        renderTaps(data);
        if (harness.bus_monitor.state === 'connected' && data.taps.D1 && data.taps.D1.usable_for_diagnosis && data.taps.D2 && data.taps.D2.usable_for_diagnosis)
          renderBus({...data, sda:data.taps.D1, scl:data.taps.D2});
      } else renderBus(data);
    }
  } catch (error) { setText('bus-status', 'Bus unavailable: ' + error.message); setText('digital-tap-status', 'Capture unavailable: ' + error.message); }
  finally { busBusy = false; el('sample-bus').disabled = false; el('sample-taps').disabled = false; }
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
function renderTelemetry() {
  const target = el('telemetry-fields');
  target.replaceChildren();
  const event = [...serialEvents].reverse().find(item => /(?:^|\s)[A-Za-z][A-Za-z0-9_]{0,31}=\S+/.test(item.line));
  if (!event) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = 'Structured fields appear here when the device emits them.';
    target.append(empty);
    setText('telemetry-source', 'Awaiting key=value output');
    return;
  }
  const fields = [...event.line.matchAll(/(?:^|\s)([A-Za-z][A-Za-z0-9_]{0,31})=([^\s]{1,64})/g)].slice(0, 16);
  const prefix = event.line.split(/\s/, 1)[0];
  const age = Date.now() - Date.parse(event.timestamp);
  setText('telemetry-source', (preview ? 'PREVIEW · ' : age > 15000 ? 'STALE · ' : 'OBSERVED · ') + prefix + ' · ' + timeLabel(event.timestamp));
  for (const [, key, value] of fields) {
    const card = document.createElement('div');
    const label = document.createElement('span');
    const reading = document.createElement('strong');
    label.textContent = key.replaceAll('_', ' ');
    reading.textContent = value;
    card.append(label, reading);
    target.append(card);
  }
}
function renderSerial() {
  renderTelemetry();
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
  if (serialBusy || serialPaused || captureBusy) return;
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
    if (port !== el('dut-port').value || preview) return;
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
function voiceState(state, message) {
  el('voice-debug').dataset.state = state;
  setText('voice-status', message);
}
function clearVoiceTranscript() {
  el('voice-transcript').replaceChildren();
  const p = document.createElement('p'); p.className = 'empty-state';
  p.textContent = 'Your live transcript will appear here while the microphone is active.';
  el('voice-transcript').append(p);
  voice.userDraft = null; voice.assistantDraft = null;
}
function renderVoiceTurn(role, text, draft = false) {
  const target = el('voice-transcript');
  target.querySelector('.empty-state')?.remove();
  let row = draft ? (role === 'user' ? voice.userDraft : voice.assistantDraft) : null;
  if (!row) {
    row = document.createElement('div'); row.className = 'voice-turn'; row.dataset.role = role;
    const label = document.createElement('strong'); label.textContent = role === 'user' ? 'You' : 'Grok';
    const content = document.createElement('span'); row.append(label, content); target.append(row);
    if (draft) {
      if (role === 'user') voice.userDraft = row;
      else voice.assistantDraft = row;
    }
  }
  row.lastElementChild.textContent = text;
  target.scrollTop = target.scrollHeight;
}
function finishVoiceDraft(role) {
  if (role === 'user') voice.userDraft = null;
  else voice.assistantDraft = null;
}
function b64FromBuffer(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, Math.min(i + 0x8000, bytes.length)));
  }
  return btoa(binary);
}
function pcmBufferFromBase64(value) {
  const binary = atob(value), buffer = new ArrayBuffer(binary.length), bytes = new Uint8Array(buffer);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return buffer;
}
function playVoiceAudio(encoded) {
  if (!voice.audio || !voice.active) return;
  const pcm = new Int16Array(pcmBufferFromBase64(encoded));
  const audio = voice.audio.createBuffer(1, pcm.length, 24000), channel = audio.getChannelData(0);
  for (let i = 0; i < pcm.length; i += 1) channel[i] = pcm[i] / 32768;
  const player = voice.audio.createBufferSource(); player.buffer = audio; player.connect(voice.audio.destination);
  const startAt = Math.max(voice.playbackAt, voice.audio.currentTime + 0.015);
  voice.playbackAt = startAt + audio.duration;
  voice.players.add(player); player.onended = () => voice.players.delete(player); player.start(startAt);
}
function stopVoicePlayback() {
  clearTimeout(voice.playbackTimer); voice.playbackTimer = null;
  for (const player of voice.players) { try { player.stop(); } catch {} }
  voice.players.clear();
  if (voice.audio) voice.playbackAt = voice.audio.currentTime;
}
function voiceReplyIsPlaying() {
  return Boolean(voice.audio && voice.playbackAt > voice.audio.currentTime + 0.04);
}
function voiceContext() {
  const verdict = el('assessment');
  return {
    preview_mode: preview,
    preview_notice: preview ? 'Values below are synthetic preview samples, never live readings.' : null,
    harness: harness || null,
    selected_ports: {s3:el('lab-port').value || null, dut:el('dut-port').value || null},
    latest_probe_sample: latestSample || null,
    latest_bus_sample: latestBus || null,
    current_assessment: {state:verdict.dataset.state || 'unknown', title:el('assessment-title').textContent,
      detail:el('assessment-detail').textContent},
    recent_dut_serial: serialEvents.slice(-12).map(event => ({timestamp:event.timestamp, line:event.line})),
    source_inventory: inventory ? {revision:inventory.short_commit, files:inventory.files.map(file => file.path)} : null,
  };
}
async function voiceRequest(url, body) {
  const response = await fetch(url, {method:'POST', cache:'no-store', headers:{'Content-Type':'application/json','X-Benchy-Local':'1'},
    body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw Error(data.error || 'Voice request failed');
  return data;
}
async function loadVoiceStatus() {
  try {
    const response = await fetch('/api/voice/status', {cache:'no-store'}), data = await response.json();
    const button = el('voice-toggle'); button.disabled = !data.configured;
    document.body.dataset.voiceConfigured = String(Boolean(data.configured));
    if (data.configured) voiceState('idle', 'Ready · ' + data.model + ' · voice tools are read-only');
    else voiceState('error', 'Set XAI_API_KEY before launching the dashboard to enable voice.');
  } catch { voiceState('error', 'Voice setup status is unavailable.'); }
}
function closeVoice(message = 'Conversation ended.') {
  if (!voice.active && !voice.stream && !voice.audio && !voice.socket) return;
  voice.active = false; voice.ready = false; voice.generation += 1;
  voice.aborter?.abort(); voice.aborter = null;
  voice.pendingTools = []; voice.toolRun = false;
  voice.audioQueue = []; voice.tools = [];
  if (voice.socket) { voice.socket.onclose = null; try { voice.socket.close(1000, 'Conversation ended'); } catch {} }
  voice.socket = null;
  if (voice.processor) { voice.processor.port.onmessage = null; try { voice.processor.disconnect(); } catch {} }
  if (voice.source) { try { voice.source.disconnect(); } catch {} }
  if (voice.mute) { try { voice.mute.disconnect(); } catch {} }
  voice.processor = null; voice.source = null; voice.mute = null;
  if (voice.stream) for (const track of voice.stream.getTracks()) track.stop();
  voice.stream = null; stopVoicePlayback();
  if (voice.audio) { const context = voice.audio; voice.audio = null; context.close().catch(() => {}); }
  clearVoiceTranscript();
  el('voice-toggle').setAttribute('aria-pressed', 'false');
  setText('voice-button-label', 'Start conversation');
  voiceState(message.startsWith('Could not') || message.startsWith('Voice error') ? 'error' : 'idle', message);
  el('voice-toggle').disabled = document.body.dataset.voiceConfigured !== 'true';
}
function sendVoiceEvent(event) {
  if (voice.socket && voice.socket.readyState === WebSocket.OPEN) voice.socket.send(JSON.stringify(event));
}
async function executePendingVoiceTools(generation) {
  if (voice.toolRun || !voice.pendingTools.length) return;
  voice.toolRun = true; voiceState('thinking', 'Grok is checking Benchy evidence…');
  const calls = voice.pendingTools.splice(0), outputs = [];
  for (const call of calls) {
    let result;
    try {
      const args = JSON.parse(call.arguments || '{}');
      result = await voiceRequest('/api/voice/tool', {name:call.name, arguments:args});
    } catch (error) { result = {error:error.message || 'Tool call failed'}; }
    outputs.push({type:'conversation.item.create', item:{type:'function_call_output', call_id:call.call_id,
      output:JSON.stringify(result)}});
  }
  voice.toolRun = false;
  if (!voice.active || generation !== voice.generation) return;
  for (const output of outputs) sendVoiceEvent(output);
  const waitMs = Math.max(0, (voice.playbackAt - (voice.audio?.currentTime || 0)) * 1000);
  if (waitMs) await new Promise(resolve => setTimeout(resolve, Math.min(waitMs + 30, 30_000)));
  if (voice.active && generation === voice.generation) {
    sendVoiceEvent({type:'response.create'});
    voiceState('listening', 'Listening · ask a follow-up whenever you’re ready.');
  }
}
function handleVoiceEvent(event, generation) {
  if (!voice.active || generation !== voice.generation) return;
  if (event.type === 'session.created') {
    const snapshot = voiceContext();
    const instructions = 'You are Benchy, a concise conversational hardware debugging partner. Ask focused questions, read the declared harness before selecting probes, and distinguish physical S3 evidence from DUT claims. P1/P2/P3 accept only known 0–3.3 V signals with common ground; never suggest 5 V or unknown voltage. Ask the user to confirm physical placement if wiring may have changed. Use only read-only tools; never flash firmware. If Preview mode is on, treat every displayed reading as synthetic. Explain what each measurement shows and its uncertainty. Current dashboard snapshot (source labels are authoritative): ' + JSON.stringify(snapshot);
    voice.tools.forEach(tool => { if (tool.name === 'build_and_flash_dut' || tool.name === 'flash_dut') throw Error('Write tools are blocked in voice mode'); });
    sendVoiceEvent({type:'session.update', session:{
      modalities:['text','audio'], voice:'eve', instructions,
      turn_detection:{type:'server_vad'},
      audio:{input:{format:{type:'audio/pcm',rate:24000},transcription:{model:'grok-transcribe'}},
        output:{format:{type:'audio/pcm',rate:24000}},
      }, tools:voice.tools, tool_choice:'auto'
    }});
    voiceState('connecting', 'Connected · setting up microphone and read-only tools…');
  } else if (event.type === 'session.updated') {
    voice.ready = true;
    for (const audio of voice.audioQueue.splice(0)) sendVoiceEvent({type:'input_audio_buffer.append', audio:b64FromBuffer(audio)});
    el('voice-toggle').disabled = false;
    voiceState('listening', 'Listening · speak naturally; click to stop.');
  } else if (event.type === 'conversation.item.input_audio_transcription.updated') {
    renderVoiceTurn('user', event.transcript || '', true);
  } else if (event.type === 'conversation.item.input_audio_transcription.completed') {
    renderVoiceTurn('user', event.transcript || '', true); finishVoiceDraft('user');
  } else if (event.type === 'response.output_audio_transcript.delta') {
    const current = voice.assistantDraft?.lastElementChild?.textContent || '';
    renderVoiceTurn('assistant', current + (event.delta || ''), true);
  } else if (event.type === 'response.output_audio_transcript.done') {
    if (event.transcript && !voice.assistantDraft) renderVoiceTurn('assistant', event.transcript, true);
    finishVoiceDraft('assistant');
  } else if (event.type === 'response.output_audio.delta' || event.type === 'response.audio.delta') {
    if (event.delta) playVoiceAudio(event.delta);
    voiceState('speaking', 'Grok is speaking · interrupt any time.');
  } else if (event.type === 'input_audio_buffer.speech_started') {
    stopVoicePlayback(); voiceState('listening', 'Listening…');
  } else if (event.type === 'response.function_call_arguments.done') {
    voice.pendingTools.push({name:event.name, arguments:event.arguments, call_id:event.call_id});
  } else if (event.type === 'response.done') {
    if (voice.pendingTools.length) executePendingVoiceTools(generation);
    else if (voiceReplyIsPlaying()) {
      const generationAtEnd = generation;
      const waitMs = Math.max(0, (voice.playbackAt - voice.audio.currentTime) * 1000);
      voiceState('speaking', 'Grok is finishing · speak after the reply to avoid microphone echo.');
      voice.playbackTimer = setTimeout(() => {
        voice.playbackTimer = null;
        if (voice.active && generationAtEnd === voice.generation)
          voiceState('listening', 'Listening · speak naturally; click to stop.');
      }, waitMs + 40);
    } else voiceState('listening', 'Listening · speak naturally; click to stop.');
  } else if (event.type === 'error') {
    closeVoice('Voice error · ' + (event.error?.message || 'check the xAI connection and retry.'));
  }
}
async function startVoice() {
  const button = el('voice-toggle'); button.disabled = true;
  voiceState('connecting', 'Requesting microphone access…');
  button.setAttribute('aria-pressed', 'true'); setText('voice-button-label', 'End conversation');
  clearVoiceTranscript(); voice.active = true; voice.generation += 1;
  const generation = voice.generation;
  try {
    if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode)
      throw Error('This browser does not support live microphone audio.');
    voice.stream = await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,
      noiseSuppression:true,autoGainControl:true}});
    voice.audio = new AudioContext({sampleRate:24000});
    await voice.audio.resume();
    await voice.audio.audioWorklet.addModule('/audio-worklet.js');
    const [token, toolData] = await Promise.all([
      voiceRequest('/api/voice/session', {}),
      fetch('/api/voice/tools', {cache:'no-store'}).then(async response => {
        const data = await response.json(); if (!response.ok) throw Error(data.error || 'Voice tools unavailable'); return data;
      }),
    ]);
    voice.tools = toolData.tools || [];
    if (!voice.tools.length) throw Error('No read-only Benchy tools are available. Install the MCP extra.');
    const url = 'wss://api.x.ai/v1/realtime?model=grok-voice-latest';
    voice.socket = new WebSocket(url, ['xai-client-secret.' + token.value]);
    voice.socket.onmessage = message => {
      try { handleVoiceEvent(JSON.parse(message.data), generation); }
      catch (error) { closeVoice('Voice error · ' + (error.message || 'could not process the session.')); }
    };
    voice.socket.onerror = () => closeVoice('Could not connect to Grok voice. Check your network and xAI account.');
    voice.socket.onclose = event => {
      if (voice.active && generation === voice.generation) closeVoice(event.reason || 'Grok voice connection closed.');
    };
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(Error('Timed out connecting to Grok voice.')), 15_000);
      voice.socket.addEventListener('open', () => { clearTimeout(timeout); resolve(); }, {once:true});
      voice.socket.addEventListener('error', () => { clearTimeout(timeout); reject(Error('Could not connect to Grok voice.')); }, {once:true});
    });
    if (!voice.active || generation !== voice.generation) return;
    voice.source = voice.audio.createMediaStreamSource(voice.stream);
    voice.processor = new AudioWorkletNode(voice.audio, 'benchy-pcm-capture', {numberOfInputs:1,numberOfOutputs:1,outputChannelCount:[1]});
    voice.mute = voice.audio.createGain(); voice.mute.gain.value = 0;
    voice.processor.port.onmessage = message => {
      if (!voice.active || !voice.socket || voice.socket.readyState !== WebSocket.OPEN) return;
      // Speaker playback can leak into the microphone and be transcribed as the user's next turn.
      // Drop those frames while a Grok response is queued or playing.
      if (voiceReplyIsPlaying()) return;
      if (voice.ready) sendVoiceEvent({type:'input_audio_buffer.append', audio:b64FromBuffer(message.data)});
      else {
        voice.audioQueue.push(message.data);
        if (voice.audioQueue.length > 20) voice.audioQueue.shift();
      }
    };
    voice.source.connect(voice.processor); voice.processor.connect(voice.mute); voice.mute.connect(voice.audio.destination);
    button.disabled = false;
  } catch (error) {
    closeVoice('Could not start voice: ' + (error.message || 'please retry.'));
  }
}
function toggleVoice() {
  if (voice.active) closeVoice();
  else startVoice();
}
function togglePreview() {
  preview = !preview; document.body.classList.toggle('preview', preview);
  el('preview-toggle').setAttribute('aria-pressed', String(preview));
  setText('session-badge', preview ? 'PREVIEW DATA' : 'LIVE SESSION');
  el('probe-declaration-form').querySelector('button[type=submit]').disabled = preview;
  serialSeq = 0; serialEvents = []; renderSerial(); resetProbeDisplay(); renderBus(null);
  if (auto) { sampleProbes(); sampleBus(); }
  pollSerial();
}

async function saveNewCapture(event) {
  event.preventDefault();
  if (captureBusy || preview) return;
  const payload = {lab_port:el('lab-port').value, dut_port:el('dut-port').value,
    label:el('capture-label').value.trim(), note:el('capture-note').value};
  if (!payload.lab_port || !payload.label) return;
  captureBusy = true; el('save-capture').disabled = true;
  setText('save-capture-status', 'Capturing physical inputs and device output…');
  try {
    const response = await fetch('/api/records', {method:'POST',
      headers:{'Content-Type':'application/json','X-Benchy-Local':'1'}, body:JSON.stringify(payload)});
    const record = await response.json();
    if (!response.ok) throw Error(record.error || 'Capture failed');
    setText('save-capture-status', 'Saved “' + record.title + '” on this computer' +
      (record.capture_errors.length ? ' · partial capture; review recorded errors below.' : ' · selected as After below.'));
    await window.BenchyRecords.selectSaved(record.id);
  } catch (error) { setText('save-capture-status', 'Not saved: ' + error.message); }
  finally { captureBusy = false; renderFreshness(); if (auto) sampleProbes(); }
}

el('save-capture-form').addEventListener('submit', saveNewCapture);
el('preview-toggle').addEventListener('click', togglePreview);
el('voice-toggle').addEventListener('click', toggleVoice);
el('refresh-button').addEventListener('click', async () => { await loadHarness(); await Promise.all([loadPorts(), loadCode()]); if (auto) { sampleProbes(); sampleBus(); } pollSerial(); });
for (const kind of ['lab', 'dut']) el(kind + '-port').addEventListener('change', event => {
  localStorage.setItem('benchos-' + kind + '-port', event.target.value);
  if (kind === 'dut') { serialSeq = 0; serialEvents = []; renderSerial(); pollSerial(); }
  if (kind === 'lab') { resetProbeDisplay(); renderBus(null); if (auto) { sampleProbes(); sampleBus(); } }
});
el('sample-probes').addEventListener('click', sampleProbes);
el('sample-bus').addEventListener('click', sampleBus);
el('sample-taps').addEventListener('click', sampleBus);
el('export-taps').addEventListener('click', () => { if (latestTaps) download('benchy-digital-taps.json', latestTaps); });
el('auto-sample').addEventListener('click', () => { auto = !auto; el('auto-sample').setAttribute('aria-pressed', String(auto)); setText('auto-sample', auto ? 'Live: on' : 'Live: off'); if (auto) { sampleProbes(); sampleBus(); } });
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
loadVoiceStatus();
loadHarness().then(() => Promise.all([loadPorts(), loadCode()])).then(() => {
  renderAssessment(); sampleProbes(); sampleBus(); pollSerial();
  setInterval(() => { if (auto) sampleProbes(); }, 5000);
  setInterval(() => { if (auto) sampleBus(); }, 9000);
  setInterval(pollSerial, 2400);
  setInterval(loadPorts, 15000);
  setInterval(renderFreshness, 1000);
});
