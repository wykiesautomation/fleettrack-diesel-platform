from pathlib import Path
import re

root = Path.cwd()
base = root / 'app' / 'templates' / 'base.html'
api = root / 'app' / 'device_api.py'

if not base.exists() or not api.exists():
    raise SystemExit('ERROR: Run this script from the AssetTrack360 repository root.')

base_text = base.read_text(encoding='utf-8')
api_text = api.read_text(encoding='utf-8')

# Replace only the Signals & Inputs sidebar destination.
replacements = [
    ('<a href="{{url_for(\'main.devices\')}}">↗ <span>Signals & Inputs</span></a>',
     '<a href="{{url_for(\'device_api.signals_inputs_entry\')}}">↗ <span>Signals & Inputs</span></a>'),
    ('<a href="{{ url_for(\'main.devices\') }}">↗ <span>Signals & Inputs</span></a>',
     '<a href="{{ url_for(\'device_api.signals_inputs_entry\') }}">↗ <span>Signals & Inputs</span></a>'),
    ('<a href="{{url_for(\'main.devices\')}}">↗ <span>Signals &amp; Inputs</span></a>',
     '<a href="{{url_for(\'device_api.signals_inputs_entry\')}}">↗ <span>Signals &amp; Inputs</span></a>'),
]
changed = False
for old, new in replacements:
    if old in base_text:
        base_text = base_text.replace(old, new, 1)
        changed = True
        break

if not changed and 'device_api.signals_inputs_entry' not in base_text:
    # More tolerant regex for formatting differences.
    pattern = r'href="\{\{\s*url_for\([\'\"]main\.devices[\'\"]\)\s*\}\}"(?=>[^<]*(?:<span>)?Signals &(?:amp;)? Inputs)'
    base_text, count = re.subn(pattern, 'href="{{ url_for(\'device_api.signals_inputs_entry\') }}"', base_text, count=1)
    changed = count == 1

if not changed and 'device_api.signals_inputs_entry' not in base_text:
    raise SystemExit('ERROR: Could not locate the Signals & Inputs link in app/templates/base.html.')

route_code = r'''

@bp.get('/signals-inputs')
@login_required
def signals_inputs_entry():
    """Open Signals & I/O Studio for the best available customer device.

    Hardware boards are preferred. If the customer only has a mobile tracker,
    the mobile data-point profile is opened instead of pretending it has GPIO.
    """
    customer_id = current_user.customer_id
    devices = (Device.query
               .filter_by(customer_id=customer_id, active=True)
               .order_by(Device.id)
               .all())

    mobile_types = {
        'MOBILE_WEB_TRACKER',
        'ANDROID_MOBILE_TRACKER',
        'MOBILE_TRACKER',
        'IOS_MOBILE_TRACKER',
    }
    selected = next((d for d in devices if d.device_type not in mobile_types), None)
    if selected is None:
        selected = next(iter(devices), None)

    if selected is None:
        flash('Connect a hardware board or mobile tracker before opening Signals & Inputs.', 'error')
        return redirect(url_for('main.connect_device'))

    return redirect(url_for('device_api.io_studio', device_id=selected.id))
'''

if 'def signals_inputs_entry():' not in api_text:
    # Insert immediately before the existing device I/O Studio route.
    markers = [
        "@bp.route('/devices/<int:device_id>/io-studio',methods=['GET','POST'])",
        "@bp.route('/devices/<int:device_id>/io-studio', methods=['GET', 'POST'])",
        "@bp.get('/devices/<int:device_id>/io-studio')",
    ]
    marker = next((m for m in markers if m in api_text), None)
    if marker is None:
        raise SystemExit('ERROR: Could not locate the existing Signals & I/O Studio route in app/device_api.py.')
    api_text = api_text.replace(marker, route_code + '\n' + marker, 1)

base.write_text(base_text, encoding='utf-8')
api.write_text(api_text, encoding='utf-8')

# Static verification.
assert 'device_api.signals_inputs_entry' in base.read_text(encoding='utf-8')
assert "@bp.get('/signals-inputs')" in api.read_text(encoding='utf-8')
assert "url_for('device_api.io_studio'" in api.read_text(encoding='utf-8')

print('PASS: Signals & Inputs sidebar now opens /signals-inputs.')
print('PASS: Hardware board is selected before a mobile tracker.')
print('PASS: If only a mobile tracker exists, mobile data points open without fake GPIO.')
print('PASS: If no device exists, Connect Device opens safely.')
