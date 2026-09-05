from pathlib import Path
R=Path('app/routes.py').read_text();T=Path('app/templates/tracking_history.html').read_text();A=Path('app/admin.py').read_text();C=Path('app/templates/platform_admin_customer.html').read_text();D=Path('app/templates/platform_admin_data_management.html').read_text();N=Path('app/templates/platform_admin_base.html').read_text();B=Path('app/templates/base.html').read_text();S=Path('app/templates/asset_device_setup.html').read_text();V=Path('app/templates/devices.html').read_text()
def test_route_requires_three_consecutive_valid_points():
 assert 'if len(fragment)>=3' in R
 assert '.filter(line=>line.length>=3)' in T
 assert 'if(segment.length>=3)' in T
def test_route_breaks_on_time_and_quality_gaps():
 for x in ("gap_seconds>120","OUT_OF_ORDER","IMPLAUSIBLE_JUMP","close_segment()"):
  assert x in R
def test_insufficient_route_is_not_drawn_or_measured():
 assert 'INSUFFICIENT_ROUTE_EVIDENCE' in R
 assert 'WAITING_FOR_VALIDATED_ROUTE' in R
 assert "strict['maximum_speed'] if accepted else 0" in R
def test_tenant_deletes_are_only_in_data_management():
 assert 'Asset Cleanup</span>' not in B and '<span>Data Management</span>' in B
 assert 'id="deleteBtn"' not in S and 'Delete Device Permanently' not in V
def test_customer_delete_is_only_on_platform_data_management():
 assert "def data_management()" in A
 assert 'Delete Customer Permanently' in D
 assert "url_for('admin.delete_customer'" not in C
 assert "url_for('admin.data_management')" in N
def test_existing_motion_and_api_contracts_remain():
 assert Path('app/mobile_safety.py').exists()
 assert "@bp.post('/api/v1/mobile/location/batch')" in R
