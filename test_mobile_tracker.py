from pathlib import Path
import py_compile
for f in ['app/routes.py','app/models.py','app/__init__.py']:
    py_compile.compile(f,doraise=True)
r=Path('app/routes.py').read_text()
m=Path('app/models.py').read_text()
js=Path('app/static/mobile_tracker.js').read_text()
html=Path('app/templates/mobile_tracker.html').read_text()
for x in ['/mobile-tracker','/api/v1/mobile/register','/api/v1/mobile/location','/api/v1/mobile/location/batch']:
    assert x in r,x
assert 'MobileTrackerRegistration' in m
for x in ['watchPosition','stopTracking','flushQueue','Authorization']:
    assert x in js,x
for x in ['Start Tracking','Stop Tracking','Register Phone','TRACKER STATUS']:
    assert x in html,x
print('MOBILE_PHONE_TRACKER PASS')
