from pathlib import Path
BASE=Path('app/templates/base.html').read_text();AB=Path('app/templates/platform_admin_base.html').read_text();CSS=Path('app/static/admin_layout_final.css').read_text();USERS=Path('app/templates/platform_admin_users.html').read_text()
def test_admin_uses_unique_scoped_shell_not_customer_side_class():
 assert 'class="admin-shell"' in AB and 'class="admin-nav"' in AB and 'class="admin-content"' in AB
 assert '<aside class="side">' not in AB and 'class="cmd"' not in AB
def test_all_admin_tabs_share_the_fixed_base():
 pages=list(Path('app/templates').glob('platform_admin_*.html'))
 dependent=[p for p in pages if p.name not in ('platform_admin_base.html','platform_admin_invoice_print.html')]
 assert len(dependent)>=15
 assert all('platform_admin_base.html' in p.read_text() for p in dependent)
def test_admin_content_and_panels_are_full_width():
 assert 'grid-template-columns:230px minmax(0,1fr)!important' in CSS
 assert '.admin-content' in CSS and 'width:100%!important' in CSS and 'max-width:none!important' in CSS
 assert '.admin-panel' in CSS and 'box-sizing:border-box!important' in CSS
def test_users_table_is_full_width_and_horizontally_safe():
 assert 'class="admin-table"' in USERS and 'class="admin-scroll"' in USERS
 assert 'display:table!important' in CSS and 'min-width:760px!important' in CSS
 assert 'overflow-x:auto!important' in CSS
def test_admin_css_loads_last_with_new_cache_version():
 assert "filename='admin_layout_final.css',v='4'" in BASE
 assert BASE.index("filename='cyan_action_contrast_final.css'") < BASE.index("filename='admin_layout_final.css'")
def test_responsive_admin_navigation_and_mobile_forms():
 assert '@media(max-width:1050px)' in CSS and 'grid-template-columns:1fr!important' in CSS
 assert '@media(max-width:680px)' in CSS and 'width:100%!important' in CSS
