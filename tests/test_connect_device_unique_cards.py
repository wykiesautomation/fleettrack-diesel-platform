from pathlib import Path
T=Path("app/templates/connect_device.html").read_text(encoding="utf-8")
R=Path("app/device_profiles/registry.py").read_text(encoding="utf-8")

def test_connection_copy_and_unique_profile_guard():
    assert "Choose a supported mobile tracker or physical board" in T
    assert "Only four physical connection choices" not in T
    assert "seen_profiles" in T
    assert "repeat(5,minmax(0,1fr))" in T

def test_all_expected_cards_have_explicit_rendering():
    for text in ["Android Phone","ESP32-D 38-pin","ESP32-WROOM-32","SIM808 SAMD21","LILYGO T-SIM7000G"]: assert text in T
    assert "is_sim808" in T and "is_tsim" in T
    assert "AT360_LILYGO_T_SIM7000G" in R

def test_tsim_badges_and_no_generic_sim808_fallback():
    for text in ["LTE / NB-IoT","Battery / Solar","Optional microSD"]: assert text in T
    assert "else 'SIM808 SAMD21'}}</b>" not in T
