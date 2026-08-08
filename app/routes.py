import os, secrets, re, hashlib, io, json, time
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort, session, current_app, send_from_directory, send_file
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import desc
from . import db
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from .email_service import send_verification_email
from .payfast import config as payfast_config,build_checkout,event_hash,valid_signature,valid_source,server_validate,forwarded_ip
from .models import Customer,User,Site,Asset,Device,SignalDefinition,Reading,Alarm,Location,WorkspaceProfile,SubscriptionPlan,Subscription,PaymentRecord,PayFastEvent,SubscriptionAuditEvent,IntegrationConnector,IntegrationSignalMapping,IntegrationEvent,ConnectorEndpointConfig,UniversalSourceMapping,WebhookReceipt,EdgeGateway,IntegrationJobEvent,MqttSubscription,MqttTopicMapping,MqttMessageEvent,MobileTrackerRegistration,MobileConsent,SecurityAuditEvent,AssetAlertSettings,CoreAlarmState,DataDeletionRequest,FleetFeatureDefaults,AssetFeatureOverride,RegistrationAttempt
from .route_intelligence import match_route, reverse_geocode, route_quality
from .security_privacy import POLICY_VERSION,audit,consent_for_device,settings_for,evaluate_mobile,FEATURE_KEYS,MANDATORY_CONTROLS,fleet_defaults_for,entitlement_map,effective_features
from .seo import SEO_PAGES, render_seo_page
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
def route_distance_km(points):
    import math
    total=0.0;previous=None
    for point in points:
        if previous is not None:
            lat1,lon1,lat2,lon2=map(math.radians,(previous.latitude,previous.longitude,point.latitude,point.longitude))
            value=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
            segment=2*6371.0088*math.asin(math.sqrt(value));elapsed=max(1,(aware(point.sampled_at)-aware(previous.sampled_at)).total_seconds())
            plausible=max(0.25,elapsed/3600*220+0.1);accuracy=max(float(point.accuracy_m or 0),float(previous.accuracy_m or 0))/1000
            if segment<=plausible and not(segment<=accuracy and float(point.speed_kmh or 0)<3):total+=segment
        previous=point
    return round(total,1)
def vehicle_day_summary(asset,device,now):
    start=now.replace(hour=0,minute=0,second=0,microsecond=0)
    points=Location.query.filter(Location.customer_id==asset.customer_id,Location.asset_id==asset.id,Location.sampled_at>=start).order_by(Location.sampled_at).limit(2000).all()
    moving=stopped=0.0;stops=[];previous=None;stop_start=None;stop_point=None;maximum=0.0
    for point in points:
        speed=max(0.0,float(point.speed_kmh or 0));maximum=max(maximum,speed)
        if previous:
            seconds=max(0,(aware(point.sampled_at)-aware(previous.sampled_at)).total_seconds())
            if seconds<=1800:
                if speed>=3:moving+=seconds
                else:stopped+=seconds
        if speed<3:
            if stop_start is None:stop_start=aware(point.sampled_at);stop_point=point
        elif stop_start is not None:
            duration=(aware(point.sampled_at)-stop_start).total_seconds()
            if duration>=300:stops.append({'started':stop_start.strftime('%H:%M'),'ended':aware(point.sampled_at).strftime('%H:%M'),'minutes':round(duration/60),'latitude':stop_point.latitude,'longitude':stop_point.longitude})
            stop_start=None;stop_point=None
        previous=point
    if stop_start and points:
        duration=(aware(points[-1].sampled_at)-stop_start).total_seconds()
        if duration>=300:stops.append({'started':stop_start.strftime('%H:%M'),'ended':'Now','minutes':round(duration/60),'latitude':stop_point.latitude,'longitude':stop_point.longitude})
    timeline=[]
    if points:
        timeline.append({'time':aware(points[0].sampled_at).strftime('%H:%M'),'title':'First position received','detail':'Tracking started for today'})
        for stop in stops[-4:]:timeline.append({'time':stop['started'],'title':'Vehicle stopped','detail':f"{stop['minutes']} min stop"})
        timeline.append({'time':aware(points[-1].sampled_at).strftime('%H:%M'),'title':'Latest position received','detail':f"{float(points[-1].speed_kmh or 0):.0f} km/h"});timeline.sort(key=lambda x:x['time'])
    online=bool(device and device.active and device.last_seen and now-aware(device.last_seen)<=timedelta(minutes=5));speed=float(points[-1].speed_kmh or 0) if points else 0.0
    return {'online':online,'motion':'MOVING' if speed>=3 else 'PARKED','tracking':'ACTIVE' if online else 'INACTIVE','distance_km':route_distance_km(points),'moving_minutes':round(moving/60),'stopped_minutes':round(stopped/60),'stop_count':len(stops),'max_speed_kmh':round(maximum),'stops':stops[-6:][::-1],'timeline':timeline[-8:][::-1]}
def mobile_code_hash(value):
    return hashlib.sha256(str(value).strip().upper().encode('utf-8')).hexdigest()
def mobile_tracker_device():
    token=request.headers.get('Authorization','').removeprefix('Bearer ').strip()
    return Device.query.filter_by(api_token=token,active=True,device_type='MOBILE_WEB_TRACKER').first() if token else None
def latest_reading(signal_id):
    return Reading.query.filter_by(signal_id=signal_id).order_by(desc(Reading.sampled_at)).first()
def active_device_for(asset):
    return Device.query.filter_by(customer_id=asset.customer_id,asset_id=asset.id,active=True).first()

def asset_status(asset):
    device=active_device_for(asset)
    if not device:
        return 'UNASSIGNED'
    if not device.last_seen or utcnow()-aware(device.last_seen)>timedelta(minutes=30):
        return 'OFFLINE'
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

ALLOWED_BILLING_ENDPOINTS={'main.public_home','main.seo_public_page','main.login','main.logout','main.register','main.health','main.billing','main.plans','main.select_plan','main.billing_checkout','main.billing_success','main.billing_cancel','main.payfast_notify','main.subscription_required','static'}

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

@bp.get('/fleet-tracking-south-africa')
@bp.get('/mobile-phone-tracking')
@bp.get('/vehicle-gps-tracking')
@bp.get('/asset-monitoring')
@bp.get('/industrial-sensor-monitoring')
@bp.get('/fleet-tracking-api')
@bp.get('/security-privacy')
def seo_public_page():
    slug=request.path.strip('/')
    rendered=render_seo_page(slug)
    return rendered if rendered is not None else abort(404)

@bp.get("/health")
def health():
    return {"status": "ok", "service": "assettrack360-rev17"}

