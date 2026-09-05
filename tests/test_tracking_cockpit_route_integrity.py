from pathlib import Path
R=Path('app/routes.py').read_text();T=Path('app/templates/tracking_history.html').read_text();C=Path('app/static/rev28_tracking.css').read_text()
def test_route_analysis_returns_segments_and_metrics():
    for x in ["'segments':route_segments","'moving_minutes'","'stopped_minutes'","'rejection_counts'"]:assert x in R
def test_rejected_point_breaks_route_continuity():
    assert 'if current:segments.append(current);current=[]' in R
    assert 'previous=None' in R
def test_distance_is_only_valid_segments():
    assert 'distance+=total' in R
    assert 'Valid segments only' in T
def test_map_draws_segments_not_one_flight_line():
    assert 'segments={{analysis.segments|tojson}}' in T
    assert 'lines.forEach' in T
    assert 'L.polyline(segment' in T
def test_cockpit_has_required_kpis():
    for x in ['DISTANCE TRAVELLED','MOVEMENT TIME','STOPPED TIME','Route Quality']:assert x in T
def test_polished_cockpit_css():
    for x in ['.cockpit-kpis','.map-hero','.route-legend','.quality-list']:assert x in C
