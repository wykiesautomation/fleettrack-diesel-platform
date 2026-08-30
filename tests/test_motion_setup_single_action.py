from pathlib import Path
T=Path('app/templates/safety_twin.html').read_text(encoding='utf-8')
S=Path('app/templates/motion_safety_setup.html').read_text(encoding='utf-8')
R=Path('app/routes.py').read_text(encoding='utf-8')
def test_one_shared_motion_setup_action():
 assert 'CONFIGURE MOTION SAFETY' in T and 'EDIT MOTION SAFETY' in T
 assert 'OPEN SETUP' not in T
 assert 'for card in safety_cards' in T
def test_back_to_live_action():
 assert 'BACK TO FLEET SAFETY LIVE' in S and 'main.safety_twin' in S
def test_route_supplies_readiness_state():
 assert 'motion_setup_ready=bool(motion_enabled and mounted and vehicle_profile)' in R
