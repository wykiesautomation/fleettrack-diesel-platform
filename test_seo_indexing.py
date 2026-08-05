from pathlib import Path
import py_compile

for filename in ('app/seo.py', 'app/__init__.py'):
    py_compile.compile(filename, doraise=True)

seo = Path('app/seo.py').read_text()
init = Path('app/__init__.py').read_text()

for text in (
    '/robots.txt', '/sitemap.xml', '/site.webmanifest',
    'SoftwareApplication', 'AssetTrack 360', 'Wykies Automation',
    'X-Robots-Tag', 'BING_SITE_VERIFICATION',
    'GOOGLE_SITE_VERIFICATION', 'fleettrack.wykiesautomation.co.za',
):
    assert text in seo, text

assert 'app.register_blueprint(seo_bp)' in init
assert 'register_seo_hooks(app)' in init
print('PUBLIC_SEO_INDEXING_REV03 PASS')
