const el = (id) => document.getElementById(id);
const names = ['P1', 'P2', 'P3'];
const model = window.BenchyModel;
let probeHistory = {};
let harness = null, latestSample = null, latestBus = null, latestTaps = null, inventory = null;
let preview = false, auto = true, probeBusy = false, busBusy = false, serialBusy = false, serialPaused = false;
let captureBusy = false;
let serialSeq = 0, serialEvents = [], session = [];
let agentConfigured = false;
const agentState = {threadId:null, messages:[], active:false, aborter:null, recognition:null, voiceTurn:false};
const voiceTranscript = new window.BenchyVoiceTranscript();
const agentFlash = {plan:null, ready:false, running:false, lastResult:null};
const voice = {micMuted:false, awaitingToolReply:false, active:false, ready:false, responseActive:false, socket:null, stream:null, audio:null, source:null, processor:null, mute:null, playbackAt:0, playbackTimer:null, players:new Set(), pendingTools:[], toolRun:false, userDraft:null, assistantDraft:null, aborter:null, generation:0, audioQueue:[], tools:[]};
try {
  const savedAgent = JSON.parse(localStorage.getItem('benchy-codex-chat-v1') || '{}');
  agentState.threadId = typeof savedAgent.threadId === 'string' ? savedAgent.threadId : null;
  agentState.messages = [];
  // Keep the Codex thread for continuity, but discard cached message text on reload.
  localStorage.setItem('benchy-codex-chat-v1', JSON.stringify({threadId:agentState.threadId}));
} catch {}
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
  setText('dut-port-label', board);
  for (const name of names) {
    const item = harness.probes[name], key = name.toLowerCase();
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
  el('signals-link').href = monitor.state === 'connected' ? '#bus' : '#digital-taps';
  setText('signals-nav-label', monitor.state === 'connected' ? 'Bus activity' : 'Signal taps');
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
  } catch (error) { setText('coverage-description', 'Harness unavailable: ' + error.message); }
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
      if (kind === 'dut' && previous !== select.value) {
        serialSeq = 0; serialEvents = []; latestTaps = null;
        renderSerial(); renderTaps(null);
      }
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
  const {comparisons, missing:missingComparisons, changing} = model.compareTelemetry(
    sample, preview ? [] : serialEvents, preview ? [] : harness && harness.telemetry_checks || []);
  const disagreement = comparisons.find(item => item.delta > Number(item.rule.max_delta_v));
  if (disagreement) return {state:'fail', label:'DUT REPORT DISAGREES', title:disagreement.rule.field + ' differs from ' + disagreement.rule.probe + '.',
    detail:'DUT serial claims ' + disagreement.claimed.toFixed(3) + ' V; S3 measured ' + disagreement.physical.toFixed(3) + ' V at the declared net. Difference ' + disagreement.delta.toFixed(3) + ' V exceeds ' + Number(disagreement.rule.max_delta_v).toFixed(3) + ' V.',
    next:'Check ADC scaling, selected pin, and report logic. Repeat with a controlled change at the sensor.'};
  const busIsFresh = latestBus && !preview && model.isFresh(latestBus.timestamp) && Math.abs(Date.parse(latestBus.timestamp) - Date.parse(sample.timestamp)) < 15000;
  const tapsAreFresh = latestTaps && !preview && model.isFresh(latestTaps.timestamp) && Math.abs(Date.parse(latestTaps.timestamp) - Date.parse(sample.timestamp)) < 15000;
  const output = !preview && model.activityVerdict(harness, latestTaps);
  if (output && output.state === 'fail') return {state:'fail', label:'OUTPUT DISAGREES WITH REPORT', title:'Measured output does not match.',
    detail:output.detail, next:'Check the output firmware and the declared sense connection; repeat under the same steady condition.'};
  const tapTargetMissed = tapsAreFresh && (latestTaps.expectations || []).find(item => item.state === 'fail');
  if (tapTargetMissed) return {state:'fail', label:'DIGITAL TARGET MISSED', title:tapTargetMissed.net + ' has unexpected activity.',
    detail:tapTargetMissed.detail, next:'Check the declared signal node and the sense branch, then capture again. This observation alone does not identify a faulty component.'};
  const endpointMismatch = tapsAreFresh && (latestTaps.comparisons || []).find(item => item.assessment === 'activity_mismatch');
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
  if (changing.length) return {state:'unknown', label:'INPUT CHANGING', title:'Hold the input steady.',
    detail:changing.join(', ') + ' changed across nearby device reports. Sequential samples cannot establish a disagreement during that change.',
    next:'Hold this condition for a few seconds, then compare the readings again.'};
  if (output && output.state !== 'pass') return {state:'unknown', label:'OUTPUT CHECK INCOMPLETE', title:'Awaiting stable output evidence.',
    detail:output.detail, next:'Keep the input steady and the device stream available, then sample taps.'};
  if (missingComparisons.length) return {state:'unknown', label:'COMPARISON INCOMPLETE', title:'Awaiting all declared fields.',
    detail:'Fresh paired evidence is missing for ' + missingComparisons.join(', ') + '. ' + comparisons.length + ' other comparison(s) matched within tolerance.',
    next:'Keep the device stream running and the input steady, then repeat the sample.'};
  if (comparisons.length) return {state:'pass', label:'REPORTS AGREE WITH PROBES', title:'Independent readings agree.', detail:comparisons.length + ' declared serial field' + (comparisons.length === 1 ? '' : 's') + ' matched fresh S3 probe readings within configured tolerance.' + (output ? ' ' + output.detail : ''), next:'Change one input or introduce a reversible fault, then capture both sources again.'};
  if (output && output.state === 'pass' && !checks.length) return {state:'pass', label:'OUTPUT MATCHES REPORTED STATE', title:'Declared output check passed.', detail:output.detail, next:'This checks the drive signal; confirm the physical load responds.'};
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
function timelineTitle(item) {
  if (item.kind === 'visual') return 'VISUAL · ' + item.title;
  if (item.kind === 'visual_analysis') return 'VISUAL ANALYSIS · ' + item.title;
  if (item.kind === 'probe') return 'PROBE · ' + item.title;
  return (item.manual ? 'CAPTURE · ' : '') + item.title;
}
function timelineDetail(item) {
  if (item.detail) return item.detail;
  if (item.sample && Array.isArray(item.sample.readings)) return item.sample.readings.map(row => row.probe).join(' + ');
  return '';
}
function pushTimeline(entry) {
  session.push({time:Date.now(), state:entry.state || 'info', title:entry.title, kind:entry.kind || '', detail:entry.detail || '', manual:false});
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
    const title = document.createElement('strong'); title.textContent = timelineTitle(item);
    const probes = document.createElement('span'); probes.className = 'timeline-probe'; probes.textContent = timelineDetail(item);
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
  for (const item of [...(sample && sample.expectations || []), ...(sample && sample.activity_checks && sample.activity_checks.checks || [])]) {
    const row = document.createElement('p');
    const label = document.createElement('strong'); label.textContent = item.tap + ' · ' + item.state.toUpperCase() + ': ';
    row.append(label, document.createTextNode(item.detail)); comparisons.append(row);
  }
  setText('digital-tap-status', sample
    ? 'S3 PHYSICAL · ' + sample.window_ms + ' ms · ' + timeLabel(sample.timestamp) + ' · counts are approximate'
    : 'Awaiting capture. Pending connections are excluded from diagnosis.');
  el('export-taps').disabled = !sample;
  renderCoverage(); renderAssessment();
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
    const dutPort = el('dut-port').value;
    const response = await fetch((hasTaps ? '/api/taps?' : '/api/bus?') + new URLSearchParams({lab_port:port,dut_port:dutPort,duration_ms:harness.activity_checks && harness.activity_checks.length ? '2000' : '1000'}), {cache:'no-store'});
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Bus sample failed');
    if (port === el('lab-port').value && dutPort === el('dut-port').value && !preview) {
      const freshEvents = data.condition_serial_events || [];
      if (freshEvents.length) {
        const seen = new Set(serialEvents.map(event => event.seq));
        serialEvents.push(...freshEvents.filter(event => !seen.has(event.seq)));
        serialEvents = serialEvents.slice(-400);
        serialSeq = Math.max(serialSeq, ...freshEvents.map(event => event.seq));
        renderSerial();
      }
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
function saveAgentChat() {
  try { localStorage.setItem('benchy-codex-chat-v1', JSON.stringify({threadId:agentState.threadId})); } catch {}
}
function renderAgentChat() {
  const target = el('agent-transcript'); target.replaceChildren();
  if (!agentState.messages.length) {
    const empty = document.createElement('p'); empty.className = 'empty-state';
    empty.textContent = 'Describe the symptom in your own words. Benchy can inspect project files and, when connected, take read-only physical measurements. Start voice to talk naturally with Benchy.';
    target.append(empty); return;
  }
  for (const message of agentState.messages) {
    const isVoice = message.source === 'grok';
    const node = document.createElement(isVoice ? 'div' : 'article');
    node.className = isVoice ? 'voice-turn' : 'agent-message'; node.dataset.role = message.role;
    const label = document.createElement(isVoice ? 'strong' : 'span');
    if (!isVoice) label.className = 'agent-message-label';
    label.textContent = message.role === 'user' ? 'You' : isVoice ? 'Grok' : 'Benchy';
    const body = document.createElement('span'); body.textContent = message.text || '';
    if (message.photoCount) body.textContent += ` · ${message.photoCount} photo${message.photoCount === 1 ? '' : 's'} attached as visual context`;
    node.append(label, body); target.append(node);
  }
  target.scrollTop = target.scrollHeight;
}
function setAgentStatus(message) { setText('agent-status', message); }
async function refreshAgentDiff() {
  setText('agent-diff-status', 'Loading current working-tree diff…');
  try {
    const response = await fetch('/api/agent/diff', {cache:'no-store'}), data = await response.json();
    if (!response.ok) throw Error(data.error || 'Diff unavailable');
    setText('agent-diff', data.empty ? 'No tracked code changes in the working tree.' : data.diff + (data.truncated ? '\n\n[Diff truncated at 200,000 characters.]' : ''));
    setText('agent-diff-status', data.empty ? 'No tracked changes.' : (data.truncated ? 'Showing first 200,000 characters.' : 'Current uncommitted tracked changes · read only'));
  } catch (error) { setText('agent-diff-status', 'Could not load diff: ' + error.message); }
}
function updateFlashButton() {
  const authorized = agentFlash.ready && el('agent-wiring-confirmed').checked &&
    el('agent-flash-phrase').value.trim() === 'FLASH' && !agentFlash.running;
  el('agent-flash-confirm').disabled = !authorized;
}
async function openFlashDialog() {
  if (agentFlash.running || agentState.active) return;
  el('agent-flash-dialog').showModal(); agentFlash.ready = false; agentFlash.plan = null;
  el('agent-wiring-confirmed').checked = false; el('agent-flash-phrase').value = '';
  el('agent-flash-confirm').disabled = true; el('agent-send-flash-result').hidden = true;
  setText('agent-flash-result', ''); setText('agent-flash-plan-status', 'Checking the declared DUT and matching USB identity…');
  setText('agent-flash-plan', 'Loading flash plan…');
  try {
    const response = await fetch('/api/agent/flash-plan', {cache:'no-store'}), data = await response.json();
    if (!response.ok || !data.ok) throw Error(data.error || 'The declared DUT is not ready to flash.');
    agentFlash.plan = data; agentFlash.ready = true;
    setText('agent-flash-plan', JSON.stringify(data, null, 2));
    setText('agent-flash-plan-status', 'Flash plan is ready. Upload rechecks the enrolled USB identity immediately before flashing.');
  } catch (error) {
    setText('agent-flash-plan-status', 'Cannot flash: ' + error.message);
    setText('agent-flash-plan', 'No upload has started.');
  }
  updateFlashButton();
}
async function runConfirmedFlash() {
  if (!agentFlash.ready || agentFlash.running || !el('agent-wiring-confirmed').checked || el('agent-flash-phrase').value.trim() !== 'FLASH') return;
  agentFlash.running = true; updateFlashButton(); el('agent-send-flash-result').hidden = true;
  setText('agent-flash-plan-status', 'Building firmware and uploading to the declared DUT. Keep both boards connected…');
  setText('agent-flash-result', 'Working…');
  try {
    const response = await fetch('/api/agent/flash', {method:'POST', cache:'no-store',
      headers:{'Content-Type':'application/json','X-Benchy-Local':'1'},
      body:JSON.stringify({confirmation:'FLASH_DECLARED_DUT', wiring_confirmed:true})});
    const data = await response.json(); agentFlash.lastResult = data;
    setText('agent-flash-result', JSON.stringify(data, null, 2));
    setText('agent-flash-plan-status', response.ok && data.ok ? 'Build/upload workflow finished. Review its physical post-check results below.' : 'Build/upload did not fully pass. Review the recorded result below.');
    el('agent-send-flash-result').hidden = false;
    refreshAgentDiff(); loadCode();
  } catch (error) {
    agentFlash.lastResult = {ok:false,error:error.message};
    setText('agent-flash-result', error.message || 'The flash request failed.');
    setText('agent-flash-plan-status', 'Flash request failed. Confirm the result before retrying.');
    el('agent-send-flash-result').hidden = false;
  } finally { agentFlash.running = false; updateFlashButton(); }
}
function assistantTextFromEvent(event) {
  if (!event || typeof event !== 'object') return null;
  if (typeof event.delta === 'string' && /agent.?message|output.?text/i.test(event.type || '')) return {delta:event.delta};
  const item = event.item && typeof event.item === 'object' ? event.item : null;
  if (item && /agent.?message/i.test(item.type || '') && typeof item.text === 'string') return {text:item.text};
  if (event.type === 'item.completed' && item && typeof item.text === 'string' && item.type === 'agent_message') return {text:item.text};
  return null;
}
function describeAgentEvent(event) {
  const type = String(event?.type || '').toLowerCase();
  const item = event?.item || {};
  if (type.includes('mcp') || String(item.type || '').toLowerCase().includes('mcp')) return 'Using Benchy measurement tools…';
  if (type.includes('command') || String(item.type || '').toLowerCase().includes('command')) return 'Inspecting or building the project…';
  if (type.includes('filechange') || type.includes('file_change')) return 'Updating project files…';
  if (type.includes('started')) return 'Benchy is investigating…';
  return null;
}
async function loadAgentStatus() {
  try {
    const response = await fetch('/api/agent/status', {cache:'no-store'}), data = await response.json();
    agentConfigured = Boolean(data.configured); el('agent-send').disabled = !agentConfigured; el('agent-flash-open').disabled = false;
    if (data.configured && data.gemini_configured) setAgentStatus('Ready · code, hardware checks, and Gemini photo context available.');
    else if (data.configured) setAgentStatus('Ready · code and hardware checks available. Add GEMINI_API_KEY in .env to enable photo context.');
    else if (!data.codex_cli) setAgentStatus('Codex CLI is unavailable to the dashboard. Restart the dashboard from a signed-in Codex environment.');
    else setAgentStatus('Benchy tools are unavailable. Install the project MCP extra in this Python environment.');
  } catch { setAgentStatus('Could not check the local Codex runtime.'); }
  loadVoiceStatus();
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const button = el('agent-dictate'); button.disabled = !Recognition;
  setText('agent-dictation-status', Recognition ? 'Browser dictation ready.' : 'Dictation requires Chrome or Edge.');
}
async function sendAgentMessage(event, options = {}) {
  if (event) event.preventDefault();
  const input = el('agent-message');
  if (voice.active && !options.fromVoice && options.message == null) {
    const voiceText = input.value.trim();
    if (!voiceText) return;
    if (voice.toolRun) { setAgentStatus('Benchy is checking the project and evidence. Wait for the answer before sending another message.'); return; }
    if (!voice.ready) { setAgentStatus('Grok is still connecting. Try sending that again in a moment.'); return; }
    if (voice.responseActive || voiceReplyIsPlaying()) interruptVoice();
    input.value = '';
    if (agentPhotos.length) {
      const result = await sendAgentMessage(null, {message:voiceText, fromVoice:true, photos:agentPhotos.map(photo => photo.dataUrl)});
      clearAgentPhotos();
      sendVoiceEvent({type:'conversation.item.create', item:{type:'message', role:'user', content:[{type:'input_text', text:'Project tool result: ' + result + '. Explain the actual result in your own voice without narrating an internal handoff. The attached photo is visual context only.'}]}});
      sendVoiceEvent({type:'response.create'});
      return;
    }
    sendVoiceText(voiceText); return;
  }
  const text = String(options.message ?? input.value).trim();
  if (!text || agentState.active || (!options.fromVoice && el('agent-send').disabled)) return '';
  if (options.message == null) input.value = '';
  agentState.active = true;
  const showCodexExchange = !options.fromVoice;
  if (showCodexExchange) {
    agentState.messages.push({role:'user', text});
    renderAgentChat();
  }
  const reply = {role:'assistant', text:''};
  const photos = options.photos || agentPhotos.map(photo => photo.dataUrl);
  if (showCodexExchange && photos.length) agentState.messages[agentState.messages.length - 1].photoCount = photos.length;
  if (showCodexExchange) agentState.messages.push(reply);
  if (showCodexExchange) saveAgentChat();
  el('agent-send').disabled = true; el('agent-flash-open').disabled = true; el('agent-stop').hidden = false;
  setAgentStatus(options.fromVoice ? 'Checking project files and hardware evidence…' : 'Benchy is investigating…');
  const controller = new AbortController(); agentState.aborter = controller; let requestError = false, requestErrorMessage = '';
  try {
    const response = await fetch('/api/agent/chat', {method:'POST', cache:'no-store', signal:controller.signal,
      headers:{'Content-Type':'application/json','X-Benchy-Local':'1'},
      body:JSON.stringify({message:text, thread_id:agentState.threadId, photos})});
    if (!response.ok) { const error = await response.json(); throw Error(error.error || 'Could not start the Codex agent.'); }
    const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = '';
    const consume = (frame) => {
      const line = frame.split('\n').find(part => part.startsWith('data:'));
      if (!line) return;
      let data; try { data = JSON.parse(line.slice(5).trim()); } catch { return; }
      if (data.thread_id) { agentState.threadId = data.thread_id; saveAgentChat(); }
      if (data.kind === 'status') { setAgentStatus(data.message); return; }
      if (data.kind === 'error') { requestError = true; requestErrorMessage = data.message || 'The Codex request failed.'; if (showCodexExchange) { agentState.messages.push({role:'error', text:requestErrorMessage}); renderAgentChat(); } return; }
      if (data.kind === 'complete') return;
      if (data.kind !== 'codex_event') return;
      const event = data.event || {}, extracted = assistantTextFromEvent(event), status = describeAgentEvent(event);
      if (status) setAgentStatus(status);
      if (extracted?.delta) reply.text += extracted.delta;
      if (extracted?.text) reply.text = extracted.text;
      if (extracted && showCodexExchange) { renderAgentChat(); saveAgentChat(); }
    };
    while (true) {
      const {value, done} = await reader.read(); buffer += decoder.decode(value || new Uint8Array(), {stream:!done});
      const frames = buffer.split('\n\n'); buffer = frames.pop() || '';
      for (const frame of frames) consume(frame);
      if (done) break;
    }
    if (buffer.trim()) consume(buffer);
    if (!reply.text) {
      if (showCodexExchange) {
        const replyIndex = agentState.messages.indexOf(reply);
        if (replyIndex >= 0) agentState.messages.splice(replyIndex, 1);
        if (!requestError) agentState.messages.push({role:'error', text:'The agent finished without returning a message. Check the dashboard terminal for a startup or authentication error.'});
      }
    }
    if (showCodexExchange) { renderAgentChat(); saveAgentChat(); }
    if (photos.length && !requestError) clearAgentPhotos();
    loadCode(); refreshAgentDiff();
    if (agentState.threadId && !requestError) setAgentStatus('Ready · Benchy is ready for another question.');
    else if (requestError) setAgentStatus('Request ended with an error.');
  } catch (error) {
    if (error.name !== 'AbortError') {
      requestError = true; requestErrorMessage = error.message || 'The Codex request failed.';
      if (showCodexExchange) {
        const replyIndex = agentState.messages.indexOf(reply);
        if (replyIndex >= 0 && !reply.text) agentState.messages.splice(replyIndex, 1);
        agentState.messages.push({role:'error', text:error.message || 'The Codex request failed.'});
        renderAgentChat(); saveAgentChat();
      }
      setAgentStatus('Request ended with an error.');
    } else {
      if (showCodexExchange) {
        const replyIndex = agentState.messages.indexOf(reply);
        if (replyIndex >= 0 && !reply.text) agentState.messages.splice(replyIndex, 1);
        renderAgentChat(); saveAgentChat();
      }
      setAgentStatus('Stopped.');
    }
  } finally {
    agentState.active = false; agentState.aborter = null; agentState.voiceTurn = false;
    el('agent-stop').hidden = true; el('agent-send').disabled = !agentConfigured; el('agent-flash-open').disabled = false;
  }
  if (requestError) return 'The project task failed. The dashboard shows the detailed error. Do not present this as a successful investigation.';
  return reply.text || (
    'The project task finished without a response. Check the local dashboard terminal for details.');
}
let agentPhotos = [];
async function prepareAgentPhoto(file) {
  if (!file || !file.type.startsWith('image/')) throw Error('Choose an image file.');
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.82));
  if (!blob || blob.size > 5 * 1024 * 1024) throw Error('A photo is larger than 5 MB after resizing.');
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(blob);
  });
  return {name:file.name, blob, dataUrl, url:URL.createObjectURL(blob)};
}
function renderAgentPhotos() {
  const root = el('agent-image-previews'); root.replaceChildren();
  agentPhotos.forEach((photo, index) => {
    const figure = document.createElement('figure'); figure.className = 'agent-photo-thumb';
    const image = document.createElement('img'); image.src = photo.url; image.alt = photo.name || `Attached photo ${index + 1}`;
    const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'small-button'; remove.textContent = 'Remove';
    remove.addEventListener('click', () => { URL.revokeObjectURL(photo.url); agentPhotos.splice(index, 1); renderAgentPhotos(); });
    figure.append(image, remove); root.append(figure);
  });
  setText('agent-image-status', agentPhotos.length ? `${agentPhotos.length} photo${agentPhotos.length === 1 ? '' : 's'} queued for Gemini description · maximum 4` : 'Gemini turns photos into text context; electrical facts still come from probes.');
  el('agent-image-input').disabled = agentPhotos.length >= 4;
}
function clearAgentPhotos() {
  for (const photo of agentPhotos) URL.revokeObjectURL(photo.url);
  agentPhotos = []; renderAgentPhotos(); el('agent-image-input').value = '';
}
el('agent-image-input').addEventListener('change', async event => {
  const files = [...event.target.files || []]; event.target.value = '';
  try {
    for (const file of files) {
      if (agentPhotos.length >= 4) break;
      agentPhotos.push(await prepareAgentPhoto(file));
    }
    renderAgentPhotos();
  } catch (error) { setText('agent-image-status', error.message || 'Could not prepare that photo.'); }
});
function startAgentDictation() {
  if (agentState.recognition) { agentState.recognition.stop(); return; }
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) return;
  const recognition = new Recognition(); agentState.recognition = recognition;
  recognition.lang = navigator.language || 'en-US'; recognition.interimResults = true; recognition.continuous = false;
  let finalText = '';
  el('agent-dictate').setAttribute('aria-pressed', 'true'); setText('agent-dictate', 'Listening…');
  setText('agent-dictation-status', 'Speech is processed by your browser’s speech service.');
  recognition.onresult = event => {
    let interim = '';
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const transcript = event.results[index][0].transcript;
      if (event.results[index].isFinal) finalText += transcript + ' '; else interim += transcript;
    }
    el('agent-message').value = (finalText + interim).trim();
  };
  recognition.onerror = event => setText('agent-dictation-status', 'Speech input error: ' + event.error);
  recognition.onend = () => {
    agentState.recognition = null; el('agent-dictate').setAttribute('aria-pressed', 'false'); setText('agent-dictate', '🎙 Speak');
    if (finalText.trim()) { agentState.voiceTurn = true; el('agent-chat-form').requestSubmit(); }
    else setText('agent-dictation-status', 'No speech recognized. You can type or try again.');
  };
  recognition.start();
}
function syncVoiceMicrophone() {
  const enabled = !voice.micMuted && !voice.toolRun && !voice.awaitingToolReply;
  if (voice.stream) for (const track of voice.stream.getAudioTracks()) track.enabled = enabled;
  el('agent-mic-mute').setAttribute('aria-pressed', String(voice.micMuted));
  setText('agent-mic-mute', voice.micMuted ? 'Unmute microphone' : 'Mute microphone');
}
function toggleVoiceMicrophone() {
  voice.micMuted = !voice.micMuted;
  if (voice.micMuted && voice.ready) sendVoiceEvent({type:'input_audio_buffer.clear'});
  syncVoiceMicrophone();
}
function voiceState(state, message) {
  el('agent-voice-panel').dataset.state = state;
  setText('agent-voice-status', message);
}
function renderVoiceTurn(role, text, draft = false, itemId = null) {
  const row = draft ? voiceTranscript.update(agentState.messages, role, text, itemId) :
    {role, text, source:'grok'};
  if (!row) return;
  if (!draft) agentState.messages.push(row);
  else if (role === 'user') voice.userDraft = row;
  else voice.assistantDraft = row;
  renderAgentChat();
}
function finishVoiceDraft(role) {
  voiceTranscript.begin(role);
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
  updateVoiceInterrupt();
}
function voiceReplyIsPlaying() {
  return Boolean(voice.audio && voice.playbackAt > voice.audio.currentTime + 0.04);
}
function updateVoiceInterrupt() {
  const button = el('agent-interrupt');
  if (button) button.hidden = !voice.active || !(voice.responseActive || voiceReplyIsPlaying());
}
function interruptVoice() {
  if (!voice.active) return;
  if (voice.responseActive) sendVoiceEvent({type:'response.cancel'});
  voice.responseActive = false;
  voice.awaitingToolReply = false; syncVoiceMicrophone();
  finishVoiceDraft('assistant');
  stopVoicePlayback();
  updateVoiceInterrupt();
  voiceState('listening', 'Interrupted · speak or type when you’re ready.');
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
    const button = el('agent-voice-toggle'); button.disabled = !data.configured;
    voice.instructions = data.instructions || 'You are Grok, the hardware debugging partner in Benchy. Speak concisely in first person without narrating routing or backend names. Use work_on_project to inspect and edit source, prepare requested firmware fixes, run builds, and take read-only measurements. Read-only probes do not prevent code edits. Wait for the actual tool result before claiming success. Uploads require the separate reviewed Build & flash action. Never invent readings or suggest unknown voltages on probes. Photos are context; Preview readings are synthetic.';
    document.body.dataset.voiceConfigured = String(Boolean(data.configured));
    if (data.configured) voiceState('idle', 'Ready · voice conversation and interruption available.');
    else voiceState('error', 'Set XAI_API_KEY before launching the dashboard to enable voice.');
  } catch { voiceState('error', 'Voice setup status is unavailable.'); }
}
async function workOnProjectFromVoice(args) {
  if (!args || typeof args !== 'object' || agentState.active)
    return 'A project task is already running. Wait for it to finish, then ask again.';
  const problem = String(args.problem || '').slice(0, 3000);
  const context = String(args.context || '').slice(0, 3000);
  const investigation = String(args.investigation || '').slice(0, 2000);
  if (!problem || !investigation) return 'The handoff did not include a clear problem and investigation request. Ask the user one clarifying question, then try again.';
  const message = [
    'The user is working with Grok in the Benchy voice UI. Complete the requested project task, including actual local source edits when the user requests a firmware or code fix. Hardware measurements are read-only; source files are editable. Never upload firmware. Give a concise first-person result for Grok to explain aloud, without narrating backend names or handoffs. Only claim edits that were actually saved, and direct the user to review and Build & flash when relevant.',
    'User problem: ' + problem,
    'Conversation context and what has already been tried: ' + (context || 'None supplied.'),
    'Requested investigation or source change: ' + investigation,
    'Current dashboard context (may be stale; take fresh measurements for explicit test requests): ' + JSON.stringify(voiceContext()),
  ].join('\n\n');
  // Bound context to the server's message limit.
  return await sendAgentMessage(null, {message:message.slice(0, 8000), fromVoice:true});
}
function sendVoiceText(text) {
  if (!voice.active || !voice.ready || !text.trim()) return;
  renderVoiceTurn('user', text.trim());
  sendVoiceEvent({type:'conversation.item.create', item:{type:'message', role:'user',
    content:[{type:'input_text', text:text.trim()}]}});
  sendVoiceEvent({type:'response.create'});
  voiceState('thinking', 'Grok is considering your message…');
}
function closeVoice(message = 'Conversation ended.') {
  if (!voice.active && !voice.stream && !voice.audio && !voice.socket) return;
  voice.active = false; voice.ready = false; voice.generation += 1;
  voice.responseActive = false;
  voice.userDraft = null; voice.assistantDraft = null; voiceTranscript.clear();
  voice.aborter?.abort(); voice.aborter = null;
  voice.pendingTools = []; voice.toolRun = false; voice.awaitingToolReply = false;
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
  el('agent-voice-toggle').setAttribute('aria-pressed', 'false');
  setText('agent-voice-button-label', 'Start conversation');
  voiceState(message.startsWith('Could not') || message.startsWith('Voice error') ? 'error' : 'idle', message);
  el('agent-voice-toggle').disabled = document.body.dataset.voiceConfigured !== 'true';
  el('agent-dictate').disabled = !(window.SpeechRecognition || window.webkitSpeechRecognition);
  updateVoiceInterrupt();
}
function sendVoiceEvent(event) {
  if (voice.socket && voice.socket.readyState === WebSocket.OPEN) voice.socket.send(JSON.stringify(event));
}
async function executePendingVoiceTools(generation) {
  if (voice.toolRun || !voice.pendingTools.length) return;
  voice.toolRun = true; voice.awaitingToolReply = true; syncVoiceMicrophone();
  sendVoiceEvent({type:'input_audio_buffer.clear'});
  voiceState('thinking', 'Checking project files and hardware evidence…');
  const calls = voice.pendingTools.splice(0), outputs = [];
  for (const call of calls) {
    let result;
    try {
      if (call.name !== 'work_on_project') throw Error('This project tool is unavailable. Restart the voice conversation.');
      const args = JSON.parse(call.arguments || '{}');
      result = await workOnProjectFromVoice(args);
    } catch (error) { result = {error:error.message || 'Tool call failed'}; }
    outputs.push({type:'conversation.item.create', item:{type:'function_call_output', call_id:call.call_id,
      output:typeof result === 'string' ? result : JSON.stringify(result)}});
  }
  voice.toolRun = false;
  if (!voice.active || generation !== voice.generation) return;
  for (const output of outputs) sendVoiceEvent(output);
  const waitMs = Math.max(0, (voice.playbackAt - (voice.audio?.currentTime || 0)) * 1000);
  if (waitMs) await new Promise(resolve => setTimeout(resolve, Math.min(waitMs + 30, 30_000)));
  if (voice.active && generation === voice.generation) {
    sendVoiceEvent({type:'response.create'});
    voiceState('thinking', 'Project task finished · preparing the spoken summary…');
  }
}
function handleVoiceEvent(event, generation) {
  if (!voice.active || generation !== voice.generation) return;
  if (event.type === 'session.created') {
    const snapshot = voiceContext();
    const instructions = (voice.instructions || 'You are Grok in Benchy. Use work_on_project for source edits and measurements. Keep uploads in the separate reviewed Build & flash action. Speak in first person without narrating internal routing.') +
      ' Include the user request, relevant conversation history, and current evidence in project tool calls. Gemini photo descriptions are fallible visual context, not electrical proof. P1, P2, and P3 are safe only for known 0–3.3 V signals with common ground. If physical placement may have changed, ask the user to confirm it before choosing new probe locations. If Preview is on, readings are synthetic. Current dashboard snapshot (source labels are authoritative): ' + JSON.stringify(snapshot);
    voice.tools.forEach(tool => { if (tool.name !== 'work_on_project') throw Error('Unexpected voice tool. Reload the dashboard before continuing.'); });
    sendVoiceEvent({type:'session.update', session:{
      modalities:['text','audio'], voice:'eve', instructions,
      turn_detection:{type:'server_vad'},
      audio:{input:{format:{type:'audio/pcm',rate:24000},transcription:{model:'grok-transcribe'}},
        output:{format:{type:'audio/pcm',rate:24000}},
      }, tools:voice.tools, tool_choice:'auto'
    }});
    voiceState('connecting', 'Connected · setting up the conversation…');
  } else if (event.type === 'session.updated') {
    voice.ready = true;
    for (const audio of voice.audioQueue.splice(0)) sendVoiceEvent({type:'input_audio_buffer.append', audio:b64FromBuffer(audio)});
    el('agent-voice-toggle').disabled = false;
    voiceState('listening', voice.micMuted ? 'Microphone muted · type to continue.' : 'Listening · speak naturally; click to stop.');
  } else if (event.type === 'conversation.item.input_audio_transcription.updated') {
    renderVoiceTurn('user', event.transcript || '', true, event.item_id);
  } else if (event.type === 'conversation.item.input_audio_transcription.completed') {
    renderVoiceTurn('user', event.transcript || '', true, event.item_id); finishVoiceDraft('user');
  } else if (event.type === 'response.output_audio_transcript.delta') {
    const current = voice.assistantDraft?.text || '';
    renderVoiceTurn('assistant', current + (event.delta || ''), true, event.item_id);
  } else if (event.type === 'response.output_audio_transcript.done') {
    if (event.transcript) renderVoiceTurn('assistant', event.transcript, true, event.item_id);
    finishVoiceDraft('assistant');
  } else if (event.type === 'response.output_audio.delta' || event.type === 'response.audio.delta') {
    if (event.delta) playVoiceAudio(event.delta);
    voiceState('speaking', 'Benchy is speaking · interrupt any time.');
    updateVoiceInterrupt();
  } else if (event.type === 'response.created') {
    voice.responseActive = true;
    updateVoiceInterrupt();
  } else if (event.type === 'input_audio_buffer.speech_started') {
    finishVoiceDraft('user');
    // Server VAD already interrupts an in-progress response. Sending a second
    // response.cancel here can race with response.done and make xAI report
    // "no active response found".
    voice.responseActive = false;
    finishVoiceDraft('assistant');
    stopVoicePlayback(); voiceState('listening', 'Listening…');
  } else if (event.type === 'response.function_call_arguments.done') {
    voice.pendingTools.push({name:event.name, arguments:event.arguments, call_id:event.call_id});
  } else if (event.type === 'response.done') {
    voice.responseActive = false;
    updateVoiceInterrupt();
    if (voice.pendingTools.length) executePendingVoiceTools(generation);
    else if (voiceReplyIsPlaying()) {
      const generationAtEnd = generation;
      const waitMs = Math.max(0, (voice.playbackAt - voice.audio.currentTime) * 1000);
      voiceState('speaking', 'Grok is finishing · speak after the reply to avoid microphone echo.');
      voice.playbackTimer = setTimeout(() => {
        voice.playbackTimer = null;
        if (voice.active && generationAtEnd === voice.generation) {
          voice.awaitingToolReply = false; syncVoiceMicrophone();
          voiceState('listening', voice.micMuted ? 'Microphone muted · type to continue.' : 'Listening · speak naturally; click to stop.');
        }
        updateVoiceInterrupt();
      }, waitMs + 40);
    } else {
      voice.awaitingToolReply = false; syncVoiceMicrophone();
      voiceState('listening', voice.micMuted ? 'Microphone muted · type to continue.' : 'Listening · speak naturally; click to stop.');
    }
  } else if (event.type === 'error') {
    const errorMessage = String(event.error?.message || 'check the xAI connection and retry.');
    // The response can finish between showing the interrupt button and the
    // cancel reaching the server. That is an expected race; preserve the
    // conversation and let the user continue.
    if (/no active response found/i.test(errorMessage)) {
      voice.responseActive = false;
      updateVoiceInterrupt();
      voiceState('listening', 'Listening · speak naturally; click to stop.');
      return;
    }
    closeVoice('Voice error · ' + errorMessage);
  }
}
async function startVoice() {
  const button = el('agent-voice-toggle'); button.disabled = true;
  el('agent-dictate').disabled = true;
  voiceState('connecting', 'Requesting microphone access…');
  button.setAttribute('aria-pressed', 'true'); setText('agent-voice-button-label', 'End conversation');
  voice.active = true; voice.generation += 1;
  voice.responseActive = false; updateVoiceInterrupt();
  const generation = voice.generation;
  try {
    if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode)
      throw Error('This browser does not support live microphone audio.');
    voice.stream = await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,
      noiseSuppression:true,autoGainControl:true}});
    syncVoiceMicrophone();
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
    if (!voice.tools.length) throw Error('No Benchy project tools are available. Check the dashboard setup.');
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
      if (voice.toolRun || voice.awaitingToolReply || voice.micMuted) return;
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
  if (auto) refreshMeasurements();
  pollSerial();
  renderFreshness();
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

