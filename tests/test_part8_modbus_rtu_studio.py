from pathlib import Path
R=Path('app/routes.py').read_text(encoding='utf-8');T=Path('app/templates/modbus_rtu_studio.html').read_text(encoding='utf-8');M=Path('client/modbus_rtu/runtime.py').read_text(encoding='utf-8');S=Path('client/modbus_rtu/simulator.py').read_text(encoding='utf-8')
def test_part8_routes_and_ui():
 assert '/modbus-rtu' in R and 'modbus_rtu_studio.html' in R and 'MODBUS RTU STUDIO' in T
 assert 'RS-485 Connection' in T and 'COM Port Discovery' in T
def test_serial_profile_validation():
 for value in ('baudrate','parity','bytesize','stopbits','slave_id','inter_request_delay_ms'):assert value in R or value in M
 assert 'available_ports' in M and 'list_ports.comports' in M
def test_read_only_functions_only():
 for forbidden in ('write_coil','write_register','write_coils','write_registers'):assert forbidden not in M
 assert 'FC05' in T and 'FC16' in T and 'Blocked' in T
def test_runtime_and_simulator():
 assert 'ModbusSerialClient' in M and 'read_holding_registers' in M and 'read_input_registers' in M
 assert 'StartAsyncSerialServer' in S and 'READ-ONLY' in S
def test_edge_contract_is_tenant_and_gateway_scoped():
 assert "/api/v1/edge/modbus-rtu/" in R and "connector_type='MODBUS_RTU'" in R and "write_function_codes=[]" in R
