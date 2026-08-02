import secrets, re
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import desc
from . import db
from .models import Customer,User,Site,Asset,Device,SignalDefinition,Reading,Alarm,Location
bp=Blueprint('main',__name__)

def utcnow(): return datetime.now(timezone.utc)
def tenant_id(): return current_user.customer_id
def slugify(v): return re.sub(r'[^a-z0-9]+','-',v.lower()).strip('-')[:70]
def parse_time(v):
    if not v:return utcnow()
    try:return datetime.fromisoformat(v.replace('Z','+00:00'))
    except:return utcnow()
def aware(value):
    if not value: return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
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

@bp.get('/health')
def health(): return {'status':'ok','service':'assettrack360-rev15b'}

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
    assets = Asset.query.filter_by(customer_id=tenant_id()).order_by(Asset.name).all()
    sites = Site.query.filter_by(customer_id=tenant_id()).order_by(Site.name).all()
    devices = Device.query.filter_by(customer_id=tenant_id(), active=True).all()
    generated_at = utcnow()

    counts = {'HEALTHY': 0, 'WARNING': 0, 'CRITICAL': 0, 'OFFLINE': 0}
    asset_cards = []
    attention_items = []
    mapped_assets = []
    tank_capacity = 0.0
    tank_volume = 0.0
    tank_count = 0
    low_tanks = 0

    for asset in assets:
        status = asset_status(asset)
        asset.status = status
        counts[status] = counts.get(status, 0) + 1
        device = Device.query.filter_by(customer_id=tenant_id(), asset_id=asset.id, active=True).first()
        signal_map = {signal.key: latest_reading(signal.id) for signal in SignalDefinition.query.filter_by(asset_id=asset.id, enabled=True).all()}

        metric_1_label, metric_1_value = 'STATUS', status
        metric_2_label, metric_2_value = 'LAST CONTACT', 'No data'

        if asset.asset_type == 'TANK':
            level = signal_map.get('level_percent')
            volume = signal_map.get('volume_l')
            metric_1_label = 'LEVEL'
            metric_1_value = f'{level.value:.1f}%' if level else 'Waiting'
            metric_2_label = 'VOLUME'
            metric_2_value = f'{volume.value:,.0f} {asset.capacity_unit or "L"}' if volume else 'Waiting'
            tank_count += 1
            tank_capacity += float(asset.capacity or 0)
            tank_volume += float(volume.value if volume else 0)
            if level and level.value <= 20: low_tanks += 1
        elif asset.asset_type == 'TRACKER':
            location = Location.query.filter_by(customer_id=tenant_id(), asset_id=asset.id).order_by(desc(Location.sampled_at)).first()
            metric_1_label = 'MOVEMENT'
            metric_1_value = f'{location.speed_kmh or 0:.0f} km/h' if location else 'No position'
            metric_2_label = 'POSITION'
            metric_2_value = f'{location.latitude:.4f}, {location.longitude:.4f}' if location else 'Waiting'
        elif asset.asset_type == 'VIBRATION':
            vibration = signal_map.get('vibration_rms')
            temperature = signal_map.get('temperature_c')
            metric_1_label = 'VIBRATION'
            metric_1_value = f'{vibration.value:.2f} mm/s' if vibration else 'Waiting'
            metric_2_label = 'TEMPERATURE'
            metric_2_value = f'{temperature.value:.1f} °C' if temperature else 'Waiting'
        else:
            first_signal = next((reading for reading in signal_map.values() if reading), None)
            metric_1_label = 'LATEST VALUE'
            metric_1_value = f'{first_signal.value:.2f} {first_signal.unit or ""}' if first_signal else 'Waiting'
            metric_2_label = 'INPUTS'
            metric_2_value = str(len(signal_map))

        last_seen = 'No telemetry'
        if asset.last_seen:
            age = generated_at - aware(asset.last_seen)
            minutes = max(0, int(age.total_seconds() // 60))
            last_seen = 'Just now' if minutes < 1 else f'{minutes} min ago' if minutes < 60 else f'{minutes // 60} h ago'

        asset_cards.append({
            'asset': asset, 'status': status,
            'metric_1_label': metric_1_label, 'metric_1_value': metric_1_value,
            'metric_2_label': metric_2_label, 'metric_2_value': metric_2_value,
            'device_type': device.device_type if device else 'No device assigned',
            'last_seen': last_seen
        })

        if status in ('CRITICAL', 'WARNING', 'OFFLINE'):
            message = 'Communication timeout' if status == 'OFFLINE' else 'Active condition requires review'
            attention_items.append({'asset': asset, 'status': status, 'message': message})

        location = Location.query.filter_by(customer_id=tenant_id(), asset_id=asset.id).order_by(desc(Location.sampled_at)).first()
        if location:
            mapped_assets.append({'id': asset.id, 'name': asset.name, 'type': asset.asset_type, 'status': status, 'lat': location.latitude, 'lon': location.longitude})

    status_order = {'CRITICAL': 0, 'WARNING': 1, 'OFFLINE': 2, 'HEALTHY': 3}
    attention_items.sort(key=lambda item: status_order.get(item['status'], 9))

    alarms = Alarm.query.filter_by(customer_id=tenant_id()).order_by(desc(Alarm.opened_at)).limit(8).all()
    recent_events = []
    for alarm in alarms:
        event_asset = db.session.get(Asset, alarm.asset_id)
        recent_events.append({
            'title': alarm.message,
            'detail': f'{event_asset.name if event_asset else "Asset"} · {alarm.severity} · {alarm.state}',
            'time': aware(alarm.opened_at).strftime('%d %b %H:%M')
        })

    online_devices = sum(1 for device in devices if device.last_seen and generated_at - aware(device.last_seen) <= timedelta(minutes=30))
    connectivity = {
        'online': online_devices,
        'offline': max(0, len(devices) - online_devices),
        'online_percent': (online_devices / len(devices) * 100) if devices else 0,
        'firmware_reported': sum(1 for device in devices if device.firmware),
        'unassigned': sum(1 for asset in assets if not any(device.asset_id == asset.id for device in devices))
    }
    tank_summary = {
        'count': tank_count,
        'capacity': tank_capacity,
        'volume': tank_volume,
        'percent': (tank_volume / tank_capacity * 100) if tank_capacity else 0,
        'low_count': low_tanks
    }

    return render_template(
        'dashboard.html', assets=assets, sites=sites, site_count=len(sites),
        device_count=len(devices), counts=counts, asset_cards=asset_cards,
        attention_items=attention_items, mapped_assets=mapped_assets,
        tank_summary=tank_summary, connectivity=connectivity,
        recent_events=recent_events, generated_at=generated_at
    )

@bp.get('/asset/<int:asset_id>')
@login_required
def asset_view(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();asset.status=asset_status(asset)
    signals=SignalDefinition.query.filter_by(asset_id=asset.id,enabled=True).all(); cards=[]
    for sig in signals:
        latest=Reading.query.filter_by(signal_id=sig.id).order_by(desc(Reading.sampled_at)).first()
        history=Reading.query.filter_by(signal_id=sig.id).order_by(desc(Reading.sampled_at)).limit(30).all()[::-1]
        cards.append({'signal':sig,'latest':latest,'history':history})
    alarms=Alarm.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).order_by(desc(Alarm.opened_at)).limit(20).all()
    location=Location.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).order_by(desc(Location.sampled_at)).first()
    device=Device.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,active=True).first()
    return render_template('asset.html',asset=asset,cards=cards,alarms=alarms,location=location,device=device)

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
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();d=Device.query.filter_by(asset_id=asset.id,active=True).first()
    if request.method=='POST' and not d:
        d=Device(customer_id=tenant_id(),asset_id=asset.id,device_uid=request.form['device_uid'],device_type=request.form.get('device_type','UNIVERSAL'),api_token=secrets.token_urlsafe(32),capabilities=[]);db.session.add(d);db.session.commit();flash('Device registered. Copy the token now.','ok')
    return render_template('device.html',asset=asset,device=d)

