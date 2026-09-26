const $ = (id) => document.getElementById(id);
const MODES = {
  light: {title:'Light sensor', accent:'cross-check', description:'Compare what the ESP32-C6 says against what the ESP32-S3 physically measures.', tag:'PHOTORESISTOR', wiring:'C6 3V3 → photoresistor → T. T → 10 kΩ → GND. T → C6 GPIO1 and S3 P1.', physicalUnit:'V', dutUnit:'V', physicalDescription:'Measured directly at test row T', dutDescription:'Claimed by device firmware', contextTitle:'Know where the signal breaks.', contextDescription:'A serial log only reports what the firmware thinks happened. Benchy checks voltage at the same sensor node, exposing false or stale readings.', steps:['C6 samples light','S3 checks voltage','Compare values'], scale:3.3},
  led: {title:'LED output', accent:'timing check', description:'Verify the actual blink frequency on GPIO20, even when firmware says the LED is blinking.', tag:'DIGITAL OUTPUT', wiring:'C6 GPIO20 → T and S3 P1. T → 330 Ω → LED anode. LED cathode → shared GND.', physicalUnit:'Hz', dutUnit:'', physicalDescription:'Rising edges counted at test row T', dutDescription:'No independent DUT report in this demo', contextTitle:'Catch the wrong pin.', contextDescription:'If C6 toggles another pin or the wire comes loose, Benchy sees zero transitions despite a successful firmware log.', steps:['C6 drives GPIO20','S3 counts edges','Check 2 Hz'], scale:3},
  servo: {title:'Servo control', accent:'signal audit', description:'Inspect frequency and pulse width on the servo signal wire before attaching the motor.', tag:'PWM SIGNAL', wiring:'C6 GPIO20 → T, S3 P1, and SG90 yellow. SG90 brown → shared GND. Red needs a separate verified 5 V supply; currently disconnected.', physicalUnit:'Hz', dutUnit:'µs', physicalDescription:'Frequency measured at P1', dutDescription:'High pulse width measured at P1', contextTitle:'Check timing before motion.', contextDescription:'A safe servo demo starts by verifying 50 Hz and a 900–2100 µs high pulse. Visible motion still requires a separate verified 5 V supply.', steps:['C6 sends PWM','S3 counts pulses','Verify width'], scale:65},
  imu: {title:'Motion sensor', accent:'power + motion', description:'Check the MPU supply independently while the ESP32-C6 reports acceleration.', tag:'I²C SENSOR', wiring:'Loading declared wiring…', physicalUnit:'V', dutUnit:'g', physicalDescription:'S3 P2 measures the declared MPU VCC net', dutDescription:'Acceleration magnitude reported by C6', contextTitle:'Separate supply from sensor data.', contextDescription:'The S3 checks voltage at P2 when the harness declares it connected to MPU VCC. Motion values still come from C6; the I²C bus is not independently decoded.', steps:['S3 checks VCC','C6 reads MPU','Compare evidence'], scale:2}
};
const PREVIEW = {
  light:{physical:{voltage_v:2.207},dut:{reported_voltage_v:0},diagnosis:{state:'fail',title:'Sensor report disagrees',detail:'The DUT is 2.21 V away from the independent probe (>0.45 V).'}},
  led:{physical:{frequency_hz:2,edges:4,pulse_us:0},dut:null,diagnosis:{state:'pass',title:'Physical signal matches',detail:'The S3 probe measured the expected timing at P1.'}},
  servo:{physical:{frequency_hz:49.95,edges:50,pulse_us:1500},dut:null,diagnosis:{state:'pass',title:'Physical signal matches',detail:'The S3 probe measured the expected timing at P1.'}},
  imu:{physical:{voltage_v:3.25,probe:'P2'},dut:{x_g:0.12,y_g:-0.08,z_g:0.99,magnitude_g:1.00,address:'0x68',who_am_i:'0x70'},diagnosis:{state:'unverified',evidence:'mixed',title:'Power verified; motion stream detected',detail:'S3 P2 measured 3.25 V at MPU VCC. Motion values are from C6; the I²C bus is not independently decoded.'}}
};
const PREVIEW_SERIAL={
  light:['Light demo ready: GPIO1, fault=1','LIGHT_MV 0000'],
  led:['LED demo ready: GPIO20, 2 Hz','LED_TOGGLE HIGH'],
  servo:['Servo demo ready: GPIO20','PWM 50Hz pulse=1500us'],
  imu:['IMU_FOUND addr=0x68 who_am_i=0x70','IMU_ACCEL_G x=0.120 y=-0.080 z=0.990 id=0x70']
};
let mode='light', preview=false, busy=false, generation=0, timer=null;
const history={physical:[],dut:[]};
let lastData=null, codeInventory=null, serialBusy=false, serialPaused=false, serialSeq=0;
let serialEvents=[];
let session=[];
try{session=JSON.parse(localStorage.getItem('benchos-session-v1')||'[]');if(!Array.isArray(session))session=[]}catch{session=[]}

