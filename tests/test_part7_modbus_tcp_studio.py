from pathlib import Path
R=Path('app/routes.py').read_text(encoding='utf-8');T=Path('app/templates/modbus_tcp_studio.html').read_text(encoding='utf-8');M=Path('client/modbus_tcp/runtime.py').read_text(encoding='utf-8');S=Path('client/modbus_tcp/simulator.py').read_text(encoding='utf-8')
def test_part7_routes_and_ui_exist():
 assert '/modbus-tcp' in R and 'modbus_tcp_studio.html' in R and 'MODBUS TCP STUDIO' in T
 assert 'Register Read Test' in T and 'Register Mapping' in T
def test_read_only_functions_only():
 assert "FUNCTIONS={1:'COILS',2:'DISCRETE_INPUTS',3:'HOLDING_REGISTERS',4:'INPUT_REGISTERS'}" in M
 for write in ('write_coil','write_register','write_coils','write_registers'):assert write not in M
 assert 'FC05' in T and 'FC16' in T and 'Blocked' in T
def test_decoding_and_runtime_contract():
 for kind in ('UINT16','INT16','UINT32','INT32','FLOAT32','UINT64','INT64','FLOAT64','BOOLEAN'):assert kind in M
 assert '/api/v1/edge/modbus-tcp/' in R and 'runtime-config' in R
def test_simulator_has_realistic_registers():
 assert 'StartAsyncTcpServer' in S and 'ModbusSequentialDataBlock' in S
 assert 'READ-ONLY' in S
