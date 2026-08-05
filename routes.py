import secrets, re
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import desc
from . import db
from .payfast import config as payfast_config,build_checkout,event_hash,valid_signature,valid_source,server_validate,forwarded_ip
from .models import Customer,User,Site,Asset,Device,SignalDefinition,Reading,Alarm,Location,WorkspaceProfile,SubscriptionPlan,Subscription,PaymentRecord,PayFastEvent,SubscriptionAuditEvent,IntegrationConnector,IntegrationSignalMapping,IntegrationEvent,ConnectorEndpointConfig,UniversalSourceMapping,WebhookReceipt,EdgeGateway,IntegrationJobEvent,MqttSubscription,MqttTopicMapping,MqttMessageEvent,DeviceConfiguration,DeviceCommand
bp=Blueprint('main',__name__)

def utcnow(): return datetime.now(timezone.utc)
def tenant_id(): return current_user.customer_id
def slugify(v): return re.sub(r'[^a-z0-9]+','-',v.lower()).strip('-')[:70]
def parse_time(v):
    if not v:return utcnow()
    try:return datetime.fromisoformat(v.replace('Z','+00:00'))
    except:return utcnow()
def aware(value):
    if not value:return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
def clean_imei(value):
    value=re.sub(r'\D','',str(value or ''));return value if len(value)==15 else ''
def device_for_tenant(device_id):return Device.query.filter_by(id=device_id,customer_id=tenant_id()).first_or_404()
def authenticated_device():
    token=request.headers.get('Authorization','').removeprefix('Bearer ').strip()
    return Device.query.filter_by(api_token=token,active=True).first() if token else None

def device_config(record):
    cfg=DeviceConfiguration.query.filter_by(device_id=record.id).first()
    if not cfg:
        cfg=DeviceConfiguration(customer_id=record.customer_id,device_id=record.id)
        db.session.add(cfg);db.session.flush()
    return cfg

def validate_device_identity(record,payload):
    reported_uid=str(payload.get('device_id','')).strip().upper()
    if not reported_uid or reported_uid!=record.device_uid:
        return jsonify(error='device_identity_mismatch'),403
    reported_imei=clean_imei(payload.get('imei'))
    if record.device_type in ('ESP32_SIM868','ESP32_LTE_CAT1') and not reported_imei:
        return jsonify(error='imei_required'),400
    if reported_imei:
        record.reported_imei=reported_imei;record.identity_checked_at=utcnow();record.last_ip=request.remote_addr
        if not record.expected_imei:
            record.imei_status='PENDING_APPROVAL';record.device_state='WAITING';db.session.commit()
            return jsonify(status='identity_pending',code='IMEI_APPROVAL_REQUIRED',reported_imei=reported_imei),409
        if not secrets.compare_digest(record.expected_imei,reported_imei):
            record.imei_status='MISMATCH';record.device_state='QUARANTINED';record.quarantine_reason='Reported IMEI does not match the approved modem';db.session.commit()
            return jsonify(error='imei_mismatch',device_state='QUARANTINED'),403
        record.imei_status='MATCHED';record.device_state='ONLINE';record.quarantine_reason=None
    if record.device_state in ('SUSPENDED','QUARANTINED','TOKEN_REVOKED','RETIRED'):
        db.session.commit();return jsonify(error='device_not_allowed',device_state=record.device_state),403
    return None

def store_device_sample(record,payload):
    sampled=parse_time(payload.get('timestamp'));sequence=str(payload.get('sequence','')).strip()
    if not sequence:return {'status':'rejected','error':'sequence_required','points':[]}
    accepted=[];asset=record.asset
    for item in payload.get('measurements',[]):
        sig=SignalDefinition.query.filter_by(asset_id=asset.id,key=item.get('point'),enabled=True).first()
        if not sig:continue
        try:raw=float(item.get('value'));value=scale_signal(sig,raw)
        except (TypeError,ValueError):continue
        seq=f'{sequence}:{sig.key}'
        if Reading.query.filter_by(signal_id=sig.id,sequence=seq).first():continue
        db.session.add(Reading(customer_id=record.customer_id,asset_id=asset.id,signal_id=sig.id,sampled_at=sampled,value=value,raw_value=raw,unit=sig.unit,quality=item.get('quality','GOOD'),sequence=seq));evaluate_alarm(sig,value);accepted.append(sig.key)
    loc=payload.get('location') or {}
    if loc.get('latitude') is not None and loc.get('longitude') is not None:
        loc_seq=f'{sequence}:location'
        if not Location.query.filter_by(asset_id=asset.id,sequence=loc_seq).first():
            try:
                lat=float(loc['latitude']);lon=float(loc['longitude']);speed=float(loc.get('speed_kmh') or 0)
                if -90<=lat<=90 and -180<=lon<=180 and 0<=speed<=250:
                    db.session.add(Location(customer_id=record.customer_id,asset_id=asset.id,sampled_at=sampled,latitude=lat,longitude=lon,speed_kmh=speed,accuracy_m=loc.get('accuracy_m'),heading=loc.get('heading'),sequence=loc_seq))
            except (TypeError,ValueError):pass
    record.last_seen=utcnow();asset.last_seen=utcnow();record.firmware=payload.get('firmware',record.firmware)
    if record.device_state=='WAITING':record.device_state='ONLINE'
    return {'status':'accepted','sequence':sequence,'points':accepted}
def latest_reading(signal_id):
    return Reading.query.filter_by(signal_id=signal_id).order_by(desc(Reading.sampled_at)).first()
def asset_status(asset):
    if not asset.last_seen or utcnow()-asset.last_seen.replace(tzinfo=asset.last_seen.tzinfo or timezone.utc)>timedelta(minutes=30): return 'OFFLINE'
    open_alarm=Alarm.query.filter_by(customer_id=asset.customer_id,asset_id=asset.id,state='OPEN').order_by(desc(Alarm.severity)).first()
    return open_alarm.severity if open_alarm else 'HEALTHY'
def scale_signal(sig,raw):
    if sig.source_type!='4-20mA': return raw
    span=sig.raw_max-sig.raw_min
    return sig.eng_min if span==0 else sig.eng_min+(raw-sig.raw_min)*(sig.eng_max-sig.eng_min)/span

def evaluate_alarm(sig,value):
    severity=None; msg=None
    if sig.critical_low is not None and value<=sig.critical_low: severity='CRITICAL';msg=f'{sig.label} critical low'
    elif sig.critical_high is not None and value>=sig.critical_high: severity='CRITICAL';msg=f'{sig.label} critical high'
    elif sig.warning_low is not None and value<=sig.warning_low: severity='WARNING';msg=f'{sig.label} warning low'
    elif sig.warning_high is not None and value>=sig.warning_high: severity='WARNING';msg=f'{sig.label} warning high'
    existing=Alarm.query.filter_by(customer_id=sig.customer_id,asset_id=sig.asset_id,signal_id=sig.id,state='OPEN').first()
    if severity and not existing: db.session.add(Alarm(customer_id=sig.customer_id,asset_id=sig.asset_id,signal_id=sig.id,severity=severity,message=msg,value=value))
    elif severity and existing: existing.severity=severity;existing.message=msg;existing.value=value
    elif existing: existing.state='CLOSED';existing.note=(existing.note or '')+' Auto-closed after return to normal.'

ALLOWED_BILLING_ENDPOINTS={'main.public_home','main.login','main.logout','main.register','main.health','main.billing','main.plans','main.select_plan','main.billing_checkout','main.billing_success','main.billing_cancel','main.payfast_notify','static'}

def set_subscription_state(sub,new_state,reason):
    if sub.state!=new_state:
        db.session.add(SubscriptionAuditEvent(customer_id=sub.customer_id,subscription_id=sub.id,previous_state=sub.state,new_state=new_state,reason=reason));sub.state=new_state;db.session.commit()

