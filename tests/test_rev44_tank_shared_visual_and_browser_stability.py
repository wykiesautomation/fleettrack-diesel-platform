from pathlib import Path
A=Path('app/templates/asset.html').read_text()
C=Path('app/templates/tank_calibration.html').read_text()
P=Path('app/templates/_tank_visual.html').read_text()
J=Path('app/static/mobile_tracker.js').read_text()
M=Path('app/templates/mobile_tracker.html').read_text()

def test_same_master_tank_visual_used_both_places():
    assert "include '_tank_visual.html'" in A
    assert "include '_tank_visual.html'" in C
    for shape in ['HORIZONTAL_CYLINDER','SPHERICAL','CONICAL_HOPPER','RECTANGULAR','IRREGULAR']:
        assert shape in P

def test_browser_tracker_pause_resume_and_wake_lock():
    for text in ['PAUSED BY BROWSER','OFFLINE QUEUE','requestWakeLock','resumeTracking','scheduleWatchRestart','watchdog','navigator.wakeLock']:
        assert text in J
    assert 'Browser tracking limitation' in M

def test_browser_tracker_recovery_and_queue_hardening():
    assert 'MAX_QUEUE=5000' in J
    assert 'maximumAge:30000,timeout:45000' in J
    assert 'retryDelay=Math.min(60000,retryDelay*2)' in J
    assert "window.addEventListener('focus'" in J

def test_no_malformed_tank_expression():
    assert 't() if false' not in A
