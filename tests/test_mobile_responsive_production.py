from pathlib import Path
B=Path('app/templates/base.html').read_text(encoding='utf-8')
C=Path('app/static/rev28_full.css').read_text(encoding='utf-8')
def test_mobile_nav_is_real_drawer_with_backdrop():
 for token in ('mobile-nav-backdrop','closeMobileMenu','body.style.overflow','side.open'):assert token in B or token in C
def test_phone_breakpoints_cover_core_views():
 for token in ('@media(max-width:900px)','@media(max-width:520px)','.tankhero','.remote-actions','.top-actions','overflow-x:hidden'):assert token in C
def test_phone_output_buttons_are_touch_friendly():
 assert 'min-height:56px' in C and 'grid-template-columns:1fr!important' in C
def test_css_cache_bumped():
 assert "v='44'" in B
