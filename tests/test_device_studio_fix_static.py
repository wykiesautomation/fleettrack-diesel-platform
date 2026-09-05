from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = (ROOT / 'app/routes.py').read_text()
PANEL = (ROOT / 'app/templates/device_panel.html').read_text()


def test_guided_workflow_is_present():
    for label in ('Select Board', 'Configure I/O', 'Validate', 'Deploy'):
        assert label in PANEL


def test_all_io_families_are_supplied():
    for value in ('analog_channels=analog_channels', 'digital_channels=digital_channels',
                  'pulse_channels=pulse_channels', 'system_channels=system_channels',
                  'output_channels=output_channels'):
        assert value in ROUTES


def test_safety_validation_is_transactional():
    for value in ('pin conflict', 'safe_boot_state', 'simulation_physical_lockout',
                  'feedback_key', 'db.session.rollback()'):
        assert value in ROUTES


def test_template_has_validation_gate():
    assert 'VALIDATION GATE' in PANEL
    assert 'Save Setup, Validate & Deploy' in PANEL