@bp.get("/mobile-tracker")
def mobile_tracker_page():
    return render_template("mobile_tracker.html")


@bp.get("/googleea2fb5a297eb0738.html")
def google_site_verification():
    return (
        "google-site-verification: googleea2fb5a297eb0738.html",
        200,
        {"Content-Type": "text/html; charset=utf-8"},
    )


@bp.get("/robots.txt")
def robots_txt():
    body=(
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /dashboard\nDisallow: /asset/\nDisallow: /devices\n"
        "Disallow: /account\nDisallow: /billing\nDisallow: /integrations\n"
        "Disallow: /edge-gateways\nDisallow: /api/\nDisallow: /onboarding\n"
        "Disallow: /admin/\nDisallow: /mobile-tracker\n\n"
        "Sitemap: https://fleettrack.wykiesautomation.co.za/sitemap.xml\n"
    )
    return body,200,{"Content-Type":"text/plain; charset=utf-8"}
@bp.get("/sitemap.xml")
def sitemap_xml():
    base_url="https://fleettrack.wykiesautomation.co.za"
    last_modified=utcnow().date().isoformat()
    pages=[("/","daily","1.0"),("/register","weekly","0.8"),("/plans","weekly","0.8")]
    pages.extend((page["path"],"weekly","0.9") for page in SEO_PAGES.values())
    entries=[]
    for path,change_frequency,priority in pages:
        entries.append("  <url>\n"+f"    <loc>{base_url}{path}</loc>\n"+f"    <lastmod>{last_modified}</lastmod>\n"+f"    <changefreq>{change_frequency}</changefreq>\n"+f"    <priority>{priority}</priority>\n"+"  </url>")
    xml='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+"\n".join(entries)+"\n</urlset>\n"
    return xml,200,{"Content-Type":"application/xml; charset=utf-8"}
@bp.get("/site.webmanifest")
def site_webmanifest():
    return jsonify(
        name="AssetTrack 360",
        short_name="AssetTrack 360",
        description="Secure fleet, diesel, tank and connected-asset monitoring.",
        start_url="/",
        display="standalone",
        background_color="#061622",
        theme_color="#083344",
    )


def _client_ip():
    forwarded=request.headers.get('CF-Connecting-IP') or request.headers.get('X-Forwarded-For','').split(',')[0].strip()
    return forwarded or request.remote_addr or 'unknown'

def _privacy_hash(value):
    pepper=current_app.config['SECRET_KEY']
    return hashlib.sha256(f'{pepper}:{value}'.encode('utf-8')).hexdigest()

def _record_attempt(email,action,accepted=False):
    db.session.add(RegistrationAttempt(email_hash=_privacy_hash(email),ip_hash=_privacy_hash(_client_ip()),action=action,accepted=accepted))

def _attempt_count(email,action,minutes,by_ip=False):
    cutoff=utcnow()-timedelta(minutes=minutes)
    query=RegistrationAttempt.query.filter(RegistrationAttempt.action==action,RegistrationAttempt.created_at>=cutoff)
    key=_privacy_hash(_client_ip()) if by_ip else _privacy_hash(email)
    return query.filter(RegistrationAttempt.ip_hash==key if by_ip else RegistrationAttempt.email_hash==key).count()

def _verification_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'],salt='assettrack360-email-verification-v1')

def _verification_url(user):
    token=_verification_serializer().dumps({'uid':user.id,'email':user.email,'nonce':user.verification_nonce})
    base=os.getenv('PUBLIC_BASE_URL','https://assettrack360.wykiesautomation.co.za').rstrip('/')
    return f'{base}{url_for("main.verify_email",token=token)}'

def _send_user_verification(user):
    user.verification_nonce=secrets.token_urlsafe(24)
    user.verification_sent_at=utcnow()
    db.session.commit()
    return send_verification_email(user.email,user.name,_verification_url(user))

@bp.route('/register',methods=['GET','POST'])
def register():
    if current_user.is_authenticated:return redirect(url_for('main.dashboard'))
    if request.method=='POST':
        company=request.form.get('company','').strip();name=request.form.get('name','').strip();email=request.form.get('email','').strip().lower();password=request.form.get('password','');honeypot=request.form.get('website','').strip()
        generic='If the address can be registered, a verification email will be sent.'
        if honeypot:
            _record_attempt(email or 'empty','REGISTER',False);db.session.commit();flash(generic,'ok');return redirect(url_for('main.login'))
        if _attempt_count(email,'REGISTER',60,True)>=5 or _attempt_count(email,'REGISTER',60,False)>=3:
            _record_attempt(email or 'empty','REGISTER',False);db.session.commit();flash('Too many registration attempts. Please wait before trying again.','error');return render_template('auth.html',mode='register')
        if len(company)<2 or len(name)<2 or '@' not in email or len(password)<10:
            _record_attempt(email or 'empty','REGISTER',False);db.session.commit();flash('Complete all fields. Password must be at least 10 characters.','error')
        elif User.query.filter_by(email=email).first():
            _record_attempt(email,'REGISTER',False);db.session.commit();flash(generic,'ok');return redirect(url_for('main.login'))
        else:
            base=slugify(company) or 'customer';slug=base;n=1
            while Customer.query.filter_by(slug=slug).first():n+=1;slug=f'{base}-{n}'
            c=Customer(name=company,slug=slug,active=False);db.session.add(c);db.session.flush()
            u=User(customer_id=c.id,email=email,name=name,role='customer_admin',password_hash=generate_password_hash(password),active=True,email_verified=False)
            db.session.add(u);_record_attempt(email,'REGISTER',True);db.session.commit()
            sent=_send_user_verification(u)
            flash(generic if sent else 'Account created, but verification email delivery is temporarily unavailable. Use Resend Verification shortly.','ok' if sent else 'error')
            return redirect(url_for('main.login'))
    return render_template('auth.html',mode='register')

@bp.get('/verify-email/<token>')
def verify_email(token):
    try:data=_verification_serializer().loads(token,max_age=1800)
    except SignatureExpired:flash('Verification link expired. Request a new email.','error');return redirect(url_for('main.login'))
    except BadSignature:flash('Invalid verification link.','error');return redirect(url_for('main.login'))
    user=db.session.get(User,int(data.get('uid',0)))
    if not user or user.email!=data.get('email') or not user.verification_nonce or user.verification_nonce!=data.get('nonce'):
        flash('This verification link is invalid or has already been used.','error');return redirect(url_for('main.login'))
    user.email_verified=True;user.email_verified_at=utcnow();user.verification_nonce=None;user.customer.active=True
    db.session.commit();flash('Email verified. Your AssetTrack 360 account is now active.','ok');return redirect(url_for('main.login'))