let refreshBusy = false, lastAutomaticTaps = 0;
async function refreshMeasurements() {
  if (refreshBusy || captureBusy) return;
  refreshBusy = true;
  try {
    await pollSerial();
    if (auto) await sampleProbes();
    await pollSerial();
    if (auto && Date.now() - lastAutomaticTaps >= 8000) {
      await sampleBus(); lastAutomaticTaps = Date.now();
    }
  } finally { refreshBusy = false; }
}

el('save-capture-form').addEventListener('submit', saveNewCapture);
el('preview-toggle').addEventListener('click', togglePreview);
el('agent-chat-form').addEventListener('submit', sendAgentMessage);
el('agent-voice-toggle').addEventListener('click', toggleVoice);
el('agent-mic-mute').addEventListener('click', toggleVoiceMicrophone);
el('agent-interrupt').addEventListener('click', interruptVoice);
el('agent-stop').addEventListener('click', () => {
  fetch('/api/agent/stop', {method:'POST', headers:{'X-Benchy-Local':'1'}}).catch(() => {});
  agentState.aborter?.abort();
});
el('agent-dictate').addEventListener('click', startAgentDictation);
el('agent-new-chat').addEventListener('click', () => {
  if (agentState.active) return;
  if (voice.active) closeVoice('Voice conversation ended · new chat started.');
  agentState.threadId = null; agentState.messages = []; voiceTranscript.clear(); saveAgentChat(); renderAgentChat();
  setAgentStatus(agentConfigured ? 'New conversation ready.' : 'Waiting for the local debugging agent.');
});
el('agent-export-chat').addEventListener('click', () => download('benchy-debug-chat.json', {
  source:'benchy_conversation', exported_at:new Date().toISOString(), thread_id:agentState.threadId, messages:agentState.messages}));
