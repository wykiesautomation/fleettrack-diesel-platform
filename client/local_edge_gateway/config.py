import json,os
from pathlib import Path
BASE=Path(os.getenv('AT360_EDGE_HOME',Path.home()/'.assettrack360-edge'))
CONFIG=BASE/'gateway.json';SECRETS=BASE/'secrets.json'
def ensure():
 for p in (BASE,BASE/'logs',BASE/'data'):p.mkdir(parents=True,exist_ok=True)
def load_json(path,default):
 ensure()
 try:return json.loads(path.read_text(encoding='utf-8'))
 except (FileNotFoundError,ValueError,TypeError):return default
def save_json(path,value):
 ensure();tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2),encoding='utf-8');tmp.replace(path)
def load():return load_json(CONFIG,{'cloud_url':'https://assettrack360.wykiesautomation.co.za','gateway_uid':'','poll_seconds':5,'config_refresh_seconds':30,'upload_batch_size':25,'cloud_timeout_seconds':30})
def secrets():return load_json(SECRETS,{'gateway_token':'','local_secrets':{}})
def bootstrap(cloud_url,gateway_uid,token):
 save_json(CONFIG,{**load(),'cloud_url':cloud_url.rstrip('/'),'gateway_uid':gateway_uid});save_json(SECRETS,{'gateway_token':token,'local_secrets':{}})
