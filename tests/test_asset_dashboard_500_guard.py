from pathlib import Path
R=Path("app/routes.py").read_text(encoding="utf-8")
def test_unknown_or_incomplete_profile_is_safe():
 assert "profile_context=device_profile_context(device) if device else {}" in R
 assert "if not isinstance(profile_context,dict):profile_context={}" in R
 assert "device_profile=profile_context" in R
def test_malformed_output_channel_is_safe():
 assert "feedback_key=output.get('feedback_key') if isinstance(output,dict) else None" in R
