from pathlib import Path
from jinja2 import Environment
T=Path("app/templates/asset.html").read_text(encoding="utf-8")
def test_asset_template_compiles_after_output_command():
 Environment().parse(T)
def test_template_does_not_introspect_last_command_runtime_object():
 assert "output_command.channel" not in T
 assert "output_command.state" not in T
 assert "output_command.action" not in T
def test_immediate_click_feedback_and_firmware_truth_remain():
 assert "COMMAND SENT" in T
 assert "Confirmed state comes from fresh device firmware feedback" in T
 assert "OUTPUT ON" in T and "OUTPUT OFF" in T
def test_mobile_responsive_features_remain():
 B=Path("app/templates/base.html").read_text(encoding="utf-8")
 C=Path("app/static/rev28_full.css").read_text(encoding="utf-8")
 assert "mobile-nav-backdrop" in B and "@media(max-width:520px)" in C
 assert "min-height:56px" in C and "overflow-x:hidden" in C
