const $ = (id) => document.getElementById(id);
const MODES = {
  light: {title:'Light sensor', accent:'cross-check', description:'Compare what the ESP32-C6 says against what the ESP32-S3 physically measures.', tag:'PHOTORESISTOR', wiring:'C6 3V3 → photoresistor → T. T → 10 kΩ → GND. T → C6 GPIO1 and S3 P1.', physicalUnit:'V', dutUnit:'V', physicalDescription:'Measured directly at test row T', dutDescription:'Claimed by device firmware', contextTitle:'Know where the signal breaks.', contextDescription:'A serial log only reports what the firmware thinks happened. BenchOS checks voltage at the same sensor node, exposing false or stale readings.', steps:['C6 samples light','S3 checks voltage','Compare values'], scale:3.3},
  led: {title:'LED output', accent:'timing check', description:'Verify the actual blink frequency on GPIO20, even when firmware says the LED is blinking.', tag:'DIGITAL OUTPUT', wiring:'C6 GPIO20 → T and S3 P1. T → 330 Ω → LED anode. LED cathode → shared GND.', physicalUnit:'Hz', dutUnit:'', physicalDescription:'Rising edges counted at test row T', dutDescription:'No independent DUT report in this demo', contextTitle:'Catch the wrong pin.', contextDescription:'If C6 toggles another pin or the wire comes loose, BenchOS sees zero transitions despite a successful firmware log.', steps:['C6 drives GPIO20','S3 counts edges','Check 2 Hz'], scale:3},
  servo: {title:'Servo control', accent:'signal audit', description:'Inspect frequency and pulse width on the servo signal wire before attaching the motor.', tag:'PWM SIGNAL', wiring:'C6 GPIO20 → T, S3 P1, and SG90 yellow. SG90 brown → shared GND. Red needs a separate verified 5 V supply; currently disconnected.', physicalUnit:'Hz', dutUnit:'µs', physicalDescription:'Frequency measured at P1', dutDescription:'High pulse width measured at P1', contextTitle:'Check timing before motion.', contextDescription:'A safe servo demo starts by verifying 50 Hz and a 900–2100 µs high pulse. Visible motion still requires a separate verified 5 V supply.', steps:['C6 sends PWM','S3 counts pulses','Verify width'], scale:65},
  imu: {title:'Motion sensor', accent:'live stream', description:'Watch the ESP32-C6 read acceleration from the MPU family breakout as you tilt it.', tag:'I²C SENSOR', wiring:'MPU VCC → C6 3V3; GND → shared GND; SDA → C6 IO6; SCL → C6 IO7; ADO → GND; NCS → 3V3. S3 P1 is not on this bus yet.', physicalUnit:'', dutUnit:'g', physicalDescription:'P1 bus observation is not connected yet', dutDescription:'Acceleration magnitude reported by C6', contextTitle:'Verify the stream, then the bus.', contextDescription:'The C6 motion stream proves it can read the MPU. Independent electrical evidence requires moving the S3 P1 tip to an isolated I²C line.', steps:['C6 reads MPU','Tilt the board','Probe I²C bus'], scale:2}
};
const PREVIEW = {
  light:{physical:{voltage_v:2.207},dut:{reported_voltage_v:0},diagnosis:{state:'fail',title:'Sensor report disagrees',detail:'The DUT is 2.21 V away from the independent probe (>0.45 V).'}},
  led:{physical:{frequency_hz:2,edges:4,pulse_us:0},dut:null,diagnosis:{state:'pass',title:'Physical signal matches',detail:'The S3 probe measured the expected timing at P1.'}},
  servo:{physical:{frequency_hz:49.95,edges:50,pulse_us:1500},dut:null,diagnosis:{state:'pass',title:'Physical signal matches',detail:'The S3 probe measured the expected timing at P1.'}},
  imu:{physical:null,dut:{x_g:0.12,y_g:-0.08,z_g:0.99,magnitude_g:1.00,address:'0x68',who_am_i:'0x71'},diagnosis:{state:'unverified',title:'Motion stream detected',detail:'These values come from the DUT. Move P1 to an isolated I²C line for independent electrical evidence.'}}
};
let mode='light', preview=false, busy=false, generation=0, timer=null;
const history={physical:[],dut:[]};

function benchScene(which){
  const captions={
    light:{center:'T / SENSOR NODE',bottom:'PHOTORESISTOR + PULL-DOWN'},
    led:{center:'T / OUTPUT NODE',bottom:'LED + SERIES RESISTOR'},
    servo:{center:'T / SERVO SIGNAL',bottom:'RED POWER LEAD UNCONNECTED'},
    imu:{center:'MPU / I²C',bottom:'SDA + SCL · 3.3 V ONLY'}
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
  $('diagram-tag').textContent=`${c.tag} · REFERENCE`;
  $('wiring-description').textContent=c.wiring;
  $('circuit-diagram').innerHTML=benchScene(mode);
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
  const scene=$('circuit-diagram').querySelector('.scene');
  scene.dataset.state=state;
  if(!preview&&data.physical){scene.classList.remove('sampling');void scene.offsetWidth;scene.classList.add('sampling')}
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
  $('connection-dot').className=`connection-dot ${preview?'preview':connected?'':'off'}`;
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
$('preview-toggle').addEventListener('click',()=>{preview=!preview;generation++;document.body.classList.toggle('preview',preview);$('preview-toggle').classList.toggle('active',preview);$('preview-toggle').setAttribute('aria-pressed',String(preview));$('session-badge').textContent=preview?'PREVIEW DATA':'LIVE SESSION';renderMode()});
$('refresh-button').addEventListener('click',async()=>{await loadPorts();generation++;tick()});
loadPorts().then(()=>{renderMode();timer=setInterval(tick,3500)});
