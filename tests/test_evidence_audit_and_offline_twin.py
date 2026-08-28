from pathlib import Path
R=Path('app/routes.py').read_text(encoding='utf-8')
T=Path('app/templates/safety_twin.html').read_text(encoding='utf-8')

def test_evidence_audit_uses_integer_user_actor_id():
    assert "'USER',current_user.id" in R
    assert "'ASSET',payload['report_id']" not in R
    assert 'Evidence PDF generated:' in R
    assert 'Evidence ZIP pack exported:' in R

def test_connectivity_bands_and_stale_battery_context():
    for state in ['ONLINE','DELAYED','STALE','OFFLINE','NEVER_SEEN']:
        assert repr(state) in R
    assert 'battery_age' in R and 'battery_stale' in R
    assert 'LAST REPORTED BATTERY' in T
    assert 'This page shows the last validated session' in T
    assert 'This is not connectivity confidence' in T

def test_offline_ui_is_not_presented_as_live():
    assert 'Last Known Validated Position' in T
    assert 'LAST SESSION CONFIDENCE' in T
    assert 'LAST VALIDATED STATE' in R
    assert 'CONNECTIVITY' in T
    assert 'NO PREDICTED DATA SHOWN' in T
