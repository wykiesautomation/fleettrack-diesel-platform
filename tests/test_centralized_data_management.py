from pathlib import Path
B=Path('app/templates/base.html').read_text();S=Path('app/templates/asset_device_setup.html').read_text();D=Path('app/templates/devices.html').read_text();C=Path('app/templates/test_data_cleanup.html').read_text();R=Path('app/routes.py').read_text()
def test_sidebar_has_one_data_management_entry_under_account():
 assert 'Asset Cleanup</span>' not in B
 assert '<span>Data Management</span>' in B
 assert "current_user.role in ('customer_admin','platform_admin')" in B
def test_setup_has_no_permanent_delete_actions():
 assert 'id="deleteBtn"' not in S and 'id="deleteSiteBtn"' not in S
 assert 'Replace Device' in S and 'Unlink Device' in S
 assert 'Account → Data Management' in S
def test_devices_registry_has_no_delete_form():
 assert "url_for('main.delete_device'" not in D
 assert 'For permanent deletion use Account → Data Management.' in D
def test_central_page_manages_assets_devices_and_sites():
 assert 'Data Management & Permanent Deletion' in C
 assert 'Delete Device Permanently' in C and 'Delete Site Permanently' in C and 'Delete Asset Permanently' in C
def test_device_delete_requires_disabled_unlinked_and_exact_confirmation():
 block=R[R.index('def delete_device'):R.index("@bp.post('/devices/<int:device_id>/rotate-token')")]
 assert 'record.active or record.asset_id' in block
 assert "confirm_uid" in block and "confirm_word" in block
 assert "url_for('main.test_data_cleanup')" in block
def test_deletion_routes_are_admin_role_guarded():
 for fn in ('delete_test_asset','delete_test_site','delete_device'):
  i=R.index('def '+fn); assert "current_user.role not in ('customer_admin','platform_admin')" in R[i:i+220]
