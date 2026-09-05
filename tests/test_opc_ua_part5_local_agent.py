from pathlib import Path
R=Path('app/edge_gateway_registry.py').read_text(encoding='utf-8')
A=Path('client/local_edge_gateway/agent.py').read_text(encoding='utf-8')
O=Path('client/local_edge_gateway/opc_client.py').read_text(encoding='utf-8')

def test_secure_registry_agent_endpoints_exist():
 for path in ('/api/v1/gateways/runtime-config','/api/v1/gateways/opc-ua/work','/api/v1/gateways/opc-ua/work-result','/api/v1/gateways/opc-ua/live-batch'):assert path in R
 assert 'authenticate_gateway()' in R and "data.get('read_only') is not True" in R

def test_agent_has_full_local_runtime_chain():
 for item in ('runtime-config','opc-ua/work','opc-ua/work-result','opc-ua/live-batch','heartbeat','queue_depth'):assert item in A
 assert 'ReadOnlyOpcClient' in A

def test_no_opc_write_or_method_api_is_implemented():
 lowered=(A+O).lower()
 for forbidden in ('.set_value(','.call_method(','alarm_ack','allow_write=true'):assert forbidden not in lowered
 assert 'browse_nodes' in O and 'read_node' in O and 'read_mapped_nodes' in O

def test_windows_startup_and_docs_are_packaged():
 for name in ('install_windows_task.ps1','uninstall_windows_task.ps1','README.md','requirements.txt'):assert (Path('client/local_edge_gateway')/name).exists()