@bp.post('/resend-verification')
def resend_verification():
    email=request.form.get('email','').strip().lower();generic='If an unverified account exists, a new verification email will be sent.'
    if _attempt_count(email,'RESEND',60,True)>=5 or _attempt_count(email,'RESEND',60,False)>=3:
        flash('Too many resend requests. Please wait before trying again.','error');return redirect(url_for('main.login'))
    user=User.query.filter_by(email=email).first();_record_attempt(email or 'empty','RESEND',bool(user and not user.email_verified));db.session.commit()
    if user and not user.email_verified:_send_user_verification(user)
    flash(generic,'ok');return redirect(url_for('main.login'))

@bp.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        email=request.form.get('email','').strip().lower();u=User.query.filter_by(email=email).first()
        if _attempt_count(email,'LOGIN',15,True)>=12:
            flash('Too many login attempts. Please wait 15 minutes.','error');return render_template('auth.html',mode='login')
        valid=bool(u and u.active and check_password_hash(u.password_hash,request.form.get('password','')))
        _record_attempt(email or 'empty','LOGIN',valid);db.session.commit()
        if valid and not u.email_verified:
            flash('Your email address has not been verified. Request a new verification email below.','error');return render_template('auth.html',mode='login',pending_email=email)
        if valid:login_user(u);return redirect(url_for('main.dashboard'))
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
    now=utcnow(); counts={'HEALTHY':0,'WARNING':0,'CRITICAL':0,'OFFLINE':0,'UNASSIGNED':0}; cards=[]; attention=[]; mapped=[]
    tank_capacity=tank_volume=0.0; tank_count=low_count=0
    for asset in assets:
        status=asset_status(asset);asset.status=status;counts[status]=counts.get(status,0)+1
        device=active_device_for(asset)
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
        device_fresh=bool(device and device.last_seen and now-aware(device.last_seen)<=timedelta(minutes=30))
        if loc and device_fresh:mapped.append({'id':asset.id,'name':asset.name,'type':asset.asset_type,'status':status,'lat':loc.latitude,'lon':loc.longitude})
    order={'CRITICAL':0,'WARNING':1,'OFFLINE':2};attention.sort(key=lambda x:order.get(x['status'],9))
    recent=[]
    for alarm in Alarm.query.filter_by(customer_id=tenant_id()).order_by(desc(Alarm.opened_at)).limit(8):
        a=db.session.get(Asset,alarm.asset_id);recent.append({'title':alarm.message,'detail':f'{a.name if a else "Asset"} · {alarm.severity} · {alarm.state}','time':aware(alarm.opened_at).strftime('%d %b %H:%M')})
    online=sum(1 for d in devices if d.last_seen and now-aware(d.last_seen)<=timedelta(minutes=30))
    connectivity={'online':online,'offline':max(0,len(devices)-online),'online_percent':online/len(devices)*100 if devices else 0,'firmware_reported':sum(1 for d in devices if d.firmware),'unassigned':sum(1 for a in assets if not any(d.asset_id==a.id for d in devices))}
    tank={'count':tank_count,'capacity':tank_capacity,'volume':tank_volume,'percent':tank_volume/tank_capacity*100 if tank_capacity else 0,'low_count':low_count}
    return render_template('dashboard.html',assets=assets,sites=sites,site_count=len(sites),device_count=len(devices),counts=counts,asset_cards=cards,attention_items=attention,mapped_assets=mapped,tank_summary=tank,connectivity=connectivity,recent_events=recent,generated_at=now)

@bp.get('/admin/test-data-cleanup')
@login_required
def test_data_cleanup():
    assets=Asset.query.filter_by(customer_id=tenant_id()).order_by(Asset.name,Asset.id).all();items=[]
    for asset in assets:
        items.append({'asset':asset,'active_device':active_device_for(asset),'devices':Device.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).count(),'locations':Location.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).count(),'readings':Reading.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).count(),'alarms':Alarm.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).count()})
    return render_template('test_data_cleanup.html',items=items)

@bp.post('/admin/test-data-cleanup/delete')
@login_required
def delete_test_asset():
    asset_id=request.form.get('asset_id',type=int)
    confirm_name=request.form.get('confirm_name','').strip()
    confirm_word=request.form.get('confirm_word','').strip().upper()
    query=Asset.query.filter_by(customer_id=tenant_id())
    asset=query.filter_by(id=asset_id).first() if asset_id is not None else None
    if asset is None and confirm_name:
        matches=query.filter_by(name=confirm_name).order_by(Asset.id).all()
        if len(matches)==1:asset=matches[0]
        elif len(matches)>1:return jsonify(ok=False,error='Duplicate asset names found. Use the selected Asset ID.'),409
    if asset is None:return jsonify(ok=False,error=f'Asset lookup failed: id={asset_id!r}, name={confirm_name!r}'),404
    if active_device_for(asset):return jsonify(ok=False,error='Active device assigned.'),409
    if confirm_name!=asset.name or confirm_word!='DELETE':return jsonify(ok=False,error='Confirmation did not match.'),400
    try:
        for model in (Reading,Location,Alarm,CoreAlarmState,DataDeletionRequest,MobileConsent,MobileTrackerRegistration,SecurityAuditEvent,AssetFeatureOverride,AssetAlertSettings,IntegrationSignalMapping,UniversalSourceMapping,MqttTopicMapping):
            model.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).delete(synchronize_session=False)
        if request.form.get('action','delete_all')=='clear_history':
            asset.last_seen=None;asset.status='UNASSIGNED';db.session.commit();return jsonify(ok=True,message='History cleared.')
        Device.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).delete(synchronize_session=False)
        SignalDefinition.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).delete(synchronize_session=False)
        name=asset.name;db.session.delete(asset);db.session.commit();return jsonify(ok=True,message=f'{name} deleted.')
    except Exception as exc:
        db.session.rollback();current_app.logger.exception('Cleanup failed asset_id=%s',asset_id);return jsonify(ok=False,error=f'Database cleanup failed: {type(exc).__name__}'),500

def _distance_km(a,b):
    import math
    lat1,lon1,lat2,lon2=map(math.radians,(a.latitude,a.longitude,b.latitude,b.longitude))
    value=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2*6371.0088*math.asin(min(1,math.sqrt(value)))

