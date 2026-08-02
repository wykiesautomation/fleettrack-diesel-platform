import secrets, re
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import desc
from . import db
from .payfast import config as payfast_config,build_checkout,event_hash,valid_signature,valid_source,server_validate,forwarded_ip
from .production import checks as production_checks, checkout_allowed
from .models import Customer,User,Site,Asset,Device,SignalDefinition,Reading,Alarm,Location,WorkspaceProfile,SubscriptionPlan,Subscription,PaymentRecord,PayFastEvent,SubscriptionAuditEvent,ProductionGateEvent
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

ALLOWED_BILLING_ENDPOINTS={'main.public_home','main.login','main.logout','main.register','main.health','main.billing','main.plans','main.select_plan','main.billing_checkout','main.billing_success','main.billing_cancel','main.payfast_notify','main.terms','main.privacy','main.payment_policy','main.readiness','main.production_status','static'}

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
def health(): return {'status':'ok','service':'assettrack360-rev18'}

@bp.get('/ready')
def readiness():
    report=production_checks(current_app)
    return jsonify(report),200 if report['ready'] else 503

@bp.get('/production-status')
@login_required
def production_status():
    if current_user.role!='platform_admin':abort(403)
    return render_template('production_status.html',report=production_checks(current_app))

@bp.get('/terms')
def terms(): return render_template('legal.html',doc='terms')
@bp.get('/privacy')
def privacy(): return render_template('legal.html',doc='privacy')
@bp.get('/payment-policy')
def payment_policy(): return render_template('legal.html',doc='payment')

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

LOGIN_ATTEMPTS={}

def login_rate_limited(ip):
    now=utcnow();entries=[t for t in LOGIN_ATTEMPTS.get(ip,[]) if (now-t).total_seconds()<900];LOGIN_ATTEMPTS[ip]=entries
    return len(entries)>=8

def record_login_failure(ip): LOGIN_ATTEMPTS.setdefault(ip,[]).append(utcnow())

@bp.route('/login',methods=['GET','POST'])
def login():
    ip=request.headers.get('CF-Connecting-IP') or request.remote_addr or 'unknown'
    if request.method=='POST':
        if login_rate_limited(ip): flash('Too many failed attempts. Try again in 15 minutes.','error');return render_template('auth.html',mode='login'),429
        u=User.query.filter_by(email=request.form.get('email','').strip().lower()).first()
        if u and u.active and check_password_hash(u.password_hash,request.form.get('password','')):login_user(u);return redirect(url_for('main.dashboard'))
        record_login_failure(ip);flash('Invalid login.','error')
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
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();d=Device.query.filter_by(asset_id=asset.id,active=True).first()
    if request.method=='POST' and not d:
        d=Device(customer_id=tenant_id(),asset_id=asset.id,device_uid=request.form['device_uid'],device_type=request.form.get('device_type','UNIVERSAL'),api_token=secrets.token_urlsafe(32),capabilities=[]);db.session.add(d);db.session.commit();flash('Device registered. Copy the token now.','ok')
    return render_template('device.html',asset=asset,device=d)

@bp.post('/alarm/<int:alarm_id>/ack')
@login_required
def acknowledge_alarm(alarm_id):
    a=Alarm.query.filter_by(id=alarm_id,customer_id=tenant_id()).first_or_404();a.state='ACKNOWLEDGED';a.acknowledged_at=utcnow();a.acknowledged_by=current_user.id;a.note=request.form.get('note');db.session.commit();return redirect(request.referrer or url_for('main.dashboard'))

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
    gate_ok,gate_report=checkout_allowed(current_app)
    if not gate_ok:
        flash('Production checkout is blocked because the final gate is incomplete.','error');return redirect(url_for('main.billing'))
    if not cfg['merchant_id'] or not cfg['merchant_key'] or not cfg['passphrase']:flash('PayFast is not configured.','error');return redirect(url_for('main.billing'))
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
    cfg=payfast_config();form=request.form;digest=event_hash(form)
    if PayFastEvent.query.filter_by(event_hash=digest).first():return 'OK',200
    ref=form.get('m_payment_id','');payment=PaymentRecord.query.filter_by(merchant_payment_id=ref).first();sig=valid_signature(form,cfg);source=valid_source(request,cfg);server=server_validate(form,cfg);amount=float(form.get('amount_gross') or 0);amount_ok=bool(payment and abs(amount-payment.amount_gross)<=.01);merchant=form.get('merchant_id')==cfg['merchant_id'];complete=form.get('payment_status')=='COMPLETE';accepted=all([payment,sig,source,server,amount_ok,merchant,complete])
    db.session.add(PayFastEvent(provider_reference=form.get('pf_payment_id'),merchant_payment_id=ref,event_hash=digest,source_ip=forwarded_ip(request),signature_valid=sig,source_valid=source,server_valid=server,amount_valid=amount_ok,accepted=accepted,reason='accepted' if accepted else 'validation_failed'))
    if payment:
        payment.provider_reference=form.get('pf_payment_id') or payment.provider_reference
        if accepted:
            payment.status='COMPLETE';payment.paid_at=utcnow();sub=Subscription.query.filter_by(id=payment.subscription_id).first();old=sub.state;sub.state='ACTIVE';sub.current_period_start=utcnow();sub.current_period_end=utcnow()+timedelta(days=30);sub.next_payment_at=sub.current_period_end;sub.grace_ends_at=None;sub.payfast_subscription_token=form.get('token') or sub.payfast_subscription_token;db.session.add(SubscriptionAuditEvent(customer_id=sub.customer_id,subscription_id=sub.id,previous_state=old,new_state='ACTIVE',reason='Validated PayFast COMPLETE ITN'))
        elif form.get('payment_status') in ('FAILED','CANCELLED'):
            payment.status=form.get('payment_status');sub=Subscription.query.filter_by(id=payment.subscription_id).first()
            if sub.state=='ACTIVE':sub.grace_ends_at=utcnow()+timedelta(days=3);set_subscription_state(sub,'GRACE_PERIOD','PayFast payment failed')
    db.session.commit();return ('OK',200) if accepted else ('INVALID',400)

@bp.post('/api/v1/ingest')
def ingest():
    token=request.headers.get('Authorization','').removeprefix('Bearer ').strip();device=Device.query.filter_by(api_token=token,active=True).first()
    if not device:return jsonify(error='unauthorized'),401
    allowed,subscription=entitlement_for(device.customer_id)
    if not allowed:return jsonify(error='subscription_inactive',state=subscription.state if subscription else 'MISSING',billing_url='/billing'),402
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
