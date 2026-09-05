from pathlib import Path
def test_rev20c_files():
 r=Path(__file__).parents[1]
 assert 'unchanged; skipped duplicate row' in (r/'client/edge_agent/service.py').read_text()
 assert 'dedup_key' in (r/'client/edge_agent/queue_store.py').read_text()
 assert 'mapping_total' in (r/'cloud/app/operations_fixes.py').read_text()
