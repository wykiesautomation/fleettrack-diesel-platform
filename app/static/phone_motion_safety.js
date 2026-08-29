(() => {
  'use strict';
  const STORAGE_KEY='at360_mobile_tracker_v1';
  const MOTION_KEY='at360_motion_profile_v2';
  const EVENT_QUEUE_KEY='at360_motion_event_queue_v2';
  const SAMPLE_QUEUE_KEY='at360_motion_sample_queue_v1';
  const API={
    capabilities:'/api/v1/mobile/motion/capabilities',
    event:'/api/v1/mobile/event',
    setup:'/api/v1/mobile/motion/setup',
    calibrate:'/api/v1/mobile/motion/calibrate',
    samples:'/api/v1/mobile/motion/samples'
  };
  let enabled=false;
  let calibrating=false;
  let calibrationSamples=[];
  let sampleBuffer=[];
  let lastImpactAt=0;
  let lastHarshAt=0;
  let tiltStartedAt=0;
  let lastTiltEventAt=0;
  let lastUnexpectedAt=0;
  let lastOrientation={roll:0,pitch:0};
  let lastGpsSpeed=0;
  let previousGpsSpeed=0;
  let lastSpeedAt=Date.now();
  let stationarySince=Date.now();
  let activeImpactEvent=null;
  let impactTimer=null;
  const el=id=>document.getElementById(id);
  function state(){try{return JSON.parse(localStorage.getItem(STORAGE_KEY)||'null');}catch{return null;}}
  function auth(){const s=state();return s?{'Content-Type':'application/json','Accept':'application/json','Authorization':`Bearer ${s.token}`}:{'Content-Type':'application/json'};}
  function saved(){try{return JSON.parse(localStorage.getItem(MOTION_KEY)||'{}');}catch{return{};}}
  function save(v){localStorage.setItem(MOTION_KEY,JSON.stringify({...saved(),...v}));}
  function log(m){const box=el('motionLog');if(box)box.textContent=`${new Date().toLocaleTimeString()}  ${m}\n${box.textContent}`;}
  function badge(id,text,ok=false){const node=el(id);if(node){node.textContent=text;node.className=`motion-badge ${ok?'ok':''}`;}}
  function queue(){try{return JSON.parse(localStorage.getItem(EVENT_QUEUE_KEY)||'[]');}catch{return[];}}
  function saveQueue(q){localStorage.setItem(EVENT_QUEUE_KEY,JSON.stringify(q.slice(-200)));if(el('motionQueueCount'))el('motionQueueCount').textContent=q.length;}
  async function requestJson(url,options={}){const response=await fetch(url,{...options,headers:{...auth(),...(options.headers||{})}});const body=await response.json().catch(()=>({}));if(!response.ok)throw new Error(body.error||`HTTP ${response.status}`);return body;}
  function currentPosition(){return window.at360LastPosition?.coords||null;}
  function currentSpeed(){const p=currentPosition();return Math.max(0,Number(p?.speed||0)*3.6);}
  function candidatePayload(type,extra={}){const s=state(),p=currentPosition();return{event:type,device_id:s?.device_uid,sequence:`${s?.device_uid||'phone'}-motion-${Date.now()}-${Math.random().toString(16).slice(2,8)}`,timestamp:new Date().toISOString(),latitude:p?.latitude??null,longitude:p?.longitude??null,accuracy_m:p?.accuracy??null,speed_before_kmh:extra.speed_before_kmh??previousGpsSpeed,speed_after_kmh:extra.speed_after_kmh??lastGpsSpeed,confidence:extra.confidence||0.5,client_version:'mobile-web-motion-3.0',motion_source:'PHONE_WEB',roll_deg:lastOrientation.roll,pitch_deg:lastOrientation.pitch,...extra};}
  async function sendCandidate(payload){try{const body=await requestJson(API.event,{method:'POST',body:JSON.stringify(payload)});log(`${payload.event.replaceAll('_',' ')} accepted.`);return body;}catch(error){const q=queue();q.push(payload);saveQueue(q);log(`${payload.event} queued offline: ${error.message}`);return null;}}
  async function reportCapabilities(permission){const s=state();if(!s)return;const body={device_id:s.device_uid,device_motion:'DeviceMotionEvent' in window,device_orientation:'DeviceOrientationEvent' in window,permission};const result=await requestJson(API.capabilities,{method:'POST',body:JSON.stringify(body)});const c=result.capabilities||{};badge('motionSensorState',c.motion_sensor?'AVAILABLE':'UNAVAILABLE',c.motion_sensor);badge('orientationSensorState',c.orientation_sensor?'AVAILABLE':'UNAVAILABLE',c.orientation_sensor);badge('impactState',c.possible_impact?'AVAILABLE':'SETUP REQUIRED',c.possible_impact);badge('tiltState',c.abnormal_tilt?'AVAILABLE':'SETUP REQUIRED',c.abnormal_tilt);badge('movementState',c.unexpected_movement?'AVAILABLE':'SETUP REQUIRED',c.unexpected_movement);badge('motionPermissionState',c.permission||permission,c.permission==='GRANTED'||c.permission==='NOT_REQUIRED');}
  function updateSpeed(){const speed=currentSpeed(),now=Date.now();previousGpsSpeed=lastGpsSpeed;lastGpsSpeed=speed;if(speed<3){if(!stationarySince)stationarySince=now;}else stationarySince=0;const elapsed=Math.max(.25,(now-lastSpeedAt)/1000);lastSpeedAt=now;return{speed,elapsed,deltaMs2:((speed-previousGpsSpeed)/3.6)/elapsed};}
  function samplePayload(dynamic){const s=state(),p=currentPosition();return{sequence:`${s?.device_uid||'phone'}-sample-${Date.now()}-${Math.random().toString(16).slice(2,8)}`,timestamp:new Date().toISOString(),dynamic_acceleration_ms2:dynamic,roll_deg:lastOrientation.roll,pitch_deg:lastOrientation.pitch,speed_kmh:lastGpsSpeed,accuracy_m:p?.accuracy??0};}
  async function flushSamples(){if(!sampleBuffer.length)return;const batch=sampleBuffer.splice(0,Math.min(100,sampleBuffer.length));try{await requestJson(API.samples,{method:'POST',body:JSON.stringify({samples:batch})});}catch{sampleBuffer=batch.concat(sampleBuffer).slice(-300);localStorage.setItem(SAMPLE_QUEUE_KEY,JSON.stringify(sampleBuffer));}}
  function motionHandler(e){if(!enabled)return;const a=e.accelerationIncludingGravity||e.acceleration;if(!a)return;const x=Number(a.x||0),y=Number(a.y||0),z=Number(a.z||0),magnitude=Math.sqrt(x*x+y*y+z*z),dynamic=Math.abs(magnitude-9.81),now=Date.now();const speed=updateSpeed();if(el('accelerationValue'))el('accelerationValue').textContent=`${dynamic.toFixed(2)} m/s²`;sampleBuffer.push(samplePayload(dynamic));if(sampleBuffer.length>=20)flushSamples();if(dynamic>=18&&now-lastImpactAt>30000){lastImpactAt=now;const payload=candidatePayload('POSSIBLE_ACCIDENT',{confidence:Math.min(.95,.48+dynamic/55),peak_acceleration_ms2:dynamic,speed_before_kmh:previousGpsSpeed,speed_after_kmh:lastGpsSpeed});sendCandidate(payload).then(result=>startImpactCountdown(result?.event_id||null,payload.sequence,30));}if(now-lastHarshAt>12000&&previousGpsSpeed>=5){if(speed.deltaMs2<=-7.5){lastHarshAt=now;sendCandidate(candidatePayload('SEVERE_BRAKING',{confidence:.86,deceleration_ms2:speed.deltaMs2,speed_before_kmh:previousGpsSpeed,speed_after_kmh:lastGpsSpeed}));}else if(speed.deltaMs2<=-4.5){lastHarshAt=now;sendCandidate(candidatePayload('HARSH_BRAKING',{confidence:.74,deceleration_ms2:speed.deltaMs2,speed_before_kmh:previousGpsSpeed,speed_after_kmh:lastGpsSpeed}));}else if(speed.deltaMs2>=4){lastHarshAt=now;sendCandidate(candidatePayload('HARSH_ACCELERATION',{confidence:.72,peak_acceleration_ms2:speed.deltaMs2,speed_before_kmh:previousGpsSpeed,speed_after_kmh:lastGpsSpeed}));}}if(dynamic>=6&&lastGpsSpeed<3&&stationarySince&&now-stationarySince>60000&&now-lastUnexpectedAt>60000){lastUnexpectedAt=now;sendCandidate(candidatePayload('UNEXPECTED_MOVEMENT',{confidence:.58,peak_acceleration_ms2:dynamic}));}}
  function orientationHandler(e){const roll=Number(e.gamma||0),pitch=Number(e.beta||0),now=Date.now();lastOrientation={roll,pitch};if(el('orientationValue'))el('orientationValue').textContent=`${roll.toFixed(1)}° / ${pitch.toFixed(1)}°`;if(calibrating){calibrationSamples.push({roll_deg:roll,pitch_deg:pitch});const target=60;if(el('calibrationProgress'))el('calibrationProgress').textContent=`${Math.min(calibrationSamples.length,target)}/${target}`;if(calibrationSamples.length>=target)finishMotionCalibration();}if(Math.abs(roll)>=65||Math.abs(pitch)>=110){if(!tiltStartedAt)tiltStartedAt=now;if(Date.now()-tiltStartedAt>=5000&&now-lastTiltEventAt>60000){lastTiltEventAt=now;sendCandidate(candidatePayload('ABNORMAL_TILT',{confidence:.72,orientation_duration_seconds:(now-tiltStartedAt)/1000}));}}else tiltStartedAt=0;}
  window.startMotionCalibration=async()=>{if(!enabled){log('Enable Motion Safety before calibration.');return;}calibrationSamples=[];calibrating=true;badge('calibrationState','SAMPLING');if(el('calibrationProgress'))el('calibrationProgress').textContent='0/60';log('Keep the phone fixed and vehicle stationary during calibration.');};
  async function finishMotionCalibration(){if(!calibrating)return;calibrating=false;const s=state();try{const result=await requestJson(API.calibrate,{method:'POST',body:JSON.stringify({device_id:s.device_uid,permission:'GRANTED',samples:calibrationSamples})});badge('calibrationState','CALIBRATED',true);if(el('calibrationProgress'))el('calibrationProgress').textContent='60/60';log(`Mounting calibrated. Roll ${result.config?.baseline_roll??result.baseline_roll}°, pitch ${result.config?.baseline_pitch??result.baseline_pitch}°.`);save({mounted:true,calibrated_at:new Date().toISOString()});}catch(error){badge('calibrationState','FAILED');log(`Calibration failed: ${error.message}`);}finally{calibrationSamples=[];}}
  function startImpactCountdown(eventId,sequence,seconds){activeImpactEvent={eventId,sequence};let remaining=seconds;const box=el('impactCountdown');if(box)box.classList.remove('hidden');if(impactTimer)clearInterval(impactTimer);const tick=()=>{if(el('impactSeconds'))el('impactSeconds').textContent=remaining;if(remaining--<=0){clearInterval(impactTimer);impactTimer=null;activeImpactEvent=null;if(box)box.classList.add('hidden');log('Possible impact cancellation window closed.');}};tick();impactTimer=setInterval(tick,1000);}
  window.cancelPossibleImpact=async()=>{if(!activeImpactEvent){log('No active possible-impact candidate to cancel.');return;}try{if(activeImpactEvent.eventId){await requestJson(`/api/v1/mobile/events/${activeImpactEvent.eventId}/cancel`,{method:'POST',body:'{}'});}else{await sendCandidate(candidatePayload('POSSIBLE_ACCIDENT_CANCELLED',{related_sequence:activeImpactEvent.sequence,confidence:1}));}if(impactTimer)clearInterval(impactTimer);impactTimer=null;activeImpactEvent=null;if(el('impactCountdown'))el('impactCountdown').classList.add('hidden');log('Possible impact cancelled by phone user.');}catch(error){log(`Impact cancellation failed: ${error.message}`);}};
  window.enableMotionSafety=async()=>{let permission='NOT_REQUIRED';try{if(typeof DeviceMotionEvent!=='undefined'&&typeof DeviceMotionEvent.requestPermission==='function')permission=(await DeviceMotionEvent.requestPermission()).toUpperCase();if(permission==='GRANTED'||permission==='NOT_REQUIRED'){window.addEventListener('devicemotion',motionHandler);window.addEventListener('deviceorientation',orientationHandler);enabled=true;save({enabled:true});badge('motionProfileState','ON',true);badge('motionPermissionState',permission,true);await reportCapabilities(permission);log('Motion Safety enabled.');}else{badge('motionPermissionState','DENIED');log('Motion permission was denied.');}}catch(error){badge('motionPermissionState','ERROR');log(error.message);}};
  window.disableMotionSafety=()=>{enabled=false;window.removeEventListener('devicemotion',motionHandler);window.removeEventListener('deviceorientation',orientationHandler);save({enabled:false});badge('motionProfileState','OFF');log('Motion Safety disabled.');};
  window.flushMotionQueue=async()=>{const q=queue(),left=[];for(const payload of q){try{await requestJson(API.event,{method:'POST',body:JSON.stringify(payload)});}catch{left.push(payload);}}saveQueue(left);await flushSamples();log(left.length?`${left.length} motion event(s) remain queued.`:'Motion event queue sent.');};
  const flushMotionQueue=window.flushMotionQueue;window.addEventListener('online',flushMotionQueue);
  badge('motionApiState','DeviceMotionEvent' in window?'AVAILABLE':'UNAVAILABLE','DeviceMotionEvent' in window);
  badge('orientationApiState','DeviceOrientationEvent' in window?'AVAILABLE':'UNAVAILABLE','DeviceOrientationEvent' in window);
  saveQueue(queue());
  try{const offlineSamples=JSON.parse(localStorage.getItem(SAMPLE_QUEUE_KEY)||'[]');if(Array.isArray(offlineSamples))sampleBuffer=offlineSamples.slice(-300);}catch{}
})();
