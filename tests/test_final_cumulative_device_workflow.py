from pathlib import Path
API=Path('app/device_api.py').read_text();T=Path('app/templates/trends_limits.html').read_text();B=Path('app/templates/base.html').read_text();S=Path('app/templates/asset_device_setup.html').read_text();D=Path('app/templates/devices.html').read_text();M=Path('app/templates/test_data_cleanup.html').read_text();R=Path('app/routes.py').read_text();C=Path('app/static/primary_action_text_fix.css').read_text();REG=Path('app/device_profiles/registry.py').read_text()
def test_all_registered_devices_are_available_in_trends_selector():
 assert 'all_devices=Device.query.filter_by(customer_id=current_user.customer_id)' in API
 assert 'device_choices=device_choices' in API
 assert 'class="device-select"' in T
 assert "item.profile.get('display_name',item.device.device_type)" in T
 assert "item.linked_asset.name if item.linked_asset else 'Unlinked'" in T
 assert "'ONLINE' if item.online else 'OFFLINE'" in T
def test_assigned_points_remain_scoped_to_selected_device():
 assert "DeviceChannelAssignment.query.filter_by(device_id=dev.id,enabled=True)" in API
 assert 'Configure Assigned Pin' in T
 assert 'Assigned pins only' in T
def test_all_board_profiles_and_pins_remain_registered():
 for code in ('AT360_ESP32D_EXPANDED','AT360_ESP32_WROOM32','AT360_SIM808_TRACKER_2AI_2DO','AT360_LILYGO_T_SIM7000G'):assert code in REG
 for name in ('esp32_wroom32.py','esp32d_38pin.py','sim808_samd21.py','lilygo_t_sim7000g.py'):assert (Path('app/device_profiles/modules')/name).exists()
def test_permanent_delete_is_centralized():
 assert '<span>Asset Cleanup</span>' not in B and '<span>Data Management</span>' in B
 assert '>Delete Device<' not in S and '>Delete Site<' not in S
 assert 'Delete Device Permanently</button>' not in D
 assert 'Data Management & Permanent Deletion' in M and 'Disabled & Unlinked Devices' in M
def test_device_delete_requires_admin_disabled_unlinked_and_exact_confirmation():
 assert "current_user.role not in ('customer_admin','platform_admin'):abort(403)" in R
 assert "if record.asset_id:" in R
 assert "Exact device UID and DELETE are required." in R
def test_primary_cyan_actions_use_dark_text():
 assert "filename='primary_action_text_fix.css'" in B
 assert '--at360-primary-text:#031923' in C and 'a.asset-add' in C and ':is(:link,:visited)' in C
