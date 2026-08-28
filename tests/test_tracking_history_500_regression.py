from pathlib import Path
R=Path("app/routes.py").read_text(encoding="utf-8")
T=Path("app/templates/tracking_history.html").read_text(encoding="utf-8")
S=Path("app/templates/safety_twin.html").read_text(encoding="utf-8")

def test_history_adapter_supplies_template_contract():
    block=R[R.index("def analyse_tracking_points"):R.index("def tracking_hmi_context")]
    required={"points","accepted","rejected","segments","journeys","stops","total_km","distance_km","max_speed","moving_minutes","stopped_minutes","rejection_counts"}
    for key in required:
        assert repr(key) in block
    assert "analysis['points']" in R
    assert "analysis.points" in T

def test_live_navigation_and_customer_title_remain_correct():
    fleet=R[R.index("def fleet_tracking"):R.index("def tracking_history")]
    assert "main.safety_twin" in fleet
    assert "Temporal Safety Twin" not in S
    assert "{{asset.name}} Safety Twin" in S
    assert "NEXT</button>" not in S
