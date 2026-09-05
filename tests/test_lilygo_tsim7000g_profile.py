from pathlib import Path

P=Path('app/device_profiles/modules/lilygo_t_sim7000g.py').read_text(encoding='utf-8')
R=Path('app/device_profiles/registry.py').read_text(encoding='utf-8')
ROUTES=Path('app/routes.py').read_text(encoding='utf-8')
F=Path('firmware/AT360_LILYGO_T_SIM7000G_FINAL.ino').read_text(encoding='utf-8')

def test_profile_is_public_and_revision_safe():
    assert 'AT360_LILYGO_T_SIM7000G' in P and 'AT360_LILYGO_T_SIM7000G' in R
    assert 'UNVERIFIED_AUTO_DETECT' in P
    assert 'LOCKED_PENDING_PHYSICAL_REVISION_VALIDATION' in P
    for pin in ['GPIO4','GPIO13','GPIO26','GPIO27','GPIO35','GPIO36']:
        assert pin in P

def test_internal_capabilities_and_optional_sd():
    for key in ['gps_fix','speed_kmh','heading','satellites','battery_v','battery_percent','charging_status','solar_v','cellular_signal','network_registered','wifi_rssi','queue_depth','sd_status','simulation_mode']:
        assert f'"{key}"' in P
    assert '"output_channels": []' in P
    assert 'OPTIONAL_MICROSD' in P

def test_claim_uid_and_firmware_contract():
    assert 'AT360-TSIM7000G-' in ROUTES
    for text in ['AT360_LILYGO_T_SIM7000G','1.0.0-tsim7000g-revision-safe','battery_percent','cellular_signal','queue_depth','sd_status','simulation_mode','claim_code','device_token']:
        assert text in F
    assert 'Customer GPIO is locked' in F
