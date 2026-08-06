(() => {
  'use strict';

  const API = {
    register: '/api/v1/mobile/register',
    location: '/api/v1/mobile/location'
  };
  const STORAGE_KEY = 'at360_mobile_tracker_v1';
  let watchId = null;
  let batteryLevel = null;
  let charging = null;

  const el = (id) => document.getElementById(id);

  function log(message) {
    const target = el('log');
    if (!target) return;
    target.textContent = `${new Date().toLocaleTimeString()}  ${message}\n${target.textContent}`;
  }

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (error) {
      log(`Local storage error: ${error.message}`);
      return null;
    }
  }

  function saveState(value) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  }

  function setRegisterBusy(busy) {
    const button = el('registerBtn');
    if (!button) return;
    button.disabled = busy;
    button.textContent = busy ? 'Registering...' : 'Register Phone';
  }

  function showTracker(state) {
    el('registerCard')?.classList.add('hidden');
    el('trackerCard')?.classList.remove('hidden');
    if (el('deviceUid')) el('deviceUid').textContent = state.device_uid || '-';
    if (el('assetName')) el('assetName').textContent = state.asset_name || 'Mobile Tracker';
    if (el('network')) el('network').textContent = navigator.onLine ? 'Online' : 'Offline';
  }

  function showRegistration() {
    el('trackerCard')?.classList.add('hidden');
    el('registerCard')?.classList.remove('hidden');
  }

  async function safeJson(response) {
    const text = await response.text();
    if (!text) return {};
    try { return JSON.parse(text); }
    catch { return { error: text.slice(0, 240) }; }
  }

  async function registerPhone() {
    const input = el('code');
    const code = (input?.value || '').trim().toUpperCase();
    if (!code || code.length < 8) {
      log('Enter the full one-time registration code.');
      input?.focus();
      return;
    }

    setRegisterBusy(true);
    log('Registering this phone...');
    try {
      const response = await fetch(API.register, {
        method: 'POST',
        cache: 'no-store',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ code })
      });
      const data = await safeJson(response);
      if (!response.ok) {
        log(`Registration failed: ${data.error || `HTTP ${response.status}`}`);
        return;
      }
      if (!data.device_uid || !data.device_token) {
        log('Registration failed: server response is incomplete.');
        return;
      }
      const state = {
        device_uid: data.device_uid,
        token: data.device_token,
        asset_name: data.asset_name || 'Mobile Tracker',
        sequence: 0
      };
      saveState(state);
      showTracker(state);
      log(`Phone registered as ${state.device_uid}. Press Start Tracking.`);
    } catch (error) {
      log(`Registration error: ${error.message}`);
    } finally {
      setRegisterBusy(false);
    }
  }

  function nextSequence() {
    const state = loadState();
    if (!state) throw new Error('Phone is not registered');
    state.sequence = (state.sequence || 0) + 1;
    saveState(state);
    return `${state.device_uid}-${Date.now()}-${state.sequence}`;
  }

  async function sendPosition(position) {
    const state = loadState();
    if (!state) {
      stopTracking();
      showRegistration();
      log('Registration is missing. Register this phone again.');
      return;
    }
    const coords = position.coords;
    const measuredSpeed = coords.speed == null ? 0 : coords.speed * 3.6;
    const payload = {
      device_id: state.device_uid,
      sequence: nextSequence(),
      timestamp: new Date(position.timestamp).toISOString(),
      latitude: coords.latitude,
      longitude: coords.longitude,
      accuracy_m: coords.accuracy,
      speed_kmh: measuredSpeed < 3 ? 0 : measuredSpeed,
      heading: coords.heading,
      battery_percent: batteryLevel,
      charging,
      client_version: 'mobile-web-1.3'
    };

    try {
      const response = await fetch(API.location, {
        method: 'POST',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
          'Authorization': `Bearer ${state.token}`
        },
        body: JSON.stringify(payload)
      });
      const data = await safeJson(response);
      if (!response.ok) {
        log(`Upload failed: ${data.error || `HTTP ${response.status}`}`);
        if (response.status === 401 || response.status === 403) {
          stopTracking();
          localStorage.removeItem(STORAGE_KEY);
          showRegistration();
          log('Device token is invalid or revoked. Register this phone again.');
        }
        return;
      }
      if (el('accuracy')) el('accuracy').textContent = `${Math.round(coords.accuracy)} m`;
      if (el('coords')) el('coords').textContent = `${coords.latitude.toFixed(5)}, ${coords.longitude.toFixed(5)}`;
      if (el('lastUpload')) el('lastUpload').textContent = new Date().toLocaleTimeString();
      log(`Position uploaded${batteryLevel !== null ? ` · Battery ${batteryLevel}%` : ''}`);
    } catch (error) {
      log(`Upload error: ${error.message}`);
    }
  }

  function startTracking() {
    if (!loadState()) {
      showRegistration();
      log('Register this phone before starting tracking.');
      return;
    }
    if (!navigator.geolocation) {
      log('This browser does not support location tracking.');
      return;
    }
    if (watchId !== null) {
      log('Tracking is already active.');
      return;
    }
    watchId = navigator.geolocation.watchPosition(
      sendPosition,
      (error) => log(`GPS error ${error.code}: ${error.message}`),
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 30000 }
    );
    if (el('statusPill')) {
      el('statusPill').textContent = 'TRACKING';
      el('statusPill').className = 'pill active';
    }
    el('startBtn')?.classList.add('hidden');
    el('stopBtn')?.classList.remove('hidden');
    log('Tracking started by the phone user.');
  }

  function stopTracking() {
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
    watchId = null;
    if (el('statusPill')) {
      el('statusPill').textContent = 'STOPPED';
      el('statusPill').className = 'pill off';
    }
    el('startBtn')?.classList.remove('hidden');
    el('stopBtn')?.classList.add('hidden');
    log('Tracking stopped.');
  }

  function clearLog() { if (el('log')) el('log').textContent = 'Ready.'; }
  function flushQueue() { log('No queued points in this web tracker build.'); }
  function updateNetwork() { if (el('network')) el('network').textContent = navigator.onLine ? 'Online' : 'Offline'; }

  window.registerPhone = registerPhone;
  window.startTracking = startTracking;
  window.stopTracking = stopTracking;
  window.clearLog = clearLog;
  window.flushQueue = flushQueue;

  document.addEventListener('DOMContentLoaded', () => {
    const button = el('registerBtn');
    button?.addEventListener('click', registerPhone);
    el('code')?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') { event.preventDefault(); registerPhone(); }
    });
    const state = loadState();
    if (state?.device_uid && state?.token) showTracker(state); else showRegistration();
    updateNetwork();
    log('Tracker controls loaded.');
  });

  window.addEventListener('online', () => { updateNetwork(); log('Network online.'); });
  window.addEventListener('offline', () => { updateNetwork(); log('Network offline.'); });

  if (navigator.getBattery) {
    navigator.getBattery().then((battery) => {
      const update = () => { batteryLevel = Math.round(battery.level * 100); charging = battery.charging; };
      update();
      battery.addEventListener('levelchange', update);
      battery.addEventListener('chargingchange', update);
    }).catch(() => log('Battery status is not available in this browser.'));
  }
})();
