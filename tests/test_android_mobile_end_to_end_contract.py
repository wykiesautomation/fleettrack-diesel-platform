from pathlib import Path
R=Path('app/routes.py').read_text()
def test_registration_keeps_android_client_version():
 assert "client_version=str(data.get('client_version')" in R
 assert "'PLATFORM:'+platform" in R
def test_heartbeat_stores_battery_and_charging():
 b=R[R.index('def mobile_tracker_heartbeat():'):R.index('def mobile_tracker_location_batch():')]
 assert "key='battery_percent'" in b and "key='charging_status'" in b
 assert "':battery'" in b and "':charging'" in b
def test_batch_requires_device_id_and_updates_firmware():
 b=R[R.index('def mobile_tracker_location_batch():'):R.index('def mobile_tracking_start():')]
 assert "item.get('device_id'" in b and 'device.firmware=' in b
def test_start_updates_firmware_and_asset_contact():
 b=R[R.index('def mobile_tracking_start():'):R.index('def mobile_tracking_stop():')]
 assert "data=request.get_json" in b and 'device.asset.last_seen=utcnow()' in b
