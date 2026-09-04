from pathlib import Path
R=Path('app/routes.py').read_text(encoding='utf-8')
B=Path('app/templates/base.html').read_text(encoding='utf-8')
S=Path('app/templates/asset_device_setup.html').read_text(encoding='utf-8')
D=Path('app/templates/devices.html').read_text(encoding='utf-8')
M=Path('app/templates/test_data_cleanup.html').read_text(encoding='utf-8')

def test_sidebar_has_one_admin_data_management_entry():
 assert '<span>Asset Cleanup</span>' not in B
 assert '<span>Data Management</span>' in B
 assert "current_user.role in ('customer_admin','platform_admin')" in B

def test_setup_page_has_safe_operations_but_no_permanent_delete():
 assert 'Replace Device' in S and 'Unlink Device' in S
 assert '>Delete Device<' not in S and '>Delete Site<' not in S
 assert 'It never permanently deletes data.' in S

def test_devices_registry_has_no_permanent_delete_button():
 assert 'Disable Device' in D and 'Enable Device' in D
 assert 'Delete Device Permanently</button>' not in D
 assert 'available only in Data Management' in D

def test_data_management_is_central_and_admin_only():
 assert 'Data Management & Permanent Deletion' in M
 assert 'Disabled & Unlinked Devices' in M
 assert "current_user.role not in ('customer_admin','platform_admin'):abort(403)" in R

def test_device_delete_requires_disabled_and_unlinked_state():
 assert "'deletable':bool(not device.active and not device.asset_id)" in R
 assert 'Ready for permanent deletion' in M
 assert 'Protected:' in M
