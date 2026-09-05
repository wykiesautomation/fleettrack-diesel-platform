from pathlib import Path
R=Path('app/routes.py').read_text();T=Path('app/templates/tracking_history.html').read_text()
def test_has_four_contexts():
    for x in ["'TANK'","'MOBILE_TANK'","'VEHICLE'","'ASSET'"]: assert x in R
def test_tank_not_vehicle_wording():
    assert 'Tank Location & Movement' in R and 'Tank Location Status' in R
    assert '{{hmi.labels.status_title}}' in T and '{{hmi.labels.overview_title}}' in T
def test_features_are_capability_aware():
    assert "'harsh_driving':has_motion and context=='VEHICLE'" in R
    assert "'driving_score':has_motion and context=='VEHICLE'" in R
    assert '{% if hmi.features.driving_score' in T
    assert '{% if hmi.features.impact %}' in T and '{% if hmi.features.tilt %}' in T
def test_gps_provenance_and_address():
    assert 'GPS source:' in T and 'hmi.gps_source_uid' in T
    assert 'Possible address' in T and 'possible_address=possible_address' in R
def test_zero_zero_not_used_as_last_known():
    assert 'abs(float(last_known.latitude))<.000001' in R
def test_unexpected_movement_for_gps_assets():
    assert "'unexpected_movement':has_gps" in R
    assert '{% if hmi.features.unexpected_movement %}' in T
