from pathlib import Path

TEMPLATE=Path('app/templates/io_studio.html').read_text(encoding='utf-8')
API=Path('app/device_api.py').read_text(encoding='utf-8')
SCHEMA=Path('app/device_profiles/schema.py').read_text(encoding='utf-8')
SIM808=Path('app/device_profiles/modules/sim808_samd21.py').read_text(encoding='utf-8')
WROOM=Path('app/device_profiles/modules/esp32_wroom32.py').read_text(encoding='utf-8')
ESP32D=Path('app/device_profiles/modules/esp32d_38pin.py').read_text(encoding='utf-8')

def test_shared_analog_channels_are_verified_calibratable_inputs():
    assert '"direction":"INPUT"' in SCHEMA
    assert '"calibratable":True' in SCHEMA
    assert 'analog_channel("analog_1", "Analog Input 1", "SIM808")' in SIM808
    assert '"pin": "A0"' in SIM808
    assert 'analog_channel("analog_2", "Analog Input 2", "SIM808")' in SIM808
    assert '"pin": "A1"' in SIM808
    assert 'analog_channel("analog_1", "Analog Input 1", "ESP32_WROOM32")' in WROOM
    assert '"pin": "GPIO34"' in WROOM
    for key,pin in [('analog_1','GPIO34'),('analog_2','GPIO35'),('analog_3','GPIO36'),('analog_4','GPIO39')]:
        assert f'analog_channel("{key}"' in ESP32D
        assert f'"pin": "{pin}"' in ESP32D

def test_io_studio_recognises_verified_calibratable_analogue_points():
    assert 'data-calibratable=' in TEMPLATE
    assert "ANALOGUE_INPUT:r=>r.signal.includes('ANALOG')||r.calibratable==='1'" in TEMPLATE
    assert "TANK_LEVEL:r=>r.signal.includes('ANALOG')||r.calibratable==='1'" in TEMPLATE
    assert '<option value="TANK_LEVEL">Tank Level</option>' in TEMPLATE
    assert "ANALOGUE_INPUT:r=>r.signal.includes('ANALOG')||r.direction==='INPUT'" not in TEMPLATE

def test_tank_level_maps_existing_channel_to_level_semantics():
    assert "purpose=='TANK_LEVEL'" in API
    assert "spec.get('direction')=='INPUT' and spec.get('calibratable')" in API
    assert "sig.signal_type='LEVEL'" in API
    assert "sig.unit='%'" in API
    assert "sig.widget='tank'" in API
    assert "sig.raw_min=0.0;sig.raw_max=100.0;sig.eng_min=0.0;sig.eng_max=100.0" in API
    assert "'normalized_firmware_input':True" in API

def test_sim808_output_safety_is_unchanged():
    assert '"channel":"DO1"' in SIM808 and '"pin":"D5"' in SIM808
    assert '"channel":"DO2"' in SIM808 and '"pin":"D6"' in SIM808
    assert SIM808.count('"safe_boot_state":"OFF"') >= 2
    assert SIM808.count('"simulation_physical_lockout":True') >= 2
    assert '"pin":"D9"' in SIM808 and '"customer_output":False' in SIM808
