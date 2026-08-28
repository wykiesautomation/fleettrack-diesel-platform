import os, secrets, re, hashlib, io, json, time
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort, session, current_app, send_from_directory, send_file
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import desc, text, inspect
from . import db
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from .email_service import send_verification_email
from .payfast import config as payfast_config,build_checkout,event_hash,valid_signature,valid_source,server_validate,forwarded_ip
from .models import Customer,User,Site,Asset,Device,SignalDefinition,Reading,Alarm,Location,WorkspaceProfile,EmailNotificationLog,SubscriptionPlan,Subscription,PaymentRecord,PayFastEvent,SubscriptionAuditEvent,IntegrationConnector,IntegrationSignalMapping,IntegrationEvent,ConnectorEndpointConfig,UniversalSourceMapping,WebhookReceipt,EdgeGateway,IntegrationJobEvent,MqttSubscription,MqttTopicMapping,MqttMessageEvent,MobileTrackerRegistration,MobileConsent,SecurityAuditEvent,AssetAlertSettings,CoreAlarmState,DataDeletionRequest,FleetFeatureDefaults,AssetFeatureOverride,RegistrationAttempt,AdvancedAccessGrant,DeviceTrendPolicy,SignalTrendPolicy,TrendCleanupState,DeviceCommand,DeviceChannelAssignment,Live360SafetyEvent
from .route_intelligence import match_route, reverse_geocode, route_quality
from .security_privacy import POLICY_VERSION,audit,consent_for_device,settings_for,evaluate_mobile,FEATURE_KEYS,MANDATORY_CONTROLS,fleet_defaults_for,entitlement_map,effective_features
from .seo import SEO_PAGES, render_seo_page
from .device_profiles import get_profile, public_profiles, profile_for_device
bp=Blueprint('main',__name__)
_calibration_schema_ready=False

@bp.before_app_request
def ensure_calibration_schema():
    global _calibration_schema_ready
    if _calibration_schema_ready:return None
    statements=[
        "ALTER TABLE signal_definition ADD COLUMN IF NOT EXISTS calibration_mode VARCHAR(30) NOT NULL DEFAULT 'LINEAR'",
        'ALTER TABLE signal_definition ADD COLUMN IF NOT EXISTS "offset" DOUBLE PRECISION NOT NULL DEFAULT 0',
        "ALTER TABLE signal_definition ADD COLUMN IF NOT EXISTS filter_alpha DOUBLE PRECISION NOT NULL DEFAULT 1",
        "ALTER TABLE signal_definition ADD COLUMN IF NOT EXISTS deadband DOUBLE PRECISION NOT NULL DEFAULT 0",
        "ALTER TABLE signal_definition ADD COLUMN IF NOT EXISTS calibrated_at TIMESTAMPTZ",
        "ALTER TABLE signal_definition ADD COLUMN IF NOT EXISTS calibrated_by INTEGER",
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS password_reset_nonce VARCHAR(80)',
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS password_reset_sent_at TIMESTAMPTZ',
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMPTZ',
        'CREATE INDEX IF NOT EXISTS ix_user_password_reset_nonce ON "user"(password_reset_nonce)',
    ]
    try:
        for statement in statements:db.session.execute(text(statement))
        db.session.commit();_calibration_schema_ready=True
    except Exception:
        db.session.rollback();current_app.logger.exception('Calibration schema migration failed')
    return None

def utcnow(): return datetime.now(timezone.utc)
def tenant_id(): return current_user.customer_id
def slugify(v): return re.sub(r'[^a-z0-9]+','-',v.lower()).strip('-')[:70]
def device_profile_context(device):
    profile=profile_for_device(device)
    return profile or {'code':'LEGACY','display_name':device.device_type if device else 'Unassigned','channels':[],'output_channels':[],'capabilities':[]}

def ensure_profile_signals(asset,profile):
    for channel in profile.get('channels',[]):
        if not SignalDefinition.query.filter_by(customer_id=asset.customer_id,asset_id=asset.id,key=channel['key']).first():
            defaults=channel.get('defaults',{})
            db.session.add(SignalDefinition(customer_id=asset.customer_id,asset_id=asset.id,key=channel['key'],label=channel['label'],signal_type=channel['signal_type'],source_type=channel['source_type'],unit=channel.get('unit',''),widget=channel.get('widget','numeric'),enabled=True,raw_min=defaults.get('raw_min',0),raw_max=defaults.get('raw_max',100),eng_min=defaults.get('eng_min',0),eng_max=defaults.get('eng_max',100),calibration_mode=defaults.get('calibration_mode','PASSTHROUGH'),offset=defaults.get('offset',0),filter_alpha=defaults.get('filter_alpha',1),deadband=defaults.get('deadband',0),critical_low=defaults.get('critical_low'),warning_low=defaults.get('warning_low'),warning_high=defaults.get('warning_high'),critical_high=defaults.get('critical_high'),config_json={'profile_code':profile['code'],'direction':channel.get('direction'),'command_channel':channel.get('command_channel')}))

MOBILE_AUTO_POINTS=(
    {"key":"gps_location","label":"GPS Location","signal_type":"LOCATION","unit":"","widget":"location","purpose":"GPS_LOCATION","required":True},
    {"key":"speed_kmh","label":"Vehicle Speed","signal_type":"SPEED","unit":"km/h","widget":"numeric","purpose":"VEHICLE_SPEED","required":True},
    {"key":"heading","label":"Heading","signal_type":"HEADING","unit":"deg","widget":"numeric","purpose":"HEADING","required":True},
    {"key":"gps_accuracy_m","label":"GPS Accuracy","signal_type":"DISTANCE","unit":"m","widget":"numeric","purpose":"GPS_ACCURACY","required":True},
    {"key":"battery_percent","label":"Phone Battery","signal_type":"PERCENT","unit":"%","widget":"battery","purpose":"PHONE_BATTERY","required":True},
    {"key":"charging_status","label":"Charging Status","signal_type":"STATE","unit":"","widget":"status","purpose":"CHARGING_STATUS","required":True},
    {"key":"last_contact","label":"Last Contact","signal_type":"TIMESTAMP","unit":"","widget":"status","purpose":"LAST_CONTACT","required":True},
    {"key":"sos_event","label":"SOS Event","signal_type":"STATE","unit":"","widget":"status","purpose":"SOS_EVENT","required":False},
)

def ensure_mobile_auto_profile(device):
    """Idempotently bind fixed phone telemetry to its already linked tracker asset."""
    if not device or not device.asset_id or str(device.device_type or '').upper() not in ('MOBILE_WEB_TRACKER','ANDROID_MOBILE_TRACKER','MOBILE_TRACKER','IOS_MOBILE_TRACKER'):
        return []
    created=[]
    for point in MOBILE_AUTO_POINTS:
        sig=SignalDefinition.query.filter_by(customer_id=device.customer_id,asset_id=device.asset_id,key=point['key']).first()
        if not sig:
            sig=SignalDefinition(customer_id=device.customer_id,asset_id=device.asset_id,key=point['key'],label=point['label'],signal_type=point['signal_type'],source_type='MOBILE',unit=point['unit'],widget=point['widget'],enabled=True,calibration_mode='PASSTHROUGH',config_json={'mobile_auto_managed':True,'optional':not point['required']})
            db.session.add(sig);db.session.flush();created.append(point['key'])
        else:
            sig.enabled=True;sig.source_type='MOBILE';cfg=dict(sig.config_json or {});cfg.update({'mobile_auto_managed':True,'optional':not point['required']});sig.config_json=cfg
        row=DeviceChannelAssignment.query.filter_by(customer_id=device.customer_id,device_id=device.id,channel_key=point['key']).first()
        if not row:
            row=DeviceChannelAssignment(customer_id=device.customer_id,device_id=device.id,channel_key=point['key'],direction='LOCATION' if point['key']=='gps_location' else 'HEALTH')
            db.session.add(row)
        row.asset_id=device.asset_id;row.signal_id=sig.id;row.purpose=point['purpose'];row.customer_label=point['label'];row.enabled=point['required'] or bool((row.config_json or {}).get('user_enabled',False));row.config_json={'mobile_auto_managed':True,'physical_gpio':False,'optional':not point['required'],'user_enabled':row.enabled}
    meta=dict(device.asset.metadata_json or {});meta['mobile_profile_state']='ACTIVE';meta['mobile_profile_device_uid']=device.device_uid;meta['mobile_profile_updated_at']=utcnow().isoformat();device.asset.metadata_json=meta
    return created

def channel_profile_default(device,signal_key):
    profile=profile_for_device(device)
    return next((x for x in (profile or {}).get('channels',[]) if x.get('key')==signal_key),None)
def profile_calibratable(device,signal):
    channel=channel_profile_default(device,signal.key)
    return bool(channel and channel.get('calibratable'))
def parse_time(v):
    if not v:return utcnow()
    try:return datetime.fromisoformat(v.replace('Z','+00:00'))
    except:return utcnow()
def aware(value):
    if not value:return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

def has_advanced_access(customer_id, device=None):
    """Return True for platform admin, active customer-wide grant, or active device grant."""
    if current_user.is_authenticated and current_user.role == 'platform_admin':
        return True
    now = utcnow()
    grants = AdvancedAccessGrant.query.filter_by(customer_id=customer_id, active=True).all()
    for grant in grants:
        if grant.expires_at and aware(grant.expires_at) <= now:
            continue
        if grant.device_id is None:
            return True
        if device and grant.device_id == device.id and device.customer_id == customer_id:
            return True
    return False
def route_distance_km(points):
    """Calculate movement distance for vehicles and walking phone trackers.

    GPS fixes commonly arrive every few seconds. Requiring every individual
    segment to exceed the full accuracy radius incorrectly reduces a real walk
    to 0.0 km. This filter accepts progressive movement while suppressing small
    stationary drift inside a conservative fraction of the reported accuracy.
    """
    import math
    def haversine(a,b):
        lat1,lon1,lat2,lon2=map(math.radians,(a.latitude,a.longitude,b.latitude,b.longitude))
        value=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
        return 2*6371.0088*math.asin(min(1,math.sqrt(value)))
    if len(points)<2:return 0.0
    total=0.0;anchor=points[0]
    for point in points[1:]:
        elapsed=max(1,(aware(point.sampled_at)-aware(anchor.sampled_at)).total_seconds())
        segment=haversine(anchor,point)
        plausible=max(0.08,elapsed/3600*180+0.05)
        accuracy_m=max(3.0,min(60.0,(float(anchor.accuracy_m or 20)+float(point.accuracy_m or 20))/2))
        movement_threshold_m=max(4.0,min(15.0,accuracy_m*0.35))
        if segment<=plausible and segment*1000>=movement_threshold_m:
            total+=segment;anchor=point
        elif elapsed>=45:
            anchor=point
    return round(total,2)
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
def trend_policy_for(device):
    if not device:return None
    policy=DeviceTrendPolicy.query.filter_by(customer_id=device.customer_id,device_id=device.id).first()
    if not policy:
        mobile=str(device.device_type or '').upper() in ('MOBILE_WEB_TRACKER','ANDROID_MOBILE_TRACKER','MOBILE_TRACKER','IOS_MOBILE_TRACKER');policy=DeviceTrendPolicy(customer_id=device.customer_id,device_id=device.id,trend_enabled=False,retention_days=93,gps_history_enabled=mobile,gps_retention_days=31)
        db.session.add(policy);db.session.flush()
    return policy
def signal_trend_enabled(device,signal):
    policy=trend_policy_for(device)
    return bool(policy and policy.trend_enabled and SignalTrendPolicy.query.filter_by(customer_id=device.customer_id,device_id=device.id,signal_id=signal.id,enabled=True).first())
def retain_latest_only(signal_id):
    latest=Reading.query.filter_by(signal_id=signal_id).order_by(desc(Reading.sampled_at),desc(Reading.id)).first()
    if latest:Reading.query.filter(Reading.signal_id==signal_id,Reading.id!=latest.id).delete(synchronize_session=False)
def retain_latest_location_only(asset_id):
    latest=Location.query.filter_by(asset_id=asset_id).order_by(desc(Location.sampled_at),desc(Location.id)).first()
    if latest:Location.query.filter(Location.asset_id==asset_id,Location.id!=latest.id).delete(synchronize_session=False)

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

BOARD_TELEMETRY_SPECS={
    'ESP32_REMOTE_IO':{
        **{f'analog_{i}':(f'Analog Input {i}','CUSTOM','%','numeric') for i in range(1,5)},
        **{f'analog_{i}_volts':(f'Analog Input {i} Voltage','VOLTAGE','V','numeric') for i in range(1,5)},
        **{f'digital_{i}':(f'Digital Input {i}','STATE','','numeric') for i in range(1,5)},
        **{f'digital_output_{i}_feedback':(f'Digital Output {i} Feedback','STATE','','numeric') for i in range(1,5)},
        'pulse_1_count':('Pulse Counter 1','COUNT','pulses','numeric'),
        'pulse_2_count':('Pulse Counter 2','COUNT','pulses','numeric'),
        'local_arm_status':('Local Arm Status','STATE','','numeric'),
        'wifi_rssi':('Wi-Fi Signal','SIGNAL','dBm','numeric'),
    },
    'SIM808_SAMD21':{
        'analog_1':('Analog Input 1','CUSTOM','%','numeric'),
        'analog_2':('Analog Input 2','CUSTOM','%','numeric'),
        'digital_1':('Digital Input 1','STATE','','numeric'),
        'digital_2':('Digital Input 2','STATE','','numeric'),
        'digital_3':('Digital Input 3','STATE','','numeric'),
        'digital_output_1_feedback':('Digital Output 1 Feedback','STATE','','numeric'),
        'digital_output_2_feedback':('Digital Output 2 Feedback','STATE','','numeric'),
        'pulse_1_count':('Pulse Input 1','COUNT','pulses','numeric'),
    },
}
def board_telemetry_spec(device,key):
    return BOARD_TELEMETRY_SPECS.get(getattr(device,'device_type',None),{}).get(key)
PASSTHROUGH_SIGNAL_SPECS={
    'battery_v':('Battery Voltage','VOLTAGE','V','battery'),
    'battery_percent':('Battery Level','PERCENT','%','battery'),
    'charging_status':('Charging Status','STATE','','numeric'),
    'digital_output_1_feedback':('Digital Output 1 Feedback','STATE','','numeric'),
    'digital_output_2_feedback':('Digital Output 2 Feedback','STATE','','numeric'),
    'gps_fix':('GPS Fix','STATE','','numeric'),
    'gsm_signal':('GSM Signal','SIGNAL','CSQ','numeric'),
    'speed_kmh':('Speed','SPEED','km/h','numeric'),
    'airtime_balance_zar':('Airtime Balance','CURRENCY','R','numeric'),
    'data_remaining_mb':('Mobile Data Remaining','DATA','MB','numeric'),
}
def enforce_passthrough_signal(sig,key):
    spec=PASSTHROUGH_SIGNAL_SPECS.get(key)
    if not spec:return
    label,signal_type,unit,widget=spec
    sig.label=label;sig.signal_type=signal_type;sig.unit=unit;sig.widget=widget
    sig.calibration_mode='PASSTHROUGH';sig.raw_min=0;sig.raw_max=100;sig.eng_min=0;sig.eng_max=100
    sig.offset=0;sig.filter_alpha=1;sig.deadband=0
    if key=='airtime_balance_zar':sig.warning_low=30;sig.critical_low=10
    elif key=='data_remaining_mb':sig.warning_low=250;sig.critical_low=100

def normalize_tank_points(points):
    clean=[]
    for point in points or []:
        try:level=float(point.get('level'));volume=float(point.get('volume'))
        except (TypeError,ValueError,AttributeError):continue
        if level < 0 or volume < 0:continue
        clean.append({'level':level,'volume':volume})
    clean.sort(key=lambda x:x['level'])
    if len(clean)<2 or len({x['level'] for x in clean})!=len(clean):return []
    return clean[:20]


def validate_tank_strapping(points, capacity=None, require_full=False):
    clean = normalize_tank_points(points)
    errors = []
    if len(clean) < 2:
        errors.append('At least two unique calibration points are required.')
    if clean:
        if clean[0]['level'] != 0 or clean[0]['volume'] != 0:
            errors.append('The first point must be 0 level and 0 volume.')
        if any(clean[i]['volume'] >= clean[i + 1]['volume'] for i in range(len(clean) - 1)):
            errors.append('Volume must increase at every calibration point.')
        if capacity and clean[-1]['volume'] > float(capacity) + 0.01:
            errors.append('The final volume may not exceed the tank capacity.')
        if require_full and capacity and abs(clean[-1]['volume'] - float(capacity)) > max(0.01, float(capacity) * 0.001):
            errors.append('The final calibration volume must match the configured tank capacity.')
    return clean, errors

def tank_volume_from_level(level,points):
    points=normalize_tank_points(points)
    if len(points)<2:return None
    value=float(level)
    if value<=points[0]['level']:return points[0]['volume']
    if value>=points[-1]['level']:return points[-1]['volume']
    for left,right in zip(points,points[1:]):
        if left['level']<=value<=right['level']:
            span=right['level']-left['level']
            if span<=0:return None
            return left['volume']+(value-left['level'])*(right['volume']-left['volume'])/span
    return None

def scale_signal(sig,raw):
    mode=str(getattr(sig,'calibration_mode','LINEAR') or 'LINEAR').upper()
    if mode=='PASSTHROUGH':value=raw
    else:
        span=float(sig.raw_max or 0)-float(sig.raw_min or 0)
        value=float(sig.eng_min or 0) if span==0 else float(sig.eng_min or 0)+(raw-float(sig.raw_min or 0))*(float(sig.eng_max or 0)-float(sig.eng_min or 0))/span
    value=value+float(getattr(sig,'offset',0) or 0)
    # Normal industrial channels are bounded by their configured engineering range.
    # This prevents a 0 V under-range input from displaying impossible negative flow,
    # level or pressure values. PASSTHROUGH channels remain unchanged.
    if mode!='PASSTHROUGH':
        low=min(float(sig.eng_min or 0),float(sig.eng_max or 0))
        high=max(float(sig.eng_min or 0),float(sig.eng_max or 0))
        value=max(low,min(high,value))
    return value

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
    if sub.state=='TRIAL' and sub.trial_ends_at and now>aware(sub.trial_ends_at):
        sub.access_source='PAYMENT_REQUIRED';set_subscription_state(sub,'PAYMENT_REQUIRED','72-hour trial expired; payment required')
    elif sub.state=='ACTIVE' and sub.current_period_end and now>aware(sub.current_period_end):
        sub.grace_ends_at=now+timedelta(days=3);set_subscription_state(sub,'GRACE_PERIOD','Paid period ended; three-day grace period started')
    elif sub.state=='GRACE_PERIOD' and sub.grace_ends_at and now>aware(sub.grace_ends_at):set_subscription_state(sub,'SUSPENDED','Grace period expired')
    return sub

def activate_paid_subscription(payment,reason='Validated COMPLETE payment'):
    if not payment or payment.status!='COMPLETE':return None
    sub=Subscription.query.filter_by(id=payment.subscription_id,customer_id=payment.customer_id).first() if payment.subscription_id else None
    if not sub:sub=Subscription.query.filter_by(customer_id=payment.customer_id).first()
    if not sub:return None
    started=aware(payment.paid_at) or aware(payment.created_at) or utcnow()
    months=max(1,int(getattr(payment,'term_months',1) or 1));period_end=started+timedelta(days=30*months)
    if period_end<=utcnow():return sub
    old=sub.state;old_source=getattr(sub,'access_source',None)
    sub.state='ACTIVE';sub.access_source='PAID';sub.current_period_start=started;sub.current_period_end=period_end;sub.paid_from=started;sub.paid_until=period_end;sub.next_payment_at=period_end;sub.grace_ends_at=None
    customer=db.session.get(Customer,payment.customer_id)
    if customer:customer.active=True
    if old!='ACTIVE' or old_source!='PAID':db.session.add(SubscriptionAuditEvent(customer_id=sub.customer_id,subscription_id=sub.id,previous_state=old,new_state='ACTIVE',reason=reason))
    return sub

def reconcile_customer_payment(customer_id):
    payment=PaymentRecord.query.filter_by(customer_id=customer_id,status='COMPLETE').order_by(desc(PaymentRecord.paid_at),desc(PaymentRecord.created_at)).first()
    if not payment:return None
    sub=activate_paid_subscription(payment,'Reconciled existing COMPLETE payment')
    if sub:db.session.commit()
    return sub

def entitlement_for(customer_id):
    sub=Subscription.query.filter_by(customer_id=customer_id).first()
    if not sub:return False,None
    if sub.state not in ('ACTIVE','GRACE_PERIOD') or getattr(sub,'access_source',None)!='PAID':
        reconciled=reconcile_customer_payment(customer_id)
        if reconciled:sub=reconciled
    refresh_subscription(sub);return sub.state in ('TRIAL','ACTIVE','GRACE_PERIOD'),sub

@bp.before_app_request
def enforce_subscription_access():
    if not current_user.is_authenticated:return None
    if current_user.role=='platform_admin':return None
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
    # A phone QR opens this public HTTPS page directly. The one-time code only
    # identifies the pending registration; explicit consent is still required
    # before a permanent device token is issued.
    code = re.sub(r'[^A-Z0-9-]', '', str(request.args.get('code', '')).strip().upper())[:9]
    return render_template("mobile_tracker.html", registration_code=code)


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
        "Sitemap: https://assettrack360.wykiesautomation.co.za/sitemap.xml\n"
    )
    return body,200,{"Content-Type":"text/plain; charset=utf-8"}