def analyse_tracking_points(rows):
    accepted=[];rejected=[];journeys=[];stops=[];current=[];previous=None;distance=0.0;maximum=0.0
    stop_start=None;stop_point=None
    for point in rows:
        reason=None;sampled=aware(point.sampled_at);accuracy=max(0.0,float(point.accuracy_m or 0));speed=max(0.0,float(point.speed_kmh or 0))
        if accuracy>150:reason='POOR_ACCURACY'
        if previous and not reason:
            elapsed=(sampled-aware(previous.sampled_at)).total_seconds();segment=_distance_km(previous,point)
            calculated=segment/(elapsed/3600) if elapsed>0 else 99999
            if elapsed<=0:reason='OUT_OF_ORDER'
            elif calculated>220:reason='IMPOSSIBLE_JUMP'
            elif speed<3 and float(previous.speed_kmh or 0)<3 and segment>max(.25,(accuracy+float(previous.accuracy_m or 0))/1000*2) and elapsed<600:reason='STATIONARY_JUMP'
        item={'latitude':point.latitude,'longitude':point.longitude,'accuracy':accuracy,'speed':speed,'timestamp':sampled.strftime('%Y-%m-%d %H:%M:%S UTC')}
        if reason:
            item['reason']=reason;rejected.append(item);continue
        if previous:
            gap=(sampled-aware(previous.sampled_at)).total_seconds()
            if gap>1200 and current:
                journeys.append(current);current=[]
            elif gap>0:distance+=_distance_km(previous,point)
        accepted.append(item);current.append(item);maximum=max(maximum,speed)
        if speed<3:
            if stop_start is None:stop_start=sampled;stop_point=point
        elif stop_start is not None:
            duration=(sampled-stop_start).total_seconds()
            if duration>=300:stops.append({'started':stop_start.strftime('%Y-%m-%d %H:%M UTC'),'duration_minutes':round(duration/60),'latitude':stop_point.latitude,'longitude':stop_point.longitude})
            stop_start=None;stop_point=None
        previous=point
    if current:journeys.append(current)
    journey_rows=[]
    for index,group in enumerate(journeys,1):
        total=sum(_distance_dict(group[i-1],group[i]) for i in range(1,len(group)))
        journey_rows.append({'number':index,'distance_km':round(total,2),'started':group[0]['timestamp'],'ended':group[-1]['timestamp'],'points':len(group)})
    return {'points':accepted,'rejected':rejected,'journeys':journey_rows,'stops':stops,'distance_km':round(distance,2),'max_speed':round(maximum)}

def _distance_dict(a,b):
    import math
    lat1,lon1,lat2,lon2=map(math.radians,(a['latitude'],a['longitude'],b['latitude'],b['longitude']))
    value=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2*6371.0088*math.asin(min(1,math.sqrt(value)))

