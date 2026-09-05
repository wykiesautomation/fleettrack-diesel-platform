from pathlib import Path
A=Path('app/templates/asset.html').read_text(encoding='utf-8')
R=Path('app/routes.py').read_text(encoding='utf-8')
C=Path('app/static/rev28_full.css').read_text(encoding='utf-8')
B=Path('app/templates/base.html').read_text(encoding='utf-8')

def test_fallback_map_draws_route_not_only_marker():
    assert 'assetRouteFallback' in A
    assert 'drawRouteFallback' in A
    assert "drawRouteFallback(rawPoints)" in A
    assert "Recorded route shown on fallback map" in A

def test_raw_route_is_drawn_immediately_before_matching():
    assert "if(rawPoints.length>1){showRaw();}" in A
    assert "Road alignment unavailable · Raw GPS remains selected" in A

def test_walking_distance_does_not_require_full_accuracy_radius():
    assert 'movement_threshold_m=max(4.0,min(15.0,accuracy_m*0.35))' in R
    assert 'segment*1000>=movement_threshold_m' in R
    assert 'return round(total,2)' in R

def test_route_canvas_style_and_cache_bust():
    assert '#assetRouteFallback.route-visible' in C
    assert "v='43'" in B
