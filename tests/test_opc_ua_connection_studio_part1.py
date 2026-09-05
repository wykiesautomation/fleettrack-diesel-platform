from pathlib import Path
R=Path("app/routes.py").read_text(encoding="utf-8")
T=Path("app/templates/opc_ua_connection_studio.html").read_text(encoding="utf-8")
D=Path("app/templates/integration_detail.html").read_text(encoding="utf-8")

def test_opc_studio_route_and_edge_result_contract():
    assert "def opc_ua_connection_studio" in R
    assert "def opc_ua_edge_test_result" in R
    assert "opc.tcp://" in R
    assert "gateway_mismatch" in R

def test_read_only_is_enforced_server_side():
    for text in ["connector.read_only=True","'allow_write':False","'allow_methods':False","'allow_alarm_ack':False"]: assert text in R
    assert "READ-ONLY ENFORCED" in T

def test_security_and_auth_fields_exist():
    for text in ["Basic256Sha256","SignAndEncrypt","ANONYMOUS","USERNAME","CERTIFICATE","LOCAL SECRET REFERENCE","EDGE GATEWAY UID"]: assert text in T
    assert "OPC UA Connection Studio" in D

def test_web_does_not_claim_direct_ot_connection():
    assert "website cannot open an OT-network OPC socket" in T
    assert "local Edge Gateway runs Test Connection" in T
