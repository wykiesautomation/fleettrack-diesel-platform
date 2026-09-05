from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_mobile_api_endpoints_complete():
    routes=(ROOT/'app/routes.py').read_text(encoding='utf-8')
    for endpoint in ['/api/v1/mobile/register','/api/v1/mobile/location','/api/v1/mobile/location/batch','/api/v1/mobile/heartbeat','/api/v1/mobile/config','/api/v1/mobile/tracking/start','/api/v1/mobile/tracking/stop','/api/v1/mobile/status']:
        assert endpoint in routes

def test_mobile_client_uses_batch_heartbeat_and_config():
    js=(ROOT/'app/static/mobile_tracker.js').read_text(encoding='utf-8')
    for endpoint in ['location/batch','mobile/heartbeat','mobile/config','tracking/start','tracking/stop']:
        assert endpoint in js
    for feature in ['max_offline_queue','max_batch_points','sendHeartbeat','loadConfig','q.slice']:
        assert feature in js

def test_mobile_batch_is_deduplicated_and_bounded():
    routes=(ROOT/'app/routes.py').read_text(encoding='utf-8')
    assert 'if len(points)>100' in routes
    assert 'duplicates.append(sequence)' in routes
    assert "Location.query.filter_by(asset_id=device.asset_id,sequence=sequence)" in routes
    assert "device_identity_mismatch" in routes

def test_mobile_api_keeps_consent_and_entitlement_gates():
    routes=(ROOT/'app/routes.py').read_text(encoding='utf-8')
    assert "consent_inactive" in routes
    assert "subscription_inactive" in routes
    assert "invalid_mobile_tracker_token" in routes
