"""Read-only Modbus RTU runtime with RS-485 serial validation."""
import hashlib
from datetime import datetime,timezone
from serial.tools import list_ports
from pymodbus.client import ModbusSerialClient
from client.modbus_tcp.runtime import decode
READ_METHODS={1:'read_coils',2:'read_discrete_inputs',3:'read_holding_registers',4:'read_input_registers'}
VALID_PARITY={'N','E','O'};VALID_DATA_BITS={7,8};VALID_STOP_BITS={1,2}

def available_ports():
    return [{'device':p.device,'description':p.description or 'Serial port','hwid':p.hwid or ''} for p in list_ports.comports()]

def validate_config(config):
    if not str(config.get('port','')).strip():raise ValueError('serial_port_required')
    if int(config.get('baudrate',9600)) not in (1200,2400,4800,9600,19200,38400,57600,115200):raise ValueError('invalid_baudrate')
    if str(config.get('parity','N')).upper() not in VALID_PARITY:raise ValueError('invalid_parity')
    if int(config.get('bytesize',8)) not in VALID_DATA_BITS:raise ValueError('invalid_data_bits')
    if int(config.get('stopbits',1)) not in VALID_STOP_BITS:raise ValueError('invalid_stop_bits')
    if not 1<=int(config.get('slave_id',1))<=247:raise ValueError('invalid_slave_id')
    return True

def open_client(config):
    validate_config(config)
    return ModbusSerialClient(port=config['port'],baudrate=int(config.get('baudrate',9600)),parity=str(config.get('parity','N')).upper(),bytesize=int(config.get('bytesize',8)),stopbits=int(config.get('stopbits',1)),timeout=float(config.get('timeout_seconds',2)),retries=int(config.get('retry_limit',2)),handle_local_echo=bool(config.get('handle_local_echo',False)))

def read_block(client,function_code,address,count,slave_id):
    if function_code not in READ_METHODS:raise ValueError('read_function_required')
    method=getattr(client,READ_METHODS[function_code])
    try:result=method(address=address,count=count,device_id=slave_id)
    except TypeError:result=method(address=address,count=count,slave=slave_id)
    if result.isError():raise RuntimeError(str(result))
    return list(result.bits[:count] if function_code in (1,2) else result.registers)

def read_once(config,function_code,address,count=1):
    client=open_client(config)
    if not client.connect():raise ConnectionError('modbus_rtu_connect_failed')
    try:return read_block(client,int(function_code),int(address),int(count),int(config.get('slave_id',1)))
    finally:client.close()

def poll_mappings(config,mappings):
    client=open_client(config)
    if not client.connect():raise ConnectionError('modbus_rtu_connect_failed')
    points=[]
    try:
        for mapping in mappings:
            raw=read_block(client,int(mapping['function_code']),int(mapping['address']),int(mapping['register_count']),int(config.get('slave_id',1)))
            value=decode(raw,mapping['data_type'],mapping.get('byte_order','BIG'),mapping.get('word_order','BIG'));stamp=datetime.now(timezone.utc).isoformat();sequence='mbrtu:'+hashlib.sha256(f"{mapping['mapping_id']}:{stamp}:{raw}".encode()).hexdigest()[:48]
            points.append({'source_path':mapping['source_path'],'value':float(value),'quality':'GOOD','source_timestamp':stamp,'sequence':sequence,'raw_registers':raw})
        return points
    finally:client.close()
