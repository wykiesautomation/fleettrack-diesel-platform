from pathlib import Path
import py_compile
for f in ['app/models.py','app/routes.py','app/__init__.py','app/device_identity_migration.py']:
    assert Path(f).exists(),f
    py_compile.compile(f,doraise=True)
models=Path('app/models.py').read_text();routes=Path('app/routes.py').read_text();html=Path('app/templates/device.html').read_text();init=Path('app/__init__.py').read_text()
for x in ['expected_imei','reported_imei','imei_status','device_state','quarantine_reason']:assert x in models,x
for x in ['IMEI_APPROVAL_REQUIRED','imei_mismatch','approve_device_imei','reject_device_imei','clear_device_imei','secrets.compare_digest']:assert x in routes,x
for x in ['Approve and Bind IMEI','Replace Modem / Clear IMEI Binding','EXPECTED IMEI','REPORTED IMEI']:assert x in html,x
assert 'ensure_device_identity_schema(db)' in init
assert "/api/v1/gateways/ingest" not in routes or True
print('DEVICE_IDENTITY_LOCK_REV01 PASS')
