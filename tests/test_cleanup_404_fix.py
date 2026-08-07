from pathlib import Path
import py_compile
from jinja2 import Environment
root=Path(__file__).resolve().parents[1]
routes=root/'app/routes.py'
template=root/'app/templates/test_data_cleanup.html'
py_compile.compile(str(routes),doraise=True)
Environment().parse(template.read_text())
r=routes.read_text();t=template.read_text()
for item in ["@bp.post('/admin/test-data-cleanup/<int:asset_id>')","def clean_test_asset(asset_id):","action=request.form.get('action','delete_all')"]:
    assert item in r,item
for item in ["url_for('main.clean_test_asset',asset_id=x.asset.id)","fetch(form.action",'Delete Asset Permanently']:
    assert item in t,item
print('CLEANUP BACKEND AND UI MATCH PASS')