def refresh_subscription(sub):
    now=utcnow()
    if sub.state=='TRIAL' and sub.trial_ends_at and now>aware(sub.trial_ends_at):set_subscription_state(sub,'SUSPENDED','Trial expired without successful payment')
    elif sub.state=='ACTIVE' and sub.current_period_end and now>aware(sub.current_period_end):
        sub.grace_ends_at=now+timedelta(days=3);set_subscription_state(sub,'GRACE_PERIOD','Paid period ended; three-day grace period started')
    elif sub.state=='GRACE_PERIOD' and sub.grace_ends_at and now>aware(sub.grace_ends_at):set_subscription_state(sub,'SUSPENDED','Grace period expired')
    return sub

def entitlement_for(customer_id):
    sub=Subscription.query.filter_by(customer_id=customer_id).first()
    if not sub:return False,None
    refresh_subscription(sub);return sub.state in ('TRIAL','ACTIVE','GRACE_PERIOD'),sub

@bp.before_app_request
def enforce_subscription_access():
    if not current_user.is_authenticated:return None
    if request.endpoint in ALLOWED_BILLING_ENDPOINTS or request.endpoint is None:return None
    allowed,sub=entitlement_for(current_user.customer_id)
    if not allowed:return redirect(url_for('main.subscription_required'))

@bp.get('/health')
def health(): return {'status':'ok','service':'assettrack360-rev17'}

@bp.route('/register',methods=['GET','POST'])
def register():
    if current_user.is_authenticated:return redirect(url_for('main.dashboard'))
    if request.method=='POST':
        company=request.form.get('company','').strip(); name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        if len(company)<2 or len(name)<2 or '@' not in email or len(password)<10: flash('Complete all fields. Password must be at least 10 characters.','error')
        elif User.query.filter_by(email=email).first(): flash('Email already registered.','error')
        else:
            base=slugify(company) or 'customer'; slug=base; n=1
            while Customer.query.filter_by(slug=slug).first():n+=1;slug=f'{base}-{n}'
            c=Customer(name=company,slug=slug);db.session.add(c);db.session.flush();u=User(customer_id=c.id,email=email,name=name,role='customer_admin',password_hash=generate_password_hash(password));db.session.add(u);db.session.commit();login_user(u);return redirect(url_for('main.onboarding'))
    return render_template('auth.html',mode='register')

@bp.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        u=User.query.filter_by(email=request.form.get('email','').strip().lower()).first()
        if u and u.active and check_password_hash(u.password_hash,request.form.get('password','')):login_user(u);return redirect(url_for('main.dashboard'))
        flash('Invalid login.','error')
    return render_template('auth.html',mode='login')
@bp.get('/logout')
@login_required
def logout():logout_user();return redirect(url_for('main.login'))

@bp.route('/onboarding',methods=['GET','POST'])
@login_required
def onboarding():
    if request.method=='POST':
        site=Site(customer_id=tenant_id(),name=request.form['site_name'],location=request.form.get('location'));db.session.add(site);db.session.flush()
        asset=Asset(customer_id=tenant_id(),site_id=site.id,name=request.form['asset_name'],asset_type=request.form['asset_type'],capacity=request.form.get('capacity') or None);db.session.add(asset);db.session.flush()
        create_default_signals(asset);db.session.commit();return redirect(url_for('main.asset_view',asset_id=asset.id))
    return render_template('onboarding.html')

def create_default_signals(asset):
    profiles={
      'TANK':[('level_percent','Tank Level','LEVEL','%','tank',20,10,90,95),('volume_l','Volume','LEVEL','L','numeric',None,None,None,None),('battery_v','Battery','VOLTAGE','V','battery',3.6,3.4,None,None),('solar_v','Solar','VOLTAGE','V','solar',None,None,None,None)],
      'TRACKER':[('speed_kmh','Speed','SPEED','km/h','numeric',None,None,100,120),('battery_v','Battery','VOLTAGE','V','battery',3.6,3.4,None,None)],
      'VIBRATION':[('vibration_rms','Vibration RMS','VIBRATION','mm/s','vibration',None,None,4.5,7.1),('temperature_c','Temperature','TEMPERATURE','°C','temperature',None,None,70,85),('battery_v','Battery','VOLTAGE','V','battery',3.6,3.4,None,None)],
      'GENERIC':[('analog_1','Universal Input','CUSTOM','','numeric',None,None,None,None)]}
    for key,label,stype,unit,widget,wl,cl,wh,ch in profiles.get(asset.asset_type,profiles['GENERIC']):db.session.add(SignalDefinition(customer_id=asset.customer_id,asset_id=asset.id,key=key,label=label,signal_type=stype,unit=unit,widget=widget,warning_low=wl,critical_low=cl,warning_high=wh,critical_high=ch))

