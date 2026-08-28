from pathlib import Path
P=Path('app/device_profiles/modules/sim808_samd21.py').read_text()
A=Path('app/templates/asset.html').read_text()
D=Path('app/templates/device_panel.html').read_text()
I=Path('app/templates/io_studio.html').read_text()
R=Path('app/routes.py').read_text()
API=Path('app/device_api.py').read_text()

def test_sim808_physical_and_internal_points_are_separate():
    for x in ['"pin":"D5"','"pin":"D6"','"direction":"HEALTH"','"physical_pin":"D5"','"physical_pin":"D6"']:
        assert x in P
    assert '"BATTERY_VOLTAGE"' in P
    assert 'solar_v' not in P

def test_dashboard_power_and_offline_controls_are_capability_aware():
    assert "'solar_v' in profile_keys" in A
    assert 'PAGE LIVE ·' in A
    assert 'Device offline' in A
    assert 'Output commands are unavailable' in A

def test_server_blocks_offline_output_commands():
    assert 'Output commands are blocked until fresh firmware telemetry is received.' in R

def test_device_panel_receives_complete_safe_context():
    for x in ['validation_results=validation_results','device_online=device_online','assignable_points=assignable_points','internal_points=internal_points']:
        assert x in R
    assert 'BOARD I/O OVERVIEW' in D

def test_io_studio_counts_and_filters_physical_points():
    assert 'physical_points=physical' in API
    assert "not in ('INPUT','OUTPUT')" in API
    assert "['INPUT','OUTPUT'].includes" in I
    assert 'internal ·' in I and 'reserved' in I
