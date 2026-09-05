import hashlib,json,logging,time
from logging.handlers import RotatingFileHandler
import requests
from .config import BASE,ensure,load,secrets
from .queue_store import put,rows,ok,fail,depth
from .opc_client import ReadOnlyOpcClient
ensure();log=logging.getLogger('AT360Edge');log.setLevel(logging.INFO)
if not log.handlers:
 h=RotatingFileHandler(BASE/'logs'/'edge.log',maxBytes=5_000_000,backupCount=5,encoding='utf-8');h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'));log.addHandler(h)
class Agent:
 def __init__(self):
  self.cfg=load();self.sec=secrets();self.base=self.cfg['cloud_url'].rstrip('/');self.headers={'Authorization':'Bearer '+self.sec.get('gateway_token',''),'User-Agent':'AssetTrack360Edge/1.0.0'};self.session=requests.Session();self.connectors=[];self.last_config=0;self.last_heartbeat=0;self.last_poll={}
 def get(self,path):r=self.session.get(self.base+path,headers=self.headers,timeout=self.cfg.get('cloud_timeout_seconds',30));r.raise_for_status();return r.json()
 def post(self,path,payload):r=self.session.post(self.base+path,json=payload,headers=self.headers,timeout=self.cfg.get('cloud_timeout_seconds',30));r.raise_for_status();return r
 def heartbeat(self):
  self.post('/api/v1/gateways/heartbeat',{'version':'1.0.0','capabilities':['OPC_UA_READ_ONLY','BROWSE','READ_TEST','SQLITE_WAL_QUEUE'],'queue_depth':depth(),'gateway_id':self.cfg.get('gateway_uid')});self.last_heartbeat=time.time()
 def refresh(self):self.connectors=self.get('/api/v1/gateways/runtime-config').get('connectors',[]);self.last_config=time.time()
 def work(self):
  data=self.get('/api/v1/gateways/opc-ua/work');job=data.get('request')
  if not job:return
  connector=next((x for x in self.connectors if x['connector_id']==data.get('connector_id')),None)
  if not connector:return
  try:
   with ReadOnlyOpcClient(connector,self.sec) as opc:result=opc.browse(job) if job.get('action')=='BROWSE' else opc.read(job)
   self.post('/api/v1/gateways/opc-ua/work-result',{'connector_id':connector['connector_id'],'request_id':job['request_id'],'success':True,'result':result})
  except Exception as exc:self.post('/api/v1/gateways/opc-ua/work-result',{'connector_id':connector['connector_id'],'request_id':job['request_id'],'success':False,'error':f'{type(exc).__name__}: {exc}'})
 def poll(self):
  now=time.time()
  for connector in self.connectors:
   if not connector.get('enabled') or not connector.get('mappings'):continue
   if now-self.last_poll.get(connector['connector_id'],0)<connector.get('poll_interval_seconds',60):continue
   try:
    with ReadOnlyOpcClient(connector,self.sec) as opc:points=opc.live()
    payload={'connector_id':connector['connector_id'],'gateway_uid':self.cfg.get('gateway_uid'),'batch_id':f"{connector['connector_id']}-{time.time_ns()}",'points':points,'read_only':True,'queue_depth':depth()};key=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest();put(payload,key);self.last_poll[connector['connector_id']]=now
   except Exception as exc:log.warning('OPC poll failed connector=%s error=%s',connector['connector_id'],exc)
 def upload(self):
  for row_id,payload,attempts in rows(self.cfg.get('upload_batch_size',25)):
   try:self.post('/api/v1/gateways/opc-ua/live-batch',json.loads(payload));ok(row_id)
   except Exception as exc:fail(row_id,exc);break
 def run(self):
  log.info('Agent started gateway=%s READ_ONLY',self.cfg.get('gateway_uid'))
  while True:
   try:
    now=time.time()
    if now-self.last_config>=self.cfg.get('config_refresh_seconds',30):self.refresh()
    if now-self.last_heartbeat>=30:self.heartbeat()
    self.work();self.poll();self.upload()
   except Exception as exc:log.exception('Agent cycle failed safely: %s',exc)
   time.sleep(max(1,self.cfg.get('poll_seconds',5)))
