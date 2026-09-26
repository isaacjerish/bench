const $ = (id) => document.getElementById(id);
const MODES = {
  light: {title:'Light sensor', accent:'cross-check', description:'Compare what the ESP32-C6 says against what the ESP32-S3 physically measures.', tag:'PHOTORESISTOR', physicalUnit:'V', dutUnit:'V', physicalDescription:'Measured directly at test row T', dutDescription:'Claimed by device firmware', contextTitle:'Know where the signal breaks.', contextDescription:'A serial log only reports what the firmware thinks happened. BenchOS checks voltage at the same sensor node, exposing false or stale readings.', steps:['C6 samples light','S3 checks voltage','Compare values'], scale:3.3},
  led: {title:'LED output', accent:'timing check', description:'Verify the actual blink frequency on GPIO20, even when firmware says the LED is blinking.', tag:'DIGITAL OUTPUT', physicalUnit:'Hz', dutUnit:'', physicalDescription:'Rising edges counted at test row T', dutDescription:'No independent DUT report in this demo', contextTitle:'Catch the wrong pin.', contextDescription:'If C6 toggles another pin or the wire comes loose, BenchOS sees zero transitions despite a successful firmware log.', steps:['C6 drives GPIO20','S3 counts edges','Check 2 Hz'], scale:3},
  servo: {title:'Servo control', accent:'signal audit', description:'Inspect frequency and pulse width on the servo signal wire before attaching the motor.', tag:'PWM SIGNAL', physicalUnit:'Hz', dutUnit:'µs', physicalDescription:'Frequency measured at P1', dutDescription:'High pulse width measured at P1', contextTitle:'Check timing before motion.', contextDescription:'A safe servo demo starts by verifying 50 Hz and a 900–2100 µs high pulse. Visible motion still requires a separate verified 5 V supply.', steps:['C6 sends PWM','S3 counts pulses','Verify width'], scale:65},
  imu: {title:'Motion sensor', accent:'live stream', description:'Watch the ESP32-C6 read acceleration from the MPU family breakout as you tilt it.', tag:'I²C SENSOR', physicalUnit:'', dutUnit:'g', physicalDescription:'P1 bus observation is not connected yet', dutDescription:'Acceleration magnitude reported by C6', contextTitle:'Verify the stream, then the bus.', contextDescription:'The C6 motion stream proves it can read the MPU. Independent electrical evidence requires moving the S3 P1 tip to an isolated I²C line.', steps:['C6 reads MPU','Tilt the board','Probe I²C bus'], scale:2}
};
const PREVIEW = {
  light:{physical:{voltage_v:2.207},dut:{reported_voltage_v:0},diagnosis:{state:'fail',title:'Sensor report disagrees',detail:'The DUT is 2.21 V away from the independent probe (>0.45 V).'}},
  led:{physical:{frequency_hz:2,edges:4,pulse_us:0},dut:null,diagnosis:{state:'pass',title:'Physical signal matches',detail:'The S3 probe measured the expected timing at P1.'}},
  servo:{physical:{frequency_hz:49.95,edges:50,pulse_us:1500},dut:null,diagnosis:{state:'pass',title:'Physical signal matches',detail:'The S3 probe measured the expected timing at P1.'}},
  imu:{physical:null,dut:{x_g:0.12,y_g:-0.08,z_g:0.99,magnitude_g:1.00,address:'0x68',who_am_i:'0x71'},diagnosis:{state:'unverified',title:'Motion stream detected',detail:'These values come from the DUT. Move P1 to an isolated I²C line for independent electrical evidence.'}}
};
let mode='light', preview=false, busy=false, generation=0, timer=null;
const history={physical:[],dut:[]};