el('agent-refresh-diff').addEventListener('click', refreshAgentDiff);
el('agent-flash-open').addEventListener('click', openFlashDialog);
el('agent-flash-close').addEventListener('click', () => el('agent-flash-dialog').close());
el('agent-flash-confirm').addEventListener('click', runConfirmedFlash);
el('agent-wiring-confirmed').addEventListener('change', updateFlashButton);
el('agent-flash-phrase').addEventListener('input', updateFlashButton);
el('agent-send-flash-result').addEventListener('click', () => {
  const result = agentFlash.lastResult || {};
  const review = {ok:result.ok, compile:result.compile, upload:result.upload, postflash:result.postflash, error:result.error};
  el('agent-flash-dialog').close();
  el('agent-message').value = 'A user-authorized build and flash attempt just completed. Review this result and explain whether it succeeded. If the hardware check is still inconclusive, use the smallest useful read-only Benchy measurement:\n' + JSON.stringify(review).slice(0, 5500);
  el('agent-chat-form').requestSubmit();
});
el('refresh-button').addEventListener('click', async () => { await loadHarness(); await Promise.all([loadPorts(), loadCode()]); if (auto) refreshMeasurements(); pollSerial(); });
for (const kind of ['lab', 'dut']) el(kind + '-port').addEventListener('change', event => {
  localStorage.setItem('benchos-' + kind + '-port', event.target.value);
  if (kind === 'dut') { serialSeq = 0; serialEvents = []; renderSerial(); pollSerial(); }
  if (kind === 'lab') { resetProbeDisplay(); renderBus(null); if (auto) refreshMeasurements(); }
});
el('sample-probes').addEventListener('click', sampleProbes);
el('sample-bus').addEventListener('click', sampleBus);
el('sample-taps').addEventListener('click', sampleBus);
el('export-taps').addEventListener('click', () => { if (latestTaps) download('benchy-digital-taps.json', latestTaps); });
el('auto-sample').addEventListener('click', () => { auto = !auto; el('auto-sample').setAttribute('aria-pressed', String(auto)); setText('auto-sample', auto ? 'Live: on' : 'Live: off'); if (auto) refreshMeasurements(); });
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

