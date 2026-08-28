from pathlib import Path
import re
root=Path.cwd(); base=root/'app/templates/base.html'; api=root/'app/device_api.py'
if not base.exists() or not api.exists(): raise SystemExit('Run from AssetTrack360 repository root.')
s=base.read_text(encoding='utf-8'); a=api.read_text(encoding='utf-8')
# Robustly redirect the three Engineering links to real HMI entry routes.
pairs={
 'Signals & Inputs':"{{url_for('device_api.signals_inputs_entry')}}",
 'Trends & Limits':"{{url_for('device_api.trends_limits_entry')}}",
 'Alarm Centre':"{{url_for('main.alarms')}}",
}
for label,target in pairs.items():
    pattern=r'href="[^"]+"(?=>[^<]*(?:<span>)?'+re.escape(label).replace(r'\&','(?:&|&amp;)')+r'(?:</span>)?)'
    s,n=re.subn(pattern,'href="'+target+'"',s,count=1)
    if n!=1 and target not in s: raise SystemExit(f'Could not patch menu link: {label}')
route1='''\n@bp.get('/signals-inputs')\n@login_required\ndef signals_inputs_entry():\n    customer_id=current_user.customer_id\n    devices=Device.query.filter_by(customer_id=customer_id,active=True).order_by(Device.id).all()\n    mobile={'MOBILE_WEB_TRACKER','ANDROID_MOBILE_TRACKER','MOBILE_TRACKER','IOS_MOBILE_TRACKER'}\n    selected=next((d for d in devices if d.device_type not in mobile),None) or next(iter(devices),None)\n    if not selected:\n        flash('Connect a board or tracker before opening Signals & Inputs.','error')\n        return redirect(url_for('main.connect_device'))\n    return redirect(url_for('device_api.io_studio',device_id=selected.id))\n\n'''
route2='''\n@bp.get('/trends-limits')\n@login_required\ndef trends_limits_entry():\n    customer_id=current_user.customer_id\n    devices=Device.query.filter_by(customer_id=customer_id,active=True).order_by(Device.id).all()\n    for dev in devices:\n        row=(DeviceChannelAssignment.query.filter_by(device_id=dev.id,enabled=True)\n             .filter(DeviceChannelAssignment.signal_id.isnot(None)).order_by(DeviceChannelAssignment.id).first())\n        if row:\n            return redirect(url_for('device_api.trends_limits',device_id=dev.id,signal_id=row.signal_id))\n    flash('Assign and save at least one point in Signals & I/O before opening Trends & Limits.','error')\n    return redirect(url_for('device_api.signals_inputs_entry'))\n\n'''
marker="@bp.route('/devices/<int:device_id>/io-studio',methods=['GET','POST'])"
if marker not in a: marker="@bp.route('/devices/<int:device_id>/io-studio', methods=['GET', 'POST'])"
if marker not in a: raise SystemExit('Existing I/O Studio route not found.')
if 'def signals_inputs_entry():' not in a: a=a.replace(marker,route1+marker,1)
trend_marker="@bp.route('/devices/<int:device_id>/trends-limits',methods=['GET','POST'])"
if trend_marker not in a: trend_marker="@bp.route('/devices/<int:device_id>/trends-limits', methods=['GET', 'POST'])"
if trend_marker not in a: raise SystemExit('Existing Trends route not found.')
if 'def trends_limits_entry():' not in a: a=a.replace(trend_marker,route2+trend_marker,1)
base.write_text(s,encoding='utf-8'); api.write_text(a,encoding='utf-8')
print('PASS Signals & Inputs -> /signals-inputs -> I/O Studio')
print('PASS Trends & Limits -> /trends-limits -> assigned pin')
print('PASS Alarm Centre -> /alarms')
