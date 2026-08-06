from pathlib import Path
import py_compile
for f in ['app/routes.py','app/models.py','app/__init__.py','app/device_identity_migration.py']:py_compile.compile(f,doraise=True)
r=Path('app/routes.py').read_text();m=Path('app/models.py').read_text()
for x in ['identity_check','/api/v1/ingest/batch','/api/v1/device/config','/api/v1/device/config/ack','tracking_history','archive_device','archive_asset']:assert x in r,x
for x in ['expected_imei','reported_imei','DeviceConfiguration','DeviceCommand']:assert x in m,x
print('CONSOLIDATED PASS')
