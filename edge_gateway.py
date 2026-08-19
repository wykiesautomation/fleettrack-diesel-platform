import csv,json,os,time,sqlite3
from pathlib import Path
import requests
try: from pymodbus.client import ModbusTcpClient
except Exception: ModbusTcpClient=None
try: from opcua import Client as OpcUaClient
except Exception: OpcUaClient=None
try: import pyodbc
except Exception: pyodbc=None

BASE=os.environ.get('ASSETTRACK_BASE_URL','').rstrip('/')
TOKEN=os.environ.get('EDGE_API_TOKEN','')
CONFIG=Path(os.environ.get('EDGE_CONFIG','edge_config.json'))
QUEUE_DB=Path(os.environ.get('EDGE_QUEUE_DB','edge_queue.db'))
VERSION='at360-edge-1.0'

def headers():return {'Authorization':'Bearer '+TOKEN}
def post(path,payload,timeout=30):
 r=requests.post(BASE+path,json=payload,headers=headers(),timeout=timeout);r.raise_for_status();return r.json() if r.content else {}
def init_queue():
 with sqlite3.connect(QUEUE_DB) as cn:cn.execute('CREATE TABLE IF NOT EXISTS queue(id INTEGER PRIMARY KEY,payload TEXT NOT NULL,created REAL NOT NULL)')
def enqueue(payload):
 with sqlite3.connect(QUEUE_DB) as cn:cn.execute('INSERT INTO queue(payload,created) VALUES(?,?)',(json.dumps(payload),time.time()))
def queue_depth():
 with sqlite3.connect(QUEUE_DB) as cn:return cn.execute('SELECT COUNT(*) FROM queue').fetchone()[0]
def flush_queue(limit=100):
 with sqlite3.connect(QUEUE_DB) as cn:
  for row_id,payload in cn.execute('SELECT id,payload FROM queue ORDER BY id LIMIT ?',(limit,)).fetchall():
   post('/api/v1/edge/ingest',json.loads(payload));cn.execute('DELETE FROM queue WHERE id=?',(row_id,));cn.commit()
def heartbeat(capabilities):post('/api/v1/edge/heartbeat',{'version':VERSION,'capabilities':capabilities,'queue_depth':queue_depth()},15)
def collect(connector):
 kind=connector['type'];points=[]
 if kind=='CSV':
  with open(connector['path'],newline='',encoding='utf-8-sig') as f:rows=list(csv.DictReader(f,delimiter=connector.get('delimiter',',')))
  if rows:
   row=rows[-1];points=[{'source_path':m['source_path'],'value':row[m.get('column',m['source_path'])],'quality':'GOOD'} for m in connector['mappings']]
 elif kind=='SQL_ODBC':
  if not pyodbc:raise RuntimeError('pyodbc unavailable')
  query=connector['query'].strip()
  if not query.lower().startswith('select'):raise RuntimeError('Only SELECT queries are allowed')
  with pyodbc.connect(os.environ[connector['dsn_env']],timeout=15,readonly=True) as cn:
   cur=cn.cursor();cur.execute(query);row=cur.fetchone();cols=[x[0] for x in cur.description];data=dict(zip(cols,row)) if row else {};points=[{'source_path':m['source_path'],'value':data[m.get('column',m['source_path'])],'quality':'GOOD'} for m in connector['mappings']]
 elif kind=='OPC_UA':
  if not OpcUaClient:raise RuntimeError('opcua unavailable')
  client=OpcUaClient(connector['endpoint'],timeout=10)
  if connector.get('username_env'):client.set_user(os.environ.get(connector['username_env'],'') );client.set_password(os.environ.get(connector.get('password_env',''),'') )
  client.connect()
  try:points=[{'source_path':m['source_path'],'value':client.get_node(m.get('node_id',m['source_path'])).get_value(),'quality':'GOOD'} for m in connector['mappings']]
  finally:client.disconnect()
 elif kind=='MODBUS_TCP':
  if not ModbusTcpClient:raise RuntimeError('pymodbus unavailable')
  client=ModbusTcpClient(connector['host'],port=int(connector.get('port',502)),timeout=10)
  if not client.connect():raise RuntimeError('Modbus connection failed')
  try:
   for m in connector['mappings']:
    function=m.get('function','holding');reader={'holding':client.read_holding_registers,'input':client.read_input_registers}.get(function)
    if not reader:raise RuntimeError('Read-only register functions only')
    rr=reader(address=int(m['address']),count=int(m.get('count',1)),device_id=int(connector.get('unit_id',1)))
    if rr.isError():raise RuntimeError(str(rr))
    points.append({'source_path':m['source_path'],'value':rr.registers[0],'quality':'GOOD'})
  finally:client.close()
 else:raise RuntimeError('Unsupported connector type: '+kind)
 return points

def run():
 if not BASE or not TOKEN:raise RuntimeError('ASSETTRACK_BASE_URL and EDGE_API_TOKEN are required')
 init_queue();last_hb=0
 while True:
  config=json.loads(CONFIG.read_text(encoding='utf-8'));connectors=[c for c in config.get('connectors',[]) if c.get('enabled',True)];caps=sorted(set(c['type'] for c in connectors))
  try:
   flush_queue()
   if time.time()-last_hb>=60:heartbeat(caps);last_hb=time.time()
  except Exception as exc:print('Cloud link',type(exc).__name__,str(exc)[:160])
  for connector in connectors:
   try:
    points=collect(connector);payload={'connector_key':connector['connector_key'],'timestamp':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'points':points}
    try:post('/api/v1/edge/ingest',payload)
    except Exception:enqueue(payload)
   except Exception as exc:print(connector.get('name'),type(exc).__name__,str(exc)[:180])
  time.sleep(max(int(config.get('cycle_seconds',30)),5))
if __name__=='__main__':run()
