from pathlib import Path
D=Path('app/templates/devices.html').read_text()
A=Path('app/templates/asset.html').read_text()
R=Path('app/routes.py').read_text()

def test_manage_javascript_is_executable_not_inside_title():
    title=D[D.index('{% block title %}'):D.index('{% endblock %}',D.index('{% block title %}'))]
    assert '<script>' not in title
    assert '{% block scripts %}<script>' in D
    assert 'toggleDeviceActions' in D

def test_device_management_has_disable_unlink_delete_and_studio():
    for text in ['Disable Device','Enable Device','Unlink from Asset','Delete Device Permanently','Device Studio']:
        assert text in D
    assert "shown_state='ONLINE' if item.online else 'OFFLINE'" in D

def test_tank_gps_is_capability_aware():
    assert 'has_location_capability=has_location_capability' in R
    assert 'valid_location=valid_location' in R
    assert 'Tank Location & Tracking' in A
    assert 'Tank Tracking' in A
    assert 'Waiting for a valid GPS fix' in A

def test_zero_zero_is_not_a_valid_position():
    assert 'abs(float(location.latitude))<0.000001' in R

def test_outputs_require_fresh_feedback_server_and_ui():
    assert 'Output state is not verified.' in R
    assert 'output_feedback_verified=output_feedback_verified' in R
    assert 'OUTPUT STATE NOT VERIFIED' in A
    assert 'not output_feedback_verified' in A

def test_sim808_not_labelled_as_esp32():
    assert 'LIVE · ESP32 physical input' not in A
    assert 'ESP32 Simulation' not in A