@bp.get("/sitemap.xml")
def sitemap_xml():
    base_url="https://assettrack360.wykiesautomation.co.za"
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
    if not WorkspaceProfile.query.filter_by(customer_id=user.customer_id).first():
        db.session.add(WorkspaceProfile(customer_id=user.customer_id,contact_email=user.email,billing_email=user.email))
    if not Subscription.query.filter_by(customer_id=user.customer_id).first():
        plan=SubscriptionPlan.query.filter_by(code='monitor',active=True).first()
        if not plan:
            plan=SubscriptionPlan.query.filter_by(active=True).order_by(SubscriptionPlan.monthly_price).first()
        if not plan:
            db.session.rollback();flash('Account verified, but no subscription plan is available. Contact support.','error');return redirect(url_for('main.login'))
        started=utcnow()
        db.session.add(Subscription(customer_id=user.customer_id,plan_id=plan.id,state='TRIAL',access_source='TRIAL',trial_started_at=started,trial_ends_at=started+timedelta(hours=72)))
    db.session.commit();flash('Email verified. Your 72-hour AssetTrack 360 trial is now active.','ok');return redirect(url_for('main.login'))

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
        if valid:
            login_user(u)
            return redirect(url_for('admin.dashboard') if u.role=='platform_admin' else url_for('main.dashboard'))
        flash('Invalid login.','error')
    return render_template('auth.html',mode='login')

@bp.get('/logout')
@login_required
def logout():logout_user();return redirect(url_for('main.login'))

@bp.get('/assets')
@login_required
def assets_register():
    customer_id=tenant_id();now=utcnow();assets=Asset.query.filter_by(customer_id=customer_id).order_by(Asset.name).all();rows=[]
    for asset in assets:
        device=active_device_for(asset);status=asset_status(asset);primary='Waiting for telemetry';secondary='No live data'
        signals={x.key:latest_reading(x.id) for x in SignalDefinition.query.filter_by(customer_id=customer_id,asset_id=asset.id,enabled=True).all()}
        if asset.asset_type=='TRACKER':
            loc=Location.query.filter_by(customer_id=customer_id,asset_id=asset.id).order_by(desc(Location.sampled_at)).first()
            primary=('Moving' if loc and float(loc.speed_kmh or 0)>=3 else 'Stationary') if loc else 'Waiting for position';secondary=f'{float(loc.speed_kmh or 0):.0f} km/h' if loc else 'No GPS telemetry'
        elif asset.asset_type=='TANK':
            volume=signals.get('volume_l');level=signals.get('level_percent');primary=f'{float(volume.value):,.0f} {asset.capacity_unit or "L"}' if volume else 'Waiting for volume';secondary=f'{float(level.value):.0f}% full' if level else 'Waiting for level'
        elif asset.asset_type=='VIBRATION':
            vibration=signals.get('vibration_rms');temperature=signals.get('temperature_c');primary=f'{float(vibration.value):.1f} mm/s' if vibration else 'Waiting for vibration';secondary=f'{float(temperature.value):.1f} °C' if temperature else 'Waiting for temperature'
        else:
            latest=next((x for x in signals.values() if x),None);primary=f'{float(latest.value):.2f} {latest.unit or ""}'.strip() if latest else 'Waiting for telemetry';secondary='Universal monitoring'
        last_seen=asset.last_seen or (device.last_seen if device else None);age='Never'
        if last_seen:
            seconds=max(0,int((now-aware(last_seen)).total_seconds()));age='Now' if seconds<60 else f'{seconds//60} min ago' if seconds<3600 else f'{seconds//3600} h ago' if seconds<86400 else f'{seconds//86400} d ago'
        rows.append({'asset':asset,'device':device,'status':status,'primary':primary,'secondary':secondary,'age':age})
    return render_template('assets_register.html',rows=rows)

@bp.route('/onboarding',methods=['GET','POST'])
@login_required
def onboarding():
    customer_id=tenant_id()
    sites=Site.query.filter_by(customer_id=customer_id).order_by(Site.name,Site.id).all()
    if request.method=='POST':
        asset_name=request.form.get('asset_name','').strip()
        submitted_asset_type=request.form.get('asset_type','').strip().upper()
        solution=request.form.get('primary_solution_profile','').strip().upper()
        monitoring_visual=request.form.get('monitoring_visual','GENERAL_MONITORING').strip().upper()
        visual_types={
            'EASY_TANK':'TANK','POINT_TANK':'TANK','ROUND_TANK':'TANK',
            'TEMPERATURE':'GENERIC','FLOW':'GENERIC','PRESSURE':'GENERIC',
            'GENERAL_MONITORING':'GENERIC','FLOW_TOTALIZER':'GENERIC',
            'STATUS_INDICATOR':'GENERIC','LIVE_TREND':'GENERIC',
        }
        if monitoring_visual not in visual_types:
            flash('Select a valid monitoring visual.','error')
            return redirect(url_for('main.onboarding'))
        use_site=request.form.get('use_site')=='on'

        # The customer-facing cards are solution profiles. Internally the
        # existing dashboard still uses the four stable asset experiences.
        solution_types={
            'TANK_MONITORING':'TANK',
            'VEHICLE_FLEET_TRACKING':'TRACKER',
            'FLEET_TRACKING':'TRACKER',
            'MACHINE_MONITORING':'VIBRATION',
            'PUMP_MONITORING':'VIBRATION',
            'MOTOR_MONITORING':'VIBRATION',
            'GENERIC_IO':'GENERIC',
            'GENERIC_I_O':'GENERIC',
        }
        direct_types={'TANK','TRACKER','VIBRATION','GENERIC'}
        card_aliases={'MACHINE':'VIBRATION','PUMP':'VIBRATION','MOTOR':'VIBRATION'}
        asset_type=solution_types.get(solution) or card_aliases.get(submitted_asset_type) or submitted_asset_type or visual_types.get(monitoring_visual)

        if len(asset_name)<2 or len(asset_name)>120:
            flash('Asset name must be between 2 and 120 characters.','error')
            return redirect(url_for('main.onboarding'))
        if asset_type not in direct_types:
            flash('Select a valid solution profile.','error')
            return redirect(url_for('main.onboarding'))

        # If an updated form supplies a solution profile, prevent a forged or
        # stale asset_type value from creating the wrong dashboard experience.
        expected_type=solution_types.get(solution)
        if asset_type!='TANK' and monitoring_visual in ('EASY_TANK','POINT_TANK','ROUND_TANK'):
            monitoring_visual='GENERAL_MONITORING'
        if expected_type and expected_type!=asset_type:
            flash('The selected solution profile does not match the asset experience.','error')
            return redirect(url_for('main.onboarding'))

        capacity=None
        capacity_unit=None
        tank_shape=request.form.get('tank_shape','').strip().upper() or None
        level_source=request.form.get('level_source','').strip().upper() or None
        if asset_type=='TANK':
            try:
                capacity=float(request.form.get('capacity',''))
            except (TypeError,ValueError):
                flash('Enter a valid tank capacity greater than zero.','error')
                return redirect(url_for('main.onboarding'))
            if capacity<=0 or capacity>1_000_000_000:
                flash('Enter a valid tank capacity greater than zero.','error')
                return redirect(url_for('main.onboarding'))
            capacity_unit=request.form.get('capacity_unit','L').strip()[:16] or 'L'
            if not tank_shape:
                flash('Select the tank shape.','error')
                return redirect(url_for('main.onboarding'))
            if not level_source:
                flash('Select the tank level source.','error')
                return redirect(url_for('main.onboarding'))

        site=None
        if use_site:
            new_site_name=request.form.get('new_site_name','').strip()
            if new_site_name:
                site=Site.query.filter(Site.customer_id==customer_id,db.func.lower(Site.name)==new_site_name.lower()).first()
                if site:
                    flash('That site already exists. Select it from the existing site list.','error')
                    return redirect(url_for('main.onboarding'))
                if len(new_site_name)<2 or len(new_site_name)>120:
                    flash('New site name must be between 2 and 120 characters.','error')
                    return redirect(url_for('main.onboarding'))
                site=Site(customer_id=customer_id,name=new_site_name,location=request.form.get('new_site_location','').strip() or None)
                db.session.add(site);db.session.flush()
            else:
                site=Site.query.filter_by(id=request.form.get('site_id',type=int),customer_id=customer_id).first()
                if not site:
                    flash('Select an existing site or enter a new site name.','error')
                    return redirect(url_for('main.onboarding'))
        else:
            site=Site.query.filter(Site.customer_id==customer_id,db.func.lower(Site.name)=='my assets').order_by(Site.id).first()
            if not site:
                site=Site(customer_id=customer_id,name='My Assets',location=None)
                db.session.add(site);db.session.flush()

        metadata={
            'onboarding_source':'SIMPLE_ADD_ASSET',
            'monitoring_visual':monitoring_visual,
            'primary_solution_profile':solution or {
                'TANK':'TANK_MONITORING','TRACKER':'VEHICLE_FLEET_TRACKING',
                'VIBRATION':'MACHINE_MONITORING','GENERIC':'GENERIC_IO'
            }[asset_type],
        }
        if submitted_asset_type and submitted_asset_type!=asset_type:
            metadata['selected_solution_card']=submitted_asset_type
        if asset_type=='TANK':
            metadata.update({'tank_shape':{'EASY_TANK':'VERTICAL_CYLINDER','POINT_TANK':'CUSTOM_STRAPPING','ROUND_TANK':'HORIZONTAL_CYLINDER'}.get(monitoring_visual,tank_shape),'level_source':level_source})

        try:
            asset=Asset(customer_id=customer_id,site_id=site.id,name=asset_name,
                        asset_type=asset_type,status='UNASSIGNED',capacity=capacity,
                        capacity_unit=capacity_unit or 'L',metadata_json=metadata)
            db.session.add(asset);db.session.flush();create_default_signals(asset);db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Simple asset onboarding failed customer_id=%s',customer_id)
            flash('The asset could not be created safely. No partial changes were saved.','error')
            return redirect(url_for('main.onboarding'))

        flash(f'{asset.name} created. Continue by selecting and connecting the physical device.','ok')
        return redirect(url_for('main.connect_device',asset_id=asset.id))
    return render_template('onboarding.html',sites=sites)

