import hashlib,re,secrets
from datetime import datetime,timezone,timedelta
from flask import Blueprint,request,jsonify,render_template,redirect,url_for,flash
from flask_login import login_required,current_user
from . import db
from .models import Device,Asset,SignalDefinition,Reading,HardwareDeviceRegistration,DeviceChannelAssignment,DeviceCommand
from .device_profiles import get_profile,public_profiles,profile_for_device

bp=Blueprint('device_api',__name__)
MOBILE_STUDIO_TYPES={"MOBILE_WEB_TRACKER","ANDROID_MOBILE_TRACKER","MOBILE_TRACKER","IOS_MOBILE_TRACKER"}
def studio_profile(device):
    profile=profile_for_device(device)
    if profile:return profile
    if device and str(device.device_type or '').upper() in MOBILE_STUDIO_TYPES:
        return {'code':'AT360_MOBILE_TRACKER','display_name':'Mobile Tracker','transport':'MOBILE_DATA','channels':[
          {'key':'gps_location','label':'GPS Location','signal_type':'LOCATION','source_type':'MOBILE','unit':'','widget':'map','direction':'VIRTUAL','pin':None,'pin_notes':'Phone GNSS; no physical GPIO.'},
          {'key':'speed_kmh','label':'Vehicle Speed','signal_type':'SPEED','source_type':'MOBILE','unit':'km/h','widget':'numeric','direction':'VIRTUAL','pin':None,'pin_notes':'Calculated from accepted location samples.'},
          {'key':'heading','label':'Heading','signal_type':'HEADING','source_type':'MOBILE','unit':'deg','widget':'numeric','direction':'VIRTUAL','pin':None,'pin_notes':'Mobile GNSS heading.'},
          {'key':'battery_percent','label':'Phone Battery','signal_type':'BATTERY','source_type':'MOBILE','unit':'%','widget':'battery','direction':'VIRTUAL','pin':None,'pin_notes':'Reported by the registered phone.'},
          {'key':'sos_event','label':'SOS Event','signal_type':'STATE','source_type':'MOBILE','unit':'','widget':'state','direction':'VIRTUAL','pin':None,'pin_notes':'Mobile app event.'}]}
    return None
def now(): return datetime.now(timezone.utc)
def h(v): return hashlib.sha256(str(v).strip().upper().encode()).hexdigest()
def bearer(): return request.headers.get('Authorization','').removeprefix('Bearer ').strip()
def auth_device(): return Device.query.filter_by(api_token=bearer(),active=True).first() if bearer() else None

@bp.route('/device-studio/connect',methods=['GET','POST'])
@login_required
def connect():
    if request.method=='POST':
        profile=get_profile(request.form.get('profile_code'))
        if not profile: flash('Select a verified hardware profile.','error');return redirect(url_for('device_api.connect'))
        code=f'{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}'
        reg=HardwareDeviceRegistration(customer_id=current_user.customer_id,profile_code=profile['code'],code_hash=h(code),expires_at=now()+timedelta(minutes=10),created_by=current_user.id)
        db.session.add(reg);db.session.commit()
        return render_template('hardware_claim.html',registration=reg,profile=profile,code=code)
    return render_template('hardware_connect.html',profiles=public_profiles())

@bp.post('/api/v2/devices/claim')
def claim():
    d=request.get_json(silent=True) or {}; code=str(d.get('claim_code','')).upper().strip(); board=re.sub(r'[^A-Z0-9]','',str(d.get('board_id','')).upper())
    reg=HardwareDeviceRegistration.query.filter_by(code_hash=h(code),provisioning_state='WAITING').first()
    if not reg:return jsonify(error='invalid_claim_code'),404
    if now()>reg.expires_at.replace(tzinfo=reg.expires_at.tzinfo or timezone.utc):reg.provisioning_state='EXPIRED';db.session.commit();return jsonify(error='claim_code_expired'),410
    profile=get_profile(reg.profile_code)
    if not profile or str(d.get('profile_code','')).upper()!=profile['code']:return jsonify(error='profile_mismatch',expected=reg.profile_code),409
    if len(board)<6:return jsonify(error='invalid_board_id'),400
    uid='AT360-'+board; existing=Device.query.filter_by(device_uid=uid).first()
    if existing and existing.customer_id!=reg.customer_id:return jsonify(error='board_already_claimed'),409
    token=secrets.token_urlsafe(36)
    dev=existing or Device(customer_id=reg.customer_id,asset_id=None,device_uid=uid,device_type=profile['device_type'],api_token=token,capabilities=[])
    if not existing:db.session.add(dev)
    dev.active=True;dev.api_token=token;dev.firmware=str(d.get('firmware',''))[:40];dev.capabilities=list(dict.fromkeys(profile.get('capabilities',[])+['PROFILE:'+profile['code']]))
    db.session.flush();reg.claimed_device_id=dev.id;reg.claimed_board_id=uid;reg.claimed_at=now();reg.provisioning_state='CLAIMED'
    for ch in profile.get('channels',[]):
        if not DeviceChannelAssignment.query.filter_by(device_id=dev.id,channel_key=ch['key']).first():db.session.add(DeviceChannelAssignment(customer_id=dev.customer_id,device_id=dev.id,channel_key=ch['key'],direction=ch.get('direction','INPUT'),purpose='UNUSED',customer_label=ch['label'],enabled=False,config_json={'profile_code':profile['code'],'pin':ch.get('pin'),'pin_notes':ch.get('pin_notes')}))
    db.session.commit();return jsonify(status='claimed',device_uid=uid,device_token=token,profile_code=profile['code'],io_studio=f'/devices/{dev.id}/io-studio'),201

