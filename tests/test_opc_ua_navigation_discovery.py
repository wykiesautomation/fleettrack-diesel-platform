from pathlib import Path
B=Path('app/templates/base.html').read_text(encoding='utf-8');R=Path('app/routes.py').read_text(encoding='utf-8');T=Path('app/templates/opc_ua_studio_landing.html').read_text(encoding='utf-8')
def test_sidebar_exposes_integration_and_opc_studio():
 for x in ['INTEGRATIONS','Integration Centre','OPC UA Studio',"url_for('main.integrations')","url_for('main.opc_ua_studio_landing')"]:assert x in B
def test_opc_landing_route_is_tenant_scoped():
 for x in ["@bp.get('/opc-ua-studio')",'def opc_ua_studio_landing','customer_id=tenant_id()',"connector_type='OPC_UA'"]:assert x in R
def test_landing_exposes_all_four_parts_and_empty_state():
 for x in ['PART 1','PART 2','PART 3','PART 4','CREATE OPC UA CONNECTION','No OPC UA connector configured','local Edge Gateway']:assert x in T
def test_navigation_does_not_claim_cloud_opc_socket():
 assert 'website never opens an OPC socket' in T