let visualSeen = {id:null, image:false, analysis:false};
let visualPoll = null;
let visualRun = false;
let visualBusy = false;

function showQr(svg) {
  const slot = el('visual-qr');
  if ((slot.dataset.svg || '') === (svg || '')) return;
  slot.dataset.svg = svg || '';
  slot.replaceChildren();
  if (!svg || !/^<svg[\s>]/i.test(svg) || /<script|on[a-z]+\s*=/i.test(svg)) {
    slot.hidden = true;
    return;
  }
  const holder = document.createElement('div');
  holder.innerHTML = svg;
  const node = holder.querySelector('svg');
  if (!node) { slot.hidden = true; return; }
  slot.hidden = false;
  slot.append(node);
}
function addVisualList(parent, title, rows, confidence) {
  if (!rows.length) return;
  const block = document.createElement('section');
  block.className = 'visual-block';
  const heading = document.createElement('h3');
  heading.textContent = title;
  const list = document.createElement('ul');
  list.className = 'visual-list';
  for (const row of rows) {
    const item = document.createElement('li');
    item.textContent = row.text;
    if (row.confidence) {
      const badge = document.createElement('span');
      badge.className = 'confidence';
      badge.textContent = row.confidence;
      item.append(badge);
    }
    list.append(item);
  }
  block.append(heading, list);
  if (confidence) block.dataset.confidence = confidence;
  parent.append(block);
}
function renderFindings(view) {
  const root = el('visual-findings');
  root.replaceChildren();
  const analysis = view.analysis;
  if (!analysis) return;
  const hardware = (analysis.observed_hardware || []).map(item => ({text:item.item, confidence:item.confidence}));
  const observations = (analysis.observations || []).map(item => ({text:item.observation, confidence:item.confidence}));
  addVisualList(root, 'OBSERVED HARDWARE', hardware);
  addVisualList(root, 'OBSERVATIONS', observations);
  if (!(analysis.possible_issues || []).length && !hardware.length && !observations.length) {
    const empty = document.createElement('p');
    empty.className = 'visual-note';
    empty.textContent = 'No visually supported findings in this photo.';
    root.append(empty);
  }
  for (const issue of analysis.possible_issues || []) {
    const card = document.createElement('article');
    card.className = 'hypothesis';
    const badge = document.createElement('span');
    badge.className = 'badge';
    badge.textContent = 'HYPOTHESIS · NOT ELECTRICALLY VERIFIED';
    const title = document.createElement('h3');
    title.textContent = issue.issue;
    const confidence = document.createElement('span');
    confidence.className = 'confidence';
    confidence.textContent = issue.confidence || '';
    card.append(badge, title, confidence);
    for (const note of issue.evidence || []) {
      const line = document.createElement('p');
      line.textContent = note;
      card.append(line);
    }
    root.append(card);
  }
  const strip = document.createElement('div');
  strip.className = 'evidence-strip';
  const visualText = observations.map(item => item.text).join(' ') || 'No visual observation yet.';
  const context = view.context || {};
  const probes = (context.expected_harness && context.expected_harness.probes) || {};
  const sourceText = Object.entries(probes).map(([name, probe]) => name + ' declared ' + (probe.state || 'unknown') + ' on ' + (probe.net || 'no net')).join(' · ') || 'No harness declaration loaded.';
  const physicalText = (view.physical_checks || []).map(item => item.summary).join(' · ') || 'No probe reading yet. Visual issues stay hypotheses.';
  for (const [label, text] of [['VISUAL', visualText], ['SOURCE', sourceText], ['PHYSICAL', physicalText]]) {
    const article = document.createElement('article');
    const heading = document.createElement('h3');
    heading.textContent = label;
    const body = document.createElement('p');
    body.textContent = text;
    article.append(heading, body);
    strip.append(article);
  }
  root.append(strip);
  if ((view.physical_checks || []).length) {
    const facts = document.createElement('section');
    facts.className = 'visual-block';
    const heading = document.createElement('h3');
    heading.textContent = 'PHYSICAL FACT';
    facts.append(heading);
    for (const check of view.physical_checks) {
      const row = document.createElement('div');
      row.className = 'fact-row';
      const text = document.createElement('span');
      text.textContent = check.summary;
      const mark = document.createElement('span');
      mark.className = 'fact-mark';
      mark.textContent = '✓';
      mark.title = 'Measured by Benchy';
      row.append(text, mark);
      facts.append(row);
    }
    const note = document.createElement('p');
    note.className = 'visual-note';
    note.textContent = 'The check mark means a probe reading was taken. It does not turn a visual hypothesis into a verified fault.';
    facts.append(note);
    root.append(facts);
  }
  const checks = analysis.recommended_checks || [];
  if (checks.length) {
    const block = document.createElement('section');
    block.className = 'visual-block';
    const heading = document.createElement('h3');
    heading.textContent = 'RECOMMENDED VERIFICATION';
    block.append(heading);
    for (const check of checks) {
      if (!check.supported) {
        const line = document.createElement('p');
        line.className = 'unsupported';
        line.textContent = (check.measurement || 'Suggestion') + ' — Benchy cannot run this check. ' + (check.reason || '');
        block.append(line);
        continue;
      }
      const row = document.createElement('div');
      row.className = 'check-row';
      const copy = document.createElement('p');
      copy.textContent = check.reason;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'small-button';
      button.textContent = check.label;
      button.addEventListener('click', () => runVisualCheck(check.measurement, check.target || '', button));
      row.append(copy, button);
      block.append(row);
    }
    root.append(block);
  }
  addVisualList(root, 'LIMITATIONS', (analysis.limitations || []).map(text => ({text})));
}
function noteVisual(view) {
  const id = view.started_at || null;
  if (visualSeen.id !== id) visualSeen = {id, image:false, analysis:false};
  if (view.image_ready && !visualSeen.image) {
    pushTimeline({kind:'visual', state:'info', title:'DUT image received', detail:'VISUAL'});
    visualSeen.image = true;
  }
  if (view.status === 'complete' && view.analysis && !visualSeen.analysis) {
    const issue = view.analysis.possible_issues && view.analysis.possible_issues[0]
      ? view.analysis.possible_issues[0].issue : 'Visual inspection complete';
    pushTimeline({kind:'visual_analysis', state:'info', title:issue, detail:'VISUAL ANALYSIS'});
    visualSeen.analysis = true;
  }
}
function renderVisual(view) {
  setText('visual-status', view.status_label || 'READY');
  const message = el('visual-message');
  if (!view.active) {
    message.textContent = view.availability && view.availability.message
      ? view.availability.message
    : (view.status === 'expired'
        ? 'This capture link has expired. Start again for a new QR code.'
        : 'Start a temporary phone capture link. Add up to four photos, then include them with your next Benchy question.');
  } else if (view.error) message.textContent = view.error;
  else if (view.status === 'waiting') message.textContent = (view.availability && view.availability.warning)
    ? view.availability.warning
    : 'Scan with your phone, then photograph the device under test.';
  else if (view.status === 'uploaded') message.textContent = 'Image received. Analysis will begin automatically.';
  else if (view.status === 'analyzing') message.textContent = 'Analyzing hardware from the photo and the declared harness.';
  else if (view.status === 'complete') message.textContent = `${view.photo_count || 1} photo${view.photo_count === 1 ? '' : 's'} ready. Ask Benchy a question to include them as visual context.`;
  else message.textContent = 'Photo context is ready.';
  showQr(view.qr_svg);
  el('visual-scan').hidden = !view.qr_svg;
  const photo = el('visual-photo');
  if (view.image_ready) {
    const next = '/api/visual/session/image?rev=' + encodeURIComponent(view.revision || 0);
    if (photo.dataset.source !== next) { photo.dataset.source = next; photo.src = next; }
    photo.hidden = false;
  } else { photo.hidden = true; photo.removeAttribute('src'); delete photo.dataset.source; }
  renderFindings(view);
  noteVisual(view);
  const keepPolling = view.active && view.status !== 'complete' && view.status !== 'error';
  if (keepPolling && !visualPoll) visualPoll = setInterval(() => { refreshVisual().catch(() => {}); }, 1000);
  if (!keepPolling && visualPoll) { clearInterval(visualPoll); visualPoll = null; }
}
async function refreshVisual() {
  const response = await fetch('/api/visual/session');
  const view = await response.json();
  if (!response.ok) throw Error(view.error || 'Visual inspection is unavailable.');
  renderVisual(view);
  return view;
}
async function startVisual() {
  if (visualBusy) return;
  visualBusy = true;
  el('visual-start').disabled = true;
  try {
    const response = await fetch('/api/visual/session', {method:'POST',
      headers:{'Content-Type':'application/json','X-Benchy-Local':'1'}, body:'{}'});
    const view = await response.json();
    if (!response.ok) throw Error(view.error || 'Could not start visual inspection.');
    renderVisual(view);
  } catch (error) {
    setText('visual-status', 'ERROR');
    el('visual-message').textContent = error.message;
  } finally {
    visualBusy = false;
    el('visual-start').disabled = false;
  }
}
async function runVisualCheck(measurement, target, button) {
  if (visualRun) return;
  const lab = el('lab-port').value;
  if (!lab) { el('visual-message').textContent = 'Choose the S3 port before running a probe check.'; return; }
  visualRun = true;
  button.disabled = true;
  try {
    const response = await fetch('/api/visual/verify', {method:'POST',
      headers:{'Content-Type':'application/json','X-Benchy-Local':'1'},
      body:JSON.stringify({measurement, target, lab_port:lab})});
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Check failed');
    const failed = data.check.reading && data.check.reading.pass === false;
    pushTimeline({kind:'probe', state:failed ? 'fail' : 'pass', title:data.check.summary, detail:'PROBE'});
    if (data.check.reading && data.check.reading.pass === true) {
      pushTimeline({kind:'probe', state:'pass', title:'Physical signal recorded', detail:'PASS'});
    }
    renderVisual(data.session);
  } catch (error) {
    el('visual-message').textContent = error.message;
  } finally {
    visualRun = false;
    button.disabled = false;
  }
}
el('visual-start').addEventListener('click', startVisual);
renderTimeline();
loadVoiceStatus();
renderAgentChat();
loadAgentStatus();
refreshAgentDiff();
refreshVisual().catch(() => {});
loadHarness().then(() => Promise.all([loadPorts(), loadCode()])).then(() => {
  renderAssessment();
  async function tick() {
    await refreshMeasurements();
    setTimeout(tick, 1500);
  }
  tick();
  setInterval(loadPorts, 15000);
  setInterval(renderFreshness, 1000);
});
