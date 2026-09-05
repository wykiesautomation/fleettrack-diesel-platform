from pathlib import Path
R=Path('app/routes.py').read_text(encoding='utf-8')
Q=Path('app/templates/quick_calibration.html').read_text(encoding='utf-8')
D=Path('app/templates/device_panel.html').read_text(encoding='utf-8')

def block():return R[R.index('def quick_calibration(asset_id):'):R.index("@bp.route('/asset/<int:asset_id>/signals'")]
def test_wizard_is_separate_and_advanced_calibration_remains():
 assert '/quick-calibration' in R and 'Quick Calibration' in D and 'Advanced Calibration & Alarms' in D
 assert 'Advanced Engineering' in Q
def test_two_point_presets_and_capability_safe_sensor_types():
 b=block();assert "'TANK_LEVEL'" in b and "'TEMPERATURE'" in b and "'PRESSURE'" in b and "'FLOW'" in b
 assert "'CURRENT_4_20MA_CONDITIONED'" in b and "'VOLTAGE_0_10_CONDITIONED'" in b and "'ADC_0_3V3'" in b
 assert 'Never connect those signals directly to an ESP32 ADC.' in Q
def test_previous_calibration_is_backed_up_before_deploy():
 b=block();assert "history=list(cfg.get('calibration_history') or [])[-9:]" in b
 assert 'history.append(previous)' in b and "'calibration_history':history" in b
def test_transactional_deploy_and_rollback():
 b=block();assert 'db.session.commit()' in b and 'db.session.rollback()' in b
 assert 'Calibration was rolled back safely. Existing calibration remains active.' in b
def test_validation_protects_ranges_and_updates_assignment():
 b=block();assert 'raw_max<=raw_min' in b and "sensor_type=='ADC_0_3V3'" in b
 assert 'assignment.purpose=application' in b and "'calibration_status':'VERIFIED'" in b
def test_normal_customer_cannot_silently_edit_engineering_calibration():
 b=block();assert "current_user.role not in ('customer_admin','platform_admin')" in b and 'has_advanced_access' in b
