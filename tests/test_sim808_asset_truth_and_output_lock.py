from pathlib import Path
R=Path('app/routes.py').read_text(encoding='utf-8');T=Path('app/templates/asset.html').read_text(encoding='utf-8')
def test_shared_connectivity_engine():
    for x in ["connectivity_state='ONLINE'","connectivity_state='DELAYED'","connectivity_state='STALE'","connectivity_state='OFFLINE'","asset_connectivity=asset_connectivity"]:assert x in R
def test_summary_uses_shared_truth_and_actual_age():
    assert 'asset_connectivity.state' in T and 'asset_connectivity.detail' in T
    assert "vehicle_summary.last_contact if" not in T
def test_battery_wording_not_stale_just_now_contradiction():
    assert 'STALE · Just now' not in T
    assert 'Reported {{operational_battery.updated}}' in T
def test_sim808_accuracy_is_labelled_estimated():
    assert 'ESTIMATED GPS ACCURACY' in T and 'sim808_profile' in R
def test_outputs_locked_until_online_and_feedback_fresh():
    assert 'not asset_connectivity.online or not output_feedback_verified' in T
    assert 'OUTPUT CONTROL LOCKED' in T
    assert 'Commands require ONLINE status and fresh firmware feedback' in T
