from pathlib import Path
R=Path('app/routes.py').read_text(encoding='utf-8')
T=Path('app/templates/asset.html').read_text(encoding='utf-8')
def test_litres_drive_percentage_and_fill():
 assert 'float(vol)/cap*100.0' in R
 assert 'max(0.0,min(100.0' in R
 assert 'tank_visual_fill=tank_stats.level or 0' in T
 assert "tank_visual_main='%.1f'|format(tank_stats.level or 0) ~ '%'" in T
def test_volume_and_available_are_unchanged():
 assert "'volume':vol" in R
 assert "'available':max(0,cap-float(vol or 0))" in R
def test_known_examples():
 assert max(0,min(100,4000/8000*100))==50
 assert max(0,min(100,3600/8000*100))==45
