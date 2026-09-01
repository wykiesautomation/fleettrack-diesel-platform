from pathlib import Path
D=Path('app/templates/device_panel.html').read_text();Q=Path('app/templates/quick_calibration.html').read_text();B=Path('app/templates/base.html').read_text();C=Path('app/static/device_action_contrast.css').read_text()
def test_quick_calibration_is_top_primary_action():
 assert 'device-panel-top-actions' in D and 'dp-action dp-primary' in D
 assert D.index('Quick Calibration') < D.index('Verified Board')
def test_capture_buttons_are_readable():
 assert 'class="capture-button" id="capture_zero"' in Q and 'class="capture-button" id="capture_span"' in Q
 assert '.capture-button:disabled' in Q and 'color:#e5f1f5!important' in Q and 'opacity:1!important' in Q
def test_capture_disables_without_live_data():
 assert "String(raw).trim()===''" in Q
 assert "document.getElementById('capture_zero').disabled=noLive" in Q
def test_visited_actions_do_not_turn_purple():
 assert "filename='device_action_contrast.css'" in B
 assert '.dp-action:link,.dp-action:visited' in C and 'color:#f4fbff!important' in C
def test_green_only_used_as_focus_outline_in_new_css():
 assert C.count('#9dde35')==1