@bp.get('/asset/<int:asset_id>/tracking')
@login_required
def tracking_history(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404()
    now=utcnow();preset=request.args.get('range','today')
    if preset=='24h':start=now-timedelta(hours=24)
    elif preset=='7d':start=now-timedelta(days=7)
    elif request.args.get('from'):
        try:start=datetime.fromisoformat(request.args['from']).replace(tzinfo=timezone.utc)
        except ValueError:start=now.replace(hour=0,minute=0,second=0,microsecond=0)
    else:start=now.replace(hour=0,minute=0,second=0,microsecond=0)
    if request.args.get('to'):
        try:end=datetime.fromisoformat(request.args['to']).replace(tzinfo=timezone.utc)
        except ValueError:end=now
    else:end=now
    if start>end:start,end=end,start
    rows=Location.query.filter(Location.customer_id==tenant_id(),Location.asset_id==asset.id,Location.sampled_at>=start,Location.sampled_at<=end).order_by(Location.sampled_at).limit(10000).all()
    return render_template('tracking_history.html',asset=asset,start=start,end=end,analysis=analyse_tracking_points(rows))

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
    phone_battery=None
    battery_signal=SignalDefinition.query.filter_by(asset_id=asset.id,key='battery_percent',enabled=True).first()
    if battery_signal:
        battery_rows=Reading.query.filter_by(signal_id=battery_signal.id).order_by(desc(Reading.sampled_at)).limit(48).all()[::-1]
        values=[max(0.0,min(100.0,float(row.value))) for row in battery_rows]
        if values:
            latest_battery_at=aware(battery_rows[-1].sampled_at)
            age_seconds=max(0,int((now-latest_battery_at).total_seconds()))
            active_mobile=bool(device and device.device_type in ('MOBILE_WEB_TRACKER','ANDROID_MOBILE_TRACKER','MOBILE_TRACKER') and device.active)
            fresh=bool(active_mobile and device.last_seen and now-aware(device.last_seen)<=timedelta(minutes=5) and age_seconds<=600)
            charging_state='Not reported'
            if active_mobile:
                for capability in (device.capabilities or []):
                    if str(capability).startswith('CHARGING:'):
                        charging_state='Yes' if str(capability).split(':',1)[1].lower()=='true' else 'No'
            age_label='Just now' if age_seconds<60 else f'{age_seconds//60} min ago' if age_seconds<3600 else f'{age_seconds//3600} h ago' if age_seconds<86400 else f'{age_seconds//86400} d ago'
            phone_battery={
                'current':round(values[-1]),'minimum':round(min(values)),'maximum':round(max(values)),
                'change':round(values[-1]-values[0]),'charging':charging_state,
                'samples':[{'time':aware(row.sampled_at).strftime('%d %b %H:%M'),'value':round(max(0.0,min(100.0,float(row.value))))} for row in battery_rows],
                'is_live':fresh,'status':'LIVE' if fresh else 'HISTORICAL','recorded_at':latest_battery_at.strftime('%Y-%m-%d %H:%M UTC'),'age':age_label,
            }

    last='No active device' if not device else 'No telemetry received'
    if device and device.last_seen:
        sec=max(0,int((now-aware(device.last_seen)).total_seconds()));last='Just now' if sec<60 else f'{sec//60} min ago' if sec<3600 else f'{sec//3600} h ago' if sec<86400 else f'{sec//86400} d ago'
    ctx={'level':lookup.get('level_percent'),'volume':lookup.get('volume_l'),'battery':lookup.get('battery_v'),'solar':lookup.get('solar_v'),'speed':lookup.get('speed_kmh'),'vibration':lookup.get('vibration_rms'),'temperature':lookup.get('temperature_c')}
    tank=None
    if asset.asset_type=='TANK':
        lvl=ctx['level'].value if ctx['level'] else None;vol=ctx['volume'].value if ctx['volume'] else None;cap=float(asset.capacity or 0);state='CRITICAL' if lvl is not None and lvl<=10 else 'WARNING' if lvl is not None and lvl<=20 else 'HEALTHY' if lvl is not None else 'WAITING';tank={'level':lvl,'volume':vol,'capacity':cap,'available':max(0,cap-float(vol or 0)) if cap else None,'unit':asset.capacity_unit or 'L','state':state}
    track=None
    if asset.asset_type=='TRACKER' or location:track={'latitude':location.latitude if location else None,'longitude':location.longitude if location else None,'speed':location.speed_kmh if location else None,'accuracy':location.accuracy_m if location else None,'heading':location.heading if location else None,'last_fix':aware(location.sampled_at).strftime('%Y-%m-%d %H:%M UTC') if location else 'Waiting for GNSS','route_count':len(route)}
    vib=None
    if asset.asset_type=='VIBRATION':
        value=ctx['vibration'].value if ctx['vibration'] else None;vib={'rms':value,'temperature':ctx['temperature'].value if ctx['temperature'] else None,'condition':'CRITICAL' if value is not None and value>=7.1 else 'WARNING' if value is not None and value>=4.5 else 'HEALTHY' if value is not None else 'WAITING'}
    vehicle_summary=vehicle_day_summary(asset,device,now) if asset.asset_type=='TRACKER' else None
    route_health=route_quality(route) if asset.asset_type=='TRACKER' else None
    return render_template('asset.html',asset=asset,signal_cards=cards,signal_lookup=lookup,chart_series=series,alarms=alarms,open_alarms=open_alarms,device=device,location=location,route_points=route,last_contact=last,generated_at=now,context=ctx,tank_stats=tank,tracking_stats=track,vibration_stats=vib,phone_battery=phone_battery,vehicle_summary=vehicle_summary,route_health=route_health)

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


@bp.route('/devices/connect',methods=['GET','POST'])
@login_required
def connect_device():
    sites=Site.query.filter_by(customer_id=tenant_id()).order_by(Site.name).all()
    active_asset_ids={row.asset_id for row in Device.query.filter_by(customer_id=tenant_id(),active=True).all() if row.asset_id}
    assets=[asset for asset in Asset.query.filter_by(customer_id=tenant_id(),asset_type='TRACKER').order_by(Asset.name).all() if asset.id not in active_asset_ids]
    if request.method=='POST':
        device_kind=request.form.get('device_kind','ANDROID_PHONE').strip().upper()
        if device_kind!='ANDROID_PHONE':
            flash('This connector is prepared but not yet enabled. Use Android Phone for the current pilot.','error')
            return redirect(url_for('main.connect_device'))
        asset_mode=request.form.get('asset_mode','existing')
        if asset_mode=='new':
            name=request.form.get('asset_name','').strip()
            site_mode=request.form.get('site_mode','existing')
            site=None
            if site_mode=='new':
                site_name=request.form.get('new_site_name','').strip()
                site_location=request.form.get('new_site_location','').strip()
                if len(site_name)<2:
                    flash('Enter a site name before continuing.','error')
                    return redirect(url_for('main.connect_device'))
                site=Site.query.filter_by(customer_id=tenant_id(),name=site_name).first()
                if not site:
                    site=Site(customer_id=tenant_id(),name=site_name,location=site_location or None)
                    db.session.add(site);db.session.flush()
            else:
                site_id=request.form.get('site_id',type=int)
                site=Site.query.filter_by(id=site_id,customer_id=tenant_id()).first()
                if not site:
                    flash('Choose an existing site or create a new site below.','error')
                    return redirect(url_for('main.connect_device'))
            if len(name)<2:
                flash('Enter an asset name before continuing.','error')
                return redirect(url_for('main.connect_device'))
            asset=Asset(customer_id=tenant_id(),site_id=site.id,name=name,asset_type='TRACKER',status='UNASSIGNED',metadata_json={'onboarding_source':'DEVICE_CENTRE'})
            db.session.add(asset);db.session.flush();create_default_signals(asset)
        else:
            asset=Asset.query.filter_by(id=request.form.get('asset_id',type=int),customer_id=tenant_id(),asset_type='TRACKER').first()
            if not asset:
                flash('No unassigned tracking asset was selected. Create a new asset below.','error')
                return redirect(url_for('main.connect_device'))
            if asset.id in active_asset_ids:
                flash('This asset already has an active device. Use Replace Phone from Device Registry.','error')
                return redirect(url_for('main.connect_device'))
        MobileTrackerRegistration.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,used_at=None).delete(synchronize_session=False)
        code=f'{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}'
        reg=MobileTrackerRegistration(customer_id=tenant_id(),asset_id=asset.id,code_hash=mobile_code_hash(code),device_uid=f'AT360-PHONE-{asset.id:06d}',expires_at=utcnow()+timedelta(minutes=30),created_by=current_user.id)
        db.session.add(reg);db.session.commit()
        session['onboarding_registration_id']=reg.id;session['onboarding_registration_code']=code
        audit(tenant_id(),'DEVICE_ONBOARDING_STARTED',asset.id,None,'USER',current_user.id,'Android phone onboarding started');db.session.commit()
        return redirect(url_for('main.connect_device_waiting'))
    return render_template('connect_device.html',assets=assets,sites=sites,has_sites=bool(sites),has_assets=bool(assets))
@bp.get('/devices/connect/waiting')
@login_required
def connect_device_waiting():
    reg_id=session.get('onboarding_registration_id');code=session.get('onboarding_registration_code')
    reg=MobileTrackerRegistration.query.filter_by(id=reg_id,customer_id=tenant_id()).first() if reg_id else None
    if not reg or not code:return redirect(url_for('main.connect_device'))
    if reg.used_at:return redirect(url_for('main.devices'))
    remaining_seconds=max(0,int((aware(reg.expires_at)-utcnow()).total_seconds()))
    payload=json.dumps({
        'type':'assetops360_registration',
        'version':1,
        'api':request.url_root.rstrip('/'),
        'code':str(code).strip().upper(),
    },separators=(',',':'))
    from .vendor import segno
    qr=segno.make(payload,error='m')
    qr_data_uri=qr.svg_data_uri(scale=6,border=3,dark='#061622',light='#ffffff')
    return render_template('connect_device_waiting.html',registration=reg,code=code,asset=reg.asset,qr_data_uri=qr_data_uri,remaining_seconds=remaining_seconds)

