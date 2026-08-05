from pathlib import Path
import py_compile
files=['app/models.py','app/routes.py','app/__init__.py','app/device_identity_migration.py']
for f in files:py_compile.compile(f,doraise=True)
r=Path('app/routes.py').read_text();m=Path('app/models.py').read_text()
for x in ["/api/v1/ingest/batch","/api/v1/device/config","/api/v1/device/config/ack","/tracking","store_device_sample","sequence_required","max_samples=100"]:assert x in r,x
for x in ['class DeviceConfiguration','class DeviceCommand','tank_capacity_l','applied_revision']:assert x in m,x
assert Path('app/templates/device_configuration.html').exists()
assert Path('docs/FIRMWARE_API_CONTRACT_REV02.md').exists()
print('FIRMWARE_READY_API_REV02 PASS')
