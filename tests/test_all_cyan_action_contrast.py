from pathlib import Path
B=Path('app/templates/base.html').read_text(encoding='utf-8')
C=Path('app/static/cyan_action_contrast_final.css').read_text(encoding='utf-8')
A=Path('app/templates/assets_register.html').read_text(encoding='utf-8')
S=Path('app/templates/safety_twin.html').read_text(encoding='utf-8')
D=Path('app/templates/asset_device_setup.html').read_text(encoding='utf-8')

def test_final_contrast_css_loads_last():
 assert "filename='cyan_action_contrast_final.css'" in B
 assert B.index("filename='primary_action_text_fix.css'") < B.index("filename='cyan_action_contrast_final.css'")

def test_all_reported_cyan_actions_are_covered():
 assert 'class="asset-add"' in A and 'a.asset-add' in C
 assert 'class="new-device"' in D and 'a.new-device' in C
 assert 'TRACKING HISTORY' in S and 'EVIDENCE CENTRE' in S
 assert '.twin .modes a.btn' in C

def test_cyan_text_is_always_dark_navy():
 assert '--at360-cyan-action-text:#031923' in C
 assert ':is(:link,:visited)' in C
 assert 'color:var(--at360-cyan-action-text)!important' in C
 assert '-webkit-text-fill-color:var(--at360-cyan-action-text)!important' in C

def test_hover_and_focus_remain_readable():
 assert '--at360-cyan-action-hover:#55dcf2' in C
 assert ':not(:disabled):hover' in C
 assert 'outline:3px solid #9dde35!important' in C

def test_disabled_primary_controls_are_readable_but_not_cyan():
 assert 'background:#294653!important' in C
 assert 'color:#e5f1f5!important' in C
 assert 'cursor:not-allowed!important' in C
