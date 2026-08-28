from pathlib import Path
A=Path('app/templates/auth.html').read_text(encoding='utf-8')

def test_title_block_contains_no_script():
    title=A[A.index('{% block title %}'):A.index('{% endblock %}')]
    assert '<script>' not in title

def test_login_has_explicit_high_contrast_colours():
    for value in ['color:#f6fbff!important','background:#061a29!important','color:#ffffff!important','background:#00d6ee!important']:
        assert value in A

def test_buttons_do_not_use_browser_defaults():
    assert '.auth-card .button,.auth-card button' in A
    assert 'font-family:Segoe UI,Arial,sans-serif!important' in A
    assert 'min-height:46px' in A

def test_auth_functions_remain_present():
    for value in ['current-password','resend_verification','Register','pw-toggle','Caps Lock is ON']:
        assert value in A

def test_mobile_readability_present():
    assert '@media(max-width:600px)' in A
    assert 'padding:23px 18px' in A