def create_default_signals(asset):
    visual=(asset.metadata_json or {}).get('monitoring_visual','GENERAL_MONITORING')
    profiles={
      'TANK':[('level_percent','Tank Level','LEVEL','%','tank',20,10,90,95),('volume_l','Volume','LEVEL','L','numeric',None,None,None,None),('battery_v','Battery','VOLTAGE','V','battery',3.6,3.4,None,None),('solar_v','Solar','VOLTAGE','V','solar',None,None,None,None)],
      'TRACKER':[('speed_kmh','Speed','SPEED','km/h','numeric',None,None,100,120),('battery_v','Battery','VOLTAGE','V','battery',3.6,3.4,None,None)],
      'VIBRATION':[('vibration_rms','Vibration RMS','VIBRATION','mm/s','vibration',None,None,4.5,7.1),('temperature_c','Temperature','TEMPERATURE','°C','temperature',None,None,70,85),('battery_v','Battery','VOLTAGE','V','battery',3.6,3.4,None,None)],
      'GENERIC':[('analog_1',{'TEMPERATURE':'Temperature','FLOW':'Flow','PRESSURE':'Pressure','FLOW_TOTALIZER':'Flow Totalizer','STATUS_INDICATOR':'Status','LIVE_TREND':'Live Trend'}.get(visual,'Universal Input'),{'TEMPERATURE':'TEMPERATURE','FLOW':'FLOW','PRESSURE':'PRESSURE','FLOW_TOTALIZER':'COUNT','STATUS_INDICATOR':'STATE'}.get(visual,'CUSTOM'),{'TEMPERATURE':'°C','FLOW':'L/min','PRESSURE':'bar','FLOW_TOTALIZER':'L'}.get(visual,''),{'TEMPERATURE':'temperature','FLOW':'flow','PRESSURE':'pressure','FLOW_TOTALIZER':'flow_totalizer','STATUS_INDICATOR':'status','LIVE_TREND':'trend'}.get(visual,'numeric'),None,None,None,None)]}
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
            first=next((r for r in sigs.values() if r),None);l1='LATEST VALUE';v1=f'{first.value:.2f} {first.unit or ""}' if first else 'Waiting';l2='INPUTS' if device else 'DEVICE';v2=str(len(sigs)) if device else 'No device connected'
        battery_reading=sigs.get('battery_percent') or sigs.get('battery_v')
        battery_text='Not reported';battery_state='UNKNOWN'
        if battery_reading:
            if battery_reading.unit=='%' or battery_reading.signal_id==getattr(next((x for x in SignalDefinition.query.filter_by(asset_id=asset.id) if x.key=='battery_percent'),None),'id',None):
                battery_value=max(0,min(100,float(battery_reading.value)));battery_text=f'{battery_value:.0f}%';battery_state='CRITICAL' if battery_value<=10 else 'LOW' if battery_value<=25 else 'GOOD'
            else:
                battery_text=f'{float(battery_reading.value):.2f} {battery_reading.unit or "V"}';battery_state='REPORTED'
        last_address='No location received yet'
        loc_for_summary=Location.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).order_by(desc(Location.sampled_at)).first()
        if loc_for_summary:
            geo=reverse_geocode(loc_for_summary.latitude,loc_for_summary.longitude,accuracy_m=loc_for_summary.accuracy_m or 0)
            last_address=geo.get('possible_address') or f'{loc_for_summary.latitude:.5f}, {loc_for_summary.longitude:.5f}'
        seen='No telemetry'
        if asset.last_seen:
            mins=max(0,int((now-aware(asset.last_seen)).total_seconds()//60));seen='Just now' if mins<1 else f'{mins} min ago' if mins<60 else f'{mins//60} h ago'
        cards.append({'asset':asset,'status':status,'metric_1_label':l1,'metric_1_value':v1,'metric_2_label':l2,'metric_2_value':v2,'device_type':device.device_type if device else 'No device assigned','last_seen':seen,'battery_text':battery_text,'battery_state':battery_state,'last_address':last_address})
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

@bp.get('/sites')
@login_required
def sites():
    customer_id=tenant_id();records=Site.query.filter_by(customer_id=customer_id).order_by(Site.name,Site.id).all();items=[{'site':s,'asset_count':Asset.query.filter_by(customer_id=customer_id,site_id=s.id).count()} for s in records]
    return render_template('sites.html',items=items)
@bp.post('/sites/<int:site_id>/rename')
@login_required
def rename_site(site_id):
    site=Site.query.filter_by(id=site_id,customer_id=tenant_id()).first_or_404();name=request.form.get('name','').strip();location=request.form.get('location','').strip()
    if len(name)<2 or len(name)>120:flash('Site name must be between 2 and 120 characters.','error');return redirect(url_for('main.sites'))
    duplicate=Site.query.filter(Site.customer_id==tenant_id(),Site.id!=site.id,db.func.lower(Site.name)==name.lower()).first()
    if duplicate:flash('Another site already uses that name.','error');return redirect(url_for('main.sites'))
    site.name=name;site.location=location or None;db.session.commit();flash('Site updated.','ok');return redirect(url_for('main.sites'))
@bp.post('/sites/<int:site_id>/delete')
@login_required
def delete_site(site_id):
    customer_id=tenant_id();site=Site.query.filter_by(id=site_id,customer_id=customer_id).first_or_404();confirm_name=request.form.get('confirm_name','').strip();confirm_word=request.form.get('confirm_word','').strip().upper()
    if confirm_name!=site.name or confirm_word!='DELETE':flash('Delete confirmation did not match.','error');return redirect(url_for('main.sites'))
    count=Asset.query.filter_by(customer_id=customer_id,site_id=site.id).count()
    if count:flash(f'Site still contains {count} asset(s). Move or delete them first.','error');return redirect(url_for('main.sites'))
    name=site.name;db.session.delete(site);db.session.commit();flash(f'Site {name} deleted.','ok');return redirect(url_for('main.sites'))
@bp.get('/asset-device-setup')
@login_required
def asset_device_setup():
    cid=tenant_id();sites=Site.query.filter_by(customer_id=cid).order_by(Site.name).all();assets=Asset.query.filter_by(customer_id=cid).order_by(Asset.name).all();devices=Device.query.filter_by(customer_id=cid).order_by(Device.device_uid).all()
    links=[{'asset':a,'device':Device.query.filter_by(customer_id=cid,asset_id=a.id,active=True).first()} for a in assets]
    return render_template('asset_device_setup.html',sites=sites,assets=assets,devices=devices,links=links)
@bp.post('/asset-device-setup/link')
@login_required
def link_asset_device():
    cid=tenant_id();a=Asset.query.filter_by(id=request.form.get('asset_id',type=int),customer_id=cid).first_or_404();d=Device.query.filter_by(id=request.form.get('device_id',type=int),customer_id=cid).first_or_404()
    if d.asset_id and d.asset_id!=a.id:flash('Device is linked to another asset. Unlink it first.','error');return redirect(url_for('main.asset_device_setup'))
    if Device.query.filter(Device.customer_id==cid,Device.asset_id==a.id,Device.active.is_(True),Device.id!=d.id).first():flash('Asset already has an active device. Use Replace Device.','error');return redirect(url_for('main.asset_device_setup'))
    d.asset_id=a.id;d.active=True;db.session.commit();flash('Asset and device linked.','ok');return redirect(url_for('main.asset_device_setup'))
@bp.post('/asset-device-setup/unlink/<int:device_id>')
@login_required
def unlink_asset_device(device_id):
    d=Device.query.filter_by(id=device_id,customer_id=tenant_id()).first_or_404();d.asset_id=None;DeviceChannelAssignment.query.filter_by(device_id=d.id).update({'enabled':False},synchronize_session=False);db.session.commit();flash('Device unlinked. Asset history retained.','ok');return redirect(url_for('main.asset_device_setup'))
@bp.post('/asset-device-setup/replace')
@login_required
def replace_asset_device():
    cid=tenant_id();a=Asset.query.filter_by(id=request.form.get('asset_id',type=int),customer_id=cid).first_or_404();new=Device.query.filter_by(id=request.form.get('new_device_id',type=int),customer_id=cid).first_or_404()
    if new.asset_id and new.asset_id!=a.id:flash('Replacement device is linked elsewhere.','error');return redirect(url_for('main.asset_device_setup'))
    old=Device.query.filter(Device.customer_id==cid,Device.asset_id==a.id,Device.active.is_(True),Device.id!=new.id).first()
    if old:old.active=False;old.asset_id=None;DeviceChannelAssignment.query.filter_by(device_id=old.id).update({'enabled':False},synchronize_session=False)
    new.asset_id=a.id;new.active=True;db.session.commit();flash('Device replaced. Asset and history retained.','ok');return redirect(url_for('main.asset_device_setup'))

@bp.get('/admin/test-data-cleanup')
@login_required
def test_data_cleanup():
    customer_id=tenant_id()
    assets=Asset.query.filter_by(customer_id=customer_id).order_by(Asset.name,Asset.id).all();items=[]
    for asset in assets:
        items.append({'asset':asset,'active_device':active_device_for(asset),'devices':Device.query.filter_by(customer_id=customer_id,asset_id=asset.id).count(),'locations':Location.query.filter_by(customer_id=customer_id,asset_id=asset.id).count(),'readings':Reading.query.filter_by(customer_id=customer_id,asset_id=asset.id).count(),'alarms':Alarm.query.filter_by(customer_id=customer_id,asset_id=asset.id).count()})
    sites=Site.query.filter_by(customer_id=customer_id).order_by(Site.name,Site.id).all()
    site_items=[{'site':site,'asset_count':Asset.query.filter_by(customer_id=customer_id,site_id=site.id).count()} for site in sites]
    return render_template('test_data_cleanup.html',items=items,site_items=site_items)
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
        customer_id=tenant_id()
        device_ids=[row.id for row in Device.query.filter_by(customer_id=customer_id,asset_id=asset.id).all()]
        DeviceCommand.query.filter_by(customer_id=customer_id,asset_id=asset.id).delete(synchronize_session=False)
        advanced_table=db.session.execute(text("SELECT to_regclass('public.advanced_access_grant')")).scalar()
        if advanced_table and device_ids:
            db.session.execute(text('DELETE FROM advanced_access_grant WHERE device_id = ANY(:device_ids)'),{'device_ids':device_ids})
        for model in (Reading,Location,Alarm,CoreAlarmState,DataDeletionRequest,MobileConsent,MobileTrackerRegistration,SecurityAuditEvent,AssetFeatureOverride,AssetAlertSettings,IntegrationSignalMapping,UniversalSourceMapping,MqttTopicMapping):
            model.query.filter_by(customer_id=customer_id,asset_id=asset.id).delete(synchronize_session=False)
        if request.form.get('action','delete_all')=='clear_history':
            asset.last_seen=None;asset.status='UNASSIGNED';db.session.commit();return jsonify(ok=True,message='History cleared.')
        # Delete device-owned policy/config rows before deleting devices.
        # PostgreSQL correctly blocks the device delete while these FKs still reference it.
        if device_ids:
            DeviceTrendPolicy.query.filter(
                DeviceTrendPolicy.customer_id==customer_id,
                DeviceTrendPolicy.device_id.in_(device_ids),
            ).delete(synchronize_session=False)
            SignalTrendPolicy.query.filter(
                SignalTrendPolicy.customer_id==customer_id,
                SignalTrendPolicy.device_id.in_(device_ids),
            ).delete(synchronize_session=False)
            DeviceChannelAssignment.query.filter(
                DeviceChannelAssignment.customer_id==customer_id,
                DeviceChannelAssignment.device_id.in_(device_ids),
            ).delete(synchronize_session=False)
        Device.query.filter_by(customer_id=customer_id,asset_id=asset.id).delete(synchronize_session=False)
        SignalDefinition.query.filter_by(customer_id=customer_id,asset_id=asset.id).delete(synchronize_session=False)
        name=asset.name;db.session.delete(asset);db.session.commit();return jsonify(ok=True,message=f'{name} deleted.')
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception('Cleanup failed asset_id=%s',asset_id)
        return jsonify(ok=False,error=f'Database cleanup failed safely: {type(exc).__name__}. No partial deletion committed.'),500
@bp.post('/admin/test-data-cleanup/delete-site')
@login_required
def delete_test_site():
    customer_id=tenant_id()
    site_id=request.form.get('site_id',type=int)
    confirm_name=request.form.get('confirm_name','').strip()
    confirm_word=request.form.get('confirm_word','').strip().upper()
    site=Site.query.filter_by(id=site_id,customer_id=customer_id).first()
    if not site:return jsonify(ok=False,error='Site not found.'),404
    if confirm_name!=site.name or confirm_word!='DELETE':return jsonify(ok=False,error='Confirmation did not match.'),400
    asset_count=Asset.query.filter_by(customer_id=customer_id,site_id=site.id).count()
    if asset_count:return jsonify(ok=False,error=f'Site still contains {asset_count} asset(s). Delete or move them first.'),409
    try:
        name=site.name
        db.session.delete(site)
        db.session.commit()
        return jsonify(ok=True,message=f'Site {name} deleted.')
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception('Site cleanup failed site_id=%s',site_id)
        return jsonify(ok=False,error=f'Site deletion failed safely: {type(exc).__name__}. No changes committed.'),500
def _distance_km(a,b):
    import math
    lat1,lon1,lat2,lon2=map(math.radians,(a.latitude,a.longitude,b.latitude,b.longitude))
    value=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2*6371.0088*math.asin(min(1,math.sqrt(value)))

def analyse_tracking_points(rows):
    """Historical adapter using the same strict evidence engine as Safety Twin."""
    strict = analyse_safety_twin_points(rows)
    rejected = list(strict['rejected']) + [dict(item, reason='STATIONARY_DRIFT') for item in strict['drift']]
    rejection_counts = {}
    for item in rejected:
        reason = item.get('reason', 'REJECTED')
        rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
    accepted = list(strict['movement'])
    segments = [accepted] if len(accepted) > 1 else []
    return {
        'accepted': accepted,
        'rejected': rejected,
        'segments': segments,
        'journeys': [],
        'stops': [],
        'total_km': strict['distance_km'],
        'distance_km': strict['distance_km'],
        'max_speed': strict['maximum_speed'],
        'maximum_speed': strict['maximum_speed'],
        'moving_minutes': strict['movement_minutes'],
        'movement_minutes': strict['movement_minutes'],
        'stopped_minutes': strict['stationary_minutes'],
        'stationary_minutes': strict['stationary_minutes'],
        'rejection_counts': rejection_counts,
        'confidence': strict['confidence'],
        'state': strict['state'],
        'raw_count': strict['raw_count'],
        'movement_count': strict['movement_count'],
        'drift_count': strict['drift_count'],
        'rejected_count': strict['rejected_count'],
    }

def _distance_dict(a,b):
    import math
    lat1,lon1,lat2,lon2=map(math.radians,(a['latitude'],a['longitude'],b['latitude'],b['longitude']))
    value=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2*6371.0088*math.asin(min(1,math.sqrt(value)))

def tracking_hmi_context(asset,device,profile,location_count=0,motion_count=0):
    asset_type=str(asset.asset_type or '').upper();caps={str(x).upper() for x in (device.capabilities or [])} if device else set();channels=list((profile or {}).get('channels',[]));keys={str(x.get('key') or '').lower() for x in channels};types={str(x.get('signal_type') or '').upper() for x in channels}
    has_gps=bool(device and ('GPS' in caps or 'GNSS' in caps or 'gps_fix' in keys or 'gps_location' in keys or 'LOCATION' in types));has_motion=bool(caps & {'MOTION_SENSORS','ACCELEROMETER','IMU','HARSH_DRIVING'});has_impact=bool(caps & {'IMPACT_SENSOR','CRASH_DETECTION'});has_tilt=bool(caps & {'ORIENTATION_SENSOR','TILT_SENSOR','ROLLOVER_DETECTION'});has_ignition=bool(caps & {'IGNITION_STATE','IGNITION_INPUT'})
    context='TANK' if asset_type=='TANK' else 'MOBILE_TANK' if asset_type in {'MOBILE_TANK','BOWSER','TANKER'} else 'VEHICLE' if asset_type in {'TRACKER','VEHICLE','CAR','TRUCK'} else 'ASSET'
    labels={
      'TANK':{'page_title':'Tank Location & Movement','overview_title':'Tank Location Overview','status_title':'Tank Location Status','current_speed':'Current Movement Speed','maximum_speed':'Maximum Movement Speed','history':'Tank Movement History','events':'Recent Movement & Safety Events'},
      'MOBILE_TANK':{'page_title':'Mobile Tank Inventory & Tracking','overview_title':'Mobile Tank Overview','status_title':'Mobile Tank Tracking Status','current_speed':'Current Speed','maximum_speed':'Maximum Movement Speed','history':'Movement & Route History','events':'Recent Movement & Safety Events'},
      'VEHICLE':{'page_title':'Fleet Tracking & Safety','overview_title':'Vehicle Overview','status_title':'Vehicle Tracking Status','current_speed':'Current Speed','maximum_speed':'Trip Maximum Speed','history':'Journey History','events':'Recent Driving & Safety Events'},
      'ASSET':{'page_title':'Asset Location & Movement','overview_title':'Asset Location Overview','status_title':'Asset Location Status','current_speed':'Current Movement Speed','maximum_speed':'Maximum Movement Speed','history':'Location History','events':'Recent Movement & Safety Events'}}[context]
    features={'gps':has_gps,'speed':has_gps,'maximum_speed':has_gps,'route_history':has_gps and location_count>0,'geofence':has_gps,'unexpected_movement':has_gps,'impact':has_impact,'tilt':has_tilt,'harsh_driving':has_motion and context=='VEHICLE','driving_score':has_motion and context=='VEHICLE' and motion_count>=5 and location_count>=10,'ignition':has_ignition}
    return {'context':context,'labels':labels,'features':features,'gps_source_uid':device.device_uid if device else None,'profile_name':(profile or {}).get('display_name','Profile not reported')}

@bp.get('/fleet-tracking')
@login_required
def fleet_tracking():
    asset=Asset.query.filter_by(customer_id=tenant_id(),asset_type='TRACKER').order_by(Asset.name,Asset.id).first()
    if not asset:
        flash('Create or assign a tracking asset before opening Fleet Tracking.','error')
        return redirect(url_for('main.onboarding'))
    return redirect(url_for('main.safety_twin',asset_id=asset.id))

@bp.get('/asset/<int:asset_id>/tracking')
@login_required
def tracking_history(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404()
    now=utcnow();preset=request.args.get('range','today')
    # Customer-facing "Today" follows South African local time (UTC+02:00),
    # while timestamps remain stored and queried in UTC.
    sast=timezone(timedelta(hours=2));local_now=now.astimezone(sast)
    if preset=='24h':start=now-timedelta(hours=24)
    elif preset=='7d':start=now-timedelta(days=7)
    elif request.args.get('from'):
        try:start=datetime.fromisoformat(request.args['from']).replace(tzinfo=sast).astimezone(timezone.utc)
        except ValueError:start=local_now.replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc)
    else:start=local_now.replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc)
    if request.args.get('to'):
        try:end=datetime.fromisoformat(request.args['to']).replace(tzinfo=sast).astimezone(timezone.utc)
        except ValueError:end=now
    else:end=now
    if start>end:start,end=end,start
    rows=Location.query.filter(Location.customer_id==tenant_id(),Location.asset_id==asset.id,Location.sampled_at>=start,Location.sampled_at<=end).order_by(Location.sampled_at).limit(10000).all()
    analysis=analyse_tracking_points(rows)
    last_known=Location.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).order_by(desc(Location.sampled_at)).first()
    safety=(asset.metadata_json or {}).get('tracking_safety',{}) or {}
    zones=safety.get('zones',[]) if isinstance(safety.get('zones',[]),list) else []
    speed_limit=float(safety.get('speed_limit_kmh') or 0)
    defaults={'impact_crash':False,'rollover':False,'harsh_driving':True,'unauthorized_movement':False,'power_tamper':False}
    saved_rules=safety.get('rules',{}) if isinstance(safety.get('rules',{}),dict) else {}
    rules={key:bool(saved_rules.get(key,default)) for key,default in defaults.items()}
    events=[];zone_evaluations=[]
    evaluation_points=analysis['points'] or ([{'latitude':last_known.latitude,'longitude':last_known.longitude,'speed':float(last_known.speed_kmh or 0),'timestamp':aware(last_known.sampled_at).strftime('%Y-%m-%d %H:%M:%S UTC')}] if last_known else [])
    for point in analysis['points']:
        if speed_limit and point['speed']>speed_limit:events.append({'type':'SPEEDING','severity':'HIGH','message':f"Speed {round(point['speed'])} km/h exceeded {round(speed_limit)} km/h",'timestamp':point['timestamp'],'latitude':point['latitude'],'longitude':point['longitude']})
    current_point=evaluation_points[-1] if evaluation_points else None
    if current_point:
        for zone in zones:
            try:
                center={'latitude':float(zone['latitude']),'longitude':float(zone['longitude'])};dist=_distance_dict(current_point,center)*1000;radius=float(zone.get('radius_m',250));inside=dist<=radius;rule='KEEP_OUT' if zone.get('rule')=='KEEP_OUT' else 'KEEP_IN';breach=(rule=='KEEP_IN' and not inside) or (rule=='KEEP_OUT' and inside)
                item={'name':str(zone.get('name') or 'Safety Zone'),'rule':rule,'inside':inside,'breach':breach,'distance_m':round(dist),'radius_m':round(radius)};zone_evaluations.append(item)
                if breach:events.append({'type':'GEOFENCE','severity':'CRITICAL','message':f"{item['name']} {rule.replace('_',' ').lower()} breach",'timestamp':current_point['timestamp'],'latitude':current_point['latitude'],'longitude':current_point['longitude']})
            except (TypeError,ValueError,KeyError):pass
    breached=next((x for x in zone_evaluations if x['breach']),None)
    selected_zone=breached or next((x for x in zone_evaluations if x['inside']),None) or (zone_evaluations[0] if zone_evaluations else None)
    if not zones:geofence={'state':'NOT CONFIGURED','warning':False,'name':None}
    elif not current_point:geofence={'state':'WAITING FOR GPS','warning':False,'name':zones[0].get('name')}
    elif selected_zone:geofence={'state':'OUTSIDE' if selected_zone['breach'] else 'INSIDE','warning':selected_zone['breach'],'name':selected_zone['name'],'detail':selected_zone}
    else:geofence={'state':'UNKNOWN','warning':False,'name':None}
    motion_rows=Live360SafetyEvent.query.filter(Live360SafetyEvent.customer_id==tenant_id(),Live360SafetyEvent.asset_id==asset.id,Live360SafetyEvent.sampled_at>=start,Live360SafetyEvent.sampled_at<=end).order_by(Live360SafetyEvent.sampled_at).limit(500).all()
    event_rule={'HARSH_BRAKING':'harsh_driving','SEVERE_BRAKING':'harsh_driving','HARSH_ACCELERATION':'harsh_driving','POSSIBLE_ACCIDENT':'impact_crash','POSSIBLE_ACCIDENT_CANCELLED':'impact_crash','CRASH_DETECTED':'impact_crash','ROLLOVER_DETECTED':'rollover','ABNORMAL_TILT':'rollover','UNEXPECTED_MOVEMENT':'unauthorized_movement','EMERGENCY_ALERT':'impact_crash'}
    motion_rows=[x for x in motion_rows if rules.get(event_rule.get(x.event_type,''),True)]
    motion_events=[{'id':x.id,'type':x.event_type,'severity':x.severity,'status':x.status,'confidence':round(float(x.confidence or 0)*100),'timestamp':aware(x.sampled_at).strftime('%Y-%m-%d %H:%M:%S UTC'),'latitude':x.latitude,'longitude':x.longitude,'speed_before_kmh':x.speed_before_kmh,'speed_after_kmh':x.speed_after_kmh,'peak_acceleration_ms2':x.peak_acceleration_ms2,'deceleration_ms2':x.deceleration_ms2} for x in motion_rows]
    motion_counts={key:sum(1 for x in motion_rows if x.event_type==key and x.status!='CANCELLED_BY_USER') for key in ('HARSH_BRAKING','SEVERE_BRAKING','HARSH_ACCELERATION','POSSIBLE_ACCIDENT','CRASH_DETECTED','ROLLOVER_DETECTED','ABNORMAL_TILT','UNEXPECTED_MOVEMENT','EMERGENCY_ALERT')}
    motion_counts['CANCELLED']=sum(1 for x in motion_rows if x.status=='CANCELLED_BY_USER')
    device=active_device_for(asset);profile=profile_for_device(device) if device else None;caps=set(str(x).upper() for x in (device.capabilities or [])) if device else set();hmi=tracking_hmi_context(asset,device,profile,len(analysis['points']),len(motion_rows))
    support={'impact_crash':hmi['features']['impact'],'rollover':hmi['features']['tilt'],'harsh_driving':hmi['features']['harsh_driving'],'unauthorized_movement':hmi['features']['unexpected_movement'],'power_tamper':any(x in caps for x in ('EXTERNAL_POWER','TAMPER_INPUT','POWER_TAMPER'))}
    enough_score_data=hmi['features']['driving_score']
    driving_score=max(0,min(100,100-motion_counts['HARSH_BRAKING']*3-motion_counts['SEVERE_BRAKING']*6-motion_counts['HARSH_ACCELERATION']*2-motion_counts['POSSIBLE_ACCIDENT']*15-motion_counts['CRASH_DETECTED']*25-motion_counts['ROLLOVER_DETECTED']*35-motion_counts['EMERGENCY_ALERT']*10)) if enough_score_data else None
    episodes=[]
    for event in events:
        key=(event['type'],event['message'])
        if not episodes or episodes[-1].get('_key')!=key:event['_key']=key;episodes.append(event)
    for event in episodes:event.pop('_key',None)
    latest_for_map=analysis['last'] or ({'latitude':last_known.latitude,'longitude':last_known.longitude,'speed':float(last_known.speed_kmh or 0),'accuracy':float(last_known.accuracy_m or 0),'timestamp':aware(last_known.sampled_at).strftime('%Y-%m-%d %H:%M:%S UTC'),'historical':True,'outside_selected_range':True} if last_known and not(abs(float(last_known.latitude))<.000001 and abs(float(last_known.longitude))<.000001) else None)
    possible_address=None
    if latest_for_map:
        geocode=reverse_geocode(latest_for_map['latitude'],latest_for_map['longitude'],accuracy_m=latest_for_map.get('accuracy') or 0);possible_address=geocode.get('possible_address') or 'Possible address unavailable'
    return render_template('tracking_history.html',asset=asset,start=start,end=end,analysis=analysis,safety=safety,zones=zones,safety_events=episodes[-100:],motion_events=motion_events,motion_counts=motion_counts,driving_score=driving_score,can_manage=current_user.role in ('customer_admin','platform_admin'),last_known=latest_for_map,possible_address=possible_address,geofence=geofence,rules=rules,support=support,device=device,profile=profile,hmi=hmi)

@bp.post('/asset/<int:asset_id>/tracking/safety')
@login_required
def tracking_safety_save(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404()
    if current_user.role not in ('customer_admin','platform_admin'):abort(403)
    try:
        speed=max(0,min(250,float(request.form.get('speed_limit_kmh') or 0)))
        zones=json.loads(request.form.get('zones_json') or '[]');clean=[]
        if not isinstance(zones,list):raise ValueError('zones must be a list')
        for zone in zones[:20]:clean.append({'name':str(zone.get('name') or 'Safety Zone')[:80],'latitude':max(-90,min(90,float(zone['latitude']))),'longitude':max(-180,min(180,float(zone['longitude']))),'radius_m':max(50,min(50000,float(zone.get('radius_m') or 250))),'rule':'KEEP_OUT' if zone.get('rule')=='KEEP_OUT' else 'KEEP_IN'})
    except (ValueError,TypeError,KeyError,json.JSONDecodeError):flash('Safety setup contains invalid zone data.','error');return redirect(url_for('main.tracking_history',asset_id=asset.id))
    rules={key:request.form.get('rule_'+key)=='on' for key in ('impact_crash','rollover','harsh_driving','unauthorized_movement','power_tamper')}
    meta=dict(asset.metadata_json or {});meta['tracking_safety']={'speed_limit_kmh':speed,'zones':clean,'rules':rules,'updated_at':utcnow().isoformat(),'updated_by':current_user.id};asset.metadata_json=meta
    db.session.add(asset);db.session.commit();flash(f'Tracking safety rules saved. {len(clean)} geofence zone(s) stored.','ok');return redirect(url_for('main.tracking_history',asset_id=asset.id))

@bp.get('/asset/<int:asset_id>')
@login_required
def asset_view(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();asset.status=asset_status(asset);now=utcnow()
    signals=SignalDefinition.query.filter_by(asset_id=asset.id,enabled=True).order_by(SignalDefinition.label).all();cards=[];lookup={};series=[];active_device=active_device_for(asset);active_trend_policy=trend_policy_for(active_device) if active_device else None
    for signal in signals:
        latest=latest_reading(signal.id);history=Reading.query.filter_by(signal_id=signal.id).order_by(desc(Reading.sampled_at)).limit(48).all()[::-1];lookup[signal.key]=latest;cards.append({'signal':signal,'latest':latest,'history':history,'has_data':bool(latest),'selected_now':bool((signal.config_json or {}).get('selected_in_last_payload',False)),'last_sampled_at':aware(latest.sampled_at).isoformat() if latest else None})
        if history and active_device and signal_trend_enabled(active_device,signal):series.append({'key':signal.key,'label':signal.label,'unit':signal.unit or '','values':[{'time':aware(r.sampled_at).strftime('%H:%M'),'value':r.value} for r in history]})
    # Monitoring visuals must use a configured process signal, never the first arbitrary reading.
    # Raw *_volts channels remain available for diagnostics/calibration but are not valid
    # engineering-value sources for Temperature, Flow, Pressure, or Totalizer visuals.
    visual_signal_candidates=[s for s in signals if re.fullmatch(r'analog_[1-9][0-9]*',str(s.key or ''))]
    visual_meta=dict(asset.metadata_json or {})
    requested_visual_signal_id=visual_meta.get('monitoring_signal_id')
    try:requested_visual_signal_id=int(requested_visual_signal_id) if requested_visual_signal_id is not None else None
    except (TypeError,ValueError):requested_visual_signal_id=None
    primary_visual_signal=next((s for s in visual_signal_candidates if s.id==requested_visual_signal_id),None)
    if primary_visual_signal is None:primary_visual_signal=next((s for s in visual_signal_candidates if s.key=='analog_1'),None)
    if primary_visual_signal is None and visual_signal_candidates:primary_visual_signal=visual_signal_candidates[0]
    primary_visual_card=next((c for c in cards if primary_visual_signal and c['signal'].id==primary_visual_signal.id),None)
    primary_trend_selected=bool(active_device and active_trend_policy and active_trend_policy.trend_enabled and primary_visual_signal and SignalTrendPolicy.query.filter_by(customer_id=tenant_id(),device_id=active_device.id,signal_id=primary_visual_signal.id,enabled=True).first())
    primary_trend_points=[]
    if primary_trend_selected and primary_visual_card:
        primary_trend_points=[{'time':aware(row.sampled_at).strftime('%H:%M:%S'),'value':float(row.value)} for row in primary_visual_card['history']]
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
    profile_caps={str(x).upper() for x in (device.capabilities or [])} if device else set()
    profile_channel_keys={str(x.get('key','')).lower() for x in device_profile_context(device).get('channels',[])} if device else set()
    has_location_capability=bool(device and ({'GPS','GNSS'} & profile_caps or {'gps_fix','gps_location','latitude','longitude'} & profile_channel_keys))
    valid_location=bool(location and -90<=float(location.latitude)<=90 and -180<=float(location.longitude)<=180 and not (abs(float(location.latitude))<0.000001 and abs(float(location.longitude))<0.000001))
    if not valid_location:location=None;route=[];track={'latitude':None,'longitude':None,'speed':None,'accuracy':None,'heading':None,'last_fix':'Waiting for valid GNSS fix','route_count':0} if has_location_capability else track
    vehicle_summary=vehicle_day_summary(asset,device,now) if has_location_capability else None
    route_health=route_quality(route) if has_location_capability else None
    last_known_address=None
    if location:
        geocode=reverse_geocode(location.latitude,location.longitude,accuracy_m=location.accuracy_m or 0)
        last_known_address=geocode.get('possible_address') or f'{location.latitude:.5f}, {location.longitude:.5f}'
    operational_battery=None
    percent_signal=SignalDefinition.query.filter_by(asset_id=asset.id,key='battery_percent',enabled=True).first()
    voltage_signal=SignalDefinition.query.filter_by(asset_id=asset.id,key='battery_v',enabled=True).first()
    selected_battery=percent_signal or voltage_signal
    selected_reading=latest_reading(selected_battery.id) if selected_battery else None
    charging_signal=SignalDefinition.query.filter_by(asset_id=asset.id,key='charging_status',enabled=True).first()
    charging_reading=latest_reading(charging_signal.id) if charging_signal else None
    if selected_reading:
        if selected_battery.key=='battery_percent':
            value=max(0,min(100,float(selected_reading.value)));state='CRITICAL' if value<=10 else 'LOW' if value<=25 else 'GOOD';display=f'{value:.0f}%'
        else:
            value=float(selected_reading.value);state='REPORTED';display=f'{value:.2f} {selected_battery.unit or "V"}'
        age=max(0,int((now-aware(selected_reading.sampled_at)).total_seconds()));age_label='Just now' if age<60 else f'{age//60} min ago' if age<3600 else f'{age//3600} h ago'
        operational_battery={'display':display,'state':state,'updated':age_label,'charging':('Yes' if float(charging_reading.value)>=0.5 else 'No') if charging_reading else (phone_battery.get('charging') if phone_battery else 'Not reported')}
    device_profile=device_profile_context(device);output_command=DeviceCommand.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,device_id=device.id).order_by(desc(DeviceCommand.created_at)).first() if device and device_profile.get('output_channels') else None
    output_feedback_verified=False
    if device and device_profile.get('output_channels'):
        feedback_ok=[]
        for output in device_profile.get('output_channels',[]):
            signal=SignalDefinition.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,key=output.get('feedback_key')).first()
            reading=latest_reading(signal.id) if signal else None
            feedback_ok.append(bool(reading and now-aware(reading.sampled_at)<=timedelta(minutes=5) and str(reading.quality or '').upper() not in ('SIMULATED','STALE','NO_FIX')))
        output_feedback_verified=bool(feedback_ok and all(feedback_ok))
    tank_orientation='VERTICAL_CYLINDER'
    if asset.asset_type=='TANK':
        asset_meta=dict(asset.metadata_json or {})
        saved_visual=dict(asset_meta.get('tank_visual') or {})
        tank_orientation=str(saved_visual.get('orientation') or '').upper()
        valid_tank_orientations={'VERTICAL_CYLINDER','HORIZONTAL_CYLINDER','SPHERICAL','CONICAL_HOPPER','RECTANGULAR','IRREGULAR'}
        if tank_orientation not in valid_tank_orientations:
            level_signal=next((x for x in signals if x.key in ('level_percent','level_mm','level_m','analog_1')),None)
            signal_calibration=dict((level_signal.config_json or {}).get('tank_calibration') or {}) if level_signal else {}
            tank_orientation=str(signal_calibration.get('orientation') or asset_meta.get('tank_shape') or 'VERTICAL_CYLINDER').upper()
        if tank_orientation not in valid_tank_orientations:tank_orientation='VERTICAL_CYLINDER'
    return render_template('asset.html',asset=asset,signal_cards=cards,signal_lookup=lookup,chart_series=series,alarms=alarms,open_alarms=open_alarms,device=device,location=location,route_points=route,last_contact=last,generated_at=now,context=ctx,tank_stats=tank,tracking_stats=track,vibration_stats=vib,phone_battery=phone_battery,vehicle_summary=vehicle_summary,route_health=route_health,output_command=output_command,device_profile=device_profile,last_known_address=last_known_address,operational_battery=operational_battery,trend_policy=active_trend_policy,tank_orientation=tank_orientation,monitoring_visual=(asset.metadata_json or {}).get('monitoring_visual','EASY_TANK' if asset.asset_type=='TANK' else 'GENERAL_MONITORING'),visual_signal_candidates=visual_signal_candidates,primary_visual_signal=primary_visual_signal,primary_visual_card=primary_visual_card,primary_trend_selected=primary_trend_selected,primary_trend_points=primary_trend_points,has_location_capability=has_location_capability,valid_location=valid_location,output_feedback_verified=output_feedback_verified)