@bp.get('/api/v2/device/profile')
def device_profile():
    dev=auth_device()
    if not dev:return jsonify(error='unauthorized'),401
    p=profile_for_device(dev)
    return jsonify(device_uid=dev.device_uid,profile=p,firmware=dev.firmware),200


@bp.get('/signals-inputs')
@login_required
def signals_inputs_entry():
    customer_id=current_user.customer_id
    devices=Device.query.filter_by(customer_id=customer_id,active=True).order_by(Device.id).all()
    mobile={'MOBILE_WEB_TRACKER','ANDROID_MOBILE_TRACKER','MOBILE_TRACKER','IOS_MOBILE_TRACKER'}
    selected=next((d for d in devices if d.device_type not in mobile),None) or next(iter(devices),None)
    if not selected:
        # Keep Signals & Inputs on its own HMI. Do not redirect to Connect Device.
        assets=Asset.query.filter_by(customer_id=customer_id).order_by(Asset.name).all()
        return render_template('io_studio_empty.html',assets=assets,profiles=public_profiles())
    return redirect(url_for('device_api.io_studio',device_id=selected.id))

@bp.route('/devices/<int:device_id>/io-studio',methods=['GET','POST'])
@login_required
def io_studio(device_id):
    dev=Device.query.filter_by(id=device_id,customer_id=current_user.customer_id).first_or_404();profile=studio_profile(dev);all_devices=Device.query.filter_by(customer_id=current_user.customer_id).order_by(Device.device_uid).all();assets=Asset.query.filter_by(customer_id=current_user.customer_id).order_by(Asset.name).all();mobile_device=dev.device_type in {'MOBILE_WEB_TRACKER','ANDROID_MOBILE_TRACKER','MOBILE_TRACKER','IOS_MOBILE_TRACKER'};compatible_assets=[a for a in assets if (a.asset_type=='TRACKER' if mobile_device else True)]
    if not profile:flash('No verified board or mobile profile is available.','error');return redirect(url_for('main.devices'))
    for spec in profile.get('channels',[]):
        if not DeviceChannelAssignment.query.filter_by(device_id=dev.id,channel_key=spec['key']).first():db.session.add(DeviceChannelAssignment(customer_id=dev.customer_id,device_id=dev.id,channel_key=spec['key'],direction=spec.get('direction','VIRTUAL'),purpose='UNUSED',customer_label=spec['label'],enabled=False,config_json={'profile_code':profile['code'],'pin':spec.get('pin'),'pin_notes':spec.get('pin_notes')}))
    db.session.commit()
    if request.method=='POST':
        key=request.form.get('channel_key');spec=next((x for x in profile.get('channels',[]) if x.get('key')==key),None)
        if not spec:abort(400)
        if spec.get('direction') in ('INPUT','OUTPUT') and not spec.get('pin'):flash('Physical point is blocked because its verified pin is undefined.','error');return redirect(request.url)
        if spec.get('direction') not in ('INPUT','OUTPUT') and not mobile_device:flash('Internal health and location points are automatic and cannot be assigned as physical I/O.','error');return redirect(request.url)
        row=DeviceChannelAssignment.query.filter_by(device_id=dev.id,channel_key=key).first_or_404();purpose=request.form.get('purpose','UNUSED').upper();asset_id=request.form.get('asset_id',type=int);asset=Asset.query.filter_by(id=asset_id,customer_id=dev.customer_id).first() if asset_id else None
        if purpose!='UNUSED' and not asset:flash('Select an asset for an enabled point.','error');return redirect(request.url)
        label=(request.form.get('customer_label') or spec['label']).strip()[:100] or spec['label'];row.purpose=purpose;row.asset_id=asset.id if asset else None;row.enabled=purpose!='UNUSED';row.customer_label=label;row.config_json={'profile_code':profile['code'],'physical_pin':spec.get('pin'),'pin_notes':spec.get('pin_notes'),'purpose':purpose}
        if row.enabled:
            sig=SignalDefinition.query.filter_by(customer_id=dev.customer_id,asset_id=asset.id,key=key).first()
            if not sig:sig=SignalDefinition(customer_id=dev.customer_id,asset_id=asset.id,key=key,label=label,signal_type=spec['signal_type'],source_type=spec['source_type'],unit=spec.get('unit',''),widget=spec.get('widget','numeric'));db.session.add(sig);db.session.flush()
            sig.label=label;sig.enabled=True;cfg=dict(sig.config_json or {});cfg.update({'device_id':dev.id,'purpose':purpose,'physical_pin':spec.get('pin')});sig.config_json=cfg;row.signal_id=sig.id
        else:row.signal_id=None
        db.session.commit();flash(f'{label} saved.','ok');return redirect(request.url)
    rows={x.channel_key:x for x in DeviceChannelAssignment.query.filter_by(device_id=dev.id).all()};profile_channels=list(profile.get('channels',[]));physical=[x for x in profile_channels if x.get('direction') in ('INPUT','OUTPUT') and x.get('pin')];internal=[x for x in profile_channels if x.get('direction') in ('HEALTH','LOCATION')];reserved=list(profile.get('reserved_pins',[]));assigned=[x for x in rows.values() if x.enabled];online=bool(dev.last_seen and now()-dev.last_seen.replace(tzinfo=dev.last_seen.tzinfo or timezone.utc)<=timedelta(minutes=30));return render_template('io_studio.html',device=dev,profile=profile,assets=compatible_assets,all_devices=all_devices,assignments=rows,is_mobile=profile['code']=='AT360_MOBILE_TRACKER',physical_points=physical,internal_points=internal,reserved_points=reserved,assigned_points=assigned,device_online=online)