@bp.get('/api/v1/device-onboarding/status/<int:registration_id>')
@login_required
def device_onboarding_status(registration_id):
    reg=MobileTrackerRegistration.query.filter_by(id=registration_id,customer_id=tenant_id()).first_or_404()
    device=Device.query.filter_by(customer_id=tenant_id(),asset_id=reg.asset_id,device_uid=reg.device_uid).order_by(desc(Device.id)).first()
    if not reg.used_at or not device:return jsonify(state='WAITING',expires_at=aware(reg.expires_at).isoformat())
    consent=MobileConsent.query.filter_by(customer_id=tenant_id(),device_uid=device.device_uid).order_by(desc(MobileConsent.id)).first()
    battery_sig=SignalDefinition.query.filter_by(asset_id=device.asset_id,key='battery_percent').first();battery=latest_reading(battery_sig.id) if battery_sig else None
    return jsonify(state='CONNECTED',device_uid=device.device_uid,asset_name=reg.asset.name,app_version=device.firmware or 'Awaiting first telemetry',consent='Active' if consent and consent.active else 'Pending',battery=round(battery.value) if battery else None,last_contact=device.last_seen.isoformat() if device.last_seen else None,open_asset=url_for('main.asset_view',asset_id=reg.asset_id),open_devices=url_for('main.devices'))

@bp.post('/devices/<int:device_id>/replace-phone')
@login_required
def replace_phone(device_id):
    record=Device.query.filter_by(id=device_id,customer_id=tenant_id()).first_or_404();asset=record.asset
    record.active=False;record.api_token=secrets.token_urlsafe(36)
    consent=MobileConsent.query.filter_by(customer_id=tenant_id(),device_uid=record.device_uid,active=True).order_by(desc(MobileConsent.id)).first()
    if consent:consent.active=False;consent.withdrawn_at=utcnow()
    MobileTrackerRegistration.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,used_at=None).delete(synchronize_session=False)
    code=f'{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}'
    reg=MobileTrackerRegistration(customer_id=tenant_id(),asset_id=asset.id,code_hash=mobile_code_hash(code),device_uid=f'AT360-PHONE-{asset.id:06d}',expires_at=utcnow()+timedelta(minutes=30),created_by=current_user.id)
    db.session.add(reg);db.session.commit();session['onboarding_registration_id']=reg.id;session['onboarding_registration_code']=code
    audit(tenant_id(),'PHONE_REPLACEMENT_STARTED',asset.id,record.id,'USER',current_user.id,'Old token revoked; replacement registration created');db.session.commit()
    return redirect(url_for('main.connect_device_waiting'))

@bp.post('/asset/<int:asset_id>/mobile-tracker/create')
@login_required
def create_mobile_tracker(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404()
    if Device.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,device_type='MOBILE_WEB_TRACKER',active=True).first():
        flash('This asset already has an active Mobile Phone Tracker.','error')
        return redirect(url_for('main.asset_view',asset_id=asset.id))
    MobileTrackerRegistration.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,used_at=None).delete(synchronize_session=False)
    code=f'{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}'
    db.session.add(MobileTrackerRegistration(customer_id=tenant_id(),asset_id=asset.id,code_hash=mobile_code_hash(code),device_uid=f'AT360-PHONE-{asset.id:06d}',expires_at=utcnow()+timedelta(minutes=30),created_by=current_user.id))
    db.session.commit()
    session['mobile_registration_code']=code;session['mobile_registration_asset']=asset.name
    return redirect(url_for('main.mobile_tracker_setup'))

@bp.get('/mobile-tracker/setup')
@login_required
def mobile_tracker_setup():
    return render_template('mobile_tracker_setup.html',code=session.pop('mobile_registration_code',None),asset_name=session.pop('mobile_registration_asset',None))

@bp.post('/api/v1/mobile/register')
def mobile_tracker_register():
    data=request.get_json(silent=True) or {};code=str(data.get('code','')).strip().upper()
    if data.get('consent') is not True or str(data.get('policy_version',''))!=POLICY_VERSION:return jsonify(error='explicit_location_consent_required',policy_version=POLICY_VERSION),422
    if not code:return jsonify(error='registration_code_required'),400
    reg=MobileTrackerRegistration.query.filter_by(code_hash=mobile_code_hash(code),used_at=None).first()
    if not reg:return jsonify(error='invalid_registration_code'),404
    if utcnow()>aware(reg.expires_at):return jsonify(error='registration_code_expired'),410
    if Device.query.filter_by(customer_id=reg.customer_id,asset_id=reg.asset_id,device_type='MOBILE_WEB_TRACKER',active=True).first():return jsonify(error='mobile_tracker_already_registered'),409
    token=secrets.token_urlsafe(36)
    old_identity=Device.query.filter_by(customer_id=reg.customer_id,device_uid=reg.device_uid,active=False).first()
    if old_identity:db.session.delete(old_identity);db.session.flush()
    device=Device(customer_id=reg.customer_id,asset_id=reg.asset_id,device_uid=reg.device_uid,device_type='MOBILE_WEB_TRACKER',api_token=token,active=True,firmware='mobile-web-1.2',capabilities=['GPS','PHONE_BATTERY','USER_CONSENT_REQUIRED'])
    reg.used_at=utcnow();db.session.add(device);db.session.flush()
    consent=MobileConsent(customer_id=reg.customer_id,asset_id=reg.asset_id,device_id=device.id,device_uid=device.device_uid,policy_version=POLICY_VERSION,active=True,user_agent_summary=(request.headers.get('User-Agent') or '')[:240]);db.session.add(consent);audit(reg.customer_id,'CONSENT_ACCEPTED',reg.asset_id,device.id,'DEVICE',None,'Explicit location consent accepted');audit(reg.customer_id,'PHONE_REGISTERED',reg.asset_id,device.id,'DEVICE',None,'Mobile tracker registered')
    if not SignalDefinition.query.filter_by(asset_id=reg.asset_id,key='battery_percent').first():
        db.session.add(SignalDefinition(customer_id=reg.customer_id,asset_id=reg.asset_id,key='battery_percent',label='Phone Battery',signal_type='PERCENT',source_type='MOBILE',unit='%',widget='battery'))
    db.session.commit()
    return jsonify(status='registered',device_uid=device.device_uid,device_token=token,asset_name=device.asset.name),201

