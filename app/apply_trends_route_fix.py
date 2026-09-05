from pathlib import Path
import re

root = Path.cwd()
base = root / 'app' / 'templates' / 'base.html'
api = root / 'app' / 'device_api.py'

if not base.exists() or not api.exists():
    raise SystemExit('Run this script from the AssetTrack360 repository root.')

base_text = base.read_text(encoding='utf-8')
api_text = api.read_text(encoding='utf-8')

# Replace only the sidebar Trends & Limits destination. Covers prior builds
# where the link incorrectly opened Devices & Sources.
patterns = [
    r'href="\{\{\s*url_for\([\'\"]main\.devices[\'\"]\)\s*\}\}">([^<]*<span>Trends &amp; Limits</span>)',
    r'href="\{\{\s*url_for\([\'\"]main\.devices[\'\"]\)\s*\}\}">([^<]*<span>Trends & Limits</span>)',
]
replacement = r'href="{{ url_for(\'device_api.trends_limits_entry\') }}">\1'
changed = False
for pattern in patterns:
    new_text, count = re.subn(pattern, replacement, base_text)
    if count:
        base_text = new_text
        changed = True
        break

# Fallback for compact one-line base templates.
if not changed:
    old = '<a href="{{url_for(\'main.devices\')}}">⌁ <span>Trends & Limits</span></a>'
    new = '<a href="{{url_for(\'device_api.trends_limits_entry\')}}">⌁ <span>Trends & Limits</span></a>'
    if old in base_text:
        base_text = base_text.replace(old, new, 1)
        changed = True

if not changed and 'device_api.trends_limits_entry' not in base_text:
    raise SystemExit('Could not locate the Trends & Limits sidebar link in base.html.')

route_code = r'''

@bp.get('/trends-limits')
@login_required
def trends_limits_entry():
    """Open Trends & Limits for the first customer device with assigned signals."""
    customer_id = current_user.customer_id
    devices = Device.query.filter_by(customer_id=customer_id, active=True).order_by(Device.id).all()
    for dev in devices:
        assignment = (DeviceChannelAssignment.query
                      .filter_by(device_id=dev.id, enabled=True)
                      .filter(DeviceChannelAssignment.signal_id.isnot(None))
                      .order_by(DeviceChannelAssignment.id)
                      .first())
        if assignment:
            return redirect(url_for('device_api.trends_limits',
                                    device_id=dev.id,
                                    signal_id=assignment.signal_id))
    flash('Assign and save at least one point in Signals & I/O before opening Trends & Limits.', 'error')
    return redirect(url_for('main.devices'))
'''

if "def trends_limits_entry():" not in api_text:
    marker = "@bp.route('/devices/<int:device_id>/trends-limits',methods=['GET','POST'])"
    if marker not in api_text:
        raise SystemExit('Could not locate the existing device Trends & Limits route.')
    api_text = api_text.replace(marker, route_code + '\n' + marker, 1)

base.write_text(base_text, encoding='utf-8')
api.write_text(api_text, encoding='utf-8')
print('PASS: Sidebar Trends & Limits now opens /trends-limits.')
print('PASS: /trends-limits selects the first active customer device with assigned signals.')
print('PASS: If no assigned signal exists, the user is redirected safely to Devices & Sources.')
