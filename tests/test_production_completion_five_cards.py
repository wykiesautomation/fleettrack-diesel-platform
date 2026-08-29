from pathlib import Path
R=Path('app/routes.py').read_text(encoding='utf-8');T=Path('app/templates/safety_twin.html').read_text(encoding='utf-8')
def test_exact_five_cards():
 for x in ('GPS Tracking','Possible Impact','Abnormal Tilt','Harsh Driving','Unexpected Movement'): assert x in R
 for x in ('GPS Validation','Movement Guardian','Impact Witness','Orientation Memory','Driving Context'): assert x not in T
def test_statuses_are_capability_aware():
 for x in ('MOTION_SENSORS','ORIENTATION_SENSOR','mounted','vehicle_profile','unexpected_movement'): assert x in R
 assert 'for card in safety_cards' in T and 'OPEN SETUP' in T
def test_customer_title(): assert 'Fleet Safety Live' in T
