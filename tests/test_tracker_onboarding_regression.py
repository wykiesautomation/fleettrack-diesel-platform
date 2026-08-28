from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_vehicle_profile_code_is_canonical():
    html = (ROOT / 'app/templates/onboarding.html').read_text(encoding='utf-8')
    assert 'data-solution="VEHICLE_FLEET_TRACKING"' in html
    assert 'data-solution="VEHICLE_TRACKING"' not in html


def test_non_tank_profiles_disable_tank_ui():
    html = (ROOT / 'app/templates/onboarding.html').read_text(encoding='utf-8')
    assert "visualPicker.classList.toggle('hidden',!isTank)" in html
    assert "tankFields.classList.toggle('open',isTank)" in html
    assert 'field.disabled=!isTank' in html


def test_backend_profile_wins_over_stale_visual():
    routes = (ROOT / 'app/routes.py').read_text(encoding='utf-8')
    assert "asset_type=solution_types.get(solution)" in routes
    assert "if asset_type!='TANK' and monitoring_visual in ('EASY_TANK','POINT_TANK','ROUND_TANK')" in routes
    assert "monitoring_visual='GENERAL_MONITORING'" in routes


def test_claim_page_shows_one_claim_code_and_no_device_token():
    waiting = (ROOT / 'app/templates/connect_device_waiting.html').read_text(encoding='utf-8')
    import re
    assert len(re.findall(r'{{\s*code\s*}}', waiting)) == 1
    assert 'device_token' not in waiting.lower()