@bp.get('/')
def public_home():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    return render_template('public_home.html')
@bp.get('/dashboard')
@login_required
def dashboard():
    assets=Asset.query.filter_by(customer_id=tenant_id()).order_by(Asset.name).all()
    sites=Site.query.filter_by(customer_id=tenant_id()).order_by(Site.name).all()
    devices=Device.query.filter_by(customer_id=tenant_id(),active=True).all()
    now=utcnow(); counts={'HEALTHY':0,'WARNING':0,'CRITICAL':0,'OFFLINE':0}; cards=[]; attention=[]; mapped=[]
    tank_capacity=tank_volume=0.0; tank_count=low_count=0
    for asset in assets:
        status=asset_status(asset);asset.status=status;counts[status]=counts.get(status,0)+1
        device=Device.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,active=True).first()
        sigs={x.key:latest_reading(x.id) for x in SignalDefinition.query.filter_by(asset_id=asset.id,enabled=True)}
        l1,v1,l2,v2='STATUS',status,'LAST CONTACT','No data'
        if asset.asset_type=='TANK':
            level=sigs.get('level_percent');volume=sigs.get('volume_l');l1='LEVEL';v1=f'{level.value:.1f}%' if level else 'Waiting';l2='VOLUME';v2=f'{volume.value:,.0f} {asset.capacity_unit or "L"}' if volume else 'Waiting';tank_count+=1;tank_capacity+=float(asset.capacity or 0);tank_volume+=float(volume.value if volume else 0);low_count+=1 if level and level.value<=20 else 0
        elif asset.asset_type=='TRACKER':
            loc=Location.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).order_by(desc(Location.sampled_at)).first();l1='MOVEMENT';v1=f'{loc.speed_kmh or 0:.0f} km/h' if loc else 'No position';l2='POSITION';v2=f'{loc.latitude:.4f}, {loc.longitude:.4f}' if loc else 'Waiting'
        elif asset.asset_type=='VIBRATION':
            vib=sigs.get('vibration_rms');temp=sigs.get('temperature_c');l1lk=''
            l1='VIBRATION';v1=f'{vib.value:.2f} mm/s' if vib else 'Waiting';l2='TEMPERATURE';v2=f'{temp.value:.1f} °C' if temp else 'Waiting'
        else:
            first=next((r for r in sigs.values() if r),None);l1='LATEST VALUE';v1=f'{first.value:.2f} {first.unit or ""}' if first else 'Waiting';l2='INPUTS';v2=str(len(sigs))
        seen='No telemetry'
        if asset.last_seen:
            mins=max(0,int((now-aware(asset.last_seen)).total_seconds()//60));seen='Just now' if mins<1 else f'{mins} min ago' if mins<60 else f'{mins//60} h ago'
        cards.append({'asset':asset,'status':status,'metric_1_label':l1,'metric_1_value':v1,'metric_2_label':l2,'metric_2_value':v2,'device_type':device.device_type if device else 'No device assigned','last_seen':seen})
        if status in ('CRITICAL','WARNING','OFFLINE'):attention.append({'asset':asset,'status':status,'message':'Communication timeout' if status=='OFFLINE' else 'Active condition requires review'})
        loc=Location.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).order_by(desc(Location.sampled_at)).first()
        if loc:mapped.append({'id':asset.id,'name':asset.name,'type':asset.asset_type,'status':status,'lat':loc.latitude,'lon':loc.longitude})
    order={'CRITICAL':0,'WARNING':1,'OFFLINE':2};attention.sort(key=lambda x:order.get(x['status'],9))
    recent=[]
    for alarm in Alarm.query.filter_by(customer_id=tenant_id()).order_by(desc(Alarm.opened_at)).limit(8):
        a=db.session.get(Asset,alarm.asset_id);recent.append({'title':alarm.message,'detail':f'{a.name if a else "Asset"} · {alarm.severity} · {alarm.state}','time':aware(alarm.opened_at).strftime('%d %b %H:%M')})
    online=sum(1 for d in devices if d.last_seen and now-aware(d.last_seen)<=timedelta(minutes=30))
    connectivity={'online':online,'offline':max(0,len(devices)-online),'online_percent':online/len(devices)*100 if devices else 0,'firmware_reported':sum(1 for d in devices if d.firmware),'unassigned':sum(1 for a in assets if not any(d.asset_id==a.id for d in devices))}
    tank={'count':tank_count,'capacity':tank_capacity,'volume':tank_volume,'percent':tank_volume/tank_capacity*100 if tank_capacity else 0,'low_count':low_count}
    return render_template('dashboard.html',assets=assets,sites=sites,site_count=len(sites),device_count=len(devices),counts=counts,asset_cards=cards,attention_items=attention,mapped_assets=mapped,tank_summary=tank,connectivity=connectivity,recent_events=recent,generated_at=now)

@bp.get('/asset/<int:asset_id>')
@login_required
def asset_view(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();asset.status=asset_status(asset);now=utcnow()
    signals=SignalDefinition.query.filter_by(asset_id=asset.id,enabled=True).order_by(SignalDefinition.label).all();cards=[];lookup={};series=[]
    for signal in signals:
        latest=latest_reading(signal.id);history=Reading.query.filter_by(signal_id=signal.id).order_by(desc(Reading.sampled_at)).limit(48).all()[::-1];lookup[signal.key]=latest;cards.append({'signal':signal,'latest':latest,'history':history})
        if history:series.append({'key':signal.key,'label':signal.label,'unit':signal.unit or '','values':[{'time':aware(r.sampled_at).strftime('%H:%M'),'value':r.value} for r in history]})
    alarms=Alarm.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).order_by(desc(Alarm.opened_at)).limit(30).all();open_alarms=[a for a in alarms if a.state in ('OPEN','ACKNOWLEDGED')]
    device=Device.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,active=True).first();location=Location.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).order_by(desc(Location.sampled_at)).first();route=Location.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).order_by(desc(Location.sampled_at)).limit(200).all()[::-1]
    last='No telemetry received'
    if asset.last_seen:
        sec=max(0,int((now-aware(asset.last_seen)).total_seconds()));last='Just now' if sec<60 else f'{sec//60} min ago' if sec<3600 else f'{sec//3600} h ago' if sec<86400 else f'{sec//86400} d ago'
    ctx={'level':lookup.get('level_percent'),'volume':lookup.get('volume_l'),'battery':lookup.get('battery_v'),'solar':lookup.get('solar_v'),'speed':lookup.get('speed_kmh'),'vibration':lookup.get('vibration_rms'),'temperature':lookup.get('temperature_c')}
    tank=None
    if asset.asset_type=='TANK':
        lvl=ctx['level'].value if ctx['level'] else None;vol=ctx['volume'].value if ctx['volume'] else None;cap=float(asset.capacity or 0);state='CRITICAL' if lvl is not None and lvl<=10 else 'WARNING' if lvl is not None and lvl<=20 else 'HEALTHY' if lvl is not None else 'WAITING';tank={'level':lvl,'volume':vol,'capacity':cap,'available':max(0,cap-float(vol or 0)) if cap else None,'unit':asset.capacity_unit or 'L','state':state}
    track=None
    if asset.asset_type=='TRACKER' or location:track={'latitude':location.latitude if location else None,'longitude':location.longitude if location else None,'speed':location.speed_kmh if location else None,'accuracy':location.accuracy_m if location else None,'heading':location.heading if location else None,'last_fix':aware(location.sampled_at).strftime('%Y-%m-%d %H:%M UTC') if location else 'Waiting for GNSS','route_count':len(route)}
    vib=None
    if asset.asset_type=='VIBRATION':
        value=ctx['vibration'].value if ctx['vibration'] else None;vib={'rms':value,'temperature':ctx['temperature'].value if ctx['temperature'] else None,'condition':'CRITICAL' if value is not None and value>=7.1 else 'WARNING' if value is not None and value>=4.5 else 'HEALTHY' if value is not None else 'WAITING'}
    return render_template('asset.html',asset=asset,signal_cards=cards,signal_lookup=lookup,chart_series=series,alarms=alarms,open_alarms=open_alarms,device=device,location=location,route_points=route,last_contact=last,generated_at=now,context=ctx,tank_stats=tank,tracking_stats=track,vibration_stats=vib)

