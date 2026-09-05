from pathlib import Path
import py_compile, sys
from jinja2 import Environment
root=Path(__file__).resolve().parents[1]
py_compile.compile(str(root/'app/routes.py'),doraise=True)
Environment().parse((root/'app/templates/connect_device_waiting.html').read_text())
sys.path.insert(0,str(root))
from app.vendor import segno
uri=segno.make('{"type":"assetops360_registration","code":"ABCD-1234"}',error='m').svg_data_uri(scale=6,border=3)
assert uri.startswith('data:image/svg+xml')
r=(root/'app/routes.py').read_text();t=(root/'app/templates/connect_device_waiting.html').read_text()
for item in ['qr_data_uri=qr.svg_data_uri','remaining_seconds=max(0,int(','from .vendor import segno']:
    assert item in r,item
for item in ['src="{{ qr_data_uri }}"','let remainingSeconds={{ remaining_seconds|int }}','remainingSeconds>0']:
    assert item in t,item
assert 'device_onboarding_qr' not in t
assert "new Date('{{registration.expires_at.isoformat()}}Z')" not in t
print('QR IMAGE AND COUNTDOWN FINAL PASS')
