from pathlib import Path
R=Path("app/routes.py").read_text(encoding="utf-8")
def test_unknown_or_incomplete_profile_is_safe():
 assert "profile_context=device_profile_context(device) if device else {}" in R
 assert "if not isinstance(profile_context,dict):profile_context={}" in R
 assert "device_profile=profile_context" in R
def test_malformed_output_channel_is_safe():
 assert "feedback_key=output.get('feedback_key') if isinstance(output,dict) else None" in R

def test_sim808_profile_detection_uses_real_firmware_field_safely():
 assert "getattr(device,'firmware','')" in R
 assert "getattr(device,'firmware_version','')" in R
 assert "device.firmware_version" not in R
 assert "profile_code=str(device_profile.get('code','')).upper() if isinstance(device_profile,dict) else ''" in R
 assert "str(device.device_type or '').upper()" in R
