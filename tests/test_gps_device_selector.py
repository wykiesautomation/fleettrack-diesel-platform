from pathlib import Path
R=Path('app/routes.py').read_text(encoding='utf-8');T=Path('app/templates/safety_twin.html').read_text(encoding='utf-8')
def test_fleet_tracking_uses_capability_aware_devices():
 for x in ('def gps_tracking_devices','GPS','GNSS','gps_location','LOCATION','MOBILE_WEB_TRACKER'):assert x in R
 assert "Asset.query.filter_by(customer_id=tenant_id(),asset_type='TRACKER').order_by" not in R
def test_selector_shows_identity_and_state():
 for x in ('SELECT GPS TRACKER','gpsTrackerSelect','row.asset.name','row.device.device_uid','row.state'):assert x in T
def test_selection_routes_to_exact_device():
 assert "device_id=selected['device'].id" in R
 assert "request.args.get('device_id',type=int)" in R
 assert 'selected_tracker_device_id' in R and 'selected_tracker_device_id' in T
def test_selector_is_tenant_scoped():
 assert 'Device.query.filter_by(customer_id=customer_id,active=True)' in R
 assert 'asset.customer_id!=customer_id' in R