@bp.post('/alarm/<int:alarm_id>/ack')
@login_required
def acknowledge_alarm(alarm_id):
    a=Alarm.query.filter_by(id=alarm_id,customer_id=tenant_id()).first_or_404();a.state='ACKNOWLEDGED';a.acknowledged_at=utcnow();a.acknowledged_by=current_user.id;a.note=request.form.get('note');db.session.commit();return redirect(request.referrer or url_for('main.dashboard'))

@bp.post('/api/v1/ingest')
def ingest():
    token=request.headers.get('Authorization','').removeprefix('Bearer ').strip();device=Device.query.filter_by(api_token=token,active=True).first()
    if not device:return jsonify(error='unauthorized'),401
    payload=request.get_json(silent=True) or {}
    if payload.get('device_id') and payload['device_id']!=device.device_uid:return jsonify(error='device_id mismatch'),403
    sampled=parse_time(payload.get('timestamp'));sequence=str(payload.get('sequence',''))
    accepted=[]; asset=device.asset
    for item in payload.get('measurements',[]):
        sig=SignalDefinition.query.filter_by(asset_id=asset.id,key=item.get('point'),enabled=True).first()
        if not sig:continue
        try: raw=float(item.get('value'));value=scale_signal(sig,raw)
        except:continue
        seq=f'{sequence}:{sig.key}' if sequence else f'{sampled.isoformat()}:{sig.key}'
        if Reading.query.filter_by(signal_id=sig.id,sequence=seq).first():continue
        db.session.add(Reading(customer_id=device.customer_id,asset_id=asset.id,signal_id=sig.id,sampled_at=sampled,value=value,raw_value=raw,unit=sig.unit,quality=item.get('quality','GOOD'),sequence=seq));evaluate_alarm(sig,value);accepted.append(sig.key)
    loc=payload.get('location') or {}
    if loc.get('latitude') is not None and loc.get('longitude') is not None:db.session.add(Location(customer_id=device.customer_id,asset_id=asset.id,sampled_at=sampled,latitude=float(loc['latitude']),longitude=float(loc['longitude']),speed_kmh=loc.get('speed_kmh'),accuracy_m=loc.get('accuracy_m'),heading=loc.get('heading'),sequence=sequence))
    device.last_seen=utcnow();asset.last_seen=utcnow();device.firmware=payload.get('firmware',device.firmware);db.session.commit();return jsonify(status='accepted',points=accepted),202

@bp.get('/api/v1/assets/<int:asset_id>/latest')
@login_required
def api_latest(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();out={}
    for s in SignalDefinition.query.filter_by(asset_id=asset.id,enabled=True):
        r=Reading.query.filter_by(signal_id=s.id).order_by(desc(Reading.sampled_at)).first();out[s.key]={'value':r.value,'unit':s.unit,'quality':r.quality,'sampled_at':r.sampled_at.isoformat()} if r else None
    return jsonify(asset={'id':asset.id,'name':asset.name,'type':asset.asset_type,'status':asset_status(asset)},signals=out)
