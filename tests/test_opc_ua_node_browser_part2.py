from pathlib import Path
R=Path('app/routes.py').read_text(encoding='utf-8');T=Path('app/templates/opc_ua_node_browser.html').read_text(encoding='utf-8');E=Path('client/edge_agent/connectors/opcua_browser.py').read_text(encoding='utf-8')
def test_routes_and_gateway_contract():
    for x in ['def opc_ua_node_browser','def opc_ua_node_browser_request','def opc_ua_node_read_request','def opc_ua_edge_browser_request','def opc_ua_edge_browser_result']:assert x in R
    assert 'gateway_mismatch' in R and 'request_id_mismatch' in R
def test_browse_limits_and_read_only():
    assert 'min(1000' in R and "'read_only':True" in R
    assert 'READ-ONLY ENFORCED' in T
    for x in ['Write','Method Call','alarm acknowledgement']:assert x in T
def test_browser_and_read_ui():
    for x in ['Browse Address Space','Search display name','Direct Node Read','SOURCE TIMESTAMP','SERVER TIMESTAMP','QUALITY']:assert x in T
def test_edge_executor_only_browses_and_reads():
    assert 'def browse_nodes' in E and 'def read_node' in E
    assert '.set_value' not in E and '.call_method' not in E
    assert 'max_nodes),1000' in E
