from pathlib import Path
import py_compile
from jinja2 import Environment
root=Path(__file__).resolve().parents[1]
py_compile.compile(str(root/'app/routes.py'),doraise=True)
py_compile.compile(str(root/'app/seo.py'),doraise=True)
for path in (root/'app/templates').glob('*.html'):
    Environment().parse(path.read_text())
r=(root/'app/routes.py').read_text();s=(root/'app/seo.py').read_text();h=(root/'app/templates/public_home.html').read_text();b=(root/'app/templates/base.html').read_text()
for value in ['/fleet-tracking-south-africa','/mobile-phone-tracking','/vehicle-gps-tracking','/asset-monitoring','/industrial-sensor-monitoring','/fleet-tracking-api','/security-privacy']:
    assert value in r and value in s,value
assert 'SEO_PAGES.values()' in r
assert 'noindex,nofollow,noarchive' in b
assert 'canonical' in h and 'SoftwareApplication' in h
assert 'Disallow: /api/' in r and 'Disallow: /admin/' in r
print('SEO FOUNDATION PASS')