@bp.post('/asset/<int:asset_id>/monitoring-visual')
@login_required
def change_monitoring_visual(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404()
    visual=request.form.get('monitoring_visual','').strip().upper()
    allowed={'GENERAL_MONITORING','TEMPERATURE','FLOW','PRESSURE','FLOW_TOTALIZER','STATUS_INDICATOR','LIVE_TREND'}
    if visual not in allowed:
        flash('Select a valid monitoring visual.','error')
        return redirect(url_for('main.asset_view',asset_id=asset.id))
    signal_id=request.form.get('monitoring_signal_id',type=int)
    candidates=SignalDefinition.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,enabled=True).all()
    candidates=[s for s in candidates if re.fullmatch(r'analog_[1-9][0-9]*',str(s.key or ''))]
    selected=next((s for s in candidates if s.id==signal_id),None)
    if selected is None:
        flash('Select a valid analog input supplied by the connected board profile.','error')
        return redirect(url_for('main.asset_view',asset_id=asset.id))
    # Process visuals define the expected engineering identity and unit.
    # Changing to a process visual updates label/type/unit, but never rewrites
    # raw or engineering calibration limits, offset, alarms, or trend policy.
    # Neutral display modes preserve the configured process identity.
    process_semantics={
        'TEMPERATURE':('Temperature','TEMPERATURE','°C','temperature'),
        'PRESSURE':('Pressure','PRESSURE','bar','pressure'),
        'FLOW':('Flow','FLOW','L/min','flow'),
        'FLOW_TOTALIZER':('Flow Totalizer','COUNT','L','flow_totalizer'),
        'STATUS_INDICATOR':('Status','STATE','','status'),
    }
    if visual in process_semantics:
        base_label,signal_type,unit,widget=process_semantics[visual]
        channel_number=selected.key.rsplit('_',1)[-1]
        selected.label=f'{base_label} · Analog Input {channel_number}'
        selected.signal_type=signal_type
        selected.unit=unit
        selected.widget=widget
    metadata=dict(asset.metadata_json or {})
    metadata['monitoring_visual']=visual
    metadata['monitoring_signal_id']=selected.id
    metadata['monitoring_signal_key']=selected.key
    asset.metadata_json=metadata
    db.session.commit()
    flash(f'Monitoring visual updated. {selected.label} is now the primary source with unit {selected.unit or "state"}. Calibration limits were preserved.','ok')
    return redirect(url_for('main.asset_view',asset_id=asset.id))
    metadata = dict(asset.metadata_json or {})
    metadata['monitoring_visual'] = visual
    asset.metadata_json = metadata
    db.session.commit()
    flash('Monitoring visual updated.', 'ok')
    return redirect(url_for('main.asset_view', asset_id=asset.id))

@bp.route('/asset/<int:asset_id>/tank-calibration', methods=['GET', 'POST'])
@login_required
def tank_calibration(asset_id):
    asset = Asset.query.filter_by(id=asset_id, customer_id=tenant_id()).first_or_404()
    if asset.asset_type != 'TANK':
        abort(404)

    device = active_device_for(asset)
    signals = SignalDefinition.query.filter_by(
        customer_id=tenant_id(), asset_id=asset.id, enabled=True
    ).order_by(SignalDefinition.label).all()
    allowed_keys = ('level_percent', 'level_mm', 'level_m', 'analog_1')
    level_signals = [signal for signal in signals if signal.key in allowed_keys]
    requested_id = request.form.get('signal_id', type=int) if request.method == 'POST' else request.args.get('signal_id', type=int)
    signal = next((item for item in level_signals if item.id == requested_id), None)
    if signal is None:
        signal = next((item for item in level_signals if item.key in ('level_percent', 'level_mm', 'level_m')), None)
    if signal is None and level_signals:
        signal = level_signals[0]
    if signal is None:
        flash('Create or connect a tank level signal before calibration.', 'error')
        return redirect(url_for('main.signals', asset_id=asset.id))

    cfg = dict(signal.config_json or {})
    calibration = dict(cfg.get('tank_calibration') or {})
    strapping = dict(cfg.get('tank_strapping') or {})

    if request.method == 'POST':
        action = request.form.get('action', 'save_draft')
        try:
            levels = request.form.getlist('level')
            volumes = request.form.getlist('volume')
            notes = request.form.getlist('note')
            submitted = []
            for index, (level, volume) in enumerate(zip(levels, volumes)):
                if not str(level).strip() and not str(volume).strip():
                    continue
                submitted.append({
                    'level': float(level),
                    'volume': float(volume),
                    'note': notes[index].strip()[:120] if index < len(notes) else '',
                })
            clean, errors = validate_tank_strapping(
                submitted,
                capacity=asset.capacity,
                require_full=(action == 'activate'),
            )
            if errors:
                raise ValueError(' '.join(dict.fromkeys(errors)))

            calibration.update({
                'status': 'ACTIVE' if action == 'activate' else 'DRAFT',
                'revision': int(calibration.get('revision') or 0) + (1 if action == 'activate' else 0),
                'level_unit': request.form.get('level_unit', signal.unit or '%').strip()[:20] or '%',
                'volume_unit': request.form.get('volume_unit', asset.capacity_unit or 'L').strip()[:20] or 'L',
                'orientation': request.form.get('orientation', 'VERTICAL_CYLINDER') if request.form.get('orientation') in ('VERTICAL_CYLINDER','HORIZONTAL_CYLINDER','SPHERICAL','CONICAL_HOPPER','RECTANGULAR','IRREGULAR') else 'VERTICAL_CYLINDER',
                'process_name': request.form.get('process_name', 'Tank Level').strip()[:80] or 'Tank Level',
                'input_type': request.form.get('input_type', 'ADC_0_3V3') if request.form.get('input_type') in ('4-20MA_CONDITIONED','VOLTAGE_0_10_CONDITIONED','ADC_0_3V3','CUSTOM_CONDITIONED') else 'ADC_0_3V3',
                'conditioner_note': request.form.get('conditioner_note', '').strip()[:240],
                'points': submitted[:20],
                'updated_at': utcnow().isoformat(),
                'updated_by': current_user.id,
            })
            if action == 'activate':
                calibration['activated_at'] = utcnow().isoformat()
                calibration['activated_by'] = current_user.id

            cfg['tank_calibration'] = calibration
            cfg['tank_strapping'] = {
                'enabled': action == 'activate',
                'points': clean,
                'level_unit': calibration['level_unit'],
                'volume_unit': calibration['volume_unit'],
                'orientation': calibration['orientation'],
                'out_of_range': 'CLAMP',
                'revision': calibration['revision'],
            }
            signal.config_json = cfg
            signal.calibrated_at = utcnow()
            signal.calibrated_by = current_user.id
            asset.capacity_unit = calibration['volume_unit']
            asset_meta = dict(asset.metadata_json or {})
            asset_meta['tank_visual'] = {'orientation': calibration['orientation'], 'updated_at': utcnow().isoformat(), 'updated_by': current_user.id}
            asset.metadata_json = asset_meta
            db.session.commit()
            flash('Tank calibration activated.' if action == 'activate' else 'Tank calibration draft saved.', 'ok')
            return redirect(url_for('main.tank_calibration', asset_id=asset.id, signal_id=signal.id))
        except (TypeError, ValueError) as exc:
            db.session.rollback()
            flash(str(exc) or 'Invalid tank calibration values. No changes were saved.', 'error')

    cfg = dict(signal.config_json or {})
    calibration = dict(cfg.get('tank_calibration') or {})
    strapping = dict(cfg.get('tank_strapping') or {})
    points = calibration.get('points') or strapping.get('points') or [
        {'level': 0, 'volume': 0, 'note': 'Empty'},
        {'level': 100, 'volume': float(asset.capacity or 0), 'note': 'Full'},
    ]
    latest = latest_reading(signal.id)
    live_level = float(latest.value) if latest else None
    live_volume = tank_volume_from_level(live_level, points) if live_level is not None else None
    max_level = max([float(point.get('level') or 0) for point in points] or [100])
    fill = (live_level / max_level * 100) if live_level is not None and max_level > 0 else 0
    return render_template(
        'tank_calibration.html', asset=asset, device=device, signals=level_signals,
        signal=signal, calibration=calibration, points=points, latest=latest,
        live_level=live_level, live_volume=live_volume, fill=max(0, min(100, fill)),
    )

@bp.get('/asset/<int:asset_id>/device-panel')
@login_required
def universal_device_panel(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();device=active_device_for(asset)
    if not device:return redirect(url_for('main.connect_device',asset_id=asset.id))
    is_mobile_device=str(device.device_type or '').upper() in ('MOBILE_WEB_TRACKER','ANDROID_MOBILE_TRACKER','MOBILE_TRACKER','IOS_MOBILE_TRACKER')
    profile=None if is_mobile_device else profile_for_device(device)
    if is_mobile_device:
        profile={'code':'AT360_MOBILE_TRACKER','display_name':'AssetTrack 360 Mobile Tracker','transport':'HTTPS Mobile API','firmware_family':'AssetTrack 360 Mobile App','capabilities':['GPS','SPEED','HEADING','GPS_ACCURACY','PHONE_BATTERY','CHARGING_STATUS','LAST_CONTACT','SOS_EVENT'],'reserved_pins':[],'channels':[{**point,'direction':'LOCATION' if point['key']=='gps_location' else 'HEALTH','source_type':'MOBILE','calibratable':False} for point in MOBILE_AUTO_POINTS],'output_channels':[],'virtual_profile':True}
    if not profile:flash('This hardware has no registered board profile.','error');return redirect(url_for('main.asset_view',asset_id=asset.id))
    mobile_profile=bool(profile.get('virtual_profile'))
    if mobile_profile:
        ensure_mobile_auto_profile(device);db.session.commit()
    channels=profile.get('channels',[])
    analog_channels=[c for c in channels if c.get('calibratable') and c.get('direction')=='INPUT']
    digital_channels=[c for c in channels if c.get('direction')=='INPUT' and not c.get('calibratable') and c.get('signal_type')=='STATE' and not c.get('safety_interlock')]
    pulse_channels=[c for c in channels if c.get('direction')=='INPUT' and c.get('signal_type')=='COUNT']
    system_channels=[c for c in channels if c.get('safety_interlock')]
    output_channels=[]
    for item in profile.get('output_channels',[]):
        row=dict(item);row['key']='output_'+str(row.get('channel','')).lower();output_channels.append(row)
    signals=SignalDefinition.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).order_by(SignalDefinition.label).all()
    if is_mobile_device:
        mobile_keys={point['key'] for point in MOBILE_AUTO_POINTS}
        signals=[x for x in signals if x.key in mobile_keys and str(x.source_type or '').upper()=='MOBILE']
    signal_map={x.key:x for x in signals}
    assignments=DeviceChannelAssignment.query.filter_by(customer_id=tenant_id(),device_id=device.id).all();assignment_map={x.channel_key:x for x in assignments}
    measurement_library={
      'CUSTOM_ANALOG':{'label':'Custom analogue','signal_type':'CUSTOM','widget':'numeric','unit':'%','units':['%','V','mA',''],'eng_min':0,'eng_max':100,'visuals':['GENERAL_MONITORING','LIVE_TREND']},
      'TANK_LEVEL':{'label':'Tank level','signal_type':'LEVEL','widget':'tank','unit':'%','units':['%','L','mm','m'],'eng_min':0,'eng_max':100,'visuals':['EASY_TANK','POINT_TANK','ROUND_TANK']},
      'TEMPERATURE':{'label':'Temperature','signal_type':'TEMPERATURE','widget':'temperature','unit':'°C','units':['°C','°F'],'eng_min':0,'eng_max':100,'visuals':['TEMPERATURE','LIVE_TREND']},
      'FLOW':{'label':'Flow','signal_type':'FLOW','widget':'flow','unit':'L/min','units':['L/min','m³/h'],'eng_min':0,'eng_max':100,'visuals':['FLOW','LIVE_TREND']},
      'PRESSURE':{'label':'Pressure','signal_type':'PRESSURE','widget':'pressure','unit':'bar','units':['bar','kPa','MPa','psi'],'eng_min':0,'eng_max':10,'visuals':['PRESSURE','LIVE_TREND']}}
    digital_library={'CUSTOM_STATUS':{'label':'Custom status','visuals':['STATUS_INDICATOR']},'RUN_STATUS':{'label':'Run status','visuals':['STATUS_INDICATOR']},'FAULT_STATUS':{'label':'Fault status','visuals':['STATUS_INDICATOR']},'DOOR_TAMPER':{'label':'Door / tamper','visuals':['STATUS_INDICATOR']}}
    pulse_library={'CUSTOM_COUNTER':{'label':'Custom counter','unit':'pulses','units':['pulses','count'],'visuals':['TOTALIZER','LIVE_TREND']},'FLOW_TOTALIZER':{'label':'Flow totalizer','unit':'L','units':['L','m³'],'visuals':['FLOW_TOTALIZER','LIVE_TREND']},'RUNTIME_COUNTER':{'label':'Runtime counter','unit':'h','units':['h','min'],'visuals':['TOTALIZER']}}
    output_library={'CUSTOM_OUTPUT':{'label':'Custom output','visuals':['OUTPUT_CONTROL']},'PUMP_CONTROL':{'label':'Pump control','visuals':['OUTPUT_CONTROL']},'VALVE_CONTROL':{'label':'Valve control','visuals':['OUTPUT_CONTROL']},'ALARM_OUTPUT':{'label':'Alarm output','visuals':['OUTPUT_CONTROL']}}
    applications=[{'code':x[0],'label':x[1],'icon':x[2]} for x in [('TANK_LEVEL','Tank level','▰'),('PUMP_MONITORING','Pump monitoring','◉'),('MACHINE_CONDITION','Machine condition','⌁'),('GENERATOR','Generator','⚡'),('COLD_ROOM','Cold room','❄'),('TRACKING','Tracking','⌖'),('SOLAR_BATTERY','Solar / battery','☀'),('GATE_TAMPER','Gate / tamper','▥'),('UNIVERSAL_ANALOGUE','Universal analogue','∿'),('CUSTOM_MONITORING','Custom monitoring','✦')]]
    pictures=[{'code':re.sub(r'[^A-Z0-9]+','_',x.upper()).strip('_'),'label':x,'icon':i} for x,i in [('Vertical tank','▰'),('Horizontal tank','▱'),('Rectangular tank','▣'),('Silo','♜'),('Mobile bowser','▭'),('Pump','◉'),('Motor','⚙'),('Motor and pump set','⚙'),('Borehole installation','↧'),('Generator','⚡'),('Cold room','❄'),('Solar installation','☀'),('Gate','▥'),('Door','▯'),('Pipeline','━'),('Flow meter','◌'),('Pressure vessel','⬭'),('Conveyor','⇢'),('Fan','✣'),('Gearbox','⬡'),('Compressor','◎'),('Custom uploaded image','＋')]]
    configured_choices=[]
    for a in assignments:
        if a.enabled:
            cfg=a.config_json or {};configured_choices.append({'key':a.channel_key,'label':a.customer_label or a.channel_key,'visual':cfg.get('visual','GENERAL_MONITORING')})
    meta=asset.metadata_json or {};policy=trend_policy_for(device);selected={x.signal_id for x in SignalTrendPolicy.query.filter_by(customer_id=tenant_id(),device_id=device.id,enabled=True).all()}
    mobile_summary=None
    if mobile_profile:
        latest_location=Location.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).order_by(desc(Location.sampled_at)).first()
        battery_signal=signal_map.get('battery_percent');battery_reading=latest_reading(battery_signal.id) if battery_signal else None
        charging=next((str(x).split(':',1)[1] for x in (device.capabilities or []) if str(x).startswith('CHARGING:')),None)
        sos_assignment=assignment_map.get('sos_event')
        mobile_summary={'points':MOBILE_AUTO_POINTS,'location':latest_location,'battery':battery_reading,'charging':charging,'last_contact':device.last_seen,'sos_enabled':bool(sos_assignment and sos_assignment.enabled),'asset_name':asset.name}
    profile_channels=list(profile.get('channels',[]));reserved_points=list(profile.get('reserved_pins',[]));assignable_points=[x for x in profile_channels if x.get('direction') in ('INPUT','OUTPUT') and x.get('pin')];internal_points=[x for x in profile_channels if x.get('direction') in ('HEALTH','LOCATION')];enabled_assignments=[x for x in assignments if x.enabled];device_online=bool(device.last_seen and utcnow()-aware(device.last_seen)<=timedelta(minutes=30))
    validation_results=[
        {'state':'PASS','message':f"{len(assignable_points)} verified physical I/O point(s) declared"},
        {'state':'PASS','message':f"{len(internal_points)} internal/health point(s) separated from customer I/O"},
        {'state':'PASS','message':f"{len(reserved_points)} reserved point(s) protected"},
    ]
    return render_template('device_panel.html',asset=asset,device=device,profile=profile,trend_policy=policy,trend_signals=[x for x in signals if x.enabled],selected_trend_signals=selected,analog_channels=analog_channels,digital_channels=digital_channels,pulse_channels=pulse_channels,system_channels=system_channels,output_channels=output_channels,signal_map=signal_map,assignment_map=assignment_map,measurement_library=measurement_library,digital_library=digital_library,pulse_library=pulse_library,output_library=output_library,applications=applications,asset_pictures=pictures,selected_application=meta.get('studio_application',''),selected_picture=meta.get('asset_picture',''),configured_choices=configured_choices,commissioned=meta.get('commissioning_state')=='COMMISSIONED',latest_reading=latest_reading,mobile_profile=mobile_profile,mobile_summary=mobile_summary,validation_results=validation_results,device_online=device_online,assignable_points=assignable_points,internal_points=internal_points,reserved_points=reserved_points,enabled_assignments=enabled_assignments)

