from pathlib import Path
A=Path("app/templates/asset.html").read_text(encoding="utf-8")
B=Path("app/templates/base.html").read_text(encoding="utf-8")
R=Path("app/routes.py").read_text(encoding="utf-8")

def tracker_block():
    return A[A.index("{% elif asset.asset_type=='TRACKER' %}"):A.index("{% elif asset.asset_type=='VIBRATION' %}")]

def test_summary_truth_and_configuration_labels():
    b=tracker_block()
    for text in ["DEVICE OFFLINE","LAST REPORTED BATTERY","LAST VALIDATED SPEED","LAST GPS ACCURACY","LAST KNOWN POSITION","SETUP REQUIRED"]:
        assert text in b
    assert "No live telemetry is available" in b

def test_no_duplicate_tracker_cockpits_or_actions():
    b=tracker_block()
    assert b.count("Open Safety Twin")==0  # actions live in the single top action row
    assert "Last Known Location & Route" not in b
    assert "Raw GPS" not in b
    assert "PHONE BATTERY" not in b
    assert "CHARGING STATUS" not in b
    assert "Historical Battery Trend" not in b

def test_one_top_action_set_includes_safety_settings():
    assert "Open Safety Twin" in A
    assert "Tracking History" in A
    assert "Evidence Centre" in A
    assert "Safety Settings" in A
    assert "Tracking Settings" in A

def test_compact_device_health_and_platform_wording():
    assert "compact-health-grid" in A
    assert "Identity and connection context" in A
    assert "Platform Online" in B and "Cloud Connected" not in B

def test_evidence_audit_and_tracking_contract_remain_fixed():
    assert "'USER',current_user.id" in R
    assert "'ASSET',payload['report_id']" not in R
    assert "'points': accepted" in R and "'last':" in R
