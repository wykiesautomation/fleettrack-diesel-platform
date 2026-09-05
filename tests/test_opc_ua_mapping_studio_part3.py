from pathlib import Path
R=Path('app/routes.py').read_text(encoding='utf-8');T=Path('app/templates/opc_ua_mapping_studio.html').read_text(encoding='utf-8');N=Path('app/templates/opc_ua_node_browser.html').read_text(encoding='utf-8')
def test_mapping_routes_exist():
    for x in ['def opc_ua_mapping_studio','def opc_ua_mapping_create','def opc_ua_mapping_toggle','def opc_ua_mapping_delete','def opc_ua_mapping_preview']:assert x in R
def test_mapping_is_tenant_and_asset_signal_scoped():
    assert 'customer_id=tenant_id()' in R
    assert 'asset_id=asset.id,customer_id=tenant_id(),enabled=True' in R
    assert 'UniversalSourceMapping' in R
def test_transform_and_duplicate_safety():
    assert 'scale=float' in R and 'offset=float' in R
    assert 'already mapped to this signal' in R
    assert 'mapped_value=raw*scale+offset' in R
def test_ui_is_read_only_and_connected_to_part2():
    assert 'READ-ONLY DATA PATH' in T
    assert 'cannot write to the OPC server or PLC' in T
    assert 'Part 3 · Mapping Studio' in N
def test_mapping_management_and_preview():
    for x in ['Create Mapping','Transformation Preview','Active OPC UA Mappings','Save Mapping','Disable','Delete']:assert x in T