@bp.post('/asset/<int:asset_id>/mobile-profile')
@login_required
def mobile_profile_settings(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();device=active_device_for(asset)
    if not device or str(device.device_type or '').upper() not in ('MOBILE_WEB_TRACKER','ANDROID_MOBILE_TRACKER','MOBILE_TRACKER','IOS_MOBILE_TRACKER'):abort(404)
    ensure_mobile_auto_profile(device)
    sos=DeviceChannelAssignment.query.filter_by(customer_id=tenant_id(),device_id=device.id,channel_key='sos_event').first()
    if sos:
        sos.enabled=request.form.get('sos_enabled')=='on';cfg=dict(sos.config_json or {});cfg['user_enabled']=sos.enabled;sos.config_json=cfg
    audit(tenant_id(),'MOBILE_PROFILE_UPDATED',asset.id,device.id,'USER',current_user.id,f'Standard mobile telemetry active; SOS={bool(sos and sos.enabled)}')
    db.session.commit();flash('Mobile tracker profile updated. Standard phone telemetry remains automatic.','ok')
    return redirect(url_for('main.universal_device_panel',asset_id=asset.id))

@bp.post('/asset/<int:asset_id>/io-configuration')
@login_required
def io_configuration(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();device=active_device_for(asset);profile=profile_for_device(device)
    if not device or not profile:abort(404)
    channels=profile.get('channels',[]);analog=[c for c in channels if c.get('calibratable') and c.get('direction')=='INPUT'];digital=[c for c in channels if c.get('direction')=='INPUT' and c.get('signal_type')=='STATE' and not c.get('safety_interlock')];pulse=[c for c in channels if c.get('direction')=='INPUT' and c.get('signal_type')=='COUNT']
    analog_lib={'CUSTOM_ANALOG':('CUSTOM','numeric'),'TANK_LEVEL':('LEVEL','tank'),'TEMPERATURE':('TEMPERATURE','temperature'),'FLOW':('FLOW','flow'),'PRESSURE':('PRESSURE','pressure')}
    try:
        meta=dict(asset.metadata_json or {});app=request.form.get('studio_application','').strip().upper();picture=request.form.get('asset_picture','').strip().upper()
        if not app or not picture:raise ValueError('Select an application and asset picture before commissioning')
        meta.update({'studio_application':app,'asset_picture':picture})
        configured=[]
        def assignment_for(key,direction):
            row=DeviceChannelAssignment.query.filter_by(device_id=device.id,channel_key=key).first()
            if not row:row=DeviceChannelAssignment(customer_id=tenant_id(),device_id=device.id,channel_key=key,direction=direction);db.session.add(row)
            return row
        for c in analog:
            key=c['key'];enabled=request.form.get(key+'_enabled')=='on';purpose=request.form.get(key+'_measurement','CUSTOM_ANALOG').upper()
            if purpose not in analog_lib:raise ValueError(key+': unsupported measurement type')
            stype,widget=analog_lib[purpose];sig=SignalDefinition.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,key=key).first();defaults=c.get('defaults',{})
            if not sig:sig=SignalDefinition(customer_id=tenant_id(),asset_id=asset.id,key=key,label=c['label'],signal_type=stype,source_type=c['source_type'],unit=c.get('unit',''),widget=widget);db.session.add(sig);db.session.flush()
            emin=float(request.form.get(key+'_eng_min',sig.eng_min or 0));emax=float(request.form.get(key+'_eng_max',sig.eng_max or 100))
            if emin==emax:raise ValueError(key+': engineering limits may not be equal')
            sig.enabled=enabled;sig.label=request.form.get(key+'_label',c['label']).strip()[:100] or c['label'];sig.unit=request.form.get(key+'_unit',sig.unit or '').strip()[:20];sig.signal_type=stype;sig.widget=widget;sig.eng_min=emin;sig.eng_max=emax
            cfg=dict(sig.config_json or {});cfg.update({'measurement_type':purpose,'physical_pin':c.get('pin'),'pin_notes':c.get('pin_notes'),'dashboard_visual':request.form.get(key+'_visual','GENERAL_MONITORING'),'studio_managed':True});sig.config_json=cfg
            row=assignment_for(key,'INPUT');row.asset_id=asset.id;row.signal_id=sig.id;row.purpose=purpose;row.customer_label=sig.label;row.enabled=enabled;row.config_json={'physical_pin':c.get('pin'),'unit':sig.unit,'eng_min':emin,'eng_max':emax,'visual':request.form.get(key+'_visual','GENERAL_MONITORING'),'pin_notes':c.get('pin_notes')}
            if enabled:configured.append((key,sig,row.config_json['visual']))
        for group,stype,default_purpose,default_visual in [(digital,'STATE','CUSTOM_STATUS','STATUS_INDICATOR'),(pulse,'COUNT','CUSTOM_COUNTER','TOTALIZER')]:
            for c in group:
                key=c['key'];enabled=request.form.get(key+'_enabled')=='on';purpose=request.form.get(key+'_purpose',default_purpose).upper();sig=SignalDefinition.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,key=key).first()
                if not sig:sig=SignalDefinition(customer_id=tenant_id(),asset_id=asset.id,key=key,label=c['label'],signal_type=stype,source_type=c['source_type'],unit=request.form.get(key+'_unit',c.get('unit','')),widget='status' if stype=='STATE' else 'numeric');db.session.add(sig);db.session.flush()
                sig.enabled=enabled;sig.label=request.form.get(key+'_label',c['label']).strip()[:100] or c['label'];sig.unit=request.form.get(key+'_unit',sig.unit or '').strip()[:20]
                cfg={'physical_pin':c.get('pin'),'visual':request.form.get(key+'_visual',default_visual)}
                if stype=='STATE':cfg.update({'active_level':request.form.get(key+'_active_level',c.get('active_level','HIGH')),'debounce_ms':max(0,min(10000,int(request.form.get(key+'_debounce_ms') or 100))),'on_label':request.form.get(key+'_on_label','ON')[:30],'off_label':request.form.get(key+'_off_label','OFF')[:30]})
                else:cfg.update({'pulses_per_unit':max(.000001,float(request.form.get(key+'_pulses_per_unit') or 1)),'debounce_ms':max(0,min(10000,int(request.form.get(key+'_debounce_ms') or 20))),'edge':request.form.get(key+'_edge',c.get('edge','FALLING'))})
                row=assignment_for(key,'INPUT');row.asset_id=asset.id;row.signal_id=sig.id;row.purpose=purpose;row.customer_label=sig.label;row.enabled=enabled;row.config_json=cfg
                if enabled:configured.append((key,sig,cfg['visual']))
        for o in profile.get('output_channels',[]):
            key='output_'+o['channel'].lower();enabled=request.form.get(key+'_enabled')=='on';row=assignment_for(key,'OUTPUT');row.asset_id=asset.id;row.signal_id=None;row.purpose=request.form.get(key+'_purpose','CUSTOM_OUTPUT').upper();row.customer_label=request.form.get(key+'_label',o['label']).strip()[:100] or o['label'];row.enabled=enabled;row.config_json={'channel':o['channel'],'physical_pin':o.get('pin'),'visual':request.form.get(key+'_visual','OUTPUT_CONTROL'),'mode':request.form.get(key+'_mode',o.get('default_mode','LATCHED')),'pulse_seconds':max(.1,min(3600,float(request.form.get(key+'_pulse_seconds') or o.get('pulse_seconds',1)))),'safe_boot_state':'OFF','simulation_physical_lockout':True,'requires_local_arm':bool(o.get('requires_local_arm')),'feedback_key':o.get('feedback_key')}
        if not configured:raise ValueError('Enable at least one input channel before commissioning')
        primary_key=request.form.get('primary_channel','').strip();primary=next((x for x in configured if x[0]==primary_key),configured[0]);meta.update({'commissioning_state':'COMMISSIONED','commissioned_at':utcnow().isoformat(),'commissioned_by':current_user.id,'primary_io_channel':primary[0],'monitoring_signal_id':primary[1].id,'monitoring_signal_key':primary[0],'monitoring_visual':primary[2]})
        picture_orientation={'VERTICAL_TANK':'VERTICAL_CYLINDER','HORIZONTAL_TANK':'HORIZONTAL_CYLINDER','RECTANGULAR_TANK':'RECTANGULAR'}.get(picture)
        if picture_orientation:meta['tank_visual']={'orientation':picture_orientation,'updated_at':utcnow().isoformat(),'updated_by':current_user.id}
        asset.metadata_json=meta;audit(tenant_id(),'DEVICE_COMMISSIONED',asset.id,device.id,'USER',current_user.id,f"{profile['code']}: {len(configured)} input channel(s); application={app}; picture={picture}");db.session.commit();flash('Solution, asset picture and verified I/O commissioned. Continue to calibration where required.','ok');return redirect(url_for('main.universal_device_panel',asset_id=asset.id))
    except (TypeError,ValueError) as exc:
        db.session.rollback();flash(str(exc)+'. No partial changes were saved.','error');return redirect(url_for('main.universal_device_panel',asset_id=asset.id))
@bp.post('/asset/<int:asset_id>/device-trending')
@login_required
def device_trending(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();device=active_device_for(asset)
    if not device:abort(404)
    policy=trend_policy_for(device);old_days=policy.retention_days;policy.trend_enabled=request.form.get('trend_enabled')=='on';policy.retention_days=request.form.get('retention_days',type=int) or 93;policy.gps_history_enabled=request.form.get('gps_history_enabled')=='on';policy.gps_retention_days=request.form.get('gps_retention_days',type=int) or 31
    if policy.retention_days not in (31,93) or policy.gps_retention_days not in (31,93):abort(400)
    policy.updated_by=current_user.id;selected={int(x) for x in request.form.getlist('signal_ids') if x.isdigit()}
    valid={x.id for x in SignalDefinition.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,enabled=True).all()}
    if not selected.issubset(valid):abort(400)
    SignalTrendPolicy.query.filter_by(customer_id=tenant_id(),device_id=device.id).delete(synchronize_session=False)
    for signal_id in selected:db.session.add(SignalTrendPolicy(customer_id=tenant_id(),device_id=device.id,signal_id=signal_id,enabled=True))
    audit(tenant_id(),'DEVICE_TREND_POLICY_CHANGED',asset.id,device.id,'USER',current_user.id,f'Trend={policy.trend_enabled}; retention={policy.retention_days}; GPS={policy.gps_history_enabled}/{policy.gps_retention_days}')
    db.session.commit()
    if policy.retention_days<old_days:flash('Trend retention reduced. Older history will be permanently removed during cleanup.','ok')
    else:flash('Device trend settings saved.','ok')
    return redirect(url_for('main.universal_device_panel',asset_id=asset.id))

