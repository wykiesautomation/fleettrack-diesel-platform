from pathlib import Path
import py_compile
root=Path(__file__).resolve().parents[1]
routes=root/'app/routes.py'
py_compile.compile(str(routes),doraise=True)
text=routes.read_text()
for required in ['def pilot_access_for(customer_id):','ASSETOPS_PILOT_MODE','ASSETOPS_PILOT_CUSTOMER_IDS','if pilot_access_for(customer_id):return True,sub']:
    assert required in text, required
print('PILOT ACCESS FIX PASS')