@bp.get('/trends-limits')
@login_required
def trends_limits_entry():
    customer_id=current_user.customer_id
    devices=Device.query.filter_by(customer_id=customer_id,active=True).order_by(Device.id).all()
    mobile={'MOBILE_WEB_TRACKER','ANDROID_MOBILE_TRACKER','MOBILE_TRACKER','IOS_MOBILE_TRACKER'}
    ordered=[d for d in devices if d.device_type not in mobile]+[d for d in devices if d.device_type in mobile]
    for dev in ordered:
        row=(DeviceChannelAssignment.query.filter_by(device_id=dev.id,enabled=True)
             .filter(DeviceChannelAssignment.signal_id.isnot(None)).order_by(DeviceChannelAssignment.id).first())
        if row:return redirect(url_for('device_api.trends_limits',device_id=dev.id,signal_id=row.signal_id))
    if ordered:
        flash('No assigned signal exists yet. Trends & Limits remains separate and is waiting for an assignment.','error')
        return redirect(url_for('device_api.trends_limits',device_id=ordered[0].id))
    return render_template('trends_limits_empty.html')

@bp.route('/devices/<int:device_id>/trends-limits',methods=['GET','POST'])
@login_required
def trends_limits(device_id):
    dev=Device.query.filter_by(id=device_id,customer_id=current_user.customer_id).first_or_404();assignments=DeviceChannelAssignment.query.filter_by(device_id=dev.id,enabled=True).filter(DeviceChannelAssignment.signal_id.isnot(None)).order_by(DeviceChannelAssignment.id).all()
    signals=[db.session.get(SignalDefinition,a.signal_id) for a in assignments];signals=[x for x in signals if x]
    requested=request.values.get('signal_id',type=int);index=next((i for i,x in enumerate(signals) if x.id==requested),0);signal=signals[index] if signals else None
    if request.method=='POST' and signal:
        def f(name,current):
            raw=request.form.get(name,'').strip()
            return float(raw) if raw else current
        mobile=dev.device_type in {'MOBILE_WEB_TRACKER','ANDROID_MOBILE_TRACKER','MOBILE_TRACKER','IOS_MOBILE_TRACKER'}
        signal.label=(request.form.get('label') or signal.label).strip()[:100]
        cfg=dict(signal.config_json or {})
        if mobile:
            signal.enabled=request.form.get('mobile_enabled','yes')=='yes'
            if request.form.get('unit') is not None:signal.unit=(request.form.get('unit') or signal.unit or '').strip()[:20]
            signal.warning_low=f('warning_low',signal.warning_low);signal.critical_low=f('critical_low',signal.critical_low);signal.warning_high=f('warning_high',signal.warning_high);signal.critical_high=f('critical_high',signal.critical_high)
            cfg.update({'sample_interval':request.form.get('sample_interval',cfg.get('sample_interval','5 seconds')),'upload_interval':request.form.get('upload_interval',cfg.get('upload_interval','15 seconds')),'retention':request.form.get('retention',cfg.get('retention','90 days')),'offline_queue':request.form.get('offline_queue','on')=='on','minimum_movement_m':max(0,min(500,float(request.form.get('minimum_movement_m') or cfg.get('minimum_movement_m',5)))),'gps_accuracy_limit_m':max(5,min(1000,float(request.form.get('gps_accuracy_limit_m') or cfg.get('gps_accuracy_limit_m',50)))),'stationary_threshold_kmh':max(0,min(20,float(request.form.get('stationary_threshold_kmh') or cfg.get('stationary_threshold_kmh',3)))),'max_plausible_speed_kmh':max(20,min(300,float(request.form.get('max_plausible_speed_kmh') or cfg.get('max_plausible_speed_kmh',300)))),'heading_threshold_deg':max(0,min(180,float(request.form.get('heading_threshold_deg') or cfg.get('heading_threshold_deg',5)))),'mobile_virtual_point':True})
        else:
            signal.unit=(request.form.get('unit') or signal.unit or '').strip()[:20];signal.raw_min=f('raw_min',signal.raw_min);signal.raw_max=f('raw_max',signal.raw_max);signal.eng_min=f('eng_min',signal.eng_min);signal.eng_max=f('eng_max',signal.eng_max);signal.warning_low=f('warning_low',signal.warning_low);signal.critical_low=f('critical_low',signal.critical_low);signal.warning_high=f('warning_high',signal.warning_high);signal.critical_high=f('critical_high',signal.critical_high);signal.deadband=max(0,f('deadband',signal.deadband));cfg.update({'sample_interval':request.form.get('sample_interval','5 seconds'),'upload_interval':request.form.get('upload_interval','1 minute'),'retention':request.form.get('retention','12 months'),'email_alarm':request.form.get('email_alarm')=='on','pulse_factor':request.form.get('pulse_factor'),'gear_ratio':request.form.get('gear_ratio'),'safe_startup_state':'OFF' if signal.signal_type=='OUTPUT' else cfg.get('safe_startup_state')})
        signal.config_json=cfg;db.session.commit();flash(f'{signal.label} saved.','ok')
        if request.form.get('next')=='1' and index<len(signals)-1:return redirect(url_for('device_api.trends_limits',device_id=dev.id,signal_id=signals[index+1].id))
        return redirect(url_for('device_api.trends_limits',device_id=dev.id,signal_id=signal.id))
    return render_template('trends_limits.html',device=dev,signals=signals,signal=signal,index=index)