@bp.post('/api/v1/mobile/location')
def mobile_tracker_location():
    device=mobile_tracker_device()
    if not device:return jsonify(error='invalid_mobile_tracker_token'),401
    consent=consent_for_device(device)
    if not consent or not consent.active:return jsonify(error='consent_inactive'),403
    allowed,subscription=entitlement_for(device.customer_id)
    if not allowed:return jsonify(error='subscription_inactive'),402
    data=request.get_json(silent=True) or {};sequence=str(data.get('sequence','')).strip()
    if str(data.get('device_id','')).upper()!=device.device_uid.upper():return jsonify(error='device_identity_mismatch'),403
    if not sequence:return jsonify(error='sequence_required'),400
    if Location.query.filter_by(asset_id=device.asset_id,sequence=sequence).first():return jsonify(status='duplicate'),200
    try:
        lat=float(data['latitude']);lon=float(data['longitude']);acc=max(0,float(data.get('accuracy_m') or 0));speed=max(0,float(data.get('speed_kmh') or 0))
    except (KeyError,TypeError,ValueError):return jsonify(error='invalid_location_payload'),400
    if not(-90<=lat<=90 and -180<=lon<=180) or speed>300:return jsonify(error='location_out_of_range'),400
    if speed<3:speed=0.0
    sampled=parse_time(data.get('timestamp'))
    db.session.add(Location(customer_id=device.customer_id,asset_id=device.asset_id,sampled_at=sampled,latitude=lat,longitude=lon,speed_kmh=speed,accuracy_m=acc,heading=data.get('heading'),sequence=sequence))
    battery=data.get('battery_percent')
    if battery is not None:
        sig=SignalDefinition.query.filter_by(asset_id=device.asset_id,key='battery_percent').first()
        if not sig:
            sig=SignalDefinition(customer_id=device.customer_id,asset_id=device.asset_id,key='battery_percent',label='Phone Battery',signal_type='PERCENT',source_type='MOBILE',unit='%',widget='battery');db.session.add(sig);db.session.flush()
        bseq=f'{sequence}:battery'
        if not Reading.query.filter_by(signal_id=sig.id,sequence=bseq).first():db.session.add(Reading(customer_id=device.customer_id,asset_id=device.asset_id,signal_id=sig.id,sampled_at=sampled,value=max(0,min(100,float(battery))),unit='%',quality='GOOD',sequence=bseq))
    charging=data.get('charging')
    capabilities=[c for c in (device.capabilities or []) if not str(c).startswith('CHARGING:')]
    capabilities.extend(['GPS','PHONE_BATTERY',f'CHARGING:{str(bool(charging)).lower()}'])
    device.capabilities=list(dict.fromkeys(capabilities))
    evaluate_mobile(device,data)
    device.last_seen=utcnow();device.asset.last_seen=sampled;device.firmware=str(data.get('client_version') or 'mobile-web-1.2')[:40]
    db.session.commit();return jsonify(status='accepted',sequence=sequence),202

@bp.get('/api/v1/mobile/status')
def mobile_tracker_status():
    device=mobile_tracker_device()
    if not device:return jsonify(error='invalid_mobile_tracker_token'),401
    latest=Location.query.filter_by(customer_id=device.customer_id,asset_id=device.asset_id).order_by(desc(Location.sampled_at)).first()
    return jsonify(status='ok',device_uid=device.device_uid,asset_name=device.asset.name,last_contact=device.last_seen.isoformat() if device.last_seen else None,last_position={'latitude':latest.latitude,'longitude':latest.longitude,'sampled_at':latest.sampled_at.isoformat(),'accuracy_m':latest.accuracy_m} if latest else None)

@bp.post('/api/v1/mobile/event')
def mobile_event():
    device=mobile_tracker_device()
    if not device:return jsonify(error='invalid_mobile_tracker_token'),401
    data=request.get_json(silent=True) or {};event=str(data.get('event','')).upper();consent=consent_for_device(device)
    if event=='TRACKING_STARTED':
        if not consent or not consent.active:return jsonify(error='consent_inactive'),403
        consent.last_tracking_started_at=utcnow();audit(device.customer_id,event,device.asset_id,device.id,'DEVICE',None,'Tracking started by phone user')
    elif event=='TRACKING_STOPPED':
        if consent:consent.last_tracking_stopped_at=utcnow()
        audit(device.customer_id,event,device.asset_id,device.id,'DEVICE',None,'Tracking stopped by phone user')
    elif event=='CONSENT_WITHDRAWN':
        if consent:consent.active=False;consent.withdrawn_at=utcnow()
        audit(device.customer_id,event,device.asset_id,device.id,'DEVICE',None,'Location consent withdrawn')
    elif event=='UNREGISTERED':
        if consent:consent.active=False;consent.withdrawn_at=utcnow()
        device.active=False;device.api_token=secrets.token_urlsafe(36);audit(device.customer_id,event,device.asset_id,device.id,'DEVICE',None,'Phone unregistered and token revoked')
    elif event=='DATA_DELETION_REQUESTED':
        db.session.add(DataDeletionRequest(customer_id=device.customer_id,asset_id=device.asset_id,device_id=device.id));audit(device.customer_id,event,device.asset_id,device.id,'DEVICE',None,'Tracking data deletion review requested')
    else:return jsonify(error='unsupported_event'),422
    db.session.commit();return jsonify(status='accepted'),202

@bp.route('/fleet-feature-settings',methods=['GET','POST'])
@login_required
def fleet_feature_settings():
    defaults=fleet_defaults_for(tenant_id());entitlements=entitlement_map(tenant_id())
    if request.method=='POST':
        for key in FEATURE_KEYS:
            if entitlements[key]:setattr(defaults,key+'_enabled',request.form.get(key+'_enabled')=='on')
        defaults.updated_by=current_user.id
        if request.form.get('apply_existing')=='yes':
            for asset in Asset.query.filter_by(customer_id=tenant_id()).all():
                override=AssetFeatureOverride.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).first()
                if not override:db.session.add(AssetFeatureOverride(customer_id=tenant_id(),asset_id=asset.id,use_fleet_defaults=True,updated_by=current_user.id))
                else:override.use_fleet_defaults=True;override.updated_by=current_user.id
        audit(tenant_id(),'FLEET_FEATURE_DEFAULTS_CHANGED',None,None,'USER',current_user.id,'Fleet feature defaults updated');db.session.commit();flash('Fleet feature defaults saved.','ok');return redirect(url_for('main.fleet_feature_settings'))
    return render_template('fleet_feature_settings.html',defaults=defaults,defaults_map={key:bool(getattr(defaults,key+'_enabled')) for key in FEATURE_KEYS},entitlements=entitlements,feature_keys=FEATURE_KEYS,mandatory=MANDATORY_CONTROLS)

