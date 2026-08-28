from pathlib import Path
R=Path("app/routes.py").read_text();B=Path("app/templates/base.html").read_text();A=Path("app/templates/asset.html").read_text();H=Path("app/templates/tracking_history.html").read_text();T=Path("app/templates/safety_twin.html").read_text()
def test_sidebar_fleet_tracking_resolves_to_safety_twin():
 block=R[R.index("def fleet_tracking"):R.index("def tracking_history")];assert "main.safety_twin" in block;assert "main.tracking_history" not in block;assert "main.fleet_tracking" in B
def test_tracking_page_is_history_and_has_navigation():
 assert "Tracking History & Route Quality" in H;assert "Historical view, not live" in H;assert "/safety-twin" in H and "/evidence" in H
def test_tracker_asset_actions_open_new_workflow():
 assert "Open Safety Twin" in A;assert "Tracking History" in A;assert "Evidence Centre" in A
def test_safety_twin_history_label_is_explicit(): assert "TRACKING HISTORY" in T
