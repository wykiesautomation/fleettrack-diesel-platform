from pathlib import Path
from jinja2 import Environment
R=Path('app/routes.py').read_text(encoding='utf-8')
T=Path('app/templates/asset.html').read_text(encoding='utf-8')
def test_output_panel_uses_newest_same_key_reading():
 assert 'matching_ids=[row.id for row in SignalDefinition.query.filter_by' in R
 assert 'order_by(desc(Reading.sampled_at),desc(Reading.id))' in R
def test_simulation_is_inferred_from_output_quality():
 assert "quality=='SIMULATED'" in R and 'simulation_active or simulated_output_seen' in R
def test_top_panel_labels_simulation_values_directly():
 assert 'SIMULATED ON' in T or "'SIMULATED '" in T
 assert "status.get('simulated')" in T
 assert 'Simulation feedback only. Physical output commands remain locked.' in T
def test_template_compiles_and_primary_status_is_safe():
 Environment().parse(T)
 assert T.index('{% set primary_status') < T.index('{{\'SIMULATED \' ~ primary_status')
