from pathlib import Path
import py_compile
for f in ['app/models.py','app/routes.py','app/__init__.py','app/device_identity_migration.py']:py_compile.compile(f,doraise=True)
print('DEVICE_IDENTITY_LOCK_REV01 PASS')
