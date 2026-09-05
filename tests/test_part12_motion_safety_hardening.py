from pathlib import Path
M=Path('app/mobile_safety.py').read_text(encoding='utf-8');R=Path('app/routes.py').read_text(encoding='utf-8');I=Path('app/__init__.py').read_text(encoding='utf-8');T=Path('app/templates/motion_safety_setup.html').read_text(encoding='utf-8')
def test_setup_and_calibration_contract():
 for token in ('motion-safety-setup','baseline_roll','baseline_pitch','mounting_not_stable','VEHICLE','WALKING'):assert token in M or token in T
def test_crash_and_rollover_gates():
 for token in ('speed_drop','stationary_after_impact','orientation_evidence','gps_fresh','ROLLOVER_DETECTED','orientation_recovered','CONFIRMATION_PENDING'):assert token in M
def test_harsh_cross_validation():
 for token in ('HARSH_BRAKING','SEVERE_BRAKING','HARSH_ACCELERATION','gps_speed_delta_kmh','acceleration_threshold_ms2'):assert token in M
def test_notification_and_audit():
 assert 'EmailNotificationLog' in M and 'CRITICAL_NOTIFICATION_QUEUED' in M and 'acknowledgement required' in M
def test_api_hardening():
 assert 'request_too_large' in M and 'rate_limit_exceeded' in M and '/api/v1/mobile/token/rotate' in M
 assert 'app.before_request(mobile_api_guard)' in I
def test_existing_event_ingest_uses_confirmation():
 assert 'confirmation(row,data,device)' in R
