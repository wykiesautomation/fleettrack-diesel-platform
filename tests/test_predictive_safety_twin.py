from pathlib import Path
R=Path('app/routes.py').read_text();T=Path('app/templates/safety_twin.html').read_text()
def test_twin_route_and_tenant_scope():
 assert "@bp.get('/asset/<int:asset_id>/safety-twin')" in R
 assert "customer_id=tenant_id()" in R[R.index('def safety_twin'):]
def test_stationary_evidence_gate():
 block=R[R.index('def analyse_safety_twin_points'):R.index("@bp.get('/asset/<int:asset_id>/safety-twin')")]
 assert 'len(candidate)>=3' in block and 'elapsed>=20' in block
 assert 'envelope=max(25.0' in block
def test_prediction_never_persisted():
 assert 'Predictions are never persisted as telemetry' in R
 assert 'PREDICTION IS NOT TELEMETRY' in T
def test_twin_uses_real_values():
 for value in ['twin.distance_km','twin.movement_minutes','battery.value','zones|length']:
  assert value in T
