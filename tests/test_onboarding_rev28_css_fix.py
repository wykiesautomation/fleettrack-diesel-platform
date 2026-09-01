from pathlib import Path


def test_onboarding_loads_dedicated_versioned_css():
    html=Path("app/templates/onboarding.html").read_text(encoding="utf-8")
    assert "onboarding_rev28_fix.css" in html
    assert "v='107'" in html


def test_onboarding_css_covers_full_page_contract():
    css=Path("app/static/onboarding_rev28_fix.css").read_text(encoding="utf-8")
    for selector in (".head", ".btn", ".app-toolbar", ".app-filter", ".application-grid", ".application-card", ".application-visual", ".application-body", ".cap-row", ".cap"):
        assert selector in css
    assert "@media(max-width:640px)" in css
    assert css.count("{")==css.count("}")
