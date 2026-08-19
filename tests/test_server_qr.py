from pathlib import Path
import py_compile
from jinja2 import Environment
root=Path(__file__).resolve().parents[1]
routes=root/'app/routes.py'; template=root/'app/templates/connect_device_waiting.html'; req=root/'requirements.txt'
py_compile.compile(str(routes),doraise=True)
Environment().parse(template.read_text())
r=routes.read_text(); t=template.read_text(); q=req.read_text()
for item in ["@bp.get('/devices/connect/qr/<int:registration_id>.png')",'def device_onboarding_qr(registration_id):',"'type':'assetops360_registration'","send_file(output,mimetype='image/png'", "response.headers['Cache-Control']='no-store, no-cache, must-revalidate, max-age=0'"]:
    assert item in r,item
assert "url_for('main.device_onboarding_qr', registration_id=registration.id)" in t
assert 'qrcodejs' not in t.lower()
assert 'new QRCode' not in t
assert 'qrcode[pil]==8.2' in q
print('SERVER GENERATED QR FIX PASS')