@bp.route('/asset/<int:asset_id>/signals',methods=['GET','POST'])
@login_required
def signals(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404()
    if request.method=='POST':
        key=slugify(request.form['key']).replace('-','_')
        s=SignalDefinition(customer_id=tenant_id(),asset_id=asset.id,key=key,label=request.form['label'],signal_type=request.form['signal_type'],source_type=request.form['source_type'],unit=request.form.get('unit',''),widget=request.form['widget'],raw_min=float(request.form.get('raw_min') or 4),raw_max=float(request.form.get('raw_max') or 20),eng_min=float(request.form.get('eng_min') or 0),eng_max=float(request.form.get('eng_max') or 100),warning_low=float(request.form['warning_low']) if request.form.get('warning_low') else None,warning_high=float(request.form['warning_high']) if request.form.get('warning_high') else None,critical_low=float(request.form['critical_low']) if request.form.get('critical_low') else None,critical_high=float(request.form['critical_high']) if request.form.get('critical_high') else None)
        db.session.add(s);db.session.commit();flash('Signal added.','ok')
    return render_template('signals.html',asset=asset,signals=SignalDefinition.query.filter_by(asset_id=asset.id).all())

@bp.route('/asset/<int:asset_id>/device',methods=['GET','POST'])
@login_required
def device(asset_id):
 asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();d=Device.query.filter_by(asset_id=asset.id,active=True).first();new_token=None
 if request.method=='POST' and not d:
  uid=request.form.get('device_uid','').strip().upper();expected=clean_imei(request.form.get('expected_imei'));mode=request.form.get('imei_binding_mode','FIRST_CONTACT')
  if len(uid)<5 or Device.query.filter_by(device_uid=uid).first():flash('Invalid or duplicate Device UID.','error');return redirect(url_for('main.device',asset_id=asset.id))
  if mode=='MANUAL' and not expected:flash('Enter a valid 15-digit IMEI.','error');return redirect(url_for('main.device',asset_id=asset.id))
  new_token=secrets.token_urlsafe(32);d=Device(customer_id=tenant_id(),asset_id=asset.id,device_uid=uid,device_type=request.form.get('device_type','UNIVERSAL'),api_token=new_token,capabilities=[],expected_imei=expected or None,imei_status='MATCHED' if expected else 'NOT_BOUND',device_state='WAITING');db.session.add(d);db.session.commit();flash('Device registered. Copy the token now.','ok')
 return render_template('device.html',asset=asset,device=d,new_token=new_token)
@bp.post('/devices/<int:device_id>/approve-imei')
@login_required
def approve_device_imei(device_id):
 d=device_for_tenant(device_id);imei=clean_imei(d.reported_imei)
 if not imei:flash('No valid reported IMEI.','error');return redirect(url_for('main.device',asset_id=d.asset_id))
 d.expected_imei=imei;d.imei_status='MATCHED';d.device_state='WAITING';d.imei_bound_at=utcnow();d.quarantine_reason=None;db.session.commit();return redirect(url_for('main.device',asset_id=d.asset_id))
@bp.post('/devices/<int:device_id>/reject-imei')
@login_required
def reject_device_imei(device_id):
 d=device_for_tenant(device_id);d.imei_status='MISMATCH';d.device_state='QUARANTINED';d.quarantine_reason='Reported IMEI rejected by administrator';db.session.commit();return redirect(url_for('main.device',asset_id=d.asset_id))
@bp.post('/devices/<int:device_id>/clear-imei')
@login_required
def clear_device_imei(device_id):
 d=device_for_tenant(device_id);d.expected_imei=None;d.reported_imei=None;d.imei_status='NOT_BOUND';d.device_state='WAITING';d.quarantine_reason=None;db.session.commit();return redirect(url_for('main.device',asset_id=d.asset_id))
@bp.post('/alarm/<int:alarm_id>/ack')
@login_required
def acknowledge_alarm(alarm_id):
    a=Alarm.query.filter_by(id=alarm_id,customer_id=tenant_id()).first_or_404();a.state='ACKNOWLEDGED';a.acknowledged_at=utcnow();a.acknowledged_by=current_user.id;a.note=request.form.get('note');db.session.commit();return redirect(request.referrer or url_for('main.dashboard'))

@bp.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    customer = Customer.query.filter_by(id=tenant_id()).first_or_404()
    profile = WorkspaceProfile.query.filter_by(customer_id=tenant_id()).first()
    if not profile:
        profile = WorkspaceProfile(
            customer_id=tenant_id(),
            contact_email=current_user.email,
            billing_email=current_user.email,
        )
        db.session.add(profile)
        db.session.commit()

    if request.method == 'POST':
        company_name = request.form.get('company_name', '').strip()
        user_name = request.form.get('user_name', '').strip()
        if len(company_name) < 2 or len(user_name) < 2:
            flash('Company and administrator names are required.', 'error')
            return redirect(url_for('main.account'))
        customer.name = company_name
        current_user.name = user_name
        profile.contact_email = request.form.get('contact_email', '').strip().lower()
        profile.contact_phone = request.form.get('contact_phone', '').strip()
        profile.billing_email = request.form.get('billing_email', '').strip().lower()
        profile.address = request.form.get('address', '').strip()
        db.session.commit()
        flash('Account settings updated.', 'ok')
        return redirect(url_for('main.account'))

    users = User.query.filter_by(customer_id=tenant_id()).order_by(User.name).all()
    subscription = Subscription.query.filter_by(customer_id=tenant_id()).first()
    return render_template(
        'account.html',
        customer=customer,
        profile=profile,
        users=users,
        subscription=subscription,
    )


@bp.get('/devices')
@login_required
def devices():
    records = Device.query.filter_by(customer_id=tenant_id()).order_by(Device.device_uid).all()
    now = utcnow()
    items = []
    for record in records:
        online = bool(
            record.active
            and record.last_seen
            and now - aware(record.last_seen) <= timedelta(minutes=30)
        )
        last_contact = 'Never'
        if record.last_seen:
            age_seconds = max(0, int((now - aware(record.last_seen)).total_seconds()))
            if age_seconds < 60:
                last_contact = 'Just now'
            elif age_seconds < 3600:
                last_contact = f'{age_seconds // 60} min ago'
            elif age_seconds < 86400:
                last_contact = f'{age_seconds // 3600} h ago'
            else:
                last_contact = f'{age_seconds // 86400} d ago'
        items.append({
            'device': record,
            'asset': record.asset,
            'online': online,
            'last_contact': last_contact,
        })
    new_token = session.pop('new_device_token', None)
    new_token_device = session.pop('new_device_uid', None)
    return render_template(
        'devices.html',
        items=items,
        new_token=new_token,
        new_token_device=new_token_device,
    )


@bp.post('/devices/<int:device_id>/rotate-token')
@login_required
def rotate_device_token(device_id):
    record = Device.query.filter_by(
        id=device_id,
        customer_id=tenant_id(),
    ).first_or_404()
    record.api_token = secrets.token_urlsafe(32)
    db.session.commit()
    session['new_device_token'] = record.api_token
    session['new_device_uid'] = record.device_uid
    flash('Device token rotated. Copy the new token now.', 'ok')
    return redirect(url_for('main.devices'))


@bp.post('/devices/<int:device_id>/toggle')
@login_required
def toggle_device(device_id):
    record = Device.query.filter_by(
        id=device_id,
        customer_id=tenant_id(),
    ).first_or_404()
    record.active = not record.active
    db.session.commit()
    flash(
        f'Device {"enabled" if record.active else "disabled"}.',
        'ok',
    )
    return redirect(url_for('main.devices'))


CONNECTOR_TYPES={
    'MQTT':{'label':'MQTT Broker','mode':'CLOUD_OR_EDGE','endpoint':'mqtts://broker.example:8883','implemented':'FOUNDATION'},
    'REST_API':{'label':'REST API','mode':'CLOUD_PULL','endpoint':'https://provider.example/api','implemented':'FOUNDATION'},
    'WEBHOOK':{'label':'Webhook','mode':'CLOUD_PUSH','endpoint':'Generated after save','implemented':'FOUNDATION'},
    'OPC_UA':{'label':'OPC UA','mode':'EDGE_OUTBOUND','endpoint':'opc.tcp://server:4840','implemented':'EDGE_REQUIRED'},
    'OPC_CLASSIC':{'label':'OPC Classic','mode':'EDGE_OUTBOUND','endpoint':'Local OPC DA server','implemented':'EDGE_REQUIRED'},
    'MODBUS_TCP':{'label':'Modbus TCP','mode':'EDGE_OUTBOUND','endpoint':'192.168.1.20:502','implemented':'EDGE_REQUIRED'},
    'MODBUS_RTU':{'label':'Modbus RTU','mode':'EDGE_OUTBOUND','endpoint':'COM3 / 9600 / 8N1','implemented':'EDGE_REQUIRED'},
    'SQL_ODBC':{'label':'SQL / ODBC','mode':'EDGE_OUTBOUND','endpoint':'Read-only DSN','implemented':'EDGE_REQUIRED'},
    'CSV_IMPORT':{'label':'CSV Import','mode':'EDGE_OR_UPLOAD','endpoint':'Folder or upload profile','implemented':'FOUNDATION'},
    'ASSETTRACK_API':{'label':'AssetTrack Device API','mode':'CLOUD_PUSH','endpoint':'/api/v1/ingest','implemented':'AVAILABLE'},
}


def connector_for_tenant(connector_id):
    return IntegrationConnector.query.filter_by(
        id=connector_id,
        customer_id=tenant_id(),
    ).first_or_404()


@bp.get('/integrations')
@login_required
def integrations():
    connectors=IntegrationConnector.query.filter_by(customer_id=tenant_id()).order_by(IntegrationConnector.name).all()
    totals={
        'all':len(connectors),
        'enabled':sum(1 for c in connectors if c.enabled),
        'healthy':sum(1 for c in connectors if c.status=='CONNECTED'),
        'attention':sum(1 for c in connectors if c.status in ('ERROR','DEGRADED')),
        'mappings':IntegrationSignalMapping.query.filter_by(customer_id=tenant_id()).count(),
    }
    return render_template('integrations.html',connectors=connectors,totals=totals,connector_types=CONNECTOR_TYPES)


@bp.route('/integrations/new',methods=['GET','POST'])
@login_required
def integration_new():
    if request.method=='POST':
        connector_type=request.form.get('connector_type','').strip().upper()
        name=request.form.get('name','').strip()
        if connector_type not in CONNECTOR_TYPES or len(name)<2:
            flash('Select a valid connector type and enter a name.','error')
            return redirect(url_for('main.integration_new'))
        if IntegrationConnector.query.filter_by(customer_id=tenant_id(),name=name).first():
            flash('An integration with this name already exists.','error')
            return redirect(url_for('main.integration_new'))
        spec=CONNECTOR_TYPES[connector_type]
        connector=IntegrationConnector(
            customer_id=tenant_id(),name=name,connector_type=connector_type,
            transport_mode=spec['mode'],endpoint=request.form.get('endpoint','').strip(),
            edge_gateway_id=request.form.get('edge_gateway_id','').strip() or None,
            credential_ref=request.form.get('credential_ref','').strip() or None,
            read_only=True,enabled=False,status='DRAFT',
            poll_interval_seconds=max(5,int(request.form.get('poll_interval_seconds') or 60)),
            config_json={'implementation_state':spec['implemented']},
        )
        db.session.add(connector);db.session.flush()
        db.session.add(IntegrationEvent(customer_id=tenant_id(),connector_id=connector.id,event_type='CREATED',status='OK',detail=f'{connector_type} connector created in read-only mode'))
        db.session.commit();flash('Integration created. Configure mappings before enabling.','ok')
        return redirect(url_for('main.integration_detail',connector_id=connector.id))
    return render_template('integration_new.html',connector_types=CONNECTOR_TYPES)


@bp.get('/integrations/<int:connector_id>')
@login_required
def integration_detail(connector_id):
    connector=connector_for_tenant(connector_id)
    mappings=IntegrationSignalMapping.query.filter_by(customer_id=tenant_id(),connector_id=connector.id).order_by(IntegrationSignalMapping.source_point).all()
    events=IntegrationEvent.query.filter_by(customer_id=tenant_id(),connector_id=connector.id).order_by(desc(IntegrationEvent.created_at)).limit(20).all()
    assets=Asset.query.filter_by(customer_id=tenant_id()).order_by(Asset.name).all()
    return render_template('integration_detail.html',connector=connector,mappings=mappings,events=events,assets=assets,connector_spec=CONNECTOR_TYPES[connector.connector_type])


@bp.post('/integrations/<int:connector_id>/test')
@login_required
def integration_test(connector_id):
    connector=connector_for_tenant(connector_id);connector.last_tested_at=utcnow()
    failures=[]
    if connector.connector_type not in ('WEBHOOK','ASSETTRACK_API') and not connector.endpoint:failures.append('endpoint missing')
    if connector.connector_type in ('OPC_UA','OPC_CLASSIC','MODBUS_TCP','MODBUS_RTU','SQL_ODBC') and not connector.edge_gateway_id:failures.append('edge gateway not assigned')
    if connector.connector_type in ('MQTT','REST_API','SQL_ODBC') and not connector.credential_ref:failures.append('credential reference missing')
    if failures:
        connector.status='ERROR';connector.last_error='; '.join(failures);status='FAILED';detail=connector.last_error
        flash('Configuration test failed: '+detail,'error')
    else:
        connector.status='CONFIGURED';connector.last_error=None;status='OK';detail='Configuration is complete. Protocol execution is enabled in the connector-specific REV19 build.'
        flash('Configuration validation passed.','ok')
    db.session.add(IntegrationEvent(customer_id=tenant_id(),connector_id=connector.id,event_type='CONFIG_TEST',status=status,detail=detail));db.session.commit()
    return redirect(url_for('main.integration_detail',connector_id=connector.id))


@bp.post('/integrations/<int:connector_id>/toggle')
@login_required
def integration_toggle(connector_id):
    connector=connector_for_tenant(connector_id)
    if not connector.enabled and connector.status not in ('CONFIGURED','CONNECTED'):
        flash('Run and pass the configuration test before enabling.','error')
    else:
        connector.enabled=not connector.enabled
        db.session.add(IntegrationEvent(customer_id=tenant_id(),connector_id=connector.id,event_type='ENABLED' if connector.enabled else 'DISABLED',status='OK',detail='Connector state changed by customer administrator'))
        db.session.commit();flash(f'Integration {"enabled" if connector.enabled else "disabled"}.','ok')
    return redirect(url_for('main.integration_detail',connector_id=connector.id))


@bp.post('/integrations/<int:connector_id>/mappings')
@login_required
def integration_mapping_add(connector_id):
    connector=connector_for_tenant(connector_id)
    asset=Asset.query.filter_by(id=request.form.get('asset_id',type=int),customer_id=tenant_id()).first_or_404()
    signal=SignalDefinition.query.filter_by(id=request.form.get('signal_id',type=int),asset_id=asset.id,customer_id=tenant_id()).first_or_404()
    source_point=request.form.get('source_point','').strip()
    if not source_point:
        flash('Source point or tag is required.','error');return redirect(url_for('main.integration_detail',connector_id=connector.id))
    mapping=IntegrationSignalMapping(
        customer_id=tenant_id(),connector_id=connector.id,asset_id=asset.id,signal_id=signal.id,
        source_point=source_point,source_data_type=request.form.get('source_data_type','FLOAT'),
        source_unit=request.form.get('source_unit','').strip(),scale=float(request.form.get('scale') or 1),
        offset=float(request.form.get('offset') or 0),quality_mode=request.form.get('quality_mode','PASSTHROUGH'),enabled=True,
    )
    db.session.add(mapping);db.session.add(IntegrationEvent(customer_id=tenant_id(),connector_id=connector.id,event_type='MAPPING_ADDED',status='OK',detail=f'{source_point} mapped to {asset.name}.{signal.key}'))
    try:db.session.commit();flash('Signal mapping added.','ok')
    except Exception:db.session.rollback();flash('That source-to-signal mapping already exists.','error')
    return redirect(url_for('main.integration_detail',connector_id=connector.id))


@bp.post('/integrations/<int:connector_id>/mappings/<int:mapping_id>/toggle')
@login_required
def integration_mapping_toggle(connector_id,mapping_id):
    connector=connector_for_tenant(connector_id)
    mapping=IntegrationSignalMapping.query.filter_by(id=mapping_id,connector_id=connector.id,customer_id=tenant_id()).first_or_404()
    mapping.enabled=not mapping.enabled;db.session.commit();flash('Signal mapping updated.','ok')
    return redirect(url_for('main.integration_detail',connector_id=connector.id))


@bp.get('/api/v1/assets/<int:asset_id>/signals')
@login_required
def integration_asset_signals(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404()
    return jsonify(signals=[{'id':s.id,'key':s.key,'label':s.label,'unit':s.unit} for s in SignalDefinition.query.filter_by(asset_id=asset.id,enabled=True).order_by(SignalDefinition.label)])


@bp.route('/integrations/<int:connector_id>/universal',methods=['GET','POST'])
@login_required
def universal_connector(connector_id):
 connector=connector_for_tenant(connector_id);cfg=ConnectorEndpointConfig.query.filter_by(connector_id=connector.id).first()
 if not cfg:cfg=ConnectorEndpointConfig(customer_id=tenant_id(),connector_id=connector.id);db.session.add(cfg);db.session.commit()
 if request.method=='POST':
  connector.endpoint=request.form.get('endpoint','').strip();connector.poll_interval_seconds=max(10,int(request.form.get('poll_interval') or 60));cfg.auth_mode=request.form.get('auth_mode','NONE');cfg.secret_env_ref=request.form.get('secret_env_ref','').strip() or None;cfg.secondary_secret_env_ref=request.form.get('secondary_secret_env_ref','').strip() or None;cfg.timeout_seconds=max(5,int(request.form.get('timeout_seconds') or 20));cfg.retry_limit=max(0,min(10,int(request.form.get('retry_limit') or 3)));cfg.backoff_seconds=max(1,int(request.form.get('backoff_seconds') or 5));cfg.hmac_secret_env_ref=request.form.get('hmac_secret_env_ref','').strip() or None;cfg.source_ip_allowlist=request.form.get('source_ip_allowlist','').strip() or None;connector.status='CONFIGURED';db.session.commit();flash('Connector execution settings saved.','ok');return redirect(url_for('main.universal_connector',connector_id=connector.id))
 mappings=UniversalSourceMapping.query.filter_by(customer_id=tenant_id(),connector_id=connector.id).all();events=IntegrationJobEvent.query.filter_by(customer_id=tenant_id(),connector_id=connector.id).order_by(desc(IntegrationJobEvent.created_at)).limit(30).all();assets=Asset.query.filter_by(customer_id=tenant_id()).order_by(Asset.name).all()
 return render_template('universal_connector.html',connector=connector,cfg=cfg,mappings=mappings,events=events,assets=assets)
@bp.post('/integrations/<int:connector_id>/universal/mappings')
@login_required
def universal_mapping_add(connector_id):
 connector=connector_for_tenant(connector_id);asset=Asset.query.filter_by(id=request.form.get('asset_id',type=int),customer_id=tenant_id()).first_or_404();signal=SignalDefinition.query.filter_by(id=request.form.get('signal_id',type=int),asset_id=asset.id,customer_id=tenant_id()).first_or_404();db.session.add(UniversalSourceMapping(customer_id=tenant_id(),connector_id=connector.id,asset_id=asset.id,signal_id=signal.id,source_path=request.form.get('source_path','').strip(),timestamp_path=request.form.get('timestamp_path','').strip() or None,quality_path=request.form.get('quality_path','').strip() or None,data_type=request.form.get('data_type','FLOAT'),scale=float(request.form.get('scale') or 1),offset=float(request.form.get('offset') or 0),byte_order=request.form.get('byte_order','BIG'),word_order=request.form.get('word_order','BIG'),enabled=True));db.session.commit();flash('Universal mapping added.','ok');return redirect(url_for('main.universal_connector',connector_id=connector.id))
@bp.post('/api/v1/integrations/<int:connector_id>/webhook')
def integration_webhook(connector_id):
 import hashlib,hmac,os,time
 connector=IntegrationConnector.query.filter_by(id=connector_id,connector_type='WEBHOOK',enabled=True).first_or_404();cfg=ConnectorEndpointConfig.query.filter_by(connector_id=connector.id).first_or_404();raw=request.get_data(cache=True);key=request.headers.get(cfg.idempotency_header,'').strip()
 if not key:return jsonify(error='idempotency_key_required'),400
 existing=WebhookReceipt.query.filter_by(connector_id=connector.id,idempotency_key=key).first()
 if existing:return jsonify(status='duplicate'),200
 secret=os.getenv(cfg.hmac_secret_env_ref or '','');supplied=request.headers.get(cfg.hmac_header,'').removeprefix('sha256=').lower();expected=hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest() if secret else ''
 if not secret or not hmac.compare_digest(supplied,expected):return jsonify(error='invalid_signature'),401
 from .integration_runtime import map_payload
 payload=request.get_json(silent=True) or {};mapped=map_payload(connector,payload,'webhook');db.session.add(WebhookReceipt(customer_id=connector.customer_id,connector_id=connector.id,idempotency_key=key,body_hash=hashlib.sha256(raw).hexdigest(),status='ACCEPTED',mapped_points=mapped,source_ip=request.remote_addr,detail=f'{mapped} points mapped'));connector.last_success_at=utcnow();connector.status='CONNECTED';db.session.commit();return jsonify(status='accepted',mapped_points=mapped),202
@bp.post('/api/v1/edge/heartbeat')
def edge_heartbeat():
 token=request.headers.get('Authorization','').removeprefix('Bearer ').strip();g=EdgeGateway.query.filter_by(api_token=token,active=True).first()
 if not g:return jsonify(error='unauthorized'),401
 g.last_heartbeat_at=utcnow();g.last_ip=request.remote_addr;data=request.get_json(silent=True) or {};g.version=data.get('version',g.version);g.capabilities=data.get('capabilities',g.capabilities);db.session.commit();return jsonify(status='ok')
@bp.post('/api/v1/edge/ingest')
def edge_ingest():
 token=request.headers.get('Authorization','').removeprefix('Bearer ').strip();g=EdgeGateway.query.filter_by(api_token=token,active=True).first()
 if not g:return jsonify(error='unauthorized'),401
 data=request.get_json(silent=True) or {};connector=IntegrationConnector.query.filter_by(customer_id=g.customer_id,edge_gateway_id=data.get('connector_key')).first()
 if not connector:return jsonify(error='connector_not_found'),404
 from .integration_runtime import path_get
 mapped=0
 for point in data.get('points',[]):
  for m in UniversalSourceMapping.query.filter_by(connector_id=connector.id,source_path=point.get('source_path'),enabled=True).all():
   try:
    raw=float(point['value']);value=raw*m.scale+m.offset;db.session.add(Reading(customer_id=g.customer_id,asset_id=m.asset_id,signal_id=m.signal_id,sampled_at=utcnow(),value=value,raw_value=raw,unit=m.signal.unit,quality=point.get('quality','GOOD'),sequence=f'edge:{g.id}:{m.id}:{time.time_ns()}'));db.session.get(Asset,m.asset_id).last_seen=utcnow();m.last_value=value;m.last_success_at=utcnow();mapped+=1
   except Exception as exc:m.last_error=f'{type(exc).__name__}: edge mapping failed'
 connector.last_success_at=utcnow();connector.status='CONNECTED';g.last_heartbeat_at=utcnow();db.session.commit();return jsonify(status='accepted',mapped_points=mapped),202
@bp.route('/integrations/<int:connector_id>/mqtt',methods=['GET','POST'])
@login_required
def mqtt_connector(connector_id):
 c=connector_for_tenant(connector_id);cfg=dict(c.config_json or {})
 if c.connector_type!='MQTT':abort(404)
 if request.method=='POST':
  c.endpoint=request.form.get('endpoint','').strip();cfg.update({'client_id':request.form.get('client_id','').strip(),'username_env':request.form.get('username_env','').strip(),'password_env':request.form.get('password_env','').strip(),'ca_file_env':request.form.get('ca_file_env','').strip()});c.config_json=cfg;c.status='CONFIGURED';db.session.commit();return redirect(url_for('main.mqtt_connector',connector_id=c.id))
 return render_template('mqtt_connector.html',connector=c,cfg=cfg,subscriptions=MqttSubscription.query.filter_by(customer_id=tenant_id(),connector_id=c.id).all(),mappings=MqttTopicMapping.query.filter_by(customer_id=tenant_id(),connector_id=c.id).all(),events=MqttMessageEvent.query.filter_by(customer_id=tenant_id(),connector_id=c.id).order_by(desc(MqttMessageEvent.received_at)).limit(30).all(),assets=Asset.query.filter_by(customer_id=tenant_id()).all())
@bp.post('/integrations/<int:connector_id>/mqtt/subscriptions')
@login_required
def mqtt_subscription_add(connector_id):
 c=connector_for_tenant(connector_id);db.session.add(MqttSubscription(customer_id=tenant_id(),connector_id=c.id,topic_filter=request.form.get('topic_filter','').strip(),qos=request.form.get('qos',type=int) or 1));db.session.commit();return redirect(url_for('main.mqtt_connector',connector_id=c.id))
@bp.post('/integrations/<int:connector_id>/mqtt/subscriptions/<int:subscription_id>/toggle')
@login_required
def mqtt_subscription_toggle(connector_id,subscription_id):
 c=connector_for_tenant(connector_id);x=MqttSubscription.query.filter_by(id=subscription_id,connector_id=c.id,customer_id=tenant_id()).first_or_404();x.enabled=not x.enabled;db.session.commit();return redirect(url_for('main.mqtt_connector',connector_id=c.id))
@bp.post('/integrations/<int:connector_id>/mqtt/mappings')
@login_required
def mqtt_mapping_add(connector_id):
 c=connector_for_tenant(connector_id);a=Asset.query.filter_by(id=request.form.get('asset_id',type=int),customer_id=tenant_id()).first_or_404();sig=SignalDefinition.query.filter_by(id=request.form.get('signal_id',type=int),asset_id=a.id).first_or_404();db.session.add(MqttTopicMapping(customer_id=tenant_id(),connector_id=c.id,subscription_id=request.form.get('subscription_id',type=int),asset_id=a.id,signal_id=sig.id,json_path=request.form.get('json_path','value'),timestamp_path=request.form.get('timestamp_path') or None,quality_path=request.form.get('quality_path') or None,scale=float(request.form.get('scale') or 1),offset=float(request.form.get('offset') or 0)));db.session.commit();return redirect(url_for('main.mqtt_connector',connector_id=c.id))
@bp.post('/integrations/<int:connector_id>/mqtt/mappings/<int:mapping_id>/toggle')
@login_required
def mqtt_mapping_toggle(connector_id,mapping_id):
 c=connector_for_tenant(connector_id);x=MqttTopicMapping.query.filter_by(id=mapping_id,connector_id=c.id,customer_id=tenant_id()).first_or_404();x.enabled=not x.enabled;db.session.commit();return redirect(url_for('main.mqtt_connector',connector_id=c.id))
@bp.get('/subscription-required')
@login_required
def subscription_required():
    sub=Subscription.query.filter_by(customer_id=tenant_id()).first();return render_template('subscription_required.html',subscription=sub)

@bp.get('/plans')
@login_required
def plans():return render_template('plans.html',plans=SubscriptionPlan.query.filter_by(active=True).order_by(SubscriptionPlan.monthly_price).all(),subscription=Subscription.query.filter_by(customer_id=tenant_id()).first())

@bp.post('/plans/<int:plan_id>/select')
@login_required
def select_plan(plan_id):
    plan=SubscriptionPlan.query.filter_by(id=plan_id,active=True).first_or_404();sub=Subscription.query.filter_by(customer_id=tenant_id()).first_or_404();sub.plan_id=plan.id;db.session.commit();flash('Plan updated.','ok');return redirect(url_for('main.billing'))

@bp.get('/billing')
@login_required
def billing():
    sub=Subscription.query.filter_by(customer_id=tenant_id()).first_or_404();refresh_subscription(sub);payments=PaymentRecord.query.filter_by(customer_id=tenant_id()).order_by(desc(PaymentRecord.created_at)).limit(30).all();days=max(0,(aware(sub.trial_ends_at)-utcnow()).days) if sub.trial_ends_at and sub.state=='TRIAL' else None
    return render_template('billing.html',subscription=sub,payments=payments,active_devices=Device.query.filter_by(customer_id=tenant_id(),active=True).count(),days_left=days,payfast_mode=payfast_config()['mode'])

@bp.post('/billing/checkout')
@login_required
def billing_checkout():
    cfg=payfast_config();sub=Subscription.query.filter_by(customer_id=tenant_id()).first_or_404()
    if not cfg['merchant_id'] or not cfg['merchant_key']:flash('PayFast is not configured.','error');return redirect(url_for('main.billing'))
    if sub.plan.monthly_price<=0:flash('Industrial plan requires a quote.','error');return redirect(url_for('main.billing'))
    ref=f'AT360-{tenant_id()}-{sub.id}-{secrets.token_hex(6).upper()}';payment=PaymentRecord(customer_id=tenant_id(),subscription_id=sub.id,merchant_payment_id=ref,amount_gross=sub.plan.monthly_price,status='PENDING');db.session.add(payment);db.session.commit();endpoint,fields=build_checkout(sub,payment,current_user,cfg);return render_template('payfast_redirect.html',endpoint=endpoint,fields=fields,payment=payment)

@bp.get('/billing/success')
@login_required
def billing_success():return render_template('payment_result.html',result='success')
@bp.get('/billing/cancel')
@login_required
def billing_cancel():return render_template('payment_result.html',result='cancel')

@bp.post('/payfast/notify')
def payfast_notify():
    cfg = payfast_config()
    form = request.form
    digest = event_hash(form)
    existing = PayFastEvent.query.filter_by(event_hash=digest).first()
    if existing and existing.accepted:
        current_app.logger.info("PayFast ITN duplicate accepted event=%s", existing.id)
        return 'OK', 200
    if existing and not existing.accepted:
        # Allow a previously rejected event to be revalidated after a configuration fix.
        db.session.delete(existing)
        db.session.flush()

    reference = form.get('m_payment_id', '')
    payment = PaymentRecord.query.filter_by(merchant_payment_id=reference).first()
    signature_ok = valid_signature(form, cfg)
    source_ok = valid_source(request, cfg)
    server_ok = server_validate(form, cfg)
    try:
        amount = float(form.get('amount_gross') or 0)
    except (TypeError, ValueError):
        amount = 0.0
    amount_ok = bool(payment and abs(amount - payment.amount_gross) <= 0.01)
    merchant_ok = form.get('merchant_id') == cfg['merchant_id']
    complete_ok = form.get('payment_status') == 'COMPLETE'
    payment_ok = bool(payment)
    accepted = all([
        payment_ok, signature_ok, source_ok, server_ok,
        amount_ok, merchant_ok, complete_ok,
    ])
    failures = [
        name for name, ok in (
            ('payment', payment_ok),
            ('signature', signature_ok),
            ('source', source_ok),
            ('server', server_ok),
            ('amount', amount_ok),
            ('merchant', merchant_ok),
            ('status', complete_ok),
        ) if not ok
    ]
    reason = 'accepted' if accepted else 'failed:' + ','.join(failures)
    current_app.logger.warning(
        "PayFast ITN validation ref=%s accepted=%s payment=%s signature=%s source=%s server=%s amount=%s merchant=%s status=%s",
        reference, accepted, payment_ok, signature_ok, source_ok,
        server_ok, amount_ok, merchant_ok, complete_ok,
    )
    db.session.add(PayFastEvent(
        provider_reference=form.get('pf_payment_id'),
        merchant_payment_id=reference,
        event_hash=digest,
        source_ip=forwarded_ip(request),
        signature_valid=signature_ok,
        source_valid=source_ok,
        server_valid=server_ok,
        amount_valid=amount_ok,
        accepted=accepted,
        reason=reason,
        payload_summary={
            'payment_status': form.get('payment_status'),
            'amount_gross': form.get('amount_gross'),
            'mode': cfg['mode'],
        },
    ))
    if payment:
        payment.provider_reference = form.get('pf_payment_id') or payment.provider_reference
        if accepted:
            payment.status = 'COMPLETE'
            payment.paid_at = utcnow()
            sub = Subscription.query.filter_by(id=payment.subscription_id).first()
            old = sub.state
            sub.state = 'ACTIVE'
            sub.current_period_start = utcnow()
            sub.current_period_end = utcnow() + timedelta(days=30)
            sub.next_payment_at = sub.current_period_end
            sub.grace_ends_at = None
            sub.payfast_subscription_token = form.get('token') or sub.payfast_subscription_token
            db.session.add(SubscriptionAuditEvent(
                customer_id=sub.customer_id,
                subscription_id=sub.id,
                previous_state=old,
                new_state='ACTIVE',
                reason='Validated PayFast COMPLETE ITN',
            ))
        elif form.get('payment_status') in ('FAILED', 'CANCELLED'):
            payment.status = form.get('payment_status')
    db.session.commit()
    return ('OK', 200) if accepted else ('INVALID', 400)

@bp.post('/api/v1/ingest')
def ingest():
    device=authenticated_device()
    if not device:return jsonify(error='invalid_device_token'),401
    allowed,subscription=entitlement_for(device.customer_id)
    if not allowed:return jsonify(error='subscription_inactive',state=subscription.state if subscription else 'MISSING',billing_url='/billing'),402
    payload=request.get_json(silent=True) or {}
    identity_error=validate_device_identity(device,payload)
    if identity_error:return identity_error
    result=store_device_sample(device,payload)
    if result.get('status')=='rejected':return jsonify(result),400
    db.session.commit();return jsonify(**result,imei_verified=device.imei_status=='MATCHED'),202

@bp.post('/api/v1/ingest/batch')
def ingest_batch():
    device=authenticated_device()
    if not device:return jsonify(error='invalid_device_token'),401
    allowed,subscription=entitlement_for(device.customer_id)
    if not allowed:return jsonify(error='subscription_inactive',state=subscription.state if subscription else 'MISSING',billing_url='/billing'),402
    body=request.get_json(silent=True) or {};samples=body.get('samples') or []
    if not isinstance(samples,list) or not samples or len(samples)>100:return jsonify(error='invalid_batch',max_samples=100),400
    identity_payload={'device_id':body.get('device_id'),'imei':body.get('imei')}
    identity_error=validate_device_identity(device,identity_payload)
    if identity_error:return identity_error
    results=[]
    for sample in samples:
        sample=dict(sample or {});sample['device_id']=device.device_uid;sample['imei']=device.reported_imei
        results.append(store_device_sample(device,sample))
    db.session.commit()
    accepted=sum(1 for x in results if x.get('status')=='accepted')
    return jsonify(status='batch_processed',accepted=accepted,rejected=len(results)-accepted,results=results),202

@bp.get('/api/v1/device/config')
def get_device_configuration():
    device=authenticated_device()
    if not device:return jsonify(error='invalid_device_token'),401
    identity_error=validate_device_identity(device,request.args)
    if identity_error:return identity_error
    cfg=device_config(device)
    pending=DeviceCommand.query.filter_by(device_id=device.id,status='PENDING').order_by(DeviceCommand.id).limit(20).all()
    now=utcnow()
    for command in pending:command.status='DELIVERED';command.delivered_at=now
    db.session.commit()
    return jsonify(status='ok',configuration={
        'revision':cfg.revision,'tank_capacity_l':cfg.tank_capacity_l,'tank_height_mm':cfg.tank_height_mm,
        'tank_shape':cfg.tank_shape,'empty_ma':cfg.empty_ma,'full_ma':cfg.full_ma,
        'low_alarm_percent':cfg.low_alarm_percent,'critical_alarm_percent':cfg.critical_alarm_percent,
        'rapid_drop_percent':cfg.rapid_drop_percent,'moving_interval_seconds':cfg.moving_interval_seconds,
        'parked_interval_seconds':cfg.parked_interval_seconds,'calibration_points':cfg.calibration_points or []},
        commands=[{'id':x.id,'type':x.command_type,'payload':x.payload or {}} for x in pending])

@bp.post('/api/v1/device/config/ack')
def acknowledge_device_configuration():
    device=authenticated_device()
    if not device:return jsonify(error='invalid_device_token'),401
    data=request.get_json(silent=True) or {};identity_error=validate_device_identity(device,data)
    if identity_error:return identity_error
    cfg=device_config(device);revision=int(data.get('revision') or 0);status=str(data.get('status','')).upper()
    if status not in ('APPLIED','REJECTED') or revision<=0:return jsonify(error='invalid_acknowledgement'),400
    cfg.applied_revision=revision;cfg.apply_status=status;cfg.apply_detail=str(data.get('detail',''))[:240];cfg.acknowledged_at=utcnow()
    for item in data.get('commands') or []:
        command=DeviceCommand.query.filter_by(id=item.get('id'),device_id=device.id).first()
        if command:
            command.status=str(item.get('status','REJECTED')).upper();command.result_detail=str(item.get('detail',''))[:240];command.acknowledged_at=utcnow()
    db.session.commit();return jsonify(status='acknowledged',revision=revision,apply_status=status)

@bp.route('/devices/<int:device_id>/configuration',methods=['GET','POST'])
@login_required
def configure_device(device_id):
    device=device_for_tenant(device_id);cfg=device_config(device)
    if request.method=='POST':
        try:
            capacity=float(request.form.get('tank_capacity_l') or 0);height=float(request.form.get('tank_height_mm') or 0)
            empty_ma=float(request.form.get('empty_ma') or 4);full_ma=float(request.form.get('full_ma') or 20)
            low=float(request.form.get('low_alarm_percent') or 20);critical=float(request.form.get('critical_alarm_percent') or 10)
            if capacity<=0 or height<=0 or not 3.5<=empty_ma<full_ma<=21 or not 0<=critical<low<=100:raise ValueError
        except ValueError:
            flash('Invalid tank configuration or alarm limits.','error');return redirect(url_for('main.configure_device',device_id=device.id))
        cfg.tank_capacity_l=capacity;cfg.tank_height_mm=height;cfg.tank_shape=request.form.get('tank_shape','RECTANGULAR')
        cfg.empty_ma=empty_ma;cfg.full_ma=full_ma;cfg.low_alarm_percent=low;cfg.critical_alarm_percent=critical
        cfg.rapid_drop_percent=float(request.form.get('rapid_drop_percent') or 5)
        cfg.moving_interval_seconds=max(30,int(request.form.get('moving_interval_seconds') or 60))
        cfg.parked_interval_seconds=max(60,int(request.form.get('parked_interval_seconds') or 600))
        cfg.revision+=1;cfg.apply_status='PENDING';cfg.apply_detail=None
        db.session.add(DeviceCommand(customer_id=device.customer_id,device_id=device.id,command_type='APPLY_CONFIGURATION',payload={'revision':cfg.revision}))
        db.session.commit();flash('Configuration saved and queued for the device.','ok')
        return redirect(url_for('main.configure_device',device_id=device.id))
    return render_template('device_configuration.html',device=device,cfg=cfg)

@bp.get('/api/v1/assets/<int:asset_id>/tracking')
@login_required
def tracking_history(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404()
    start=parse_time(request.args.get('from')) if request.args.get('from') else utcnow()-timedelta(days=1)
    end=parse_time(request.args.get('to')) if request.args.get('to') else utcnow()
    limit=min(max(request.args.get('limit',type=int) or 2000,1),5000)
    rows=Location.query.filter(Location.asset_id==asset.id,Location.customer_id==tenant_id(),Location.sampled_at>=start,Location.sampled_at<=end).order_by(Location.sampled_at).limit(limit).all()
    points=[{'timestamp':aware(x.sampled_at).isoformat(),'latitude':x.latitude,'longitude':x.longitude,'speed_kmh':x.speed_kmh,'heading':x.heading,'accuracy_m':x.accuracy_m,'sequence':x.sequence} for x in rows]
    latest=points[-1] if points else None
    return jsonify(asset={'id':asset.id,'name':asset.name},from_time=start.isoformat(),to_time=end.isoformat(),count=len(points),last_known_position=latest,points=points)

@bp.get('/api/v1/assets/<int:asset_id>/latest')
@login_required
def api_latest(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();out={}
    for s in SignalDefinition.query.filter_by(asset_id=asset.id,enabled=True):
        r=Reading.query.filter_by(signal_id=s.id).order_by(desc(Reading.sampled_at)).first();out[s.key]={'value':r.value,'unit':s.unit,'quality':r.quality,'sampled_at':r.sampled_at.isoformat()} if r else None
    return jsonify(asset={'id':asset.id,'name':asset.name,'type':asset.asset_type,'status':asset_status(asset)},signals=out)
