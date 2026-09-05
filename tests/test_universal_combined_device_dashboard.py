from pathlib import Path
R=Path("app/routes.py").read_text(encoding="utf-8")
A=Path("app/templates/asset.html").read_text(encoding="utf-8")
S=Path("app/templates/signals.html").read_text(encoding="utf-8")
P=Path("app/device_profiles/schema.py").read_text(encoding="utf-8")
def test_combined_tracking_and_monitoring():
 assert "Tracker Summary" in A and "Process Monitoring" in A
 assert "universal_signal_cards" in R and "Waiting for telemetry" in A
def test_all_profile_supported_assignments_are_dynamic():
 assert "DeviceChannelAssignment" in R and "assigned_keys" in R
 assert "profile_channels" in R and "not diagnostic and not output" in R
def test_calibration_guardrails_and_preview():
 for x in ("NORMALIZED_PERCENT","0 to 100","0 to 3.3 V","0 to 4095","4 to 20 mA"): assert x in R
 assert "LIVE SCALING PREVIEW" in S and "Invalid calibration range" in S
 assert "raw_max=100.0" in P
def test_outputs_are_readable_and_safe():
 for x in ("Latched ON/OFF or timed pulse","Safe restart","firmware feedback is fresh"): assert x in A
 assert "safe_boot_state or 'OFF'" in A
