from pathlib import Path


def test_shared_shell_fix_is_loaded_after_page_styles():
    base=Path("app/templates/base.html").read_text(encoding="utf-8")
    assert "rev28_shell_navigation_fix.css" in base
    assert base.index("{% block head_extra %}") < base.index("rev28_shell_navigation_fix.css")


def test_shell_fix_covers_navigation_and_responsive_layout():
    css=Path("app/static/rev28_shell_navigation_fix.css").read_text(encoding="utf-8")
    for selector in (".app-shell", ".side nav a", ".brand-live", ".workspace-live", ".main", ".top", ".mobile-menu"):
        assert selector in css
    assert "@media(max-width:980px)" in css
    assert css.count("{")==css.count("}")


def test_dashboard_css_is_cache_busted():
    dashboard=Path("app/templates/dashboard.html").read_text(encoding="utf-8")
    assert "dashboard_rev28_exact.css',v='106'" in dashboard
