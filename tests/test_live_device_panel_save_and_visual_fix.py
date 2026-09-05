from pathlib import Path
R=Path('app/routes.py').read_text(encoding='utf-8')
T=Path('app/templates/device_panel.html').read_text(encoding='utf-8')
A=Path('app/templates/asset.html').read_text(encoding='utf-8')

def test_live_html_and_backend_use_same_purpose_field():
    assert 'name="{{c.key}}_purpose"' in T
    assert "request.form.get(key+'_purpose','CUSTOM_ANALOG')" in R
    assert "key+'_measurement'" not in R

def test_application_picture_no_longer_blocks_existing_io_save():
    assert "raise ValueError('Select an application and asset picture before commissioning')" not in R
    assert "if app:meta['studio_application']=app" in R
    assert "if picture:meta['asset_picture']=picture" in R

def test_channel_purpose_and_visual_drive_same_combined_dashboard():
    assert 'assignment_by_key' in R
    assert "'purpose':purpose" in R
    assert "card.purpose=='TANK_LEVEL'" in A
    assert "include '_tank_visual.html'" in A
    assert 'Tracking and all assigned process I/O are shown together for this one device.' in A

def test_existing_identity_is_not_recreated():
    block=R[R.index("def io_configuration(asset_id):"):R.index("@bp.post('/asset/<int:asset_id>/device-trending')")]
    assert 'Device(' not in block
    assert 'api_token=' not in block
