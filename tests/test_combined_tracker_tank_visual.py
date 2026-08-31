from pathlib import Path
ROUTES=Path('app/routes.py').read_text(encoding='utf-8')
ASSET=Path('app/templates/asset.html').read_text(encoding='utf-8')
IO=Path('app/templates/io_studio.html').read_text(encoding='utf-8')
API=Path('app/device_api.py').read_text(encoding='utf-8')
def test_one_device_keeps_tracking_and_process_io_together():
 assert 'Tracking and all assigned process I/O are shown together for this one device.' in ASSET
 assert "card.purpose=='TANK_LEVEL'" in ASSET
 assert "include '_tank_visual.html'" in ASSET
 assert "asset.asset_type=='TANK'" not in ASSET[ASSET.index('{% if device and universal_signal_cards %}'):ASSET.index('{% if device %}',ASSET.index('{% if device and universal_signal_cards %}')+20)]
def test_assignment_purpose_drives_visual():
 assert 'assignment_by_key' in ROUTES
 assert "'purpose':purpose" in ROUTES
 assert "purpose=='TANK_LEVEL'" in API
 assert "'dashboard_visual':'EASY_TANK'" in API
 assert '<option value="TANK_LEVEL">Tank Level</option>' in IO
def test_no_second_device_or_asset_is_created():
 block=API[API.index("if purpose=='TANK_LEVEL'"):API.index('sig.config_json=cfg',API.index("if purpose=='TANK_LEVEL'"))+30]
 assert 'Device(' not in block
 assert 'Asset(' not in block
 assert 'api_token' not in block
