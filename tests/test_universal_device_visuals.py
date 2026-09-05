from pathlib import Path
A=Path("app/templates/asset.html").read_text(encoding="utf-8")
C=Path("app/static/rev28_full.css").read_text(encoding="utf-8")
F=Path("firmware/AT360_ESP32_WROOM32_FINAL.ino").read_text(encoding="utf-8")

def test_analog_percentage_and_progress_bar_are_universal():
    assert "INPUT LEVEL" in A
    assert "role=\"progressbar\"" in A
    assert "signal-level-bar" in A and "signal-level-bar" in C
    assert "aria-valuenow" in A

def test_digital_pulse_and_quality_visuals():
    assert "state-indicator" in A
    assert "TOTAL COUNTER" in A
    assert "SIMULATED" in A
    assert ".pill.simulated" in C

def test_wroom_master_firmware_and_simulation_quality():
    assert '1.6.5-wroom32-simulation-quality' in F
    assert 'AT360_ESP32_WROOM32' in F
    assert 'String quality=simulation?"SIMULATED":"GOOD"' in F
    assert 'AIN=34,DIN=27,PULSE=26,OUT=25,ARM=32,LED=33' in F
    assert 'if(simulation){simOutput=1;setOutput(false)' in F
