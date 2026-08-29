from pathlib import Path
R=Path('app/routes.py').read_text(encoding='utf-8');T=Path('app/templates/opc_ua_commissioning_centre.html').read_text(encoding='utf-8');S=Path('client/local_edge_gateway/opcua_simulator.py').read_text(encoding='utf-8')
def test_part6_routes_and_report_exist():
 assert '/opc-ua/commissioning' in R and 'commissioning-report.json' in R
 assert 'opcua_commissioning' in R and 'OPC_UA_COMMISSIONING_UPDATED' in R
def test_simulator_has_realistic_nodes_and_read_only_contract():
 for name in ('DischargePressure','FlowRate','Running','Current','Temperature','Level','Total'):assert name in S
 assert 'set_writable(False)' in S and 'set_value(' in S
 assert 'set_writable(True)' not in S
def test_commissioning_covers_end_to_end_flow():
 for key in ('gateway_heartbeat','simulator_connected','browse_passed','read_test_passed','mapping_saved','live_value_received','quality_preserved','offline_queue_tested','recovery_tested','read_only_verified'):assert key in R and key in T
 assert 'NO PLC CONTROL' in T and 'Download Report' in T
