from pathlib import Path
B=Path('app/templates/base.html').read_text()
R=Path('app/routes.py').read_text()
AR=Path('app/templates/assets_register.html').read_text()
D=Path('app/device_api.py').read_text()
I=Path('app/templates/io_studio.html').read_text()
T=Path('app/templates/tracking_history.html').read_text()

def test_assets_and_monitoring_are_separate():
    assert "url_for('main.assets_register')" in B
    assert "url_for('main.onboarding')" in B
    assert "@bp.get('/assets')" in R
    assert '+ Add Asset or Vehicle' in AR

def test_asset_register_uses_real_customer_data():
    assert 'for row in rows' in AR
    assert 'Waiting for telemetry' in R
    assert 'No device assigned' in AR

def test_io_studio_has_every_customer_device_selector():
    assert 'all_devices=Device.query.filter_by(customer_id=current_user.customer_id)' in D
    assert 'for d in all_devices' in I
    assert "url_for('device_api.io_studio',device_id=d.id)" in I
    assert 'Unassigned' in I and 'Online' in I and 'Offline' in I

def test_io_studio_is_mobile_and_physical_capability_aware():
    assert 'Add Mobile Data Point' in I
    assert 'Available Virtual Point' in I
    assert 'Safe Point Number' in I
    assert "if(o)nameBox.value=o.dataset.label;else nameBox.value=''" in I
    assert "compatible_assets=[a for a in assets if (a.asset_type=='TRACKER' if mobile_device else True)]" in D

def test_phone_tracking_cards_are_specific_and_no_power_tamper():
    for text in ['GPS Tracking','Possible Impact','Abnormal Tilt','Harsh Driving','Unexpected Movement']:
        assert text in T
    cards=T[T.index('<div class="safety-cards phone-safety-cards">'):T.index('<div class="lower-grid">')]
    assert 'Power & Tamper' not in cards
