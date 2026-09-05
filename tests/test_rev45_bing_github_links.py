from pathlib import Path
FILES=[p for p in Path('.').rglob('*') if p.is_file() and '.git' not in p.parts and p.name!='test_rev45_bing_github_links.py' and p.suffix.lower() in {'.py','.md','.html','.yml','.yaml','.ino','.txt'}]
TEXT='\n'.join(p.read_text(encoding='utf-8',errors='ignore') for p in FILES)
APP=Path('app/routes.py').read_text(encoding='utf-8')
INIT=Path('app/__init__.py').read_text(encoding='utf-8')
README=Path('README.md').read_text(encoding='utf-8')

def test_no_obsolete_public_origin_remains():
    assert 'https://fleettrack.wykiesautomation.co.za' not in TEXT

def test_canonical_origin_used_by_robots_and_sitemap():
    assert 'Sitemap: https://assettrack360.wykiesautomation.co.za/sitemap.xml' in APP
    assert 'base_url="https://assettrack360.wykiesautomation.co.za"' in APP

def test_verification_endpoints_are_present():
    assert '@app.get("/BingSiteAuth.xml")' in INIT
    assert '@bp.get("/googleea2fb5a297eb0738.html")' in APP

def test_readme_has_official_links():
    assert 'https://github.com/wykiesautomation/fleettrack-diesel-platform' in README
    assert 'https://assettrack360.wykiesautomation.co.za' in README
