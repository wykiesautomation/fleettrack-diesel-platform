from pathlib import Path
R=Path('app/routes.py').read_text(encoding='utf-8')
J=Path('app/static/phone_motion_safety.js').read_text(encoding='utf-8')
M=Path('app/static/mobile_tracker.js').read_text(encoding='utf-8')
H=Path('app/templates/mobile_tracker.html').read_text(encoding='utf-8')
T=Path('app/templates/tracking_history.html').read_text(encoding='utf-8')

def test_motion_capability_endpoint_and_profile():
    assert "/api/v1/mobile/motion/capabilities" in R
    for value in ['MOTION_SENSORS','ORIENTATION_SENSOR','POSSIBLE_IMPACT','ABNORMAL_TILT','UNEXPECTED_MOVEMENT']:
        assert value in R
    assert 'candidate_events_only' in R

def test_browser_capability_and_permission_flow():
    assert "'DeviceMotionEvent' in window" in J
    assert "'DeviceOrientationEvent' in window" in J
    assert 'requestPermission' in J
    assert 'reportCapabilities' in J
    assert 'motionPermissionState' in H

def test_motion_candidates_and_thresholds():
    for event in ['POSSIBLE_ACCIDENT','ABNORMAL_TILT','UNEXPECTED_MOVEMENT']:
        assert event in J and event in R
    assert 'dynamic>=18' in J
    assert 'Math.abs(roll)>=65' in J
    assert 'Date.now()-tiltStartedAt>=5000' in J

def test_motion_events_are_queued_offline():
    assert 'at360_motion_event_queue_v2' in J
    assert 'flushMotionQueue' in J
    assert 'q.push(payload)' in J
    assert "window.addEventListener('online',flushMotionQueue)" in J

def test_profile_ui_is_real_and_capability_aware():
    for value in ['Enable Motion Safety','Possible impact','Abnormal tilt','Unexpected movement','Dynamic acceleration','Roll / pitch']:
        assert value in H
    assert 'Advisory candidate detection only' in H
    assert 'phone_motion_safety.js?v=34' in H

def test_main_tracker_shares_live_position_and_controls_motion_card():
    assert 'window.at360LastPosition=position' in M
    assert "el('motionCard')?.classList.remove('hidden')" in M
    assert "el('motionCard')?.classList.add('hidden')" in M

def test_tracking_ui_supports_verified_phone_capabilities():
    assert "'ABNORMAL_TILT':'rollover'" in R
    assert "'UNEXPECTED_MOVEMENT':'unauthorized_movement'" in R
    assert 'MOTION_SENSORS' in R
