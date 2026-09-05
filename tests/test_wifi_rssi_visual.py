from pathlib import Path
A=Path("app/templates/asset.html").read_text(encoding="utf-8")
C=Path("app/static/rev28_full.css").read_text(encoding="utf-8")
P1=Path("app/device_profiles/modules/esp32_wroom32.py").read_text(encoding="utf-8")
P2=Path("app/device_profiles/modules/esp32d_38pin.py").read_text(encoding="utf-8")

def test_wifi_profiles_expose_same_signal_key():
    assert '"key": "wifi_rssi"' in P1
    assert '"key": "wifi_rssi"' in P2

def test_rssi_card_has_percentage_bar_and_separate_quality():
    assert "is_wifi=c.signal.key=='wifi_rssi'" in A
    assert "(rssi+100)*2" in A
    assert "SIGNAL STRENGTH" in A
    assert "Telemetry quality:" in A
    assert "role=\"progressbar\"" in A

def test_minus_72_is_fair_not_good():
    assert "rssi>=-67 else 'FAIR' if rssi>=-75" in A
    assert ".wifi-strength-bar.fair" in C
    assert "#ffb84c" in C
