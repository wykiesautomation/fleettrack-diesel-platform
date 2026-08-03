import csv,json,os,time
from pathlib import Path
import requests
try: from pymodbus.client import ModbusTcpClient,ModbusSerialClient
except Exception: ModbusTcpClient=ModbusSerialClient=None
try: from opcua import Client as OpcUaClient
except Exception: OpcUaClient=None
try: import pyodbc
except Exception: pyodbc=None

def post(base,token,payload):
 r=requests.post(base.rstrip('/')+'/api/v1/edge/ingest',json=payload,headers={'Authorization':'Bearer '+token},timeout=30);r.raise_for_status()
def run(config):
 base=os.environ['ASSETTRACK_BASE_URL'];token=os.environ['EDGE_API_TOKEN']
 while True:
  for connector in config.get('connectors',[]):
   if not connector.get('enabled',True):continue
   points=[]
   try:
    kind=connector['type']
    if kind=='CSV':
     with open(connector['path'],newline='',encoding='utf-8-sig') as f:
      row=list(csv.DictReader(f,delimiter=connector.get('delimiter',',')))[-1]
      points=[{'source_path':m['source_path'],'value':row[m['column']],'quality':'GOOD'} for m in connector['mappings']]
    elif kind=='SQL_ODBC':
     if not pyodbc:raise RuntimeError('pyodbc unavailable')
     with pyodbc.connect(os.environ[connector['dsn_env']],timeout=15) as cn:
      cur=cn.cursor();cur.execute(connector['query']);row=cur.fetchone();cols=[x[0] for x in cur.description];data=dict(zip(cols,row));points=[{'source_path':m['source_path'],'value':data[m['column']],'quality':'GOOD'} for m in connector['mappings']]
    elif kind=='OPC_UA':
     if not OpcUaClient:raise RuntimeError('opcua unavailable')
     client=OpcUaClient(connector['endpoint']);client.connect()
     try:points=[{'source_path':m['source_path'],'value':client.get_node(m['node_id']).get_value(),'quality':'GOOD'} for m in connector['mappings']]
     finally:client.disconnect()
    elif kind=='MODBUS_TCP':
     if not ModbusTcpClient:raise RuntimeError('pymodbus unavailable')
     client=ModbusTcpClient(connector['host'],port=connector.get('port',502),timeout=10);client.connect()
     try:
      for m in connector['mappings']:
       rr=client.read_holding_registers(m['address'],count=m.get('count',1),device_id=connector.get('unit_id',1));points.append({'source_path':m['source_path'],'value':rr.registers[0],'quality':'GOOD'})
     finally:client.close()
    post(base,token,{'connector_key':connector['connector_key'],'timestamp':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'points':points})
   except Exception as exc:print(connector.get('name'),type(exc).__name__,str(exc)[:150])
  time.sleep(max(config.get('cycle_seconds',30),5))
if __name__=='__main__':run(json.loads(Path(os.environ.get('EDGE_CONFIG','edge_config.json')).read_text()))
