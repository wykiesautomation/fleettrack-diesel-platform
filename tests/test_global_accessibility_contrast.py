from pathlib import Path
B=Path('app/templates/base.html').read_text(encoding='utf-8')
C=Path('app/static/accessibility_contrast.css').read_text(encoding='utf-8')

def test_contrast_layer_loads_after_page_specific_css():
    assert "filename='accessibility_contrast.css'" in B
    assert B.index("{% block head_extra %}{% endblock %}") < B.index("filename='accessibility_contrast.css'")

def test_visited_links_never_fall_back_to_browser_purple():
    assert 'a:visited' in C
    assert '--at360-link:#55dcf2' in C
    assert 'color:var(--at360-action-text)!important' in C

def test_buttons_use_white_text_and_cyan_hover():
    assert '--at360-action-text:#f4fbff' in C
    assert '--at360-action-cyan:#18c7e8' in C
    assert '--at360-action-navy:#031923' in C
    assert ':not(:disabled):hover' in C

def test_keyboard_focus_and_disabled_states_are_accessible():
    assert '--at360-focus:#9dde35' in C
    assert 'outline:3px solid var(--at360-focus)!important' in C
    assert 'color:#b8cbd4!important' in C

def test_sidebar_navigation_remains_white():
    assert '.side a:link,.side a:visited' in C
    assert 'color:#dff7ff!important' in C
