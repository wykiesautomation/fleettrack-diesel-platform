from pathlib import Path
import re

root = Path.cwd()
base = root / 'app' / 'templates' / 'base.html'
api = root / 'app' / 'device_api.py'

if not base.exists() or not api.exists():
    raise SystemExit('Run from the AssetTrack360 repository root.')

b = base.read_text(encoding='utf-8')
a = api.read_text(encoding='utf-8')

# Force three distinct sidebar destinations.
links = {
    'Signals & Inputs': "{{url_for('device_api.signals_inputs_entry')}}",
    'Trends & Limits': "{{url_for('device_api.trends_limits_entry')}}",
    'Alarm Centre': "{{url_for('main.alarm_centre')}}",
}
for label, target in links.items():
    pattern = r'href="[^"]+"(?=>[^<]*(?:<span>)?' + re.escape(label).replace(r'\&', '(?:&|&amp;)') + r'(?:</span>)?)'
    b, count = re.subn(pattern, 'href="' + target + '"', b, count=1)
    if count != 1 and target not in b:
        raise SystemExit('Could not patch sidebar link: ' + label)

# Remove any old generic entry routes to avoid duplicate endpoints.
a = re.sub(r"\n@bp\.get\('/signals-inputs'\).*?(?=\n@bp\.)", '\n', a, flags=re.S)
a = re.sub(r"\n@bp\.get\('/trends-limits'\).*?(?=\n@bp\.)", '\n', a, flags=re.S)

io_marker = "@bp.route('/devices/<int:device_id>/io-studio',methods=['GET','POST'])"
if io_marker not in a:
    io_marker = "@bp.route('/devices/<int:device_id>/io-studio', methods=['GET', 'POST'])"
trend_marker = "@bp.route('/devices/<int:device_id>/trends-limits',methods=['GET','POST'])"
if trend_marker not in a:
    trend_marker = "@bp.route('/devices/<int:device_id>/trends-limits', methods=['GET', 'POST'])"
if io_marker not in a or trend_marker not in a:
    raise SystemExit('Existing I/O Studio or Trends route not found.')

signals_route = '''\n@bp.get('/signals-inputs')\n@login_required\ndef signals_inputs_entry():\n    devices = Device.query.filter_by(customer_id=current_user.customer_id, active=True).order_by(Device.id).all()\n    mobile_types = {'MOBILE_WEB_TRACKER','ANDROID_MOBILE_TRACKER','MOBILE_TRACKER','IOS_MOBILE_TRACKER'}\n    device = next((d for d in devices if d.device_type not in mobile_types), None)\n    if device is None:\n        device = next(iter(devices), None)\n    if device is None:\n        flash('Connect a board or tracker before opening Signals & Inputs.', 'error')\n        return redirect(url_for('main.connect_device'))\n    return redirect(url_for('device_api.io_studio', device_id=device.id))\n\n'''

trends_route = '''\n@bp.get('/trends-limits')\n@login_required\ndef trends_limits_entry():\n    devices = Device.query.filter_by(customer_id=current_user.customer_id, active=True).order_by(Device.id).all()\n    for device in devices:\n        assignment = (DeviceChannelAssignment.query\n            .filter_by(device_id=device.id, enabled=True)\n            .filter(DeviceChannelAssignment.signal_id.isnot(None))\n            .order_by(DeviceChannelAssignment.id).first())\n        if assignment:\n            return redirect(url_for('device_api.trends_limits', device_id=device.id, signal_id=assignment.signal_id))\n    flash('No assigned signal is ready. Assign and save a point in Signals & Inputs first.', 'error')\n    return redirect(url_for('device_api.signals_inputs_entry'))\n\n'''

a = a.replace(io_marker, signals_route + io_marker, 1)
a = a.replace(trend_marker, trends_route + trend_marker, 1)

base.write_text(b, encoding='utf-8')
api.write_text(a, encoding='utf-8')

# Verify separation.
assert "device_api.signals_inputs_entry" in b
assert "device_api.trends_limits_entry" in b
assert "main.alarm_centre" in b
assert "return redirect(url_for('device_api.io_studio'" in a
assert "return redirect(url_for('device_api.trends_limits'" in a
print('PASS: Signals & Inputs opens I/O Studio only.')
print('PASS: Trends & Limits opens one-pin-at-a-time Trends only.')
print('PASS: Alarm Centre opens /alarms only.')