@bp.route('/asset/<int:asset_id>/signals',methods=['GET','POST'])
@login_required
def signals(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();device=active_device_for(asset);profile=device_profile_context(device)
    advanced_access=has_advanced_access(asset.customer_id,device)
    if request.method=='POST' and not advanced_access:
        abort(403)
    if request.method=='POST':
        action=request.form.get('action','add')
        if action=='save_all_calibrations':
            signal_ids=[]
            for value in request.form.getlist('signal_ids'):
                try:signal_ids.append(int(value))
                except (TypeError,ValueError):abort(400)
            signal_ids=list(dict.fromkeys(signal_ids))
            if not signal_ids:flash('No calibration changes were submitted.','error');return redirect(url_for('main.signals',asset_id=asset.id))
            try:
                changed=[]
                for signal_id in signal_ids:
                    sig=SignalDefinition.query.filter_by(id=signal_id,asset_id=asset.id,customer_id=tenant_id()).first_or_404()
                    channel=channel_profile_default(device,sig.key)
                    if not channel or not channel.get('calibratable'):abort(400)
                    prefix=f'sig_{signal_id}_'
                    def f(name,current=None):
                        value=request.form.get(prefix+name,'').strip();return current if value=='' else float(value)
                    sig.label=request.form.get(prefix+'label',sig.label).strip()[:100] or sig.label
                    sig.unit=request.form.get(prefix+'unit',sig.unit).strip()[:20]
                    sig.calibration_mode=request.form.get(prefix+'calibration_mode','LINEAR').upper()
                    if sig.calibration_mode not in ('LINEAR','PASSTHROUGH'):raise ValueError(f'{sig.label}: invalid calibration mode')
                    sig.raw_min=f('raw_min',sig.raw_min);sig.raw_max=f('raw_max',sig.raw_max);sig.eng_min=f('eng_min',sig.eng_min);sig.eng_max=f('eng_max',sig.eng_max)
                    sig.offset=f('offset',sig.offset or 0);sig.filter_alpha=max(0.01,min(1.0,f('filter_alpha',sig.filter_alpha or 1)));sig.deadband=max(0,f('deadband',sig.deadband or 0))
                    sig.critical_low=f('critical_low',None);sig.warning_low=f('warning_low',None);sig.warning_high=f('warning_high',None);sig.critical_high=f('critical_high',None)
                    ordered=[x for x in (sig.critical_low,sig.warning_low,sig.warning_high,sig.critical_high) if x is not None]
                    if ordered!=sorted(ordered):raise ValueError(f'{sig.label}: alarm order must be LL <= L <= H <= HH')
                    if sig.calibration_mode=='LINEAR' and float(sig.raw_max)==float(sig.raw_min):raise ValueError(f'{sig.label}: raw maximum must differ from raw minimum')
                    cfg=dict(sig.config_json or {})
                    if request.form.get(prefix+'tank_strapping_enabled')=='on':
                        levels=request.form.getlist(prefix+'tank_level');volumes=request.form.getlist(prefix+'tank_volume');points=[]
                        for level,volume in zip(levels,volumes):
                            if str(level).strip()=='' and str(volume).strip()=='':continue
                            points.append({'level':float(level),'volume':float(volume)})
                        points=normalize_tank_points(points)
                        if len(points)<2:raise ValueError(f'{sig.label}: tank strapping requires at least two unique ascending level points')
                        if any(points[i]['volume']>points[i+1]['volume'] for i in range(len(points)-1)):raise ValueError(f'{sig.label}: tank volume must not decrease as level rises')
                        cfg['tank_strapping']={'enabled':True,'points':points,'level_unit':request.form.get(prefix+'tank_level_unit','%')[:20] or '%','volume_unit':request.form.get(prefix+'tank_volume_unit','L')[:20] or 'L','out_of_range':'CLAMP'}
                    else:cfg.pop('tank_strapping',None)
                    sig.config_json=cfg
                    sig.calibrated_at=utcnow();sig.calibrated_by=current_user.id;changed.append(sig.label)
                db.session.commit();flash(f'{len(changed)} channel calibration changes saved together.','ok')
            except ValueError as exc:
                db.session.rollback();flash(str(exc)+'. No calibration changes were saved.','error')
            except Exception:
                db.session.rollback();current_app.logger.exception('Save all calibration failed asset_id=%s',asset.id);flash('Calibration save failed safely. No partial changes were saved.','error')
            return redirect(url_for('main.signals',asset_id=asset.id,open='all'))
        if action in ('save_calibration','restore_defaults'):
            sig=SignalDefinition.query.filter_by(id=request.form.get('signal_id',type=int),asset_id=asset.id,customer_id=tenant_id()).first_or_404()
            channel=channel_profile_default(device,sig.key)
            if not channel or not channel.get('calibratable'):abort(400)
            defaults=channel.get('defaults',{})
            if action=='restore_defaults':
                sig.label=channel['label'];sig.unit=channel.get('unit','');sig.calibration_mode=defaults.get('calibration_mode','LINEAR');sig.raw_min=defaults.get('raw_min',0);sig.raw_max=defaults.get('raw_max',100);sig.eng_min=defaults.get('eng_min',0);sig.eng_max=defaults.get('eng_max',100);sig.offset=defaults.get('offset',0);sig.filter_alpha=defaults.get('filter_alpha',1);sig.deadband=defaults.get('deadband',0);sig.critical_low=defaults.get('critical_low');sig.warning_low=defaults.get('warning_low');sig.warning_high=defaults.get('warning_high');sig.critical_high=defaults.get('critical_high')
            else:
                def f(name,current=None):
                    value=request.form.get(name,'').strip();return current if value=='' else float(value)
                sig.label=request.form.get('label',sig.label).strip()[:100] or sig.label;sig.unit=request.form.get('unit',sig.unit).strip()[:20];sig.calibration_mode=request.form.get('calibration_mode','LINEAR').upper();sig.raw_min=f('raw_min',sig.raw_min);sig.raw_max=f('raw_max',sig.raw_max);sig.eng_min=f('eng_min',sig.eng_min);sig.eng_max=f('eng_max',sig.eng_max);sig.offset=f('offset',sig.offset or 0);sig.filter_alpha=max(0.01,min(1.0,f('filter_alpha',sig.filter_alpha or 1)));sig.deadband=max(0,f('deadband',sig.deadband or 0));sig.critical_low=f('critical_low',None);sig.warning_low=f('warning_low',None);sig.warning_high=f('warning_high',None);sig.critical_high=f('critical_high',None)
                ordered=[x for x in (sig.critical_low,sig.warning_low,sig.warning_high,sig.critical_high) if x is not None]
                if ordered!=sorted(ordered):flash('Alarm order must be LL <= L <= H <= HH.','error');return redirect(url_for('main.signals',asset_id=asset.id))
                cfg=dict(sig.config_json or {})
                if request.form.get('tank_strapping_enabled')=='on':
                    points=[]
                    try:
                        for level,volume in zip(request.form.getlist('tank_level'),request.form.getlist('tank_volume')):
                            if str(level).strip()=='' and str(volume).strip()=='':continue
                            points.append({'level':float(level),'volume':float(volume)})
                    except ValueError:flash('Tank strapping points must contain valid numbers.','error');return redirect(url_for('main.signals',asset_id=asset.id))
                    points=normalize_tank_points(points)
                    if len(points)<2:flash('Tank strapping requires at least two unique level points.','error');return redirect(url_for('main.signals',asset_id=asset.id))
                    if any(points[i]['volume']>points[i+1]['volume'] for i in range(len(points)-1)):flash('Tank volume must not decrease as level rises.','error');return redirect(url_for('main.signals',asset_id=asset.id))
                    cfg['tank_strapping']={'enabled':True,'points':points,'level_unit':request.form.get('tank_level_unit','%')[:20] or '%','volume_unit':request.form.get('tank_volume_unit','L')[:20] or 'L','out_of_range':'CLAMP'}
                else:cfg.pop('tank_strapping',None)
                sig.config_json=cfg
            sig.calibrated_at=utcnow();sig.calibrated_by=current_user.id;db.session.commit();flash('Channel calibration saved.' if action=='save_calibration' else 'Profile defaults restored.','ok');return redirect(url_for('main.signals',asset_id=asset.id))
        key=slugify(request.form['key']).replace('-','_');record=SignalDefinition(customer_id=tenant_id(),asset_id=asset.id,key=key,label=request.form['label'],signal_type=request.form['signal_type'],source_type=request.form['source_type'],unit=request.form.get('unit',''),widget=request.form['widget'],raw_min=float(request.form.get('raw_min') or 4),raw_max=float(request.form.get('raw_max') or 20),eng_min=float(request.form.get('eng_min') or 0),eng_max=float(request.form.get('eng_max') or 100),warning_low=float(request.form['warning_low']) if request.form.get('warning_low') else None,warning_high=float(request.form['warning_high']) if request.form.get('warning_high') else None,critical_low=float(request.form['critical_low']) if request.form.get('critical_low') else None,critical_high=float(request.form['critical_high']) if request.form.get('critical_high') else None);db.session.add(record);db.session.commit();flash('Signal added.','ok')
    rows=SignalDefinition.query.filter_by(asset_id=asset.id).all();calibration_channels=[{'signal':x,'profile':channel_profile_default(device,x.key)} for x in rows if profile_calibratable(device,x)]
    return render_template('signals.html',asset=asset,signals=rows,device_profile=profile,calibration_channels=calibration_channels,advanced_access=advanced_access)
@bp.route('/asset/<int:asset_id>/device',methods=['GET','POST'])
@login_required
def device(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();d=Device.query.filter_by(asset_id=asset.id,active=True).first()
    if request.method=='POST' and not d:
        d=Device(customer_id=tenant_id(),asset_id=asset.id,device_uid=request.form['device_uid'],device_type=request.form.get('device_type','UNIVERSAL'),api_token=secrets.token_urlsafe(32),capabilities=[]);db.session.add(d);db.session.commit();flash('Device registered. Copy the token now.','ok')
    return render_template('device.html',asset=asset,device=d)

@bp.post('/asset/<int:asset_id>/output-command')
@login_required
def create_output_command(asset_id):
 asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();device=active_device_for(asset);profile=profile_for_device(device)
 if not device or not profile:abort(404)
 if not device.last_seen or utcnow()-aware(device.last_seen)>timedelta(minutes=30):
  flash('Device is offline. Output commands are blocked until fresh firmware telemetry is received.','error');return redirect(url_for('main.asset_view',asset_id=asset.id))
 feedback_ready=[]
 for output in profile.get('output_channels',[]):
  signal=SignalDefinition.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,key=output.get('feedback_key')).first();reading=latest_reading(signal.id) if signal else None
  feedback_ready.append(bool(reading and utcnow()-aware(reading.sampled_at)<=timedelta(minutes=5) and str(reading.quality or '').upper() not in ('SIMULATED','STALE')))
 if not feedback_ready or not all(feedback_ready):
  flash('Output state is not verified. Commands are blocked until fresh firmware feedback is received.','error');return redirect(url_for('main.asset_view',asset_id=asset.id))
 channel=request.form.get('channel','DO1').strip().upper();action=request.form.get('action','').strip().upper();allowed={x['channel']:x for x in profile.get('output_channels',[])}
 if channel not in allowed or action not in ('OUTPUT_ON','OUTPUT_OFF'):abort(400)
 DeviceCommand.query.filter(DeviceCommand.device_id==device.id,DeviceCommand.channel==channel,DeviceCommand.state.in_(['PENDING','DELIVERED'])).update({'state':'SUPERSEDED'},synchronize_session=False)
 policy=allowed[channel];simulation_only=bool(policy.get('simulation_only',False));cmd=DeviceCommand(customer_id=tenant_id(),asset_id=asset.id,device_id=device.id,channel=channel,action=action,simulation_only=simulation_only,requested_by=current_user.id,request_token=secrets.token_hex(24),expires_at=utcnow()+timedelta(seconds=45));db.session.add(cmd);db.session.commit();flash(f'{channel} command queued. Device safety policy remains authoritative.','ok');return redirect(url_for('main.asset_view',asset_id=asset.id))
@bp.get('/api/v1/device/commands/next')
def device_command_next():
 token=request.headers.get('Authorization','').removeprefix('Bearer ').strip();device=Device.query.filter_by(api_token=token,active=True).first()
 if not device:return jsonify(error='unauthorized'),401
 cmd=DeviceCommand.query.filter_by(customer_id=device.customer_id,device_id=device.id,state='PENDING').filter(DeviceCommand.expires_at>utcnow()).order_by(DeviceCommand.created_at).first();device.last_seen=utcnow()
 if not cmd:db.session.commit();return ('',204)
 cmd.state='DELIVERED';cmd.delivered_at=utcnow();db.session.commit();return jsonify(id=cmd.id,request_token=cmd.request_token,channel=cmd.channel,action=cmd.action,simulation_only=cmd.simulation_only),200
@bp.post('/api/v1/device/commands/<int:command_id>/ack')
def device_command_ack(command_id):
 token=request.headers.get('Authorization','').removeprefix('Bearer ').strip();device=Device.query.filter_by(api_token=token,active=True).first()
 if not device:return jsonify(error='unauthorized'),401
 cmd=DeviceCommand.query.filter_by(id=command_id,customer_id=device.customer_id,device_id=device.id).first();data=request.get_json(silent=True) or {}
 if not cmd:return jsonify(error='not_found'),404
 if data.get('request_token')!=cmd.request_token:return jsonify(error='token_mismatch'),403
 result=str(data.get('result','REJECTED')).upper();cmd.state=result if result in ('COMPLETED','REJECTED','FAILED') else 'REJECTED';cmd.acknowledged_at=utcnow();cmd.completed_at=utcnow() if cmd.state=='COMPLETED' else None;cmd.feedback_value=1.0 if data.get('feedback') else 0.0;cmd.failure_reason=str(data.get('reason',''))[:240] or None;db.session.commit();return jsonify(status='accepted'),202

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
    customer_id=tenant_id()
    sites=Site.query.filter_by(customer_id=customer_id).order_by(Site.name).all()
    active_asset_ids={row.asset_id for row in Device.query.filter_by(customer_id=customer_id,active=True).all() if row.asset_id}
    assets=[a for a in Asset.query.filter_by(customer_id=customer_id).order_by(Asset.name).all() if a.id not in active_asset_ids]
    requested_asset_id=request.args.get('asset_id',type=int)
    preselected_asset=next((a for a in assets if a.id==requested_asset_id),None)
    if request.method=='POST':
        kind=request.form.get('device_kind','ANDROID_PHONE').strip().upper()
        profile=get_profile(request.form.get('profile_code')) if kind=='HARDWARE_PROFILE' else None
        if kind not in ('ANDROID_PHONE','HARDWARE_PROFILE') or (kind=='HARDWARE_PROFILE' and not profile):
            flash('Select a supported physical device.','error');return redirect(url_for('main.connect_device',asset_id=request.form.get('asset_id',type=int)))
        asset_mode=request.form.get('asset_mode','existing')
        if asset_mode=='new':
            name=request.form.get('asset_name','').strip()
            requested_asset_type=request.form.get('new_asset_type','GENERIC').strip().upper()
            allowed_asset_types={'TANK','TRACKER','VIBRATION','GENERIC'}
            if len(name)<2 or len(name)>120:
                flash('Enter an asset name between 2 and 120 characters.','error');return redirect(url_for('main.connect_device'))
            if requested_asset_type not in allowed_asset_types:
                flash('Select a valid asset type.','error');return redirect(url_for('main.connect_device'))
            if kind=='ANDROID_PHONE' and requested_asset_type!='TRACKER':
                flash('Android Phone can only be connected to a tracking asset.','error');return redirect(url_for('main.connect_device'))
            requested_site_id=request.form.get('site_id',type=int)
            site=Site.query.filter_by(id=requested_site_id,customer_id=customer_id).first() if requested_site_id else None
            if not site:
                site=Site.query.filter(Site.customer_id==customer_id,db.func.lower(Site.name)=='my assets').order_by(Site.id).first()
            if not site:
                site=Site(customer_id=customer_id,name='My Assets',location=None);db.session.add(site);db.session.flush()
            asset=Asset(customer_id=customer_id,site_id=site.id,name=name,asset_type=requested_asset_type,status='UNASSIGNED',metadata_json={'onboarding_source':'DEVICE_CENTRE'})
            db.session.add(asset);db.session.flush();create_default_signals(asset)
        else:
            asset=Asset.query.filter_by(id=request.form.get('asset_id',type=int),customer_id=customer_id).first()
            if not asset or asset.id in active_asset_ids:
                flash('Select an unassigned asset or create a new one.','error');return redirect(url_for('main.connect_device'))
            if kind=='ANDROID_PHONE' and asset.asset_type!='TRACKER':
                flash('Android Phone can only be connected to a tracking asset.','error');return redirect(url_for('main.connect_device',asset_id=asset.id))
        if kind=='HARDWARE_PROFILE':
            metadata=dict(asset.metadata_json or {})
            metadata.update({'onboarding_source':'DEVICE_CENTRE','profile_code':profile['code'],'claim_state':'WAITING'})
            metadata.pop('primary_solution_profile',None)
            asset.metadata_json=metadata
            ensure_profile_signals(asset,profile)
            MobileTrackerRegistration.query.filter_by(customer_id=customer_id,asset_id=asset.id,used_at=None).delete(synchronize_session=False)
            code=f'{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}'
            pending_uid=f'AT360-CLAIM-{asset.id:06d}-{secrets.token_hex(3).upper()}'
            reg=MobileTrackerRegistration(customer_id=customer_id,asset_id=asset.id,code_hash=mobile_code_hash(code),device_uid=pending_uid,expires_at=utcnow()+timedelta(minutes=10),created_by=current_user.id,onboarding_kind='HARDWARE',profile_code=profile['code'],provisioning_state='WAITING')
            db.session.add(reg);db.session.flush()
            audit(customer_id,'HARDWARE_CLAIM_STARTED',asset.id,None,'USER',current_user.id,f"{profile['code']} claim code created; full verified board capability set will be configured after claim")
            db.session.commit()
            session['onboarding_registration_id']=reg.id
            session['onboarding_registration_code']=code
            session['onboarding_device_kind']='HARDWARE_PROFILE'
            session['onboarding_profile_code']=profile['code']
            session.pop('onboarding_solution_profile',None)
            flash(f"{profile['display_name']} claim code created. Configure the board functions after connection.",'ok')
            return redirect(url_for('main.connect_device_waiting'))
        MobileTrackerRegistration.query.filter_by(customer_id=customer_id,asset_id=asset.id,used_at=None).delete(synchronize_session=False)
        code=f'{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}'
        reg=MobileTrackerRegistration(customer_id=customer_id,asset_id=asset.id,code_hash=mobile_code_hash(code),device_uid=f'AT360-PHONE-{asset.id:06d}',expires_at=utcnow()+timedelta(minutes=30),created_by=current_user.id)
        db.session.add(reg);db.session.commit();session['onboarding_registration_id']=reg.id;session['onboarding_registration_code']=code
        return redirect(url_for('main.connect_device_waiting'))
    return render_template('connect_device.html',assets=assets,sites=sites,device_profiles=public_profiles(),has_sites=bool(sites),has_assets=bool(assets),preselected_asset=preselected_asset)
@bp.get('/devices/connect/waiting')
@login_required
def connect_device_waiting():
    reg_id=session.get('onboarding_registration_id');code=session.get('onboarding_registration_code')
    reg=MobileTrackerRegistration.query.filter_by(id=reg_id,customer_id=tenant_id()).first() if reg_id else None
    if not reg or not code:return redirect(url_for('main.connect_device'))
    if reg.used_at:return redirect(url_for('main.devices'))
    remaining_seconds=max(0,int((aware(reg.expires_at)-utcnow()).total_seconds()))
    if (session.get('onboarding_device_kind') or ('HARDWARE_PROFILE' if reg.onboarding_kind=='HARDWARE' else 'ANDROID_PHONE')) == 'HARDWARE_PROFILE':
        payload=json.dumps({
            'type':'assetops360_registration',
            'version':1,
            'api':request.url_root.rstrip('/'),
            'code':str(code).strip().upper(),
        },separators=(',',':'))
        mobile_registration_url=''
    else:
        # Standard phone cameras understand an HTTPS URL. No app, API address,
        # token copy or manual code entry is required by the phone user.
        mobile_registration_url=url_for('main.mobile_tracker_page',code=str(code).strip().upper(),_external=True,_scheme='https')
        payload=mobile_registration_url
    # Use the installed Segno package directly. The previous app.vendor wrapper
    # is not part of the deployed application and caused this route to return 500.
    # Keep a safe fallback so the claim code page still opens if QR support is
    # temporarily unavailable; the visible claim code remains usable manually.
    try:
        import segno
        qr=segno.make(payload,error='m')
        qr_data_uri=qr.svg_data_uri(scale=6,border=3,dark='#061622',light='#ffffff')
    except ImportError:
        current_app.logger.exception('QR generation unavailable: install segno')
        qr_data_uri=''
    return render_template('connect_device_waiting.html',registration=reg,code=code,asset=reg.asset,qr_data_uri=qr_data_uri,remaining_seconds=remaining_seconds,mobile_registration_url=mobile_registration_url,onboarding_kind=session.get('onboarding_device_kind') or ('HARDWARE_PROFILE' if reg.onboarding_kind=='HARDWARE' else 'ANDROID_PHONE'),onboarding_profile_code=session.get('onboarding_profile_code') or reg.profile_code or '',onboarding_solution_profile=session.get('onboarding_solution_profile') or '')

@bp.get('/api/v1/device-onboarding/status/<int:registration_id>')
@login_required
def device_onboarding_status(registration_id):
    reg=MobileTrackerRegistration.query.filter_by(id=registration_id,customer_id=tenant_id()).first_or_404()
    is_hardware=(reg.onboarding_kind=='HARDWARE') or bool(reg.profile_code)
    final_uid=reg.claimed_board_id if is_hardware else reg.device_uid
    device=Device.query.filter_by(customer_id=tenant_id(),asset_id=reg.asset_id,device_uid=final_uid,active=True).order_by(desc(Device.id)).first() if final_uid else None
    if not reg.used_at or not device:return jsonify(state='WAITING',kind='HARDWARE' if is_hardware else 'MOBILE',expires_at=aware(reg.expires_at).isoformat())
    if is_hardware:
        return jsonify(state='CONNECTED',kind='HARDWARE',device_uid=device.device_uid,asset_name=reg.asset.name,profile_code=reg.profile_code or device.profile_code,firmware=device.firmware or 'Awaiting first telemetry',provisioning_state=reg.provisioning_state or 'CONNECTED',last_contact=device.last_seen.isoformat() if device.last_seen else None,open_studio=url_for('main.universal_device_panel',asset_id=reg.asset_id),open_asset=url_for('main.asset_view',asset_id=reg.asset_id),open_devices=url_for('main.devices'))
    consent=MobileConsent.query.filter_by(customer_id=tenant_id(),device_uid=device.device_uid).order_by(desc(MobileConsent.id)).first()
    battery_sig=SignalDefinition.query.filter_by(asset_id=device.asset_id,key='battery_percent').first();battery=latest_reading(battery_sig.id) if battery_sig else None
    return jsonify(state='CONNECTED',kind='MOBILE',device_uid=device.device_uid,asset_name=reg.asset.name,app_version=device.firmware or 'Awaiting first telemetry',consent='Active' if consent and consent.active else 'Pending',battery=round(battery.value) if battery else None,last_contact=device.last_seen.isoformat() if device.last_seen else None,open_studio=url_for('main.universal_device_panel',asset_id=reg.asset_id),open_asset=url_for('main.asset_view',asset_id=reg.asset_id),open_devices=url_for('main.devices'))

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
    reg=MobileTrackerRegistration(customer_id=tenant_id(),asset_id=asset.id,code_hash=mobile_code_hash(code),device_uid=f'AT360-PHONE-{asset.id:06d}',expires_at=utcnow()+timedelta(minutes=30),created_by=current_user.id)
    db.session.add(reg);db.session.commit()
    session['onboarding_registration_id']=reg.id;session['onboarding_registration_code']=code
    audit(tenant_id(),'DEVICE_ONBOARDING_STARTED',asset.id,None,'USER',current_user.id,'Android phone onboarding started from asset screen');db.session.commit()
    return redirect(url_for('main.connect_device_waiting'))

@bp.get('/mobile-tracker/setup')
@login_required
def mobile_tracker_setup():
    if session.get('onboarding_registration_id') and session.get('onboarding_registration_code'):return redirect(url_for('main.connect_device_waiting'))
    flash('Start phone onboarding from Connect Device or the asset page to generate a QR code.','error')
    return redirect(url_for('main.connect_device'))

@bp.post('/api/v1/device/claim')
def hardware_device_claim():
    data=request.get_json(silent=True) or {}
    code=str(data.get('claim_code','')).strip().upper()
    board_id=re.sub(r'[^A-Z0-9]','',str(data.get('board_id','')).strip().upper())
    requested_profile=str(data.get('profile_code','')).strip().upper()
    firmware=str(data.get('firmware','')).strip()[:40]
    if not code:return jsonify(error='claim_code_required'),400
    if len(board_id)<6 or len(board_id)>32:return jsonify(error='invalid_board_id'),400
    reg=MobileTrackerRegistration.query.filter_by(code_hash=mobile_code_hash(code),used_at=None).first()
    if not reg:return jsonify(error='invalid_claim_code'),404
    if utcnow()>aware(reg.expires_at):
        reg.provisioning_state='EXPIRED';db.session.commit();return jsonify(error='claim_code_expired'),410
    if reg.onboarding_kind!='HARDWARE' and not reg.profile_code:return jsonify(error='hardware_claim_required'),422
    expected_profile=get_profile(reg.profile_code)
    if not expected_profile:return jsonify(error='registered_profile_not_available'),409
    if requested_profile!=expected_profile['code']:return jsonify(error='profile_mismatch',expected_profile=expected_profile['code']),409
    final_uid=('AT360-WROOM32-' if 'WROOM' in requested_profile else 'AT360-BOARD-')+board_id
    existing=Device.query.filter_by(device_uid=final_uid).first()
    if existing and (existing.customer_id!=reg.customer_id or existing.asset_id!=reg.asset_id):return jsonify(error='board_already_claimed'),409
    token=secrets.token_urlsafe(36)
    try:
        if existing:
            device=existing;device.active=True;device.api_token=token;device.device_type=expected_profile['device_type'];device.firmware=firmware or device.firmware
        else:
            device=Device(customer_id=reg.customer_id,asset_id=reg.asset_id,device_uid=final_uid,device_type=expected_profile['device_type'],api_token=token,active=True,firmware=firmware,capabilities=[])
            db.session.add(device)
        capabilities=[x for x in (device.capabilities or []) if not str(x).startswith('PROFILE:')]
        capabilities.extend(expected_profile.get('capabilities',[]));capabilities.append('PROFILE:'+expected_profile['code'])
        device.capabilities=list(dict.fromkeys(capabilities));db.session.flush()
        reg.device_uid=final_uid;reg.claimed_board_id=final_uid;reg.claimed_at=utcnow();reg.used_at=utcnow();reg.provisioning_state='CONNECTED'
        asset=db.session.get(Asset,reg.asset_id);asset.status='OFFLINE';metadata=dict(asset.metadata_json or {});metadata['claim_state']='CONNECTED';metadata['claimed_device_uid']=final_uid;asset.metadata_json=metadata
        ensure_profile_signals(asset,expected_profile)
        audit(reg.customer_id,'HARDWARE_CLAIM_COMPLETED',reg.asset_id,device.id,'DEVICE',None,f"{expected_profile['code']} claimed as {final_uid}")
        db.session.commit()
    except Exception:
        db.session.rollback();current_app.logger.exception('Hardware claim failed board_id=%s profile=%s',board_id,requested_profile);return jsonify(error='claim_failed_safely'),500
    return jsonify(status='claimed',device_uid=device.device_uid,device_token=token,profile_code=expected_profile['code'],asset_name=device.asset.name),201

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
    client_version=str(data.get('client_version') or 'mobile-web-2.0')[:40];platform=re.sub(r'[^A-Z0-9_-]','',str(data.get('platform') or 'WEB').upper())[:20] or 'WEB';device=Device(customer_id=reg.customer_id,asset_id=reg.asset_id,device_uid=reg.device_uid,device_type='MOBILE_WEB_TRACKER',api_token=token,active=True,firmware=client_version,capabilities=['GPS','PHONE_BATTERY','USER_CONSENT_REQUIRED','PLATFORM:'+platform])
    reg.used_at=utcnow();db.session.add(device);db.session.flush()
    consent=MobileConsent(customer_id=reg.customer_id,asset_id=reg.asset_id,device_id=device.id,device_uid=device.device_uid,policy_version=POLICY_VERSION,active=True,user_agent_summary=(request.headers.get('User-Agent') or '')[:240]);db.session.add(consent);audit(reg.customer_id,'CONSENT_ACCEPTED',reg.asset_id,device.id,'DEVICE',None,'Explicit location consent accepted');audit(reg.customer_id,'PHONE_REGISTERED',reg.asset_id,device.id,'DEVICE',None,'Mobile tracker registered')
    ensure_mobile_auto_profile(device)
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
    ensure_mobile_auto_profile(device)
    for point_key,point_value in (('speed_kmh',speed),('heading',data.get('heading')),('gps_accuracy_m',acc),('charging_status',1 if data.get('charging') else 0)):
        if point_value is None:continue
        mobile_sig=SignalDefinition.query.filter_by(customer_id=device.customer_id,asset_id=device.asset_id,key=point_key).first()
        mobile_seq=f'{sequence}:{point_key}'
        if mobile_sig and not Reading.query.filter_by(signal_id=mobile_sig.id,sequence=mobile_seq).first():db.session.add(Reading(customer_id=device.customer_id,asset_id=device.asset_id,signal_id=mobile_sig.id,sampled_at=sampled,value=float(point_value),unit=mobile_sig.unit,quality='GOOD',sequence=mobile_seq))
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
    policy=trend_policy_for(device)
    if battery is not None and sig and not signal_trend_enabled(device,sig):retain_latest_only(sig.id)
    if not policy.gps_history_enabled:
        policy.gps_history_enabled=True;policy.gps_retention_days=31
        audit(device.customer_id,'MOBILE_GPS_HISTORY_AUTO_ENABLED',device.asset_id,device.id,'DEVICE',None,'GPS route history enabled')
    device.last_seen=utcnow();device.asset.last_seen=sampled;device.firmware=str(data.get('client_version') or 'mobile-web-1.2')[:40]
    db.session.commit();return jsonify(status='accepted',sequence=sequence),202

@bp.get('/api/v1/mobile/status')
def mobile_tracker_status():
    device=mobile_tracker_device()
    if not device:return jsonify(error='invalid_mobile_tracker_token'),401
    latest=Location.query.filter_by(customer_id=device.customer_id,asset_id=device.asset_id).order_by(desc(Location.sampled_at)).first()
    age_seconds=max(0,int((utcnow()-aware(device.last_seen)).total_seconds())) if device.last_seen else None
    live_state='ONLINE' if age_seconds is not None and age_seconds<=300 else 'DELAYED' if age_seconds is not None and age_seconds<=900 else 'OFFLINE'
    return jsonify(status='ok',tracking_state=live_state,age_seconds=age_seconds,device_uid=device.device_uid,asset_name=device.asset.name,last_contact=device.last_seen.isoformat() if device.last_seen else None,last_position={'latitude':latest.latitude,'longitude':latest.longitude,'sampled_at':latest.sampled_at.isoformat(),'accuracy_m':latest.accuracy_m} if latest else None)

@bp.get('/api/v1/mobile/config')
def mobile_tracker_config():
    device=mobile_tracker_device()
    if not device:return jsonify(error='invalid_mobile_tracker_token'),401
    consent=consent_for_device(device)
    if not consent or not consent.active:return jsonify(error='consent_inactive'),403
    policy=trend_policy_for(device)
    return jsonify(status='ok',api_version='2026.2',device_uid=device.device_uid,asset_name=device.asset.name,
        location_interval_seconds=15,heartbeat_interval_seconds=60,max_batch_points=100,max_offline_queue=1000,
        gps_history_enabled=bool(policy.gps_history_enabled),gps_retention_days=policy.gps_retention_days or 31,
        features={'batch_upload':True,'offline_queue':True,'heartbeat':True,'battery':True,'charging':True,'speed':True,'heading':True,'safety_events':True,'phone_motion_profile':True,'candidate_events_only':True})

@bp.post('/api/v1/mobile/heartbeat')
def mobile_tracker_heartbeat():
    device=mobile_tracker_device()
    if not device:return jsonify(error='invalid_mobile_tracker_token'),401
    consent=consent_for_device(device)
    if not consent or not consent.active:return jsonify(error='consent_inactive'),403
    data=request.get_json(silent=True) or {}
    if str(data.get('device_id','')).upper()!=device.device_uid.upper():return jsonify(error='device_identity_mismatch'),403
    ensure_mobile_auto_profile(device)
    battery=data.get('battery_percent');charging=data.get('charging');sampled=utcnow();base_sequence=('heartbeat:'+str(data.get('sequence') or int(time.time())))[:70]
    if battery is not None:
        try:battery=max(0,min(100,float(battery)))
        except (TypeError,ValueError):return jsonify(error='invalid_battery_percent'),400
        sig=SignalDefinition.query.filter_by(customer_id=device.customer_id,asset_id=device.asset_id,key='battery_percent').first();sequence=base_sequence+':battery'
        if sig and not Reading.query.filter_by(signal_id=sig.id,sequence=sequence).first():db.session.add(Reading(customer_id=device.customer_id,asset_id=device.asset_id,signal_id=sig.id,sampled_at=sampled,value=battery,unit='%',quality='GOOD',sequence=sequence))
    if charging is not None:
        sig=SignalDefinition.query.filter_by(customer_id=device.customer_id,asset_id=device.asset_id,key='charging_status').first();sequence=base_sequence+':charging'
        if sig and not Reading.query.filter_by(signal_id=sig.id,sequence=sequence).first():db.session.add(Reading(customer_id=device.customer_id,asset_id=device.asset_id,signal_id=sig.id,sampled_at=sampled,value=1.0 if bool(charging) else 0.0,unit=sig.unit,quality='GOOD',sequence=sequence))
    capabilities=[c for c in (device.capabilities or []) if not str(c).startswith(('CHARGING:','PLATFORM:'))]
    platform=re.sub(r'[^A-Z0-9_-]','',str(data.get('platform') or 'WEB').upper())[:20] or 'WEB'
    capabilities.extend(['GPS','PHONE_BATTERY','PLATFORM:'+platform,'CHARGING:'+str(bool(data.get('charging'))).lower()]);device.capabilities=list(dict.fromkeys(capabilities))
    device.last_seen=sampled;device.asset.last_seen=sampled;device.firmware=str(data.get('client_version') or device.firmware or 'mobile-web-2.0')[:40]
    db.session.commit();return jsonify(status='online',tracking_state='ONLINE',server_time=sampled.isoformat()),202

@bp.post('/api/v1/mobile/location/batch')
def mobile_tracker_location_batch():
    device=mobile_tracker_device()
    if not device:return jsonify(error='invalid_mobile_tracker_token'),401
    consent=consent_for_device(device)
    if not consent or not consent.active:return jsonify(error='consent_inactive'),403
    allowed,_subscription=entitlement_for(device.customer_id)
    if not allowed:return jsonify(error='subscription_inactive'),402
    data=request.get_json(silent=True) or {};points=data.get('points')
    if not isinstance(points,list) or not points:return jsonify(error='points_required'),400
    if len(points)>100:return jsonify(error='batch_too_large',maximum=100),413
    ensure_mobile_auto_profile(device);accepted=[];duplicates=[];rejected=[]
    for index,item in enumerate(points):
        if not isinstance(item,dict):rejected.append({'index':index,'error':'invalid_point'});continue
        sequence=str(item.get('sequence','')).strip()[:80]
        if str(item.get('device_id','')).upper()!=device.device_uid.upper():rejected.append({'index':index,'sequence':sequence,'error':'device_identity_mismatch'});continue
        if not sequence:rejected.append({'index':index,'error':'sequence_required'});continue
        if Location.query.filter_by(asset_id=device.asset_id,sequence=sequence).first():duplicates.append(sequence);continue
        try:
            lat=float(item['latitude']);lon=float(item['longitude']);acc=max(0,float(item.get('accuracy_m') or 0));speed=max(0,float(item.get('speed_kmh') or 0))
            if not(-90<=lat<=90 and -180<=lon<=180) or speed>300:raise ValueError()
        except (KeyError,TypeError,ValueError):rejected.append({'index':index,'sequence':sequence,'error':'invalid_location_payload'});continue
        sampled=parse_time(item.get('timestamp'));speed=0.0 if speed<3 else speed
        # Store every valid mobile observation. Route analysis remains responsible for
        # excluding poor-accuracy points and impossible jumps from the operational route.
        db.session.add(Location(customer_id=device.customer_id,asset_id=device.asset_id,sampled_at=sampled,latitude=lat,longitude=lon,speed_kmh=speed,accuracy_m=acc,heading=item.get('heading'),sequence=sequence))
        for key,value in (('speed_kmh',speed),('heading',item.get('heading')),('gps_accuracy_m',acc),('charging_status',1 if item.get('charging') else 0),('battery_percent',item.get('battery_percent'))):
            if value is None:continue
            sig=SignalDefinition.query.filter_by(customer_id=device.customer_id,asset_id=device.asset_id,key=key).first();reading_sequence=f'{sequence}:{key}'
            if sig and not Reading.query.filter_by(signal_id=sig.id,sequence=reading_sequence).first():db.session.add(Reading(customer_id=device.customer_id,asset_id=device.asset_id,signal_id=sig.id,sampled_at=sampled,value=max(0,min(100,float(value))) if key=='battery_percent' else float(value),unit=sig.unit,quality='GOOD',sequence=reading_sequence))
        evaluate_mobile(device,item);accepted.append(sequence)
    policy=trend_policy_for(device)
    if not policy.gps_history_enabled:policy.gps_history_enabled=True;policy.gps_retention_days=31
    device.last_seen=utcnow();device.asset.last_seen=utcnow();batch_versions=[str(p.get('client_version') or '')[:40] for p in points if isinstance(p,dict) and p.get('client_version')];device.firmware=(batch_versions[-1] if batch_versions else device.firmware);db.session.commit()
    return jsonify(status='processed',device_uid=device.device_uid,accepted=accepted,duplicates=duplicates,rejected=rejected,accepted_count=len(accepted),duplicate_count=len(duplicates),rejected_count=len(rejected),server_time=utcnow().isoformat()),207 if rejected else 202

@bp.post('/api/v1/mobile/tracking/start')
def mobile_tracking_start():
    device=mobile_tracker_device()
    if not device:return jsonify(error='invalid_mobile_tracker_token'),401
    consent=consent_for_device(device)
    if not consent or not consent.active:return jsonify(error='consent_inactive'),403
    data=request.get_json(silent=True) or {};consent.last_tracking_started_at=utcnow();device.last_seen=utcnow();device.asset.last_seen=utcnow();device.firmware=str(data.get('client_version') or device.firmware or 'mobile-web-2.0')[:40];audit(device.customer_id,'TRACKING_STARTED',device.asset_id,device.id,'DEVICE',None,'Tracking started by mobile API');db.session.commit()
    return jsonify(status='tracking_started',device_uid=device.device_uid,asset_name=device.asset.name),202

@bp.post('/api/v1/mobile/tracking/stop')
def mobile_tracking_stop():
    device=mobile_tracker_device()
    if not device:return jsonify(error='invalid_mobile_tracker_token'),401
    consent=consent_for_device(device)
    if consent:consent.last_tracking_stopped_at=utcnow()
    device.last_seen=utcnow();audit(device.customer_id,'TRACKING_STOPPED',device.asset_id,device.id,'DEVICE',None,'Tracking stopped by mobile API');db.session.commit()
    return jsonify(status='tracking_stopped'),202

@bp.route('/api/v1/mobile/motion/capabilities',methods=['GET','POST'])
def mobile_motion_capabilities():
    device=mobile_tracker_device()
    if not device:return jsonify(error='invalid_mobile_tracker_token'),401
    consent=consent_for_device(device)
    if not consent or not consent.active:return jsonify(error='consent_inactive'),403
    prefixes=('MOTION_API:','ORIENTATION_API:','MOTION_PERMISSION:','MOTION_PROFILE:')
    if request.method=='POST':
        data=request.get_json(silent=True) or {}
        if str(data.get('device_id','')).upper()!=device.device_uid.upper():return jsonify(error='device_identity_mismatch'),403
        motion=bool(data.get('device_motion'));orientation=bool(data.get('device_orientation'));permission=str(data.get('permission') or 'UNKNOWN').upper()
        if permission not in ('GRANTED','DENIED','PROMPT','NOT_REQUIRED','UNKNOWN'):return jsonify(error='invalid_motion_permission'),400
        capabilities=[str(c) for c in (device.capabilities or []) if not str(c).startswith(prefixes) and str(c) not in ('MOTION_SENSORS','ORIENTATION_SENSOR','POSSIBLE_IMPACT','ABNORMAL_TILT','UNEXPECTED_MOVEMENT')]
        capabilities.extend([f'MOTION_API:{str(motion).lower()}',f'ORIENTATION_API:{str(orientation).lower()}',f'MOTION_PERMISSION:{permission}','MOTION_PROFILE:2.0'])
        if motion and permission in ('GRANTED','NOT_REQUIRED'):
            capabilities.extend(['MOTION_SENSORS','POSSIBLE_IMPACT','UNEXPECTED_MOVEMENT'])
        if orientation and permission in ('GRANTED','NOT_REQUIRED'):
            capabilities.extend(['ORIENTATION_SENSOR','ABNORMAL_TILT'])
        device.capabilities=list(dict.fromkeys(capabilities));device.last_seen=utcnow()
        audit(device.customer_id,'PHONE_MOTION_CAPABILITY_UPDATED',device.asset_id,device.id,'DEVICE',None,f'Motion={motion}; orientation={orientation}; permission={permission}')
        db.session.commit()
    caps=set(str(c) for c in (device.capabilities or []))
    return jsonify(status='ok',profile='PHONE_MOTION_SAFETY_2_0',capabilities={
        'motion_sensor':'MOTION_SENSORS' in caps,
        'orientation_sensor':'ORIENTATION_SENSOR' in caps,
        'possible_impact':'POSSIBLE_IMPACT' in caps,
        'abnormal_tilt':'ABNORMAL_TILT' in caps,
        'unexpected_movement':'UNEXPECTED_MOVEMENT' in caps,
        'power_tamper':False,
        'permission':next((x.split(':',1)[1] for x in caps if x.startswith('MOTION_PERMISSION:')),'UNKNOWN')
    })

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
    elif event in ('HARSH_BRAKING','SEVERE_BRAKING','HARSH_ACCELERATION','POSSIBLE_ACCIDENT','POSSIBLE_ACCIDENT_CANCELLED','CRASH_DETECTED','ROLLOVER_DETECTED','ABNORMAL_TILT','UNEXPECTED_MOVEMENT','EMERGENCY_ALERT'):
        if not consent or not consent.active:return jsonify(error='consent_inactive'),403
        sequence=str(data.get('sequence') or '').strip()[:140]
        if not sequence:return jsonify(error='sequence_required'),400
        existing=Live360SafetyEvent.query.filter_by(sequence=sequence).first()
        if existing:return jsonify(status='duplicate',event_id=existing.id),200
        def bounded(name,low,high,default=None):
            value=data.get(name,default)
            if value is None:return None
            return max(low,min(high,float(value)))
        try:
            sampled=parse_time(data.get('timestamp'));lat=bounded('latitude',-90,90);lon=bounded('longitude',-180,180)
            confidence=bounded('confidence',0,1,0);accuracy=bounded('accuracy_m',0,5000)
            before=bounded('speed_before_kmh',0,300);after=bounded('speed_after_kmh',0,300)
            peak=bounded('peak_acceleration_ms2',0,100);decel=bounded('deceleration_ms2',-30,30)
        except (TypeError,ValueError):return jsonify(error='invalid_safety_event_payload'),400
        severity='CRITICAL' if event in ('POSSIBLE_ACCIDENT','CRASH_DETECTED','ROLLOVER_DETECTED','ABNORMAL_TILT','EMERGENCY_ALERT') else 'HIGH' if event in ('HARSH_BRAKING','SEVERE_BRAKING') else 'WARNING'
        status='CANCELLED_BY_USER' if event=='POSSIBLE_ACCIDENT_CANCELLED' else 'POSSIBLE' if event in ('POSSIBLE_ACCIDENT','ABNORMAL_TILT','UNEXPECTED_MOVEMENT') else 'CONFIRMED' if event in ('CRASH_DETECTED','ROLLOVER_DETECTED','EMERGENCY_ALERT') else 'RECORDED'
        row=Live360SafetyEvent(customer_id=device.customer_id,asset_id=device.asset_id,device_id=device.id,event_type=event,severity=severity,confidence=confidence,status=status,sampled_at=sampled,latitude=lat,longitude=lon,accuracy_m=accuracy,speed_before_kmh=before,speed_after_kmh=after,peak_acceleration_ms2=peak,deceleration_ms2=decel,sequence=sequence,detail_json={'client_version':str(data.get('client_version') or '')[:40],'detection_version':'phone-motion-safety-2.0','roll_deg':bounded('roll_deg',-180,180),'pitch_deg':bounded('pitch_deg',-180,180),'motion_source':str(data.get('motion_source') or 'PHONE_WEB')[:30],'candidate_only':event in ('POSSIBLE_ACCIDENT','ABNORMAL_TILT','UNEXPECTED_MOVEMENT')})
        db.session.add(row);audit(device.customer_id,event,device.asset_id,device.id,'DEVICE',None,f'{event.replace("_"," ").title()} advisory received')
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

@bp.route('/notifications/email',methods=['GET','POST'])
@login_required
def notifications_email():
    profile=WorkspaceProfile.query.filter_by(customer_id=tenant_id()).first()
    if request.method=='POST':
        email=(request.form.get('contact_email') or current_user.email).strip().lower()
        if '@' not in email:flash('Enter a valid email address.','error');return redirect(url_for('main.notifications_email'))
        if not profile:profile=WorkspaceProfile(customer_id=tenant_id());db.session.add(profile)
        profile.contact_email=email
        defaults=FleetFeatureDefaults.query.filter_by(customer_id=tenant_id()).first()
        if not defaults:defaults=FleetFeatureDefaults(customer_id=tenant_id());db.session.add(defaults)
        defaults.email_notifications_enabled=request.form.get('enabled')=='on';defaults.updated_by=current_user.id;db.session.commit();flash('Email notification settings saved.','ok');return redirect(url_for('main.notifications_email'))
    logs=EmailNotificationLog.query.filter_by(customer_id=tenant_id()).order_by(EmailNotificationLog.created_at.desc()).limit(50).all()
    defaults=FleetFeatureDefaults.query.filter_by(customer_id=tenant_id()).first()
    return render_template('email_notifications.html',profile=profile,logs=logs,defaults=defaults)

@bp.post('/notifications/email/test')
@login_required
def test_notification_email():
    from .email_service import send_notification_email
    profile=WorkspaceProfile.query.filter_by(customer_id=tenant_id()).first();recipient=(profile.contact_email if profile and profile.contact_email else current_user.email)
    row=EmailNotificationLog(customer_id=tenant_id(),recipient=recipient,subject='AssetTrack 360 Test Notification',severity='INFO',state='QUEUED');db.session.add(row);db.session.flush()
    ok,message_id,error=send_notification_email(recipient,current_user.name,'AssetTrack 360 Test Notification','Test notification','This is not an active alarm. Email delivery is configured correctly.',url_for('main.dashboard',_external=True))
    row.state='SENT' if ok else 'FAILED';row.provider_message_id=message_id;row.failure_reason=error;row.sent_at=utcnow() if ok else None;db.session.commit();flash('Test email sent.' if ok else f'Test email failed: {error}','ok' if ok else 'error');return redirect(url_for('main.notifications_email'))

@bp.get('/alarms')
@login_required
def alarm_centre():
    state=request.args.get('state','OPEN').upper();query=Alarm.query.filter_by(customer_id=tenant_id())
    if state!='ALL':query=query.filter_by(state=state)
    alarms=query.order_by(Alarm.opened_at.desc()).limit(250).all();assets={a.id:a for a in Asset.query.filter_by(customer_id=tenant_id()).all()}
    counts={x:Alarm.query.filter_by(customer_id=tenant_id(),state=x).count() for x in ('OPEN','ACKNOWLEDGED','CLOSED')}
    return render_template('alarm_centre.html',alarms=alarms,assets=assets,counts=counts,state=state)

@bp.post('/alarms/<int:alarm_id>/action')
@login_required
def alarm_action(alarm_id):
    alarm=Alarm.query.filter_by(id=alarm_id,customer_id=tenant_id()).first_or_404();action=request.form.get('action','ACKNOWLEDGE').upper();note=request.form.get('note','').strip()[:500]
    if action=='ACKNOWLEDGE':alarm.state='ACKNOWLEDGED';alarm.acknowledged_at=utcnow();alarm.acknowledged_by=current_user.id;alarm.note=note or 'Acknowledged'
    elif action=='CLOSE':alarm.state='CLOSED';alarm.note=note or 'Closed after review'
    elif action=='REOPEN':alarm.state='OPEN';alarm.note=note or 'Reopened'
    else:abort(400)
    db.session.commit();flash(f'Alarm {action.lower()} complete.','ok');return redirect(url_for('main.alarm_centre',state=request.form.get('return_state','OPEN')))

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
        items.append({'device':record,'asset':record.asset,'online':online,'last_contact':last_contact,'consent':consent,'battery':battery,'profile':device_profile_context(record)})
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

    customer_id=record.customer_id
    expected_uid=str(record.device_uid or '').strip()

    try:
        # Remove or detach every real foreign-key reference to device.id before
        # deleting the identity. This also covers newer tables such as mobile
        # state, channel assignments and hardware claim registrations without
        # making the route depend on a specific deployed schema revision.
        inspector=inspect(db.engine)
        preparer=db.engine.dialect.identifier_preparer
        for table_name in inspector.get_table_names():
            if table_name=='device':
                continue
            columns={c['name']:c for c in inspector.get_columns(table_name)}
            for fk in inspector.get_foreign_keys(table_name):
                if fk.get('referred_table')!='device':
                    continue
                constrained=fk.get('constrained_columns') or []
                referred=fk.get('referred_columns') or []
                if len(constrained)!=1 or referred!=['id']:
                    continue
                column_name=constrained[0]
                table_sql=preparer.quote(table_name)
                column_sql=preparer.quote(column_name)
                if columns.get(column_name,{}).get('nullable',True):
                    db.session.execute(
                        text(f'UPDATE {table_sql} SET {column_sql}=NULL WHERE {column_sql}=:device_id'),
                        {'device_id':record.id},
                    )
                else:
                    db.session.execute(
                        text(f'DELETE FROM {table_sql} WHERE {column_sql}=:device_id'),
                        {'device_id':record.id},
                    )

        # Revoke the old token in the same transaction, then remove only the
        # device identity. The linked asset remains available for a replacement.
        record.api_token=secrets.token_urlsafe(32)
        db.session.flush()
        db.session.delete(record)
        db.session.commit()
        flash(f'Device {expected_uid} permanently deleted. The linked asset was retained.','ok')
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception('Permanent device delete failed device_id=%s customer_id=%s',device_id,customer_id)
        flash(f'Device deletion failed safely: {type(exc).__name__}. No partial deletion was committed.','error')

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
    'MQTT':{'label':'MQTT Broker','mode':'CLOUD_OR_EDGE','endpoint':'mqtts://broker.example:8883','implemented':'RUNTIME_READY'},
    'REST_API':{'label':'REST API','mode':'CLOUD_PULL','endpoint':'https://provider.example/api','implemented':'RUNTIME_READY'},
    'WEBHOOK':{'label':'Webhook','mode':'CLOUD_PUSH','endpoint':'Generated after save','implemented':'AVAILABLE'},
    'OPC_UA':{'label':'OPC UA','mode':'EDGE_OUTBOUND','endpoint':'opc.tcp://server:4840','implemented':'EDGE_READY'},
    'OPC_CLASSIC':{'label':'OPC Classic','mode':'EDGE_OUTBOUND','endpoint':'Local OPC DA server','implemented':'EDGE_REQUIRED'},
    'MODBUS_TCP':{'label':'Modbus TCP','mode':'EDGE_OUTBOUND','endpoint':'192.168.1.20:502','implemented':'EDGE_READY'},
    'MODBUS_RTU':{'label':'Modbus RTU','mode':'EDGE_OUTBOUND','endpoint':'COM3 / 9600 / 8N1','implemented':'EDGE_REQUIRED'},
    'SQL_ODBC':{'label':'SQL / ODBC','mode':'EDGE_OUTBOUND','endpoint':'Read-only DSN','implemented':'EDGE_READY'},
    'CSV_IMPORT':{'label':'CSV Import','mode':'EDGE_OR_UPLOAD','endpoint':'Upload or watched folder','implemented':'AVAILABLE'},
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
        connector.status='CONFIGURED';connector.last_error=None;status='OK';detail='Configuration validation passed. Live protocol status remains test-ready until an end-to-end connection succeeds.'
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


@bp.post('/integrations/<int:connector_id>/rest/run')
@login_required
def rest_connector_run(connector_id):
 connector=connector_for_tenant(connector_id)
 if connector.connector_type!='REST_API':abort(404)
 cfg=ConnectorEndpointConfig.query.filter_by(connector_id=connector.id).first_or_404()
 from .rest_runtime import pull_once
 result=pull_once(connector,cfg);flash(f"REST pull completed: {result.get('mapped',0)} points mapped." if result.get('ok') else result.get('error','REST pull failed.'),'ok' if result.get('ok') else 'error')
 return redirect(url_for('main.universal_connector',connector_id=connector.id))

@bp.post('/integrations/<int:connector_id>/webhook/test')
@login_required
def webhook_test_sample(connector_id):
 connector=connector_for_tenant(connector_id)
 if connector.connector_type!='WEBHOOK':abort(404)
 payload=request.get_json(silent=True) if request.is_json else json.loads(request.form.get('sample_payload') or '{}')
 from .integration_runtime import map_payload
 try:mapped=map_payload(connector,payload,'webhook-test');connector.last_success_at=utcnow();connector.status='CONNECTED';db.session.add(IntegrationJobEvent(customer_id=tenant_id(),connector_id=connector.id,worker_type='WEBHOOK_TEST',status='OK',mapped_points=mapped,detail=f'{mapped} points mapped from authenticated in-app test'));db.session.commit();flash(f'Webhook sample accepted: {mapped} points mapped.','ok')
 except Exception as exc:db.session.rollback();flash(f'Webhook sample failed: {type(exc).__name__}.','error')
 return redirect(url_for('main.universal_connector',connector_id=connector.id))

@bp.route('/integrations/<int:connector_id>/csv-import',methods=['GET','POST'])
@login_required
def csv_import_connector(connector_id):
 import csv,hashlib
 connector=connector_for_tenant(connector_id)
 if connector.connector_type!='CSV_IMPORT':abort(404)
 assets=Asset.query.filter_by(customer_id=tenant_id()).order_by(Asset.name).all();result=None
 if request.method=='POST':
  upload=request.files.get('csv_file');delimiter=request.form.get('delimiter',',')
  if not upload or not upload.filename.lower().endswith('.csv'):flash('Select a CSV file.','error');return redirect(request.url)
  raw=upload.read(5*1024*1024+1)
  if len(raw)>5*1024*1024:flash('CSV exceeds the 5 MB limit.','error');return redirect(request.url)
  try:rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig')),delimiter=delimiter))[:10001]
  except Exception:flash('CSV could not be parsed as UTF-8.','error');return redirect(request.url)
  if len(rows)>10000:flash('CSV exceeds the 10,000 row limit.','error');return redirect(request.url)
  asset=Asset.query.filter_by(id=request.form.get('asset_id',type=int),customer_id=tenant_id()).first_or_404();signal=SignalDefinition.query.filter_by(id=request.form.get('signal_id',type=int),asset_id=asset.id,customer_id=tenant_id()).first_or_404();value_col=request.form.get('value_column','').strip();time_col=request.form.get('timestamp_column','').strip();quality_col=request.form.get('quality_column','').strip();scale=float(request.form.get('scale') or 1);offset=float(request.form.get('offset') or 0);dry=request.form.get('dry_run')=='on';valid=stored=duplicates=errors=0
  for index,row in enumerate(rows,1):
   try:
    raw_value=float(row[value_col]);value=raw_value*scale+offset;sampled=parse_time(row.get(time_col)) if time_col else utcnow();quality=str(row.get(quality_col) or 'GOOD')[:20] if quality_col else 'GOOD';seq='csv:'+hashlib.sha256(f'{connector.id}:{signal.id}:{index}:{sampled.isoformat()}:{raw_value}'.encode()).hexdigest()[:40];valid+=1
    if not dry:
     if Reading.query.filter_by(signal_id=signal.id,sequence=seq).first():duplicates+=1;continue
     db.session.add(Reading(customer_id=tenant_id(),asset_id=asset.id,signal_id=signal.id,sampled_at=sampled,value=value,raw_value=raw_value,unit=signal.unit,quality=quality,sequence=seq));stored+=1
   except Exception:errors+=1
  if not dry:asset.last_seen=utcnow();connector.last_success_at=utcnow();connector.status='CONNECTED';db.session.add(IntegrationJobEvent(customer_id=tenant_id(),connector_id=connector.id,worker_type='CSV_IMPORT',status='OK' if not errors else 'PARTIAL',mapped_points=stored,detail=f'{stored} stored; {errors} errors; {duplicates} duplicates'));db.session.commit()
  result={'message':'Preview completed. No rows stored.' if dry else 'CSV import completed.','rows':len(rows),'valid':valid,'stored':stored,'duplicates':duplicates,'errors':errors,'headers':list(rows[0].keys()) if rows else [],'preview':rows[:10]}
 return render_template('csv_import.html',connector=connector,assets=assets,result=result)

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
@bp.post('/api/v1/integrations/<int:connector_id>/mqtt/message')
def mqtt_worker_message(connector_id):
 import os
 supplied=request.headers.get('Authorization','').removeprefix('Bearer ').strip();expected=os.getenv('MQTT_WORKER_TOKEN','')
 if not expected or not secrets.compare_digest(supplied,expected):return jsonify(error='unauthorized'),401
 connector=IntegrationConnector.query.filter_by(id=connector_id,connector_type='MQTT',enabled=True).first()
 if not connector:return jsonify(error='connector_not_found'),404
 topic=request.headers.get('X-MQTT-Topic','').strip()
 if not topic:return jsonify(error='topic_required'),400
 from .mqtt_runtime import process_message
 mapped=process_message(connector,topic,request.get_data(cache=False));return jsonify(status='accepted',mapped_points=mapped),202

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
def billing_success():
    reconcile_customer_payment(tenant_id())
    return render_template('payment_result.html',result='success')
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
            payment.invoice_number = payment.invoice_number or f'AT360-INV-{payment.id:07d}'
            sub=activate_paid_subscription(payment,'Validated PayFast COMPLETE ITN')
            if not sub:
                current_app.logger.error('PayFast COMPLETE has no matching subscription payment_id=%s customer_id=%s',payment.id,payment.customer_id)
                db.session.rollback();return 'INVALID',500
            sub.payfast_subscription_token=form.get('token') or sub.payfast_subscription_token
        elif form.get('payment_status') in ('FAILED', 'CANCELLED'):
            payment.status = form.get('payment_status')
    db.session.commit()
    return ('OK', 200) if accepted else ('INVALID', 400)

@bp.post('/api/v1/ingest')
def ingest():
    token=request.headers.get('Authorization','').removeprefix('Bearer ').strip()
    device=Device.query.filter_by(api_token=token,active=True).first()
    if not device:return jsonify(error='unauthorized'),401
    allowed,subscription=entitlement_for(device.customer_id)
    if not allowed:return jsonify(error='subscription_inactive',state=subscription.state if subscription else 'MISSING',billing_url='/billing'),402
    payload=request.get_json(silent=True) or {}
    if payload.get('device_id') and payload['device_id']!=device.device_uid:return jsonify(error='device_id mismatch'),403
    sampled=parse_time(payload.get('timestamp'));sequence=str(payload.get('sequence','')).strip();stored=[];duplicates=[];asset=device.asset
    incoming_keys={str(item.get('point','')).strip() for item in payload.get('measurements',[]) if str(item.get('point','')).strip()}
    apply_dashboard_selection=bool(payload.get('dashboard_selection'))
    managed_keys=set(BOARD_TELEMETRY_SPECS.get(device.device_type,{}))|set(PASSTHROUGH_SIGNAL_SPECS)
    if apply_dashboard_selection:
        for existing_signal in SignalDefinition.query.filter_by(customer_id=device.customer_id,asset_id=asset.id).all():
            if existing_signal.key in managed_keys:
                existing_cfg=dict(existing_signal.config_json or {});existing_cfg['selected_in_last_payload']=existing_signal.key in incoming_keys;existing_signal.config_json=existing_cfg
    esp32_specs={
        'analog_1':('Analog Input','CUSTOM','%','numeric'),
        'analog_1_volts':('Analog Input Voltage','VOLTAGE','V','numeric'),
        'digital_1':('Digital Input','STATE','','numeric'),
        'pulse_1_count':('Pulse Count','COUNT','pulses','numeric'),
        'local_arm_status':('Local Arm Status','STATE','','numeric'),
        'test_output_feedback':('Test Output Feedback','STATE','','numeric'),
    }
    for item in payload.get('measurements',[]):
        key=str(item.get('point','')).strip()
        if not key:continue
        sig=SignalDefinition.query.filter_by(customer_id=device.customer_id,asset_id=asset.id,key=key).first()
        if not sig:
            profile=profile_for_device(device);channel=next((x for x in (profile or {}).get('channels',[]) if x['key']==key),None)
            if channel:
                sig=SignalDefinition(customer_id=device.customer_id,asset_id=asset.id,key=key,label=channel['label'],signal_type=channel['signal_type'],source_type=channel['source_type'],unit=channel.get('unit',''),widget=channel.get('widget','numeric'),enabled=True,config_json={'profile_code':profile['code'],'direction':channel.get('direction','INPUT'),'command_channel':channel.get('command_channel')});db.session.add(sig);db.session.flush()
            else:
                board_spec=board_telemetry_spec(device,key)
                passthrough_spec=PASSTHROUGH_SIGNAL_SPECS.get(key) if device.device_type!='ESP32_REMOTE_IO' else None
                spec=board_spec or passthrough_spec
                if spec:
                    label,signal_type,unit,widget=spec
                    sig=SignalDefinition(customer_id=device.customer_id,asset_id=asset.id,key=key,label=label,signal_type=signal_type,source_type='API',unit=unit,widget=widget,enabled=True,calibration_mode='PASSTHROUGH',raw_min=0,raw_max=100,eng_min=0,eng_max=100,offset=0,filter_alpha=1,deadband=0,config_json={'auto_discovered':True,'device_type':device.device_type});db.session.add(sig);db.session.flush()
        if not sig:continue
        selected_cfg=dict(sig.config_json or {});selected_cfg['selected_in_last_payload']=True if apply_dashboard_selection else selected_cfg.get('selected_in_last_payload',False);sig.config_json=selected_cfg
        if not sig.enabled:sig.enabled=True
        enforce_passthrough_signal(sig,key)
        try:
            raw=float(item.get('value'));value=scale_signal(sig,raw);previous=latest_reading(sig.id)
            alpha=max(0.01,min(1.0,float(getattr(sig,'filter_alpha',1) or 1)))
            if previous:value=alpha*value+(1-alpha)*float(previous.value)
            if previous and abs(value-float(previous.value))<max(0,float(getattr(sig,'deadband',0) or 0)):value=float(previous.value)
        except (TypeError,ValueError):continue
        seq=f'{sequence}:{sig.key}' if sequence else f'{sampled.isoformat()}:{sig.key}'
        if Reading.query.filter_by(signal_id=sig.id,sequence=seq).first():
            duplicates.append(sig.key);continue
        db.session.add(Reading(customer_id=device.customer_id,asset_id=asset.id,signal_id=sig.id,sampled_at=sampled,value=value,raw_value=raw,unit=sig.unit,quality=item.get('quality','GOOD'),sequence=seq))
        evaluate_alarm(sig,value);stored.append(sig.key)
        strap=dict(sig.config_json or {}).get('tank_strapping') if sig.key in ('level_percent','level_mm','level_m','analog_1') else None
        if strap and strap.get('enabled'):
            volume=tank_volume_from_level(value,strap.get('points'))
            if volume is not None:
                volume_sig=SignalDefinition.query.filter_by(customer_id=device.customer_id,asset_id=asset.id,key='volume_l').first()
                if not volume_sig:
                    volume_sig=SignalDefinition(customer_id=device.customer_id,asset_id=asset.id,key='volume_l',label='Tank Volume',signal_type='LEVEL',source_type='DERIVED',unit=strap.get('volume_unit','L'),widget='numeric',enabled=True,calibration_mode='PASSTHROUGH');db.session.add(volume_sig);db.session.flush()
                volume_seq=f'{sequence}:volume_l' if sequence else f'{sampled.isoformat()}:volume_l'
                if not Reading.query.filter_by(signal_id=volume_sig.id,sequence=volume_seq).first():
                    db.session.add(Reading(customer_id=device.customer_id,asset_id=asset.id,signal_id=volume_sig.id,sampled_at=sampled,value=volume,raw_value=value,unit=volume_sig.unit,quality=item.get('quality','GOOD'),sequence=volume_seq));evaluate_alarm(volume_sig,volume);stored.append('volume_l')
    loc=payload.get('location') or {}
    location_accepted=False;location_duplicate=False;location_rejection=None;location_id=None
    # Accept one authoritative location object from the authenticated device only.
    # The linked Device.asset_id is always used, so a phone token can never write
    # GPS history to a SIM808 tank asset or vice versa.
    if loc.get('latitude') is not None and loc.get('longitude') is not None:
        try:
            latitude=float(loc['latitude']);longitude=float(loc['longitude']);accuracy=max(0.0,float(loc.get('accuracy_m') or 0));speed=max(0.0,float(loc.get('speed_kmh') or 0));heading=float(loc.get('heading') or 0)
            if not (-90<=latitude<=90 and -180<=longitude<=180):raise ValueError('coordinates_out_of_range')
            if abs(latitude)<0.000001 and abs(longitude)<0.000001:raise ValueError('zero_zero_is_not_a_fix')
            if speed>300:raise ValueError('speed_out_of_range')
            location_sequence=(sequence or f"gps-{device.id}-{int(sampled.timestamp()*1000)}")[:80]
            existing_location=Location.query.filter_by(asset_id=asset.id,sequence=location_sequence).first()
            if existing_location:
                location_duplicate=True;location_id=existing_location.id
            else:
                row=Location(customer_id=device.customer_id,asset_id=asset.id,sampled_at=sampled,latitude=latitude,longitude=longitude,speed_kmh=speed,accuracy_m=accuracy,heading=heading,sequence=location_sequence);db.session.add(row);db.session.flush();location_accepted=True;location_id=row.id
        except (TypeError,ValueError) as exc:
            location_rejection=str(exc) or 'invalid_location_payload'
    policy=trend_policy_for(device)
    for signal_key in stored:
        sig=SignalDefinition.query.filter_by(customer_id=device.customer_id,asset_id=asset.id,key=signal_key).first()
        if sig and not signal_trend_enabled(device,sig):retain_latest_only(sig.id)
    # GPS-capable registered hardware must retain route history. Do not collapse
    # a SIM808 tank, vehicle, bowser or generic GPS asset to one last-known row.
    profile=profile_for_device(device) or {};profile_keys={str(x.get('key') or '').lower() for x in profile.get('channels',[])};device_caps={str(x).upper() for x in (device.capabilities or [])};gps_capable=bool({'GPS','GNSS'} & device_caps or {'gps_fix','gps_location','latitude','longitude'} & profile_keys)
    if gps_capable:
        policy.gps_history_enabled=True
        if int(policy.gps_retention_days or 0) not in (31,93):policy.gps_retention_days=31
    elif location_accepted and not policy.gps_history_enabled:
        retain_latest_location_only(asset.id)
    device.last_seen=utcnow();asset.last_seen=utcnow();device.firmware=payload.get('firmware',device.firmware)
    db.session.commit();return jsonify(status='accepted',device_uid=device.device_uid,asset_id=asset.id,asset_name=asset.name,points=list(dict.fromkeys(stored+duplicates)),stored=list(dict.fromkeys(stored)),duplicates=list(dict.fromkeys(duplicates)),sequence=sequence,location_accepted=location_accepted,location_duplicate=location_duplicate,location_id=location_id,location_rejection=location_rejection,gps_history_enabled=bool(policy.gps_history_enabled),server_time=utcnow().isoformat()),202
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

# Predictive Safety Twin Batch 1-2: strict evidence-aware operational view.
def analyse_safety_twin_points(rows):
    """Build an evidence chain without allowing GPS drift to become movement.

    Raw observations are retained, but movement requires three consecutive points
    outside an accuracy-aware stationary envelope and at least 20 seconds of
    sustained displacement. Predictions are never persisted as telemetry.
    """
    raw=[]; rejected=[]; movement=[]; drift=[]; anchor=None; candidate=[]
    for row in rows:
        acc=max(3.0,float(row.accuracy_m or 0)); item={'latitude':float(row.latitude),'longitude':float(row.longitude),'accuracy':acc,'speed':max(0.0,float(row.speed_kmh or 0)),'timestamp':aware(row.sampled_at).isoformat()}
        raw.append(item)
        if not (-90<=item['latitude']<=90 and -180<=item['longitude']<=180) or (abs(item['latitude'])<.000001 and abs(item['longitude'])<.000001):
            item['reason']='INVALID_COORDINATES';rejected.append(item);continue
        if acc>100:
            item['reason']='POOR_ACCURACY';rejected.append(item);continue
        if anchor is None: anchor=row;drift.append(item);continue
        elapsed=max(0.0,(aware(row.sampled_at)-aware(anchor.sampled_at)).total_seconds())
        distance_m=_distance_km(anchor,row)*1000
        envelope=max(25.0,min(100.0,float(anchor.accuracy_m or 0)+acc))
        if distance_m<=envelope:
            candidate=[];drift.append(item);continue
        candidate.append((row,item,distance_m,elapsed))
        if len(candidate)>=3 and elapsed>=20:
            movement.extend(x[1] for x in candidate);anchor=row;candidate=[]
    distance_km=0.0;maximum=0.0;moving_seconds=0.0
    previous=None
    for item in movement:
        if previous:
            seconds=max(0.0,(datetime.fromisoformat(item['timestamp'])-datetime.fromisoformat(previous['timestamp'])).total_seconds())
            km=_distance_km(type('P',(),previous),type('P',(),item));distance_km+=km
            calculated=km/(seconds/3600) if seconds else 0.0
            maximum=max(maximum,min(300.0,calculated));moving_seconds+=seconds
        previous=item
    confidence=max(0,min(100,100-len(rejected)*8-(5 if len(raw)<3 else 0)))
    return {'raw':raw,'rejected':rejected,'movement':movement,'drift':drift,'raw_count':len(raw),'rejected_count':len(rejected),'movement_count':len(movement),'drift_count':len(drift),'distance_km':round(distance_km,2),'maximum_speed':round(maximum),'movement_minutes':round(moving_seconds/60),'stationary_minutes':round(max(0,((aware(rows[-1].sampled_at)-aware(rows[0].sampled_at)).total_seconds()-moving_seconds)/60)) if len(rows)>1 else 0,'confidence':confidence,'state':'MOVING' if movement else 'STATIONARY'}

@bp.get('/asset/<int:asset_id>/safety-twin')
@login_required
def safety_twin(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404()
    now=utcnow();rows=Location.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).order_by(desc(Location.sampled_at)).limit(250).all();rows=list(reversed(rows))
    twin=analyse_safety_twin_points(rows)
    latest=rows[-1] if rows else None
    device=Device.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,active=True).order_by(desc(Device.last_seen)).first()
    safety=(asset.metadata_json or {}).get('tracking_safety',{}) or {};zones=safety.get('zones',[]) if isinstance(safety.get('zones',[]),list) else []
    caps=set(str(x).upper() for x in (device.capabilities or [])) if device else set()
    battery_sig=SignalDefinition.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,key='battery_percent').first()
    battery=Reading.query.filter_by(signal_id=battery_sig.id).order_by(desc(Reading.sampled_at)).first() if battery_sig else None
    last_age=int(max(0,(now-aware(device.last_seen)).total_seconds())//60) if device and device.last_seen else None
    evidence=[{'label':'GPS observations','detail':f"{twin['raw_count']} raw points received",'state':'MEASURED'},{'label':'Quality gate','detail':f"{twin['rejected_count']} point(s) rejected",'state':'VALIDATED'},{'label':'Stationary envelope','detail':f"{twin['drift_count']} point(s) remained inside uncertainty",'state':'PROVED'},{'label':'Movement confirmation','detail':f"{twin['movement_count']} confirmed movement point(s)",'state':'PROVED'}]
    return render_template('safety_twin.html',asset=asset,device=device,twin=twin,latest=latest,zones=zones,safety=safety,caps=caps,battery=battery,last_age=last_age,evidence=evidence,now=now)

# Evidence Report & Client Export Centre - Batch 3
def _evidence_role_allowed():
    return current_user.role in ('customer_admin','platform_admin')

def _evidence_payload(asset,twin,rows,device,zones,evidence,report_type='CURRENT_STATE'):
    from .evidence_reports import report_id, canonical_json
    generated=utcnow();battery_sig=SignalDefinition.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,key='battery_percent').first();battery=Reading.query.filter_by(signal_id=battery_sig.id).order_by(desc(Reading.sampled_at)).first() if battery_sig else None
    charging='Unknown'
    if device:
        values=[str(x) for x in (device.capabilities or []) if str(x).startswith('CHARGING:')]
        if values:charging='Yes' if values[-1].split(':',1)[1].lower()=='true' else 'No'
    events=Live360SafetyEvent.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).order_by(desc(Live360SafetyEvent.sampled_at)).limit(100).all()
    base={'customer_name':asset.customer.name,'asset_name':asset.name,'asset_id':asset.id,'device_uid':device.device_uid if device else 'NO ACTIVE DEVICE','firmware':device.firmware if device else 'Not reported','report_type':report_type,'period':f"{aware(rows[0].sampled_at).isoformat() if rows else 'No observations'} to {aware(rows[-1].sampled_at).isoformat() if rows else 'No observations'}",'generated_at':generated.isoformat(),'generated_by':current_user.email,'state':twin['state'],'distance_km':twin['distance_km'],'movement_minutes':twin['movement_minutes'],'stationary_minutes':twin['stationary_minutes'],'maximum_speed':twin['maximum_speed'],'confidence':twin['confidence'],'raw_count':twin['raw_count'],'movement_count':twin['movement_count'],'drift_count':twin['drift_count'],'rejected_count':twin['rejected_count'],'battery':f"{float(battery.value):.0f}%" if battery else 'Not reported','charging':charging,'geofence_count':len(zones),'evidence':evidence,'accepted_locations':twin['movement'],'rejected_observations':twin['rejected'],'stationary_drift':[dict(x,reason='STATIONARY_DRIFT') for x in twin['drift']],'safety_events':[{'timestamp':aware(x.sampled_at).isoformat(),'event_type':x.event_type,'severity':x.severity,'status':x.status,'confidence':x.confidence} for x in events],'device_status':{'device_uid':device.device_uid if device else None,'firmware':device.firmware if device else None,'last_seen':aware(device.last_seen).isoformat() if device and device.last_seen else None,'active':bool(device and device.active),'capabilities':device.capabilities if device else []},'geofences':zones}
    base['payload_sha256']=hashlib.sha256(canonical_json(base)).hexdigest();base['report_id']=report_id(asset.id,generated,base);return base

