from pathlib import Path
R=Path("app/routes.py").read_text(encoding="utf-8")
T=Path("app/templates/asset.html").read_text(encoding="utf-8")
def test_calibrated_volume_is_percentage_source_of_truth():
    assert "float(vol)/cap*100.0" in R
    assert "max(0.0,min(100.0" in R
def test_tank_visual_and_label_share_derived_level():
    assert "tank_visual_fill=tank_stats.level or 0" in T
    assert "tank_visual_main='%.1f'|format(tank_stats.level or 0) ~ '%'" in T
def test_litres_and_available_are_preserved():
    assert "'volume':vol" in R and "'available':max(0,cap-float(vol or 0))" in R
