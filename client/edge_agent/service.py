import json,logging,random,time,traceback
from logging.handlers import RotatingFileHandler
from .config import BASE,ensure,load,load_secrets
from .queue_store import put,batch,ok,fail,depth,prune
from .connectors.modbus import read as modbus_read
from .connectors.opcua import read as opc_read
from .connectors.sqlcsv import sql,csv_read,changed
from .http_transport import build,health
ensure();log=logging.getLogger('AssetTrackEdge');log.setLevel(logging.INFO)
if not log.handlers:
 h=RotatingFileHandler(BASE/'logs'/'gateway.log',maxBytes=5_000_000,backupCount=5);h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'));log.addHandler(h)
HEARTBEAT_PATH='/api/v1/gateways/heartbeat';INGEST_PATH='/api/v1/gateways/ingest'
def collect(c,secrets):
 if c['type'] in ('MODBUS_TCP','MODBUS_RTU'):return modbus_read(c),str(time.time_ns())
 if c['type']=='OPC_UA':return opc_read(c,secrets),str(time.time_ns())
 if c['type']=='SQL_ODBC':return sql(c,secrets)
 if c['type']=='CSV':return csv_read(c)
 raise ValueError('Unsupported connector '+c['type'])
def upload(cfg,secrets,session):
 token=secrets.get('edge_api_token','').strip();url=cfg['cloud_url'].rstrip('/')+INGEST_PATH;accepted=0
 for i,p,a in batch(cfg.get('upload_batch_size',100)):
  try:r=session.post(url,json=json.loads(p),headers={'Authorization':'Bearer '+token},timeout=cfg.get('cloud_timeout_seconds',90));r.raise_for_status();ok(i);accepted+=1
  except Exception as e:fail(i,e);log.warning('Upload failed attempt=%s queue=%s error=%s',a+1,depth(),e);break
 if accepted:log.info('Upload accepted batches=%s queue=%s endpoint=REV20A2',accepted,depth())
def heartbeat(cfg,secrets,session):
 try:
  r=session.post(cfg['cloud_url'].rstrip('/')+HEARTBEAT_PATH,json={'version':'1.0.3','capabilities':['OPC_UA','MODBUS_TCP','MODBUS_RTU','SQL_ODBC','CSV'],'queue_depth':depth(),'gateway_id':cfg.get('gateway_id')},headers={'Authorization':'Bearer '+secrets.get('edge_api_token','').strip()},timeout=cfg.get('cloud_timeout_seconds',90));r.raise_for_status();data=r.json();log.info('Heartbeat accepted gateway=%s api=%s queue=%s',data.get('gateway_id'),data.get('api_revision'),depth());return True
 except Exception as e:log.warning('Heartbeat failed queue=%s error=%s',depth(),e);return False
def cycle(session=None):
 cfg=load();secrets=load_secrets();session=session or build(cfg);prune(cfg.get('queue_max_rows',10000))
 collected=0
 for c in cfg.get('connectors',[]):
  if not c.get('enabled',True):continue
  try:
   points,cursor=collect(c,secrets)
   if c['type'] in ('CSV','SQL_ODBC') and not changed(c['connector_key'],cursor):log.info('%s unchanged; skipped duplicate row',c.get('name'));continue
   payload={'connector_key':c['connector_key'],'timestamp':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'points':points};inserted=put(payload,dedup_key=f"{c['connector_key']}:{cursor}")
   if inserted:log.info('%s collected %s points queue=%s',c.get('name'),len(points),depth());collected+=len(points)
  except Exception as e:log.error('%s collection failed: %s',c.get('name'),e)
 upload(cfg,secrets,session);return heartbeat(cfg,secrets,session),collected
def run():
 cfg=load();log.info('AssetTrack Edge Gateway REV20C starting');session=build(cfg);failures=0
 while True:
  try:
   online,_=cycle(session);failures=0 if online else failures+1
  except Exception:failures+=1;log.error(traceback.format_exc())
  base=max(load().get('scan_seconds',30),5);delay=min(base*(2**min(failures,5)),load().get('max_backoff_seconds',600));delay+=random.uniform(0,min(5,delay*.1));time.sleep(delay)
if __name__=='__main__':run()