@bp.get('/asset/<int:asset_id>/evidence')
@login_required
def evidence_centre(asset_id):
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();device=Device.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,active=True).order_by(desc(Device.last_seen)).first();audits=SecurityAuditEvent.query.filter(SecurityAuditEvent.customer_id==tenant_id(),SecurityAuditEvent.asset_id==asset.id,SecurityAuditEvent.event_type.in_(['EVIDENCE_REPORT_GENERATED','EVIDENCE_PACK_EXPORTED'])).order_by(desc(SecurityAuditEvent.created_at)).limit(30).all()
    return render_template('evidence_centre.html',asset=asset,device=device,audits=audits,can_export=_evidence_role_allowed())

@bp.get('/asset/<int:asset_id>/evidence.pdf')
@login_required
def evidence_pdf(asset_id):
    if not _evidence_role_allowed():abort(403)
    from .evidence_reports import build_pdf
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();rows=Location.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).order_by(desc(Location.sampled_at)).limit(250).all();rows=list(reversed(rows));twin=analyse_safety_twin_points(rows);device=Device.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,active=True).order_by(desc(Device.last_seen)).first();safety=(asset.metadata_json or {}).get('tracking_safety',{}) or {};zones=safety.get('zones',[]) if isinstance(safety.get('zones',[]),list) else [];evidence=[{'label':'GPS observations','detail':f"{twin['raw_count']} raw points received",'state':'MEASURED'},{'label':'Quality gate','detail':f"{twin['rejected_count']} point(s) rejected",'state':'VALIDATED'},{'label':'Stationary envelope','detail':f"{twin['drift_count']} point(s) excluded as drift",'state':'PROVED'},{'label':'Movement confirmation','detail':f"{twin['movement_count']} movement point(s) confirmed",'state':'PROVED'}];payload=_evidence_payload(asset,twin,rows,device,zones,evidence);data=build_pdf(payload);audit(tenant_id(),'EVIDENCE_REPORT_GENERATED',asset.id,device.id if device else None,'ASSET',payload['report_id'],'PDF evidence report generated');db.session.commit();return send_file(io.BytesIO(data),mimetype='application/pdf',as_attachment=True,download_name=f"{payload['report_id']}.pdf")