function benchScene(which){
  const captions={
    light:{center:'T / SENSOR NODE',bottom:'PHOTORESISTOR + PULL-DOWN'},
    led:{center:'T / OUTPUT NODE',bottom:'LED + SERIES RESISTOR'},
    servo:{center:'T / SERVO SIGNAL',bottom:'RED POWER LEAD UNCONNECTED'},
    imu:{center:'U / MPU VCC',bottom:'P2 POWER CHECK · 3.3 V ONLY'}
  };
  const c=captions[which];
  return `<div class="scene" data-mode="${which}">
    <img class="scene-image" src="/scene-${which}.png" alt="Illustrative overhead view of the ${which} breadboard setup">
    <span class="scene-label left">C6 / DUT</span>
    <span class="scene-label right">S3 / PROBE</span>
    <span class="scene-label center">${c.center}</span>
    <span class="scene-label bottom">${c.bottom}</span>
    <span class="scene-point" aria-hidden="true"></span>
  </div>`;
}

function renderMode(){
  const c=MODES[mode];
  $('breadcrumb-mode').textContent=mode.toUpperCase();
  $('page-title').innerHTML=`${c.title} <em>${c.accent}</em>`;
  $('page-description').textContent=c.description;
  $('diagram-tag').textContent=`${c.tag} · ${mode==='imu'?'DECLARED WIRING':'REFERENCE'}`;
  $('wiring-description').textContent=c.wiring;
  $('circuit-diagram').innerHTML=benchScene(mode);
  $('circuit-diagram').dataset.mode=mode;
  $('physical-unit').textContent=c.physicalUnit;
  $('dut-unit').textContent=c.dutUnit;
  $('physical-description').textContent=c.physicalDescription;
  $('physical-source-label').textContent=mode==='imu'?'INDEPENDENT / S3 P2':'INDEPENDENT / S3 P1';
  $('dut-description').textContent=c.dutDescription;
  $('second-source-label').textContent=mode==='servo'?'PULSE WIDTH':mode==='led'?'DUT REPORT':'DUT REPORT';
  $('second-source-badge').textContent=mode==='servo'?'ESP32-S3 · P1':mode==='led'?'NOT REPORTED':'ESP32-C6 · SERIAL';
  $('context-title').textContent=c.contextTitle;
  $('context-description').textContent=c.contextDescription;
  $('context-steps').innerHTML=c.steps.map((step,i)=>`${i?'<span class="step-arrow">→</span>':''}<span><b class="step-number">${i+1}</b>${step}</span>`).join('');
  document.querySelectorAll('.mode-button').forEach(b=>{
    const active=b.dataset.mode===mode;
    b.classList.toggle('active',active);
    if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');
  });
  history.physical=[];history.dut=[];renderSpark('physical',c.scale);renderSpark('dut',c.scale);
  $('physical-value').textContent='—';$('dut-value').textContent='—';
  $('verdict-block').className='verdict-block neutral';$('verdict-icon').className='verdict-icon';
  $('verdict-icon').textContent='—';$('verdict-label').textContent='AWAITING DATA';
  $('verdict-title').textContent='Checking hardware';$('verdict-detail').textContent='Waiting for the next reading.';
  tick();
}
function renderSpark(type,max){
  const values=history[type],svg=$(`${type}-spark`),line=svg.querySelector('.spark-line'),fill=svg.querySelector('.spark-fill');
  if(!values.length){line.setAttribute('d','');fill.setAttribute('d','');return}
  const points=values.map((v,i)=>[Math.round(i*300/Math.max(1,values.length-1)),Math.round(52-Math.min(1,Math.max(0,v/max))*46)]);
  const path='M'+points.map(p=>p.join(' ')).join(' L');line.setAttribute('d',path);fill.setAttribute('d',path+` L${points.at(-1)[0]} 58 L${points[0][0]} 58 Z`);
}
function sampleValue(kind,data){
  if(kind==='physical'){
    if(mode==='light'&&data.physical)return [data.physical.voltage_v,Number(data.physical.voltage_v).toFixed(3)];
    if(mode==='led'&&data.physical)return [data.physical.frequency_hz,Number(data.physical.frequency_hz).toFixed(1)];
    if(mode==='servo'&&data.physical)return [data.physical.frequency_hz,Number(data.physical.frequency_hz).toFixed(2)];
    if(mode==='imu'&&data.physical)return [data.physical.voltage_v,Number(data.physical.voltage_v).toFixed(3)];
  }else{
    if(mode==='light'&&data.dut)return [data.dut.reported_voltage_v,Number(data.dut.reported_voltage_v).toFixed(3)];
    if(mode==='servo'&&data.physical)return [data.physical.pulse_us,String(data.physical.pulse_us)];
    if(mode==='imu'&&data.dut)return [data.dut.magnitude_g,Number(data.dut.magnitude_g).toFixed(3)];
  }
  return null;
}
function renderData(data){
  lastData=data;
  const state=data.diagnosis.state;
  $('circuit-diagram').dataset.state=state;
  const scene=$('circuit-diagram').querySelector('.scene');
  scene.dataset.state=state;
  if(!preview&&data.physical){scene.classList.remove('sampling');void scene.offsetWidth;scene.classList.add('sampling')}
  $('verdict-block').className=`verdict-block ${state==='unknown'?'neutral':state}`;
  $('verdict-icon').className=`verdict-icon ${state==='unknown'?'':state}`;
  $('verdict-icon').textContent=state==='pass'?'✓':state==='fail'?'!':state==='unverified'?'?':'—';
  $('verdict-label').textContent=state==='pass'?'PHYSICAL CHECK PASSED':state==='fail'?(data.diagnosis.evidence==='dut'?'DUT DATA ANOMALY':data.diagnosis.evidence==='mixed'?'POWER PRESENT · LINK FAILED':'PHYSICAL FAULT DETECTED'):state==='unverified'?(data.physical?'POWER VERIFIED · BUS UNVERIFIED':'DUT REPORT ONLY'):'INSUFFICIENT EVIDENCE';
  $('verdict-title').textContent=data.diagnosis.title;$('verdict-detail').textContent=data.diagnosis.detail;
  for(const kind of ['physical','dut']){
    const measurement=sampleValue(kind,data),target=$(`${kind}-value`);
    target.textContent=measurement?measurement[1]:'—';
    if(measurement){history[kind].push(measurement[0]);if(history[kind].length>22)history[kind].shift();renderSpark(kind,kind==='dut'&&mode==='servo'?2200:kind==='physical'&&mode==='imu'?3.5:MODES[mode].scale)}
  }
  if(mode==='imu'&&data.dut){$('dut-description').textContent=`x ${data.dut.x_g.toFixed(2)} · y ${data.dut.y_g.toFixed(2)} · z ${data.dut.z_g.toFixed(2)} g${data.dut.who_am_i?' · ID '+data.dut.who_am_i:''}`}
  else $('dut-description').textContent=MODES[mode].dutDescription;
  $('sample-time').textContent=new Date().toLocaleTimeString();
  $('confidence-source').textContent=mode==='imu'?(data.physical?'S3 P2 power + C6 serial':'C6 serial only'):'Physical S3 probe';
  const errs=(data.errors||[]).map(e=>`${e.device}: ${e.message}`);
  $('footer-status').textContent=preview?'PREVIEW · sample data':errs.length?errs.join(' · '):`Last sample ${new Date().toLocaleTimeString()}`;
  const connected=!!(data.physical||data.dut);
  $('connection-dot').className=`connection-dot ${preview?'preview':connected?'':'off'}`;
  $('connection-label').textContent=preview?'Preview data':connected?'Hardware active':'Awaiting hardware';
  renderEvidence(data);
  if(!preview&&connected)recordSession(data);
}
function renderEvidence(data){
  const evidence=[];
  if(data.physical){
    const p=data.physical;
    evidence.push(mode==='imu'?`S3 P2 measured ${p.voltage_v.toFixed(3)} V on the declared MPU VCC net.`:
      mode==='light'?`S3 P1 measured ${p.voltage_v.toFixed(3)} V at the sensor node.`:
      `S3 P1 counted ${p.edges} transitions in ${p.window_ms} ms (${p.frequency_hz.toFixed(1)} Hz).`);
  }
  if(data.dut){
    evidence.push(mode==='light'?`C6 firmware reported ${data.dut.reported_voltage_v.toFixed(3)} V.`:
      mode==='imu'?`C6 reported ${data.dut.magnitude_g.toFixed(3)} g and chip ID ${data.dut.who_am_i||'unknown'}.`:
      'The current demo has no independent DUT serial value.');
  }
  for(const error of data.errors||[])evidence.push(`${error.device} reported: ${error.message}`);
  if(!evidence.length)evidence.push('Waiting for a physical reading or DUT report.');
  const list=$('evidence-list');list.replaceChildren();
  for(const line of evidence){const item=document.createElement('li');item.textContent=line;list.append(item)}
  const verdict=data.diagnosis||{};
  let next='Choose the board ports and inspect a known safe test point.';
  let unknown='The breadboard wiring is declared by the user; Benchy cannot discover it automatically.';
  if(mode==='imu'){
    const imuError=(data.errors||[]).some(e=>e.device==='C6'&&e.message.includes('IMU_ERROR'));
    next=imuError&&data.physical?'Check sensor-side SCL and SDA continuity. VCC was present during this failure.':
      data.dut?'To establish the bus itself, add independent read-only SDA/SCL observation. The motion values still come from C6.':
      'Inspect MPU VCC with P2 and the C6 serial stream.';
    unknown='P2 cannot decode I²C traffic or verify sensor data registers. A good voltage does not prove the bus is connected.';
  }else if(mode==='light'){
    next=data.physical&&!data.dut?'The C6 is currently declared as running imu_demo. Flash the light demo before comparing the C6 ADC report.':
      verdict.state==='fail'?'Check the C6 ADC pin and conversion path, then repeat the independent S3 measurement.':
      'Change the light level and compare the C6 report with S3 P1 again.';
    unknown='A matching voltage checks one node at one time; it does not prove every part of the sensor path.';
  }else if(mode==='servo'){
    next=verdict.state==='fail'?'Check the C6 GPIO20 signal path and rerun frequency and pulse-width checks.':
      'Verify a suitable separate 5 V supply before attaching the SG90 power lead.';
    unknown='A valid control pulse does not confirm servo supply current or shaft motion.';
  }else if(mode==='led'){
    next=verdict.state==='fail'?'Check the C6 GPIO20 connection, LED series resistor, and shared ground.':
      'Confirm the LED is visibly blinking; P1 establishes electrical timing only.';
    unknown='P1 counts transitions but cannot confirm optical brightness.';
  }
  if(!data.physical&&!data.dut&&!(data.errors||[]).length)
    next='Choose the board ports, then collect a live reading on a known safe node.';
  $('next-check').textContent=next;
  $('uncertainty').textContent=unknown;
}
function saveSession(){try{localStorage.setItem('benchos-session-v1',JSON.stringify(session.slice(-100)))}catch{}}
function recordSession(data,manual=false){
  const now=Date.now(),last=session.at(-1),state=data.diagnosis?.state||'unknown';
  if(!manual&&last&&last.mode===mode&&last.state===state&&now-last.time<30000)return;
  const item={time:now,mode,state,title:data.diagnosis?.title||'Reading',manual,
    physical:data.physical||null,dut:data.dut||null,errors:data.errors||[],
    evidence:data.diagnosis?.evidence||null};
  session.push(item);if(session.length>100)session.shift();saveSession();renderTimeline();
}
function renderTimeline(){
  const target=$('timeline');target.replaceChildren();
  if(!session.length){const empty=document.createElement('p');empty.className='empty-state';empty.textContent='Readings will appear here as they arrive.';target.append(empty);return}
  for(const item of [...session].reverse().slice(0,25)){
    const row=document.createElement('div');row.className='timeline-row';row.dataset.state=item.state;
    const time=document.createElement('time');time.textContent=new Date(item.time).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});
    const title=document.createElement('strong');title.textContent=`${item.manual?'CAPTURE · ':''}${item.title}`;
    const circuit=document.createElement('span');circuit.className='timeline-mode';circuit.textContent=item.mode.toUpperCase();
    const mark=document.createElement('span');mark.className='timeline-mark';mark.textContent=item.state==='pass'?'✓':item.state==='fail'?'!':'·';
    row.append(time,title,circuit,mark);target.append(row);
  }
}
function downloadJson(name,data){
  const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function tick(){
  if(preview){renderData(PREVIEW[mode]);return}
  if(busy)return;
  const lab=$('lab-port').value,dut=$('dut-port').value;
  if(!lab&&!(mode==='imu'&&dut)){
    renderData({physical:null,dut:null,diagnosis:{state:'unknown',title:'Choose your board ports',detail:'Select the ESP32-S3 lab controller and the ESP32-C6 DUT above.'},errors:[]});return;
  }
  busy=true;const requestGeneration=generation;
  const query=new URLSearchParams({mode,lab_port:lab,dut_port:dut});
  try{const response=await fetch(`/api/snapshot?${query}`,{cache:'no-store'});const data=await response.json();if(!response.ok)throw Error(data.error||'Measurement failed');if(requestGeneration===generation)renderData(data)}
  catch(err){if(requestGeneration===generation)renderData({physical:null,dut:null,diagnosis:{state:'unknown',title:'Connection interrupted',detail:String(err.message||err)},errors:[{device:'Dashboard',message:String(err.message||err)}]})}
  finally{busy=false}
}
async function loadPorts(){
  try{
    const response=await fetch('/api/config',{cache:'no-store'}),data=await response.json();
    for(const kind of ['lab','dut']){
      const select=$(`${kind}-port`),previous=select.value,preferred=localStorage.getItem(`benchos-${kind}-port`)||data[`${kind}_port`]||'';
      select.replaceChildren(new Option(kind==='lab'?'Choose S3 port':'Choose C6 port',''));
      for(const port of data.ports)select.add(new Option(`${port.device} · ${port.description||'USB serial'}`,port.device));
      select.value=previous&&[...select.options].some(x=>x.value===previous)?previous:[...select.options].some(x=>x.value===preferred)?preferred:'';
    }
    $('connection-label').textContent=data.ports.length?`${data.ports.length} serial port${data.ports.length===1?'':'s'} found`:'No serial ports found';
  }catch(err){$('footer-status').textContent=`Port discovery failed: ${err.message}`}
}
async function loadHarness(){
  try{
    const response=await fetch('/api/harness',{cache:'no-store'}),data=await response.json();
    if(!response.ok)throw Error(data.error||'Harness unavailable');
    const probe=data.probes?.P2,dut=data.dut||{};
    const attached=probe?.state==='connected'&&probe.net==='MPU_VCC';
    MODES.imu.wiring=attached
      ?`Declared: ${probe.tip} (S3 P2) → MPU VCC; SDA → ${dut.sensor_sda||'unspecified'}; SCL → ${dut.sensor_scl||'unspecified'}. MPU GND → shared GND; ADO → GND; NCS → 3V3. P1: ${data.probes?.P1?.net||'unspecified'}. Confirm this map after any wire move.`
      :'P2 is not declared connected to MPU VCC. Update harness/current.yaml after checking the wiring; the dashboard omits the independent supply check.';
  }catch(err){MODES.imu.wiring=`Wiring declaration unavailable: ${err.message}. Check harness/current.yaml before interpreting P2.`}
  if(mode==='imu')$('wiring-description').textContent=MODES.imu.wiring;
}
function renderSerial(){
  const target=$('serial-lines'),needle=$('serial-filter').value.trim().toLowerCase();target.replaceChildren();
  const matching=serialEvents.filter(e=>e.line.toLowerCase().includes(needle)).slice(-160);
  if(!matching.length){const empty=document.createElement('p');empty.className='empty-state';empty.textContent=needle?'No lines match this filter.':'Raw device output will appear here.';target.append(empty);return}
  for(const event of matching){
    const row=document.createElement('div');row.className='serial-line'+(/ERROR|FAIL|WARN/i.test(event.line)?' error':'');
    const time=document.createElement('span');time.className='line-time';time.textContent=new Date(event.timestamp).toLocaleTimeString([], {hour12:false});
    const line=document.createElement('span');line.textContent=event.line;row.append(time,line);target.append(row);
  }
  target.scrollTop=target.scrollHeight;
}
async function pollSerial(){
  if(serialBusy||serialPaused)return;
  if(preview){
    if(!serialEvents.length){serialEvents=PREVIEW_SERIAL[mode].map((line,index)=>({seq:index+1,timestamp:new Date().toISOString(),line}));renderSerial()}
    $('serial-status').textContent='PREVIEW · sample output';$('serial-live-dot').classList.remove('active');return;
  }
  const port=$('dut-port').value;
  if(!port){$('serial-status').textContent='Choose C6 port to sample output';$('serial-live-dot').classList.remove('active');return}
  serialBusy=true;
  try{
    const query=new URLSearchParams({port,duration_ms:'700',after:String(serialSeq)});
    const response=await fetch(`/api/serial?${query}`,{cache:'no-store'}),data=await response.json();
    if(!response.ok)throw Error(data.error||'Serial sample failed');
    if(port!==$('dut-port').value)return;
    serialSeq=data.latest_seq;
    if(data.events.length){serialEvents.push(...data.events);if(serialEvents.length>400)serialEvents=serialEvents.slice(-400);renderSerial()}
    $('serial-status').textContent=`${port.split('/').at(-1)} · ${data.sample_window_ms} ms window · ${serialEvents.length} lines`;
    $('serial-live-dot').classList.add('active');
  }catch(err){$('serial-status').textContent=`Serial unavailable: ${err.message}`;$('serial-live-dot').classList.remove('active')}
  finally{serialBusy=false}
}
async function loadCode(){
  try{
    const response=await fetch('/api/code',{cache:'no-store'}),data=await response.json();
    if(!response.ok)throw Error(data.error||'Code inventory failed');
    codeInventory=data;
    $('source-revision').textContent=data.short_commit||'LOCAL';
    $('source-state').textContent=data.commit?`${data.short_commit}${data.dirty?' · modified':' · clean'}`:'Git revision unavailable';
    $('firmware-state').textContent=data.declared_dut_firmware?`${data.declared_dut_firmware} · declared`:'Unspecified';
    const select=$('source-select'),previous=select.value;
    select.replaceChildren(new Option('Choose source file',''));
    for(const file of data.files)select.add(new Option(file.path,file.path));
    const suggested=`dut_examples/${data.declared_dut_firmware}/${data.declared_dut_firmware}.ino`;
    select.value=data.files.some(f=>f.path===previous)?previous:data.files.some(f=>f.path===suggested)?suggested:'';
    if(select.value)await loadSource();
  }catch(err){$('source-state').textContent=`Unavailable: ${err.message}`;$('source-revision').textContent='OFFLINE'}
}
async function loadSource(){
  const path=$('source-select').value,target=$('source-code');target.replaceChildren();
  if(!path){const empty=document.createElement('p');empty.className='empty-state';empty.textContent='Select a file to inspect local code.';target.append(empty);return}
  try{
    const response=await fetch(`/api/source?${new URLSearchParams({path})}`,{cache:'no-store'}),data=await response.json();
    if(!response.ok)throw Error(data.error||'Source read failed');
    if(path!==$('source-select').value)return;
    const modified=codeInventory?.modified_files?.includes(path);
    $('source-meta').textContent=`${path} · SHA-256 ${data.sha256_short}… · ${modified?'modified locally':'matches checked-out file'} · local source only`;
    const fragment=document.createDocumentFragment();
    for(const [index,line] of data.text.split('\n').entries()){
      const row=document.createElement('div');row.className='source-row'+(/^\s*(\/\/|#)/.test(line)?' comment':/^\s*(#include|import|from)\b/.test(line)?' directive':'');
      const number=document.createElement('span');number.className='source-number';number.textContent=String(index+1);
      const code=document.createElement('span');code.className='source-text';code.textContent=line||' ';
      row.append(number,code);fragment.append(row);
    }
    target.append(fragment);
  }catch(err){$('source-meta').textContent=`Source unavailable: ${err.message}`}
}
document.querySelectorAll('.mode-button').forEach(button=>button.addEventListener('click',()=>{mode=button.dataset.mode;generation++;if(preview){serialEvents=[];pollSerial()}renderMode()}));
for(const kind of ['lab','dut'])$(`${kind}-port`).addEventListener('change',event=>{
  localStorage.setItem(`benchos-${kind}-port`,event.target.value);
  if(kind==='dut'){serialSeq=0;serialEvents=[];renderSerial();pollSerial()}
  generation++;tick();
});
$('preview-toggle').addEventListener('click',()=>{
  preview=!preview;generation++;serialSeq=0;serialEvents=[];renderSerial();
  document.body.classList.toggle('preview',preview);$('preview-toggle').classList.toggle('active',preview);
  $('preview-toggle').setAttribute('aria-pressed',String(preview));
  $('session-badge').textContent=preview?'PREVIEW DATA':'LIVE SESSION';
  $('capture-button').disabled=preview;renderMode();pollSerial();
});
$('refresh-button').addEventListener('click',async()=>{await Promise.all([loadPorts(),loadHarness(),loadCode()]);generation++;tick();pollSerial()});
$('capture-button').addEventListener('click',()=>{if(lastData&&!preview)recordSession(lastData,true)});
$('export-session').addEventListener('click',()=>downloadJson('benchy-session.json',{source:'local_dashboard',exported_at:new Date().toISOString(),entries:session}));
$('clear-session').addEventListener('click',()=>{session=[];saveSession();renderTimeline()});
$('serial-pause').addEventListener('click',()=>{serialPaused=!serialPaused;$('serial-pause').textContent=serialPaused?'Resume':'Pause';$('serial-pause').setAttribute('aria-pressed',String(serialPaused));$('serial-status').textContent=serialPaused?'Sampling paused':'Resuming samples…';if(!serialPaused)pollSerial()});
$('serial-clear').addEventListener('click',()=>{serialEvents=[];renderSerial()});
$('serial-export').addEventListener('click',()=>downloadJson('benchy-serial.json',{source:preview?'preview':'serial_observed',port:$('dut-port').value,continuous:false,events:serialEvents}));
$('serial-filter').addEventListener('input',renderSerial);
$('source-select').addEventListener('change',loadSource);
$('source-refresh').addEventListener('click',loadCode);
renderTimeline();
Promise.all([loadPorts(),loadHarness(),loadCode()]).then(()=>{renderMode();pollSerial();timer=setInterval(tick,3500);setInterval(pollSerial,2400)});
