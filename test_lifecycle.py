from pathlib import Path
import py_compile
for f in ('app/routes.py','app/models.py','app/__init__.py'): py_compile.compile(f,doraise=True)
r=Path('app/routes.py').read_text();a=Path('app/templates/asset.html').read_text();d=Path('app/templates/dashboard.html').read_text();x=Path('app/templates/archived_assets.html').read_text()
for value in ['asset_is_archived','/assets/<int:asset_id>/archive','/assets/archived','/assets/<int:asset_id>/restore','/assets/<int:asset_id>/permanent-delete','integration or MQTT mappings']:
 assert value in r,value
for value in ['Archive Asset','Restore Asset']: assert value in a,value
assert 'Archived ({{archived_asset_count}})' in d
for value in ['Archived Assets','Permanently Delete Asset','confirm_name','confirm_word']: assert value in x,value
print('ASSET_DEVICE_LIFECYCLE PASS')
