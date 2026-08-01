from pathlib import Path
for f in ['app.py','requirements.txt','render.yaml','Procfile','.env.example','.gitignore','templates/index.html','templates/dashboard.html','templates/billing.html','docs/DEPLOY_TO_RENDER.md','docs/PAYFAST_SANDBOX.md']:assert Path(f).exists(),f
s=Path('app.py').read_text();
for x in ['/billing/payfast/start','/billing/payfast/notify','DATABASE_URL','pf_signature','postgresql','/api/device/telemetry']:assert x in s,x
print('REV08_STRUCTURE PASS')
