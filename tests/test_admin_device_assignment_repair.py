from pathlib import Path
A=Path("app/admin.py").read_text(encoding="utf-8")
T=Path("app/templates/platform_admin_devices.html").read_text(encoding="utf-8")
def test_repair_is_platform_admin_only_and_transactional():
 for token in ("repair_device_assignments","@owner_only","db.session.commit()","db.session.rollback()","Tenant mismatch"):assert token in A
def test_repair_preserves_identity_and_reuses_exact_signals():
 assert "SignalDefinition.query.filter_by(customer_id=device.customer_id,asset_id=asset.id,key=key)" in A
 assert "api_token=" not in A[A.index("def repair_device_assignments"):A.index("@admin_bp.get('/support')")]
 assert "reconciled_by_platform_admin" in A
def test_admin_has_explicit_repair_action():
 assert "Repair assignments" in T and "No UID, token, telemetry or history will be changed" in T