@bp.post('/api/v2/telemetry')
def telemetry():
    dev=auth_device()
    if not dev:return jsonify(error='unauthorized'),401
    p=profile_for_device(dev);allowed={x['key'] for x in p.get('channels',[])};data=request.get_json(silent=True) or {};seq=str(data.get('sequence','')).strip()
    if not seq:return jsonify(error='sequence_required'),400
    stored=[];rejected=[]
    for item in data.get('measurements',[]):
        key=str(item.get('point','')).strip();assignment=DeviceChannelAssignment.query.filter_by(device_id=dev.id,channel_key=key,enabled=True).first()
        if key not in allowed or not assignment or not assignment.signal_id:rejected.append(key);continue
        try:value=float(item.get('value'))
        except (TypeError,ValueError):rejected.append(key);continue
        if not Reading.query.filter_by(signal_id=assignment.signal_id,sequence=f'{seq}:{key}').first():
            sig=db.session.get(SignalDefinition,assignment.signal_id);db.session.add(Reading(customer_id=dev.customer_id,asset_id=assignment.asset_id,signal_id=sig.id,sampled_at=now(),value=value,raw_value=value,unit=sig.unit,quality=str(item.get('quality','GOOD'))[:20],sequence=f'{seq}:{key}'));stored.append(key)
    dev.last_seen=now();dev.firmware=str(data.get('firmware',dev.firmware or ''))[:40];db.session.commit();return jsonify(status='accepted',stored=stored,rejected=rejected,sequence=seq),202

@bp.post('/api/v2/device/commands/<int:command_id>/ack')
def ack(command_id):
    dev=auth_device()
    if not dev:return jsonify(error='unauthorized'),401
    cmd=DeviceCommand.query.filter_by(id=command_id,device_id=dev.id).first_or_404();d=request.get_json(silent=True) or {}
    if d.get('request_token')!=cmd.request_token:return jsonify(error='token_mismatch'),403
    result=str(d.get('result','REJECTED')).upper();cmd.state=result if result in ('COMPLETED','REJECTED','FAILED') else 'REJECTED';cmd.feedback_value=1.0 if d.get('feedback') else 0.0;cmd.acknowledged_at=now();cmd.completed_at=now() if cmd.state=='COMPLETED' else None;cmd.failure_reason=str(d.get('reason',''))[:240] or None;db.session.commit();return jsonify(status='accepted'),202
