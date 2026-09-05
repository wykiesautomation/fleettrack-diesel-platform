from pathlib import Path
T=Path('app/templates/tracking_history.html').read_text(encoding='utf-8')
C=Path('app/static/rev28_tracking.css').read_text(encoding='utf-8')

def test_supported_rule_has_real_on_off_toggle():
    assert 'rule-supported' in T
    assert 'rule-toggle' in T
    assert "{{'ON' if rules[key] else 'OFF'}}" in T
    assert "input.addEventListener('change',update)" in T

def test_whole_supported_row_clicks_checkbox():
    assert 'for="rule_{{key}}"' in T
    assert 'id="rule_{{key}}"' in T
    assert 'Click anywhere on this row to change' in T

def test_unsupported_rules_are_status_not_fake_checkbox():
    assert 'NOT SUPPORTED' in T
    unavailable=T[T.index("{% else %}<div class=\"rule rule-unavailable"):T.index('{% endif %}{% endfor %}')]
    assert 'type="checkbox"' not in unavailable

def test_green_only_means_changeable():
    assert 'Green controls can be changed' in T
    assert '.rule-supported.is-on' in C
    assert "v='33'" in T
