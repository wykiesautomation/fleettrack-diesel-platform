from pathlib import Path
B=Path('app/templates/base.html').read_text(encoding='utf-8')
S=Path('app/templates/asset_device_setup.html').read_text(encoding='utf-8')
R=Path('app/routes.py').read_text(encoding='utf-8')

def test_sidebar_opens_management_not_onboarding():
    assert "url_for('main.asset_device_setup')" in B
    link=B[B.index("url_for('main.asset_device_setup')")-20:B.index("url_for('main.asset_device_setup')")+100]
    assert 'Asset & Device Setup' in link

def test_management_page_contains_expected_workflow():
    for text in ['Select Site','Select Existing Asset','Linked Device','Current Asset ↔ Device Link','Site Protection','Device Protection']:
        assert text in S

def test_onboarding_remains_separate_action():
    assert '+ Connect New Device' in S
    assert "url_for('main.connect_device')" in S

def test_management_actions_are_wired_to_real_routes():
    for endpoint in ['main.link_asset_device','main.replace_asset_device']:
        assert endpoint in S
    assert '/asset-device-setup/unlink/' in S
    assert '/devices/${device.value}/delete' in S
    assert "@bp.get('/asset-device-setup')" in R

def test_history_protection_wording_remains_visible():
    assert 'Asset history retained' in S
    assert 'historical trends stay available' in S
    assert 'No cascade delete is allowed' in S
