from pathlib import Path
R=Path("app/routes.py").read_text(encoding="utf-8"); T=Path("app/templates/safety_twin.html").read_text(encoding="utf-8"); H=Path("app/templates/tracking_history.html").read_text(encoding="utf-8"); A=Path("app/templates/asset.html").read_text(encoding="utf-8"); E=Path("app/templates/evidence_centre.html").read_text(encoding="utf-8")
def test_safety_twin_is_live_entry():
    block=R[R.index("def fleet_tracking"):R.index("def tracking_history")]
    assert "main.safety_twin" in block and "main.tracking_history" not in block
def test_history_uses_shared_strict_engine():
    block=R[R.index("def analyse_tracking_points"):R.index("def tracking_hmi_context")]
    assert "analyse_safety_twin_points(rows)" in block
    assert "STATIONARY_DRIFT" in block
def test_next_removed_and_roles_clear():
    assert "NEXT</button>" not in T
    assert "TRACKING HISTORY" in T
    assert "Tracking History & Route Quality" in H
    assert "Historical view, not live" in H
    assert "VALIDATED DISTANCE" in H and "MOVEMENT TIME" in H
def test_asset_summary_actions_and_evidence_role():
    assert "Open Safety Twin" in A
    assert "Tracking History" in A
    assert "Evidence Centre" in A
    assert "Generate Customer Evidence" in E
