from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_mobile_tracking_path_is_present():
    routes=(ROOT/'app/routes.py').read_text(encoding='utf-8')
    js=(ROOT/'app/static/mobile_tracker.js').read_text(encoding='utf-8')
    for value in ['/api/v1/mobile/register','/api/v1/mobile/location','/api/v1/mobile/status']:
        assert value in routes and value in js
    for value in ['watchPosition','TRACKING_KEY','QUEUE_KEY','battery_percent','accuracy_m','speed_kmh']:
        assert value in js

def test_mobile_device_panel_matches_approved_flow():
    html=(ROOT/'app/templates/device_panel.html').read_text(encoding='utf-8')
    for value in ['Mobile Tracker · Mobile data points','Safe profile enforcement active.','AUTO ASSIGNED','Save SOS Setting']:
        assert value in html
    assert 'Save Point' not in html
    assert '{% if not profile.virtual_profile %}' in html

def test_sim808_backend_profile_is_available():
    profile=(ROOT/'app/device_profiles/modules/sim808_samd21.py').read_text(encoding='utf-8')
    routes=(ROOT/'app/routes.py').read_text(encoding='utf-8')
    for value in ['AT360_SIM808_TRACKER_2AI_2DO','GPS','GPRS','STANDALONE_RECONNECT','DIGITAL_OUTPUT_2']:
        assert value in profile
    assert '/api/v2/telemetry' in routes

def test_mobile_profile_filters_stale_board_signals():
    routes=(ROOT/'app/routes.py').read_text(encoding='utf-8')
    assert 'profile=None if is_mobile_device else profile_for_device(device)' in routes
    assert 'mobile_keys' in routes
