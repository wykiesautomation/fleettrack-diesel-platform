from pathlib import Path
R=Path("app/routes.py").read_text(encoding="utf-8")
T=Path("app/templates/tracking_history.html").read_text(encoding="utf-8")

def block(): return R[R.index("def analyse_safety_twin_points"):R.index("@bp.get('/asset/<int:asset_id>/safety-twin')")]

def test_mobile_api_accuracy_and_route_quality_are_separate():
    b=block()
    assert "if acc>150" in b
    assert "if acc>50" in b
    assert "LOW_CONFIDENCE_GPS" in b
    assert "GPS_QUALITY_INSUFFICIENT" in b

def test_movement_still_requires_sustained_evidence():
    b=block()
    assert "len(candidate)>=3" in b
    assert "elapsed>=20" in b
    assert "envelope" in b

def test_tracking_ui_never_calls_raw_speed_validated():
    assert "VALIDATED SPEED" in T
    assert "Raw {{analysis.raw_speed" in T
    assert "GPS Validation Summary" in T
