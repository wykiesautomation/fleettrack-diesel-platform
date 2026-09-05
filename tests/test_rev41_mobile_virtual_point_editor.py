from pathlib import Path
T=Path('app/templates/trends_limits.html').read_text(encoding='utf-8')
D=Path('app/device_api.py').read_text(encoding='utf-8')

def test_mobile_uses_data_point_not_pin_language():
    for value in ['Configure Mobile Data Point','Data Point\' if is_mobile','Save {{\'Data Point\' if is_mobile','mobile data point']:
        assert value in T

def test_mobile_editor_has_no_physical_scaling_panel():
    mobile=T[T.index('{% if is_mobile %}',T.index('id="tab-scaling"')):T.index('{% else %}',T.index('id="tab-scaling"'))]
    for forbidden in ['Raw Input Minimum','Raw Input Maximum','Calibration Offset','Calibration Multiplier']:
        assert forbidden not in mobile
    assert 'APP / VIRTUAL data point' in mobile

def test_gps_editor_has_relevant_settings():
    for value in ['Location Upload Interval','Minimum Movement Distance','GPS Accuracy Limit','Offline Queue']:
        assert value in T

def test_other_phone_points_have_relevant_settings():
    for value in ['Stationary Threshold','Maximum Plausible Speed','Update Threshold','Low Battery Warning','Critical Battery']:
        assert value in T

def test_backend_does_not_apply_raw_scaling_to_mobile():
    assert "mobile=dev.device_type in" in D
    mobile=D[D.index('if mobile:',D.index('def trends_limits')):D.index('else:',D.index('if mobile:',D.index('def trends_limits')))]
    assert 'signal.raw_min=' not in mobile
    assert "'mobile_virtual_point':True" in D