function node(x,y,w,h,kind,title,sub){return `<rect class="node ${kind}" x="${x}" y="${y}" width="${w}" height="${h}" rx="9"/><text class="node-title" x="${x+15}" y="${y+25}">${title}</text><text class="node-sub" x="${x+15}" y="${y+44}">${sub}</text>`}
function circuitSvg(which){
  const base=`<defs><pattern id="dots" width="18" height="18" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#31505a" opacity=".45"/></pattern></defs><rect width="630" height="235" fill="url(#dots)"/>`;
  const ground='<text class="wire-label" x="20" y="215">GND ─────────────────────── SHARED GROUND ───────────────────────────── GND</text>';
  const joint=(x,y)=>`<circle class="joint" cx="${x}" cy="${y}" r="4"/>`;
  let drawing='';
  if(which==='light')drawing=`
    ${node(15,92,145,63,'node-dut','C6 · GPIO1','DUT ADC INPUT')}
    ${node(457,92,158,63,'node-lab','S3 · P1','2 × 10kΩ DIVIDER')}
    ${node(215,10,191,53,'','3V3 → LDR','LIGHT-DEPENDENT R')}
    <rect x="453" y="10" width="161" height="53" rx="8" fill="#362d26" stroke="#886440"/><text class="node-sub" x="467" y="31">SERIAL CLAIM</text><text class="node-sub" x="467" y="49">LIGHT_MV</text>
    <path class="wire" d="M160 123 H310 V63 M310 123 V171"/><path class="wire-probe" d="M310 123 H457"/>
    ${joint(310,123)}<text class="wire-label" x="320" y="111">TEST NODE T</text>
    <rect class="node" x="272" y="171" width="76" height="29" rx="5"/><text class="node-sub" x="286" y="190">10kΩ ↓ GND</text>
    <path class="wire-dash" d="M160 103 H437 V37 H453"/>
    ${ground}`;
  else if(which==='led')drawing=`
    ${node(15,94,145,62,'node-dut','C6 · GPIO20','DIGITAL OUTPUT')}
    ${node(457,94,158,62,'node-lab','S3 · P1','EDGE COUNTER')}
    <path class="wire" d="M160 125 H310 V160"/><path class="wire-probe" d="M310 125 H457"/>
    ${joint(310,125)}<text class="wire-label" x="254" y="109">TEST NODE T</text>
    ${node(234,160,155,47,'','330Ω → LED','TO SHARED GND')}
    <path class="wire-dash" d="M86 94 V45 H401"/><text class="wire-label" x="409" y="49">EXPECTED: 2 Hz</text>
    ${ground}`;
  else if(which==='servo')drawing=`
    ${node(15,94,145,62,'node-dut','C6 · GPIO20','50 Hz PWM OUTPUT')}
    ${node(457,94,158,62,'node-lab','S3 · P1','FREQ + PULSE WIDTH')}
    <path class="wire" d="M160 125 H310 V160"/><path class="wire-probe" d="M310 125 H457"/>
    ${joint(310,125)}<text class="wire-label" x="241" y="109">SIGNAL NODE T</text>
    ${node(235,160,152,47,'','SG90 signal','YELLOW WIRE')}
    <rect x="425" y="17" width="190" height="48" rx="8" fill="#362d26" stroke="#886440"/><text class="node-sub" x="440" y="36" fill="#d9b179">SEPARATE 5 V SUPPLY</text><text class="node-sub" x="440" y="53" fill="#baa484">needed for motion</text>
    <path class="wire-dash" d="M518 65 V77 H384 V184"/><text class="wire-label" x="22" y="46">EXPECTED: 50 Hz · 900–2100 µs</text>
    ${ground}`;
  else drawing=`
    ${node(15,69,152,66,'node-dut','ESP32-C6','I²C MASTER')}
    ${node(449,69,166,66,'','MPU breakout','ACCEL + GYRO')}
    <path class="wire" d="M167 89 H449 M167 116 H449"/><text class="wire-label" x="278" y="81">SDA / IO6</text><text class="wire-label" x="278" y="137">SCL / IO7</text>
    <rect x="425" y="8" width="190" height="45" rx="8" fill="#362d26" stroke="#886440"/><text class="node-sub" x="439" y="27">C6 SERIAL REPORT</text><text class="node-sub" x="439" y="44">IMU_ACCEL_G</text>
    <path class="wire-dash" d="M93 69 V29 H425"/>
    <rect class="node node-lab" x="226" y="164" width="177" height="43" rx="8" opacity=".55"/><text class="node-sub" x="241" y="182">S3 · P1</text><text class="node-sub" x="241" y="198">NOT YET ON I²C BUS</text>
    <text class="wire-label" x="26" y="215">3V3 + GND SHARED · ADO LOW · NCS HIGH</text>`;
  return `<svg viewBox="0 0 630 235" role="img" aria-label="Reference wiring for ${which} demo">${base}${drawing}</svg>`;
}

