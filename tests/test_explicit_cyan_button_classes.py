from pathlib import Path
B=Path('app/templates/base.html').read_text();C=Path('app/static/cyan_action_contrast_final.css').read_text();D=Path('app/templates/devices.html').read_text();A=Path('app/templates/assets_register.html').read_text();S=Path('app/templates/asset_device_setup.html').read_text();T=Path('app/templates/safety_twin.html').read_text()
def test_real_classes_are_explicitly_covered():
 assert 'class="registry-add"' in D and 'html body .main a.registry-add' in C
 assert 'class="asset-add"' in A and 'html body .main a.asset-add' in C
 assert 'class="new-device"' in S and 'html body .main a.new-device' in C
 assert 'TRACKING HISTORY' in T and 'html body .main .twin .modes a.btn' in C
def test_all_states_force_dark_text():
 for selector in ('a.registry-add:visited','a.asset-add:visited','a.new-device:visited','.twin .modes a.btn:visited'):assert selector in C
 assert 'color:#031923!important' in C and '-webkit-text-fill-color:#031923!important' in C
def test_cache_version_is_advanced():
 assert "filename='cyan_action_contrast_final.css',v='3'" in B
def test_hover_is_explicit():
 assert 'a.registry-add:hover' in C and 'a.asset-add:hover' in C and 'a.new-device:hover' in C
def test_final_css_is_after_previous_contrast_layer():
 assert B.index("filename='primary_action_text_fix.css'") < B.index("filename='cyan_action_contrast_final.css'")
