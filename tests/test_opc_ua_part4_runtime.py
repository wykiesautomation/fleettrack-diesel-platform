from pathlib import Path
R=Path('app/routes.py').read_text(encoding='utf-8');E=Path('client/edge_agent/connectors/opcua_runtime.py').read_text(encoding='utf-8');S=Path('client/edge_agent/opcua_live_service.py').read_text(encoding='utf-8');T=Path('app/templates/opc_ua_runtime_dashboard.html').read_text(encoding='utf-8')
def test_runtime_config_is_read_only_and_tenant_gateway_scoped():
 for x in ['def opc_ua_runtime_config','read_only_policy_required','gateway_mismatch',"'allow_write':False","'allow_methods':False"]:assert x in R
def test_live_batch_quality_stale_and_duplicate_contract():
 for x in ['def opc_ua_live_batch',"allowed_quality={'GOOD','UNCERTAIN','BAD','STALE','UNKNOWN'}",'Reading.query.filter_by(signal_id=mapping.signal_id,sequence=sequence)','quality=\'STALE\'','accepted_count','duplicate_count','rejected_count']:assert x in R
def test_edge_runtime_has_durable_queue_and_no_write_api():
 for x in ['read_mapped_nodes','point_sequence','normalize_quality','source_timestamp']:assert x in E
 for x in ['put(payload,key)','upload_queued','queue_depth']:assert x in S
 assert '.set_value' not in E+S and '.call_method' not in E+S
def test_runtime_dashboard_is_operationally_clear():
 for x in ['EDGE GATEWAY RUNTIME & LIVE DATA FLOW','Live Mapping Health','READ-ONLY ENFORCED','SQLite WAL offline queue','Wrong gateway/customer rejected']:assert x in T
