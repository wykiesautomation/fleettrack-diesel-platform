from pathlib import Path
A=Path('app/templates/asset.html').read_text(encoding='utf-8')
C=Path('app/static/rev28_full.css').read_text(encoding='utf-8')
B=Path('app/templates/base.html').read_text(encoding='utf-8')

def test_raw_gps_is_default_selected_view():
    raw=A[A.index('id="rawRouteBtn"'):A.index('</button>',A.index('id="rawRouteBtn"'))]
    matched=A[A.index('id="matchedRouteBtn"'):A.index('</button>',A.index('id="matchedRouteBtn"'))]
    assert 'selected' in raw and 'aria-pressed="true"' in raw
    assert 'selected' not in matched and 'aria-pressed="false"' in matched

def test_buttons_have_clear_descriptions():
    for value in ['Actual phone points','Optional road alignment','Fit Entire Route','Zoom to all points','ROUTE VIEW','MAP ACTION']:
        assert value in A

def test_fit_is_action_not_selected_mode():
    fit=A[A.index('id="fitRouteBtn"'):A.index('</button>',A.index('id="fitRouteBtn"'))]
    assert 'route-action' in fit
    assert 'route-toggle' not in fit
    assert 'action-done' in A

def test_no_automatic_switch_to_matched_route():
    assert 'setTimeout(showMatched' not in A
    assert "if(rawPoints.length>1){showRaw();}" in A

def test_matched_becomes_selected_only_after_success():
    function=A[A.index('async function showMatched'):A.index('async function addressFor')]
    assert "mode('matched'" in function
    assert function.index("mode('matched'") > function.index("data.route?.status==='matched'")
    assert 'Raw GPS remains selected' in function

def test_cache_bumped():
    assert "v='43'" in B
    assert '.route-toggle.selected' in C
