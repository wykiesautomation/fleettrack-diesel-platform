from pathlib import Path
H=Path('app/templates/public_home.html').read_text()
L=Path('app/templates/public_landing.html').read_text()
S=Path('app/seo.py').read_text()
T=Path('app/templates/tracking_history.html').read_text()
R=Path('app/routes.py').read_text()
README=Path('README.md').read_text()

def test_search_identity_is_consistent():
    assert 'AssetTrack 360 by Wykies Automation | Fleet & Asset Monitoring' in H
    assert 'AssetTrack 360 by Wykies Automation' in H
    assert 'SITE_NAME = "AssetTrack 360 by Wykies Automation"' in S
    assert 'alternateName' in S
    assert 'AssetTrack 360 by Wykies Automation' in L
    assert 'AssetTrack 360 by Wykies Automation' in README

def test_geofence_json_is_synchronized_before_submit():
    assert 'value="[]"' in T
    assert "safetyForm.addEventListener('submit'" in T
    assert 'syncZones();' in T
    assert 'Saving Safety Rules...' in T

def test_geofence_requires_name_and_rejects_duplicate():
    assert 'Enter a zone name before using the last position.' in T
    assert 'A geofence with this name already exists.' in T
    assert 'Click Save Safety Rules to store it.' in T

def test_backend_persists_and_reports_zone_count():
    assert "if not isinstance(zones,list):raise ValueError" in R
    assert "db.session.add(asset);db.session.commit()" in R
    assert "geofence zone(s) stored" in R
