from pathlib import Path
ROUTES=Path("app/routes.py").read_text(encoding="utf-8")
TEMPLATE=Path("app/templates/device_panel.html").read_text(encoding="utf-8")

def test_analogue_purpose_field_matches_backend():
    assert "name=\"{{c.key}}_purpose\"" in TEMPLATE
    assert "request.form.get(key+'_purpose','CUSTOM_ANALOG')" in ROUTES
    assert "request.form.get(key+'_measurement','CUSTOM_ANALOG')" not in ROUTES

def test_selected_purpose_updates_signal_semantics():
    assert "analog_lib={'CUSTOM_ANALOG':('CUSTOM','numeric'),'TANK_LEVEL':('LEVEL','tank'),'TEMPERATURE':('TEMPERATURE','temperature')" in ROUTES
    assert "sig.signal_type=stype;sig.widget=widget" in ROUTES
    assert "'measurement_type':purpose" in ROUTES
    assert "row.purpose=purpose" in ROUTES
