from pathlib import Path
T=Path('app/templates/io_studio.html').read_text(encoding='utf-8')

def test_empty_point_dropdown_has_visible_reason():
    assert 'Select a supported function first' in T
    assert 'No ${label} point on ${boardName}' in T
    assert 'All ${label} points are already assigned' in T
    assert 'pointHelp' in T

def test_mobile_analogue_input_explanation_is_explicit():
    assert 'Mobile Tracker has no physical analogue input.' in T
    assert 'Select GPS Location, Phone Battery, SOS Event' in T

def test_unsupported_functions_are_disabled():
    assert 'option.disabled=true' in T
    assert '(not supported)' in T
    assert 'decorateFunctions();refresh();' in T

def test_add_button_is_locked_without_valid_point():
    assert 'id="add" type="button" disabled' in T
    assert 'addButton.disabled=true' in T
    assert 'addButton.disabled=false' in T

def test_analogue_rule_is_not_any_input_direction():
    assert "ANALOGUE_INPUT:r=>r.signal.includes('ANALOG')" in T
    assert "ANALOGUE_INPUT:r=>r.signal.includes('ANALOG')||r.direction==='INPUT'" not in T
