from pathlib import Path
from jinja2 import Environment
T=Path('app/templates/asset.html').read_text(encoding='utf-8')
def test_primary_status_is_defined_before_first_use():
 set_pos=T.index("{% set primary_status=output_statuses.get(primary_output.channel,{}) %}")
 use_pos=T.index("{{primary_status.get('state','WAITING')}}")
 assert set_pos < use_pos
def test_no_jinja_expression_in_legacy_html_comment():
 assert "Legacy safety contract: Latest: <b>{{primary_status" not in T
def test_template_parses():
 Environment().parse(T)
def test_mobile_and_customer_friendly_controls_remain():
 B=Path('app/templates/base.html').read_text(encoding='utf-8')
 C=Path('app/static/rev28_full.css').read_text(encoding='utf-8')
 assert 'mobile-nav-backdrop' in B
 assert '@media(max-width:520px)' in C
 assert 'TURN ON' in T and 'TURN OFF' in T and 'COMMAND SENT' in T
