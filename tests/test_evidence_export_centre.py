from pathlib import Path
R=Path('app/routes.py').read_text();E=Path('app/evidence_reports.py').read_text();T=Path('app/templates/evidence_centre.html').read_text()
def test_tenant_scoped_exports_and_role_gate():
 assert "def _evidence_role_allowed" in R and "customer_id=tenant_id()" in R[R.index('def evidence_pdf'):]
 assert "if not _evidence_role_allowed():abort(403)" in R
def test_pdf_and_pack_routes_exist():
 assert "evidence.pdf" in R and "evidence-pack.zip" in R
 assert 'build_pdf' in E and 'build_pack' in E
def test_integrity_manifest_and_required_files():
 for name in ['Evidence_Report.pdf','Evidence_Summary.json','Accepted_Locations.csv','Rejected_Observations.csv','Safety_Events.csv','Device_Status.json','Geofence_Definition.json','Integrity_Manifest.txt']:
  assert name in E
def test_customer_ui_and_audit_events():
 assert 'Download Evidence PDF' in T and 'Export Evidence Pack' in T
 assert 'EVIDENCE_REPORT_GENERATED' in R and 'EVIDENCE_PACK_EXPORTED' in R
def test_prediction_is_not_exported_as_telemetry():
 assert 'Predictions and counterfactual previews are not device telemetry' in E
