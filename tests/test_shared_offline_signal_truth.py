from pathlib import Path
R=Path('app/routes.py').read_text(encoding='utf-8')
A=Path('app/templates/asset.html').read_text(encoding='utf-8')

def test_shared_signal_freshness_uses_reading_and_device_age():
    assert "effective_age=max([x for x in (sample_age_minutes,device_age_minutes)" in R
    assert "freshness='WAITING' if not latest else 'OFFLINE'" in R
    assert "else 'STALE' if effective_age is not None and effective_age>15" in R
    assert "else 'DELAYED' if effective_age is not None and effective_age>5" in R

def test_old_good_values_are_relabelled_last_reported():
    assert "'last_reported':bool(latest and freshness!='LIVE')" in R
    assert 'LAST REPORTED · ' in A
    assert 'card.display_quality' in A
    assert 'min old' in A

def test_page_refresh_badge_does_not_claim_device_is_live():
    assert 'DASHBOARD LIVE · DEVICE ' in A
    assert "PAGE LIVE · ' + new Date()" not in A
    assert 'data-device-connectivity' in A

def test_output_freshness_safety_remains_present():
    assert "timedelta(minutes=5)" in R
    assert "quality not in ('SIMULATED','STALE','NO_FIX')" in R
