from pathlib import Path
T=Path('app/templates/tracking_history.html').read_text(encoding='utf-8')
C=Path('app/static/rev28_tracking.css').read_text(encoding='utf-8')

def test_position_map_exists_without_leaflet():
    assert 'trackingMapFallback' in T
    assert 'openstreetmap.org/export/embed.html' in T
    assert '&amp;marker={{last_known.latitude}},{{last_known.longitude}}' in T

def test_leaflet_only_replaces_fallback_after_ready():
    assert "typeof window.L==='undefined'" in T
    assert "m.whenReady" in T
    assert "shell.classList.add('leaflet-ready')" in T
    assert '.track-map-shell.leaflet-ready .track-map-fallback{visibility:hidden}' in C

def test_route_and_marker_are_rendered():
    assert 'L.polyline(line' in T
    assert 'L.marker([last.latitude,last.longitude])' in T
    assert 'm.fitBounds(line' in T

def test_cache_busted():
    assert "v='33'" in T
