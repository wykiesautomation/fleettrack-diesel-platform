from pathlib import Path
R=Path('app/routes.py').read_text(encoding='utf-8')
T=Path('app/templates/connect_device.html').read_text(encoding='utf-8')

def connect_block():
    return R[R.index('def connect_device():'):R.index("@bp.get('/devices/connect/waiting')")]

def test_new_board_is_explicit_default_in_ui_and_backend():
    assert 'name="hardware_connection_mode" value="NEW_BOARD" checked' in T
    assert 'New Board never opens or reuses an existing device.' in T
    assert "request.form.get('hardware_connection_mode','NEW_BOARD')" in connect_block()

def test_existing_device_reuse_requires_explicit_choice():
    b=connect_block()
    assert "hardware_connection_mode=='USE_EXISTING'" in b
    assert "if hardware_connection_mode=='USE_EXISTING' and existing_connected" in b
    assert "if asset.asset_type=='TANK' and existing_connected" not in b

def test_new_board_still_creates_fresh_claim_registration():
    b=connect_block()
    assert "code=f'{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}'" in b
    assert "provisioning_state='WAITING'" in b
    assert "session['onboarding_registration_id']=reg.id" in b
    assert 'NEW_BOARD claim code created' in b

def test_new_board_does_not_disable_or_unlink_existing_device():
    b=connect_block()
    assert 'existing_connected.active=False' not in b
    assert 'existing_connected.asset_id=None' not in b
    assert 'db.session.delete(existing_connected)' not in b