@bp.route('/asset/<int:asset_id>/feature-settings',methods=['GET','POST'])
@login_required
def asset_feature_settings(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();override=AssetFeatureOverride.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).first()
    if not override:override=AssetFeatureOverride(customer_id=tenant_id(),asset_id=asset.id);db.session.add(override);db.session.flush()
    entitlements=entitlement_map(tenant_id());effective=effective_features(asset)
    if request.method=='POST':
        override.use_fleet_defaults=request.form.get('use_fleet_defaults')=='on';override.updated_by=current_user.id
        if not override.use_fleet_defaults:override.features_json={key:(request.form.get(key+'_enabled')=='on') for key in FEATURE_KEYS if entitlements[key]}
        audit(tenant_id(),'ASSET_FEATURE_OVERRIDE_CHANGED',asset.id,None,'USER',current_user.id,'Vehicle feature configuration updated');db.session.commit();flash('Vehicle feature settings saved.','ok');return redirect(url_for('main.asset_feature_settings',asset_id=asset.id))
    return render_template('asset_feature_settings.html',asset=asset,override=override,effective=effective,entitlements=entitlements,feature_keys=FEATURE_KEYS,mandatory=MANDATORY_CONTROLS)

@bp.route('/asset/<int:asset_id>/alert-settings',methods=['GET','POST'])
@login_required
def alert_settings(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();cfg=settings_for(asset)
    if request.method=='POST':
        cfg.battery_warning=max(5,min(95,float(request.form.get('battery_warning') or 20)));cfg.battery_critical=max(1,min(cfg.battery_warning,float(request.form.get('battery_critical') or 10)));cfg.battery_recovered=max(cfg.battery_warning,min(100,float(request.form.get('battery_recovered') or 25)))
        cfg.offline_warning_minutes=max(1,min(1440,int(request.form.get('offline_warning_minutes') or 5)));cfg.offline_critical_minutes=max(cfg.offline_warning_minutes,min(2880,int(request.form.get('offline_critical_minutes') or 15)))
        cfg.gps_accuracy_limit_m=max(10,min(1000,float(request.form.get('gps_accuracy_limit_m') or 50)));cfg.speed_warning_kmh=max(10,min(250,float(request.form.get('speed_warning_kmh') or 100)));cfg.speed_critical_kmh=max(cfg.speed_warning_kmh,min(300,float(request.form.get('speed_critical_kmh') or 120)));cfg.extended_stop_minutes=max(5,min(1440,int(request.form.get('extended_stop_minutes') or 30)))
        for key in ('battery','offline','gps','speed','extended_stop'):setattr(cfg,key+'_enabled',request.form.get(key+'_enabled')=='on')
        cfg.updated_by=current_user.id;audit(asset.customer_id,'ALERT_SETTINGS_CHANGED',asset.id,None,'USER',current_user.id,'Vehicle alert settings updated');db.session.commit();flash('Alert settings saved.','ok');return redirect(url_for('main.alert_settings',asset_id=asset.id))
    return render_template('alert_settings.html',asset=asset,cfg=cfg)

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
        consent=MobileConsent.query.filter_by(customer_id=tenant_id(),device_uid=record.device_uid).order_by(MobileConsent.id.desc()).first()
        battery_sig=SignalDefinition.query.filter_by(asset_id=record.asset_id,key='battery_percent').first();battery=latest_reading(battery_sig.id) if battery_sig else None
        items.append({'device':record,'asset':record.asset,'online':online,'last_contact':last_contact,'consent':consent,'battery':battery})
    new_token = session.pop('new_device_token', None)
    new_token_device = session.pop('new_device_uid', None)
    return render_template(
        'devices.html',
        items=items,
        new_token=new_token,
        new_token_device=new_token_device,
    )


@bp.post('/devices/<int:device_id>/delete')
@login_required
def delete_device(device_id):
    record=Device.query.filter_by(id=device_id,customer_id=tenant_id()).first_or_404()
    if record.active:
        flash('Disable the device before permanently deleting it.','error')
        return redirect(url_for('main.devices'))
    expected_uid=str(record.device_uid or '').strip()
    confirm_uid=request.form.get('confirm_uid','').strip()
    confirm_word=request.form.get('confirm_word','').strip().upper()
    if confirm_uid!=expected_uid or confirm_word!='DELETE':
        flash('Permanent delete confirmation did not match the Device UID and DELETE.','error')
        return redirect(url_for('main.devices'))
    # Preserve the asset, tracking history, readings and alarms. Remove only the device identity/token.
    record.api_token=secrets.token_urlsafe(32)
    db.session.delete(record)
    db.session.commit()
    flash(f'Device {expected_uid} permanently deleted. Asset and history were retained.','ok')
    return redirect(url_for('main.devices'))

@bp.post('/devices/<int:device_id>/rotate-token')
@login_required
def rotate_device_token(device_id):
    record = Device.query.filter_by(
        id=device_id,
        customer_id=tenant_id(),
    ).first_or_404()
    record.api_token = secrets.token_urlsafe(32)
    audit(record.customer_id,'TOKEN_ROTATED',record.asset_id,record.id,'USER',current_user.id,'Device token rotated')
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
    audit(record.customer_id,'DEVICE_ENABLED' if record.active else 'DEVICE_DISABLED',record.asset_id,record.id,'USER',current_user.id,'Device state changed')
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

@bp.get('/api/v1/assets/<int:asset_id>/route-intelligence')
@login_required
def route_intelligence_api(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404()
    rows=Location.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).order_by(desc(Location.sampled_at)).limit(200).all()[::-1]
    matched=match_route(rows);quality=route_quality(rows)
    return jsonify(route=matched,quality=quality)

@bp.get('/api/v1/reverse-geocode')
@login_required
def reverse_geocode_api():
    try:
        lat=float(request.args['lat']);lon=float(request.args['lon']);accuracy=float(request.args.get('accuracy_m') or 0)
    except (KeyError,TypeError,ValueError):return jsonify(error='valid_lat_lon_required'),400
    if not (-90<=lat<=90 and -180<=lon<=180):return jsonify(error='coordinates_out_of_range'),400
    return jsonify(reverse_geocode(lat,lon,accuracy_m=accuracy,force_refresh=request.args.get('refresh','').lower() in ('1','true','yes')))

@bp.get('/api/v1/assets/<int:asset_id>/latest')
@login_required
def api_latest(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();out={}
    for s in SignalDefinition.query.filter_by(asset_id=asset.id,enabled=True):
        r=Reading.query.filter_by(signal_id=s.id).order_by(desc(Reading.sampled_at)).first();out[s.key]={'value':r.value,'unit':s.unit,'quality':r.quality,'sampled_at':r.sampled_at.isoformat()} if r else None
    return jsonify(asset={'id':asset.id,'name':asset.name,'type':asset.asset_type,'status':asset_status(asset)},signals=out)