@bp.get('/asset/<int:asset_id>/evidence-pack.zip')
@login_required
def evidence_pack(asset_id):
    if not _evidence_role_allowed():abort(403)
    from .evidence_reports import build_pack
    asset=Asset.query.filter_by(id=asset_id,customer_id=tenant_id()).first_or_404();rows=Location.query.filter_by(customer_id=tenant_id(),asset_id=asset.id).order_by(desc(Location.sampled_at)).limit(250).all();rows=list(reversed(rows));twin=analyse_safety_twin_points(rows);device=Device.query.filter_by(customer_id=tenant_id(),asset_id=asset.id,active=True).order_by(desc(Device.last_seen)).first();safety=(asset.metadata_json or {}).get('tracking_safety',{}) or {};zones=safety.get('zones',[]) if isinstance(safety.get('zones',[]),list) else [];evidence=[{'label':'GPS observations','detail':f"{twin['raw_count']} raw points received",'state':'MEASURED'},{'label':'Quality gate','detail':f"{twin['rejected_count']} point(s) rejected",'state':'VALIDATED'},{'label':'Stationary envelope','detail':f"{twin['drift_count']} point(s) excluded as drift",'state':'PROVED'},{'label':'Movement confirmation','detail':f"{twin['movement_count']} movement point(s) confirmed",'state':'PROVED'}];payload=_evidence_payload(asset,twin,rows,device,zones,evidence);data=build_pack(payload);audit(tenant_id(),'EVIDENCE_PACK_EXPORTED',asset.id,device.id if device else None,'ASSET',payload['report_id'],'Evidence ZIP pack exported');db.session.commit();return send_file(io.BytesIO(data),mimetype='application/zip',as_attachment=True,download_name=f"{payload['report_id']}.zip")
