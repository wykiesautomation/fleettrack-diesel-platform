from pathlib import Path
S=Path('app/templates/asset_device_setup.html').read_text();D=Path('app/templates/devices.html').read_text();B=Path('app/templates/base.html').read_text();R=Path('app/routes.py').read_text();T=Path('app/templates/tracking_history.html').read_text()
def test_setup_has_no_delete_buttons_and_has_data_management_link():
 assert 'Delete Site</button>' not in S and 'id="deleteSiteBtn"' not in S
 assert 'id="deleteBtn"' not in S
 assert 'Open Data Management' in S
 assert "url_for('main.test_data_cleanup')" in S
def test_devices_has_visible_and_clickable_data_management():
 assert 'Open Data Management' in D
 assert "url_for('main.test_data_cleanup')" in D
 assert 'Delete Device Permanently' not in D
def test_sidebar_has_data_management():
 assert '<span>Data Management</span>' in B
 assert "main.test_data_cleanup" in B
def test_route_no_crow_flight():
 assert 'if len(fragment)>=3' in R
 assert 'WAITING_FOR_VALIDATED_ROUTE' in R
 assert '.filter(line=>line.length>=3)' in T
