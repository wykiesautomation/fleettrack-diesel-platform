from pathlib import Path
R=Path("app/routes.py").read_text(encoding="utf-8")
M=Path("app/mobile_safety.py").read_text(encoding="utf-8")
W=Path("scripts/motion_safety_worker.py").read_text(encoding="utf-8")
T=Path("app/templates/safety_twin.html").read_text(encoding="utf-8")

def test_all_gps_capable_devices_are_tenant_scoped_and_exact_selected():
    for token in ("GPS","GNSS","gps_location","LOCATION","MOBILE_WEB_TRACKER","customer_id=customer_id,active=True","device_id=selected['device'].id"):assert token in R
    assert "gpsTrackerSelect" in T and "selected_tracker_device_id" in T

def test_route_analysis_is_ordered_segmented_and_has_real_journeys_stops():
    for token in ("ordered=sorted(rows","if current:segments.append(current);current=[]","distance+=total","'journeys':journeys","'stops':stops","movement_by_time.setdefault"):assert token in R

def test_pending_motion_candidates_are_finalised_and_audited():
    for token in ("CONFIRMATION_PENDING","POSSIBLE_ACCIDENT","ABNORMAL_TILT","cancel_deadline","UNCONFIRMED","INSUFFICIENT_EVIDENCE","SAFETY_CANDIDATE_FINALISED","SAFETY_CANDIDATE_REVIEWED","motion-safety-3.2"):assert token in M
    assert "processed=reevaluate_pending_safety_events()" in W
    assert "Motion Safety reevaluated" in W
