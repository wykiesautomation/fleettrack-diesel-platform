from pathlib import Path
R=Path("app/routes.py").read_text(encoding="utf-8")
T=Path("app/templates/asset.html").read_text(encoding="utf-8")
def test_latest_uses_firmware_feedback():
 assert "Latest: <b>{{primary_status.get('state','WAITING')}}" in T
 assert "output_statuses[output.get('channel')" in R
def test_local_arm_blocks_on_and_pulse_server_side():
 assert "action in ('OUTPUT_ON','OUTPUT_PULSE')" in R
 assert "Local Arm is not active" in R
 assert "arm_blocked" in T
def test_off_remains_safe_action():
 assert "OFF remains available as the safe action" in T
 assert "not status.get('fresh')" in T
def test_simulation_cannot_command_physical_output():
 assert "Simulation is active. Physical output commands are locked." in R
 assert "SIMULATION ACTIVE" in T
 assert "simulation_only=False" in R
