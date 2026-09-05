from pathlib import Path

def test_required_files():
 root=Path(__file__).parents[1]
 for name in ['integration_worker.py','app/integration_runtime.py','edge_gateway/edge_gateway.py','app/templates/universal_connector.html']:
  assert (root/name).exists()
