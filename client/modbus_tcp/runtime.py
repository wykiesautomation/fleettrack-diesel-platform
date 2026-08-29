"""Read-only Modbus TCP runtime and decoder for AssetTrack 360."""
import struct,time,hashlib
from datetime import datetime,timezone
from pymodbus.client import ModbusTcpClient
FUNCTIONS={1:'COILS',2:'DISCRETE_INPUTS',3:'HOLDING_REGISTERS',4:'INPUT_REGISTERS'}
READ_METHODS={1:'read_coils',2:'read_discrete_inputs',3:'read_holding_registers',4:'read_input_registers'}

def words_to_bytes(registers,byte_order='BIG',word_order='BIG'):
 words=list(registers)
 if word_order=='LITTLE':words.reverse()
 chunks=[]
 for word in words:
  b=int(word).to_bytes(2,'big',signed=False)
  chunks.append(b if byte_order=='BIG' else b[::-1])
 return b''.join(chunks)

def decode(registers,data_type='UINT16',byte_order='BIG',word_order='BIG'):
 data_type=data_type.upper();raw=words_to_bytes(registers,byte_order,word_order)
 formats={'UINT16':'>H','INT16':'>h','UINT32':'>I','INT32':'>i','FLOAT32':'>f','UINT64':'>Q','INT64':'>q','FLOAT64':'>d'}
 if data_type=='BOOLEAN':return bool(registers[0])
 if data_type not in formats:raise ValueError('unsupported_data_type')
 size=struct.calcsize(formats[data_type])
 if len(raw)<size:raise ValueError('insufficient_registers')
 return struct.unpack(formats[data_type],raw[:size])[0]

def read_block(client,function_code,address,count,unit_id):
 if function_code not in READ_METHODS:raise ValueError('read_function_required')
 method=getattr(client,READ_METHODS[function_code])
 try:result=method(address=address,count=count,device_id=unit_id)
 except TypeError:result=method(address=address,count=count,slave=unit_id)
 if result.isError():raise RuntimeError(str(result))
 return list(result.bits[:count] if function_code in (1,2) else result.registers)

def read_once(config,address,function_code,count=1):
 client=ModbusTcpClient(config['host'],port=int(config.get('port',502)),timeout=float(config.get('timeout_seconds',3)),retries=int(config.get('retry_limit',2)))
 if not client.connect():raise ConnectionError('modbus_tcp_connect_failed')
 try:return read_block(client,int(function_code),int(address),int(count),int(config.get('unit_id',1)))
 finally:client.close()

def mapped_points(config,mappings):
 client=ModbusTcpClient(config['host'],port=int(config.get('port',502)),timeout=float(config.get('timeout_seconds',3)),retries=int(config.get('retry_limit',2)))
 if not client.connect():raise ConnectionError('modbus_tcp_connect_failed')
 points=[]
 try:
  for m in mappings:
   values=read_block(client,int(m['function_code']),int(m['address']),int(m['register_count']),int(config.get('unit_id',1)))
   value=decode(values,m['data_type'],m.get('byte_order','BIG'),m.get('word_order','BIG'));stamp=datetime.now(timezone.utc).isoformat();seq='mbtcp:'+hashlib.sha256(f"{m['mapping_id']}:{stamp}:{values}".encode()).hexdigest()[:48]
   points.append({'source_path':m['source_path'],'value':float(value),'raw_registers':values,'quality':'GOOD','source_timestamp':stamp,'sequence':seq})
  return points
 finally:client.close()