function renderMode(){
  const c=MODES[mode];
  $('breadcrumb-mode').textContent=mode.toUpperCase();
  $('page-title').innerHTML=`${c.title} <em>${c.accent}</em>`;
  $('page-description').textContent=c.description;
  $('diagram-tag').textContent=`${c.tag} · REFERENCE`;
  $('legend-middle').textContent=mode==='servo'?'Required power':mode==='led'?'Expected timing':mode==='imu'?'C6 report':'DUT claim';
  $('circuit-diagram').innerHTML=circuitSvg(mode);
  $('circuit-diagram').dataset.mode=mode;
  $('physical-unit').textContent=c.physicalUnit;
  $('dut-unit').textContent=c.dutUnit;
  $('physical-description').textContent=c.physicalDescription;
  $('dut-description').textContent=c.dutDescription;
  $('second-source-label').textContent=mode==='servo'?'PULSE WIDTH':mode==='led'?'DUT REPORT':'DUT REPORT';
  $('second-source-badge').textContent=mode==='servo'?'ESP32-S3 · P1':mode==='led'?'NOT REPORTED':'ESP32-C6 · SERIAL';
  $('context-title').textContent=c.contextTitle;
  $('context-description').textContent=c.contextDescription;
  $('context-steps').innerHTML=c.steps.map((step,i)=>`${i?'<span class="step-arrow">→</span>':''}<span><b class="step-number">${i+1}</b>${step}</span>`).join('');
  document.querySelectorAll('.mode-button').forEach(b=>b.classList.toggle('active',b.dataset.mode===mode));
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
  }else{
    if(mode==='light'&&data.dut)return [data.dut.reported_voltage_v,Number(data.dut.reported_voltage_v).toFixed(3)];
    if(mode==='servo'&&data.physical)return [data.physical.pulse_us,String(data.physical.pulse_us)];
    if(mode==='imu'&&data.dut)return [data.dut.magnitude_g,Number(data.dut.magnitude_g).toFixed(3)];
  }
  return null;
}
function renderData(data){
  const state=data.diagnosis.state;
  $('circuit-diagram').dataset.state=state;
  $('verdict-block').className=`verdict-block ${state==='unknown'?'neutral':state}`;
  $('verdict-icon').className=`verdict-icon ${state==='unknown'?'':state}`;
  $('verdict-icon').textContent=state==='pass'?'✓':state==='fail'?'!':state==='unverified'?'?':'—';
  $('verdict-label').textContent=state==='pass'?'PHYSICAL CHECK PASSED':state==='fail'?'PHYSICAL FAULT DETECTED':state==='unverified'?'DUT REPORT ONLY':'INSUFFICIENT EVIDENCE';
  $('verdict-title').textContent=data.diagnosis.title;$('verdict-detail').textContent=data.diagnosis.detail;
  for(const kind of ['physical','dut']){
    const measurement=sampleValue(kind,data),target=$(`${kind}-value`);
    target.textContent=measurement?measurement[1]:'—';
    if(measurement){history[kind].push(measurement[0]);if(history[kind].length>22)history[kind].shift();renderSpark(kind,kind==='dut'&&mode==='servo'?2200:MODES[mode].scale)}
  }
  if(mode==='imu'&&data.dut){$('dut-description').textContent=`x ${data.dut.x_g.toFixed(2)} · y ${data.dut.y_g.toFixed(2)} · z ${data.dut.z_g.toFixed(2)} g${data.dut.who_am_i?' · ID '+data.dut.who_am_i:''}`}
  else $('dut-description').textContent=MODES[mode].dutDescription;
  $('sample-time').textContent=new Date().toLocaleTimeString();
  $('confidence-source').textContent=mode==='imu'?'C6 serial only':'Physical S3 probe';
  const errs=(data.errors||[]).map(e=>`${e.device}: ${e.message}`);
  $('footer-status').textContent=preview?'PREVIEW · sample data':errs.length?errs.join(' · '):`Last sample ${new Date().toLocaleTimeString()}`;
  const connected=!!(data.physical||data.dut);
  $('connection-dot').className=`live-dot ${preview?'preview':connected?'':'off'}`;
  $('connection-label').textContent=preview?'Preview data':connected?'Hardware active':'Awaiting hardware';
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
document.querySelectorAll('.mode-button').forEach(button=>button.addEventListener('click',()=>{mode=button.dataset.mode;generation++;renderMode()}));
for(const kind of ['lab','dut'])$(`${kind}-port`).addEventListener('change',event=>{localStorage.setItem(`benchos-${kind}-port`,event.target.value);generation++;tick()});
$('preview-toggle').addEventListener('click',()=>{preview=!preview;generation++;document.body.classList.toggle('preview',preview);$('preview-toggle').classList.toggle('active',preview);$('preview-toggle').setAttribute('aria-pressed',String(preview));$('session-badge').textContent=preview?'SESSION · PREVIEW':'SESSION · LIVE';renderMode()});
$('refresh-button').addEventListener('click',async()=>{await loadPorts();generation++;tick()});
loadPorts().then(()=>{renderMode();timer=setInterval(tick,3500)});
