from pathlib import Path
T=Path('app/templates/asset.html').read_text(encoding='utf-8')
def test_output_controls_use_plain_language_and_feedback():
 for token in ('TURN ON','TURN OFF','ON NOW','OFF NOW','OUTPUT ON','OUTPUT OFF','WAITING FOR FEEDBACK'):assert token in T
def test_click_has_immediate_pending_feedback():
 assert 'COMMAND SENT' in T and 'is-sending' in T
 assert 'waiting for device confirmation' in T
def test_buttons_follow_confirmed_state():
 assert "output_state=='ON'" in T and "output_state=='OFF'" in T
 assert 'Already ON' in T and 'Already OFF' in T
