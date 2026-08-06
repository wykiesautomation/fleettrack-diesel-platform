from pathlib import Path
import py_compile
py_compile.compile('app/routes.py', doraise=True)
py_compile.compile('app/models.py', doraise=True)
routes=Path('app/routes.py').read_text()
html=Path('app/templates/devices.html').read_text()
for value in ['device_is_archived','/archive','/restore','/permanent-delete','confirm_uid','confirm_word','db.session.delete(record)']:
    assert value in routes, value
for value in ['Archived Devices','Permanently Delete Device','Archive','Restore','confirm_uid','confirm_word']:
    assert value in html, value
assert routes.count("@bp.post('/devices/<int:device_id>/archive')") == 1
assert routes.count("@bp.post('/devices/<int:device_id>/permanent-delete')") == 1
print('DEVICE_LIFECYCLE PASS')
