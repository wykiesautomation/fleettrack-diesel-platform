from pathlib import Path
A=Path("app/templates/asset.html").read_text(encoding="utf-8")
B=Path("app/templates/base.html").read_text(encoding="utf-8")
C=Path("app/static/rev28_full.css").read_text(encoding="utf-8")

def test_tracker_dashboard_is_summary_not_duplicate_cockpit():
    block=A[A.index("{% elif asset.asset_type=='TRACKER' %}"):A.index("{% elif asset.asset_type=='VIBRATION' %}")]
    assert "Tracker Summary" in block
    assert "DEVICE OFFLINE" in block
    assert "LAST REPORTED BATTERY" in block
    assert "LAST VALIDATED SPEED" in block
    assert "LAST GPS ACCURACY" in block
    assert "Open Safety Twin" in block
    assert "Last Known Location & Route" not in block
    assert "Raw GPS" not in block

def test_platform_and_device_status_are_not_confused():
    assert "Platform Online" in B
    assert "Cloud Connected" not in B
    assert "Device status shown per asset" in B

def test_summary_action_links_are_readable_when_visited():
    assert ".tracker-summary-actions a:visited" in C
    assert "#f4fbff" in C
