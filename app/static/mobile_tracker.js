(() => {
  'use strict';
  const API={register:'/api/v1/mobile/register',location:'/api/v1/mobile/location',batch:'/api/v1/mobile/location/batch',heartbeat:'/api/v1/mobile/heartbeat',config:'/api/v1/mobile/config',start:'/api/v1/mobile/tracking/start',stop:'/api/v1/mobile/tracking/stop',event:'/api/v1/mobile/event',status:'/api/v1/mobile/status'};
  const STORAGE_KEY='at360_mobile_tracker_v1',QUEUE_KEY='at360_mobile_queue_v2',TRACKING_KEY='at360_tracking_enabled_v2';
  const HEARTBEAT_MS=60000,STALE_MS=150000,MAX_QUEUE=5000,WATCHDOG_MS=45000,RESTART_DELAY_MS=10000;
  let watchId=null,heartbeatId=null,healthId=null,watchdogId=null,restartId=null,wakeLock=null,lastPosition=null,lastFixAt=0,batteryLevel=null,charging=null,uploading=false,pausedByBrowser=false,retryDelay=2000,serverConfig={heartbeat_interval_seconds:60,max_batch_points:100,max_offline_queue:1000};
  const el=id=>document.getElementById(id);
  const nowIso=()=>new Date().toISOString();
  function platform(){const ua=navigator.userAgent||'';return /iPhone|iPad|iPod/i.test(ua)?'ios':/Android/i.test(ua)?'android':'web';}
  const authHeaders=s=>({'Content-Type':'application/json','Accept':'application/json','Authorization':`Bearer ${s.token}`});
  function log(message){const t=el('log');if(t)t.textContent=`${new Date().toLocaleTimeString()}  ${message}\n${t.textContent}`;}
  function read(key,fallback=null){try{const x=localStorage.getItem(key);return x?JSON.parse(x):fallback;}catch{return fallback;}}
  function write(key,value){localStorage.setItem(key,JSON.stringify(value));}
  const loadState=()=>read(STORAGE_KEY,null); const saveState=v=>write(STORAGE_KEY,v);
  const loadQueue=()=>read(QUEUE_KEY,[]); function saveQueue(q){write(QUEUE_KEY,q.slice(-Math.min(MAX_QUEUE,serverConfig.max_offline_queue||MAX_QUEUE)));updateQueue();}
  function trackingWanted(){return localStorage.getItem(TRACKING_KEY)==='true';}
  function setTrackingWanted(v){localStorage.setItem(TRACKING_KEY,v?'true':'false');}
  function setRegisterBusy(v){const b=el('registerBtn');if(b){b.disabled=v;b.textContent=v?'Registering...':'Register Phone';}}
  function showTracker(s){el('registerCard')?.classList.add('hidden');el('trackerCard')?.classList.remove('hidden');el('motionCard')?.classList.remove('hidden');if(el('deviceUid'))el('deviceUid').textContent=s.device_uid||'-';if(el('assetName'))el('assetName').textContent=s.asset_name||'Mobile Tracker';updateNetwork();updateQueue();refreshStatus();}
  function showRegistration(){el('trackerCard')?.classList.add('hidden');el('motionCard')?.classList.add('hidden');el('registerCard')?.classList.remove('hidden');}
  async function safeJson(r){const t=await r.text();try{return t?JSON.parse(t):{};}catch{return{error:t.slice(0,240)}}}
  function nextSequence(){const s=loadState();if(!s)throw Error('Phone is not registered');s.sequence=(s.sequence||0)+1;saveState(s);return`${s.device_uid}-${Date.now()}-${s.sequence}`;}
  function updateQueue(){if(el('queueCount'))el('queueCount').textContent=String(loadQueue().length);}
  function updateNetwork(){if(el('network'))el('network').textContent=navigator.onLine?'Online':'Offline';}
  function lastSuccess(){return Number(loadState()?.last_success_at||0);}
  function refreshStatus(){
    const pill=el('statusPill'); if(!pill)return;
    if(!trackingWanted()){pill.textContent='STOPPED';pill.className='pill off';return;}
    if(pausedByBrowser){pill.textContent='PAUSED BY BROWSER';pill.className='pill warning';return;}
    if(!navigator.onLine&&loadQueue().length){pill.textContent='OFFLINE QUEUE';pill.className='pill warning';return;}
    const age=Date.now()-lastSuccess();
    if(lastSuccess()===0){pill.textContent='STARTING';pill.className='pill warning';}
    else if(age<=STALE_MS){pill.textContent='TRACKING';pill.className='pill active';}
    else{pill.textContent='DELAYED';pill.className='pill warning';}
    const last=lastSuccess();if(el('lastUpload'))el('lastUpload').textContent=last?new Date(last).toLocaleTimeString():'Never';
  }
  function positionPayload(position,isHeartbeat=false){const s=loadState(),c=position.coords;const speed=c.speed==null?0:c.speed*3.6;return{device_id:s.device_uid,sequence:nextSequence(),timestamp:new Date(position.timestamp||Date.now()).toISOString(),latitude:c.latitude,longitude:c.longitude,accuracy_m:c.accuracy,speed_kmh:speed<3?0:speed,heading:c.heading,battery_percent:batteryLevel,charging,client_version:'mobile-web-1.4',heartbeat:isHeartbeat};}
  function enqueue(payload,reason){const q=loadQueue();q.push(payload);saveQueue(q);log(`Point queued (${reason}). Queue: ${q.length}`);}
  async function uploadPayload(payload,queueOnFailure=true){
    const s=loadState();if(!s)return false;
    try{
      const r=await fetch(API.location,{method:'POST',cache:'no-store',headers:{'Content-Type':'application/json','Accept':'application/json','Authorization':`Bearer ${s.token}`},body:JSON.stringify(payload)});const data=await safeJson(r);
      if(!r.ok){
        if(r.status===401||r.status===403){setTrackingWanted(false);stopWatch();localStorage.removeItem(STORAGE_KEY);showRegistration();log('Token invalid or consent inactive. Register again.');return false;}
        if(queueOnFailure)enqueue(payload,data.error||`HTTP ${r.status}`);return false;
      }
      s.last_success_at=Date.now();saveState(s);if(el('lastUpload'))el('lastUpload').textContent=new Date(s.last_success_at).toLocaleTimeString();refreshStatus();return true;
    }catch(e){if(queueOnFailure)enqueue(payload,e.message);return false;}
  }
  async function sendPosition(position){lastPosition=position;lastFixAt=Date.now();pausedByBrowser=false;window.at360LastPosition=position;if(el('accuracy'))el('accuracy').textContent=`${Math.round(position.coords.accuracy)} m`;if(el('coords'))el('coords').textContent=`${position.coords.latitude.toFixed(5)}, ${position.coords.longitude.toFixed(5)}`;const ok=await uploadPayload(positionPayload(position));if(ok){log(`Position uploaded${batteryLevel!==null?` · Battery ${batteryLevel}%`:''}`);flushQueue();}}
  async function flushQueue(){if(uploading||!navigator.onLine)return;const state=loadState(),queue=loadQueue();if(!state||!queue.length){updateQueue();return;}uploading=true;try{const limit=Math.min(100,serverConfig.max_batch_points||100),batch=queue.slice(0,limit),r=await fetch(API.batch,{method:'POST',cache:'no-store',headers:authHeaders(state),body:JSON.stringify({points:batch})}),d=await safeJson(r);if(r.status===401||r.status===403){setTrackingWanted(false);stopWatch();localStorage.removeItem(STORAGE_KEY);showRegistration();log('Token invalid or consent inactive. Register again.');return;}if(!r.ok&&r.status!==207)throw Error(d.error||`HTTP ${r.status}`);const handled=new Set([...(d.accepted||[]),...(d.duplicates||[])]),remaining=queue.filter((p,i)=>i>=limit||!handled.has(p.sequence));saveQueue(remaining);log(remaining.length?`${remaining.length} queued point(s) still pending.`:'Queued points uploaded.');if(remaining.length&&remaining.length<queue.length){retryDelay=2000;setTimeout(flushQueue,250);}}catch(e){log(`Queue upload delayed: ${e.message}`);const delay=retryDelay;retryDelay=Math.min(60000,retryDelay*2);setTimeout(flushQueue,delay);}finally{uploading=false;}}
  async function sendHeartbeat(){const state=loadState();if(!state||!navigator.onLine)return;try{const r=await fetch(API.heartbeat,{method:'POST',cache:'no-store',headers:authHeaders(state),body:JSON.stringify({device_id:state.device_uid,sequence:`hb-${Date.now()}`,battery_percent:batteryLevel,charging,platform:platform(),client_version:'mobile-web-2.0'})});if(r.ok){state.last_success_at=Date.now();saveState(state);refreshStatus();}}catch(e){log(`Heartbeat delayed: ${e.message}`);}}
  async function loadConfig(){const state=loadState();if(!state)return;try{const r=await fetch(API.config,{cache:'no-store',headers:{'Accept':'application/json','Authorization':`Bearer ${state.token}`}}),d=await safeJson(r);if(r.ok)serverConfig={...serverConfig,...d};}catch(e){log('Using safe local tracker settings.');}}
  async function sendEvent(event){const s=loadState();if(!s)return false;const endpoint=event==='TRACKING_STARTED'?API.start:event==='TRACKING_STOPPED'?API.stop:API.event;try{return(await fetch(endpoint,{method:'POST',cache:'no-store',headers:authHeaders(s),body:JSON.stringify({event})})).ok;}catch{return false;}}
  function stopWatch(){if(watchId!==null)navigator.geolocation.clearWatch(watchId);watchId=null;if(heartbeatId)clearInterval(heartbeatId);heartbeatId=null;if(watchdogId)clearInterval(watchdogId);watchdogId=null;if(restartId)clearTimeout(restartId);restartId=null;releaseWakeLock();}
  async function requestWakeLock(){if(!trackingWanted()||document.visibilityState!=='visible'||!('wakeLock' in navigator))return;try{wakeLock=await navigator.wakeLock.request('screen');wakeLock.addEventListener('release',()=>{wakeLock=null;});log('Screen wake lock active while tracker is visible.');}catch(e){log('Screen wake lock unavailable. Keep this screen open for browser tracking.');}}
  async function releaseWakeLock(){try{if(wakeLock)await wakeLock.release();}catch{}wakeLock=null;}
  function scheduleWatchRestart(reason){if(!trackingWanted()||restartId)return;log(`Tracking recovery scheduled (${reason}).`);restartId=setTimeout(()=>{restartId=null;if(watchId!==null){navigator.geolocation.clearWatch(watchId);watchId=null;}beginWatch(true);},RESTART_DELAY_MS);}
  function handleGpsError(e){log(`GPS error ${e.code}: ${e.message}`);if(e.code!==1)scheduleWatchRestart('GPS callback stopped');}
  function watchdog(){if(!trackingWanted())return;const silent=lastFixAt?Date.now()-lastFixAt:Infinity;if(document.visibilityState==='hidden'){pausedByBrowser=true;refreshStatus();return;}if(silent>STALE_MS)scheduleWatchRestart('no GPS fix received');}
  async function resumeTracking(reason){if(!trackingWanted())return;pausedByBrowser=false;if(watchId!==null){navigator.geolocation.clearWatch(watchId);watchId=null;}beginWatch(true);await requestWakeLock();sendHeartbeat();flushQueue();log(`Tracking resumed after ${reason}.`);}
  function beginWatch(restored=false){
    if(!navigator.geolocation){log('This browser does not support location tracking.');return;}
    if(watchId!==null)return;
    lastFixAt=Date.now();watchId=navigator.geolocation.watchPosition(sendPosition,handleGpsError,{enableHighAccuracy:true,maximumAge:30000,timeout:45000});
    heartbeatId=setInterval(()=>{sendHeartbeat();flushQueue();},Math.max(30000,(serverConfig.heartbeat_interval_seconds||60)*1000));watchdogId=setInterval(watchdog,WATCHDOG_MS);sendHeartbeat();requestWakeLock();
    el('startBtn')?.classList.add('hidden');el('stopBtn')?.classList.remove('hidden');refreshStatus();
    if(!restored)sendEvent('TRACKING_STARTED');log(restored?'Tracking restored after page reload.':'Tracking started by phone user.');
  }
  function startTracking(){if(!loadState()){showRegistration();log('Register this phone first.');return;}setTrackingWanted(true);beginWatch(false);}
  function stopTracking(notify=true){setTrackingWanted(false);stopWatch();el('startBtn')?.classList.remove('hidden');el('stopBtn')?.classList.add('hidden');refreshStatus();if(notify)sendEvent('TRACKING_STOPPED');log('Tracking stopped.');}
  async function registerPhone(){const code=(el('code')?.value||'').trim().toUpperCase();if(!el('consentCheck')?.checked){log('Accept the privacy notice.');return;}if(code.length<8){log('Enter the full registration code.');return;}setRegisterBusy(true);try{const r=await fetch(API.register,{method:'POST',cache:'no-store',credentials:'same-origin',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({code,consent:true,policy_version:'2026.1',platform:platform(),client_version:'mobile-web-2.0'})});const d=await safeJson(r);if(!r.ok)throw Error(d.error||`HTTP ${r.status}`);saveState({device_uid:d.device_uid,token:d.device_token,asset_name:d.asset_name||'Mobile Tracker',sequence:0,last_success_at:0});saveQueue([]);setTrackingWanted(false);showTracker(loadState());await loadConfig();log(`Phone registered as ${d.device_uid}.`);}catch(e){log(`Registration failed: ${e.message}`);}finally{setRegisterBusy(false);}}
  async function withdrawConsent(){stopTracking(false);if(await sendEvent('CONSENT_WITHDRAWN')){localStorage.removeItem(STORAGE_KEY);localStorage.removeItem(QUEUE_KEY);showRegistration();}}
  async function unregisterPhone(){if(!confirm('Unregister this phone and revoke its token?'))return;stopTracking(false);await sendEvent('UNREGISTERED');localStorage.removeItem(STORAGE_KEY);localStorage.removeItem(QUEUE_KEY);showRegistration();}
  async function requestDataDeletion(){if(await sendEvent('DATA_DELETION_REQUESTED'))log('Deletion request submitted.');}
  function clearLocalTrackerData(){stopTracking(false);localStorage.removeItem(STORAGE_KEY);localStorage.removeItem(QUEUE_KEY);showRegistration();log('Local tracker data cleared.');}
  function clearLog(){if(el('log'))el('log').textContent='Ready.';}
  window.registerPhone=registerPhone;window.startTracking=startTracking;window.stopTracking=stopTracking;window.flushQueue=flushQueue;window.withdrawConsent=withdrawConsent;window.unregisterPhone=unregisterPhone;window.requestDataDeletion=requestDataDeletion;window.clearLocalTrackerData=clearLocalTrackerData;window.clearLog=clearLog;
  document.addEventListener('DOMContentLoaded',()=>{el('registerBtn')?.addEventListener('click',registerPhone);const linkedCode=(el('code')?.value||'').trim();if(linkedCode){log('Secure one-time QR link loaded. Review consent and register this phone.');el('consentCheck')?.focus();}const s=loadState();if(s?.device_uid&&s?.token){showTracker(s);loadConfig().then(()=>{if(trackingWanted())beginWatch(true);});}else showRegistration();updateNetwork();updateQueue();healthId=setInterval(refreshStatus,15000);log('Tracker controls loaded.');});
  window.addEventListener('online',()=>{updateNetwork();log('Network online. Retrying queue.');flushQueue();});window.addEventListener('offline',()=>{updateNetwork();log('Network offline. New points will be queued.');});
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'&&trackingWanted()){pausedByBrowser=true;releaseWakeLock();refreshStatus();log('Browser backgrounded. Android may pause web GPS.');}else if(document.visibilityState==='visible')resumeTracking('browser foreground');});
  window.addEventListener('pageshow',()=>resumeTracking('page restore'));window.addEventListener('focus',()=>resumeTracking('window focus'));window.addEventListener('online',()=>resumeTracking('network recovery'));
  if(navigator.getBattery)navigator.getBattery().then(b=>{const u=()=>{batteryLevel=Math.round(b.level*100);charging=b.charging;};u();b.addEventListener('levelchange',u);b.addEventListener('chargingchange',u);}).catch(()=>log('Battery status unavailable.'));
})();
