"""AssetTrack 360 mobile motion-safety setup, confirmation and API guards.
Advisory safety logic only. It is not a certified emergency or crash-detection system.
"""
from collections import defaultdict,deque
from datetime import datetime,timezone,timedelta
import secrets,threading,time
from flask import Blueprint,abort,jsonify,render_template,request
from flask_login import current_user,login_required
from . import db
from .models import Asset,Device,EmailNotificationLog,Live360SafetyEvent,SecurityAuditEvent,WorkspaceProfile
motion_bp=Blueprint('motion_safety',__name__)
_LOCK=threading.Lock();_BUCKETS=defaultdict(deque)
def now():return datetime.now(timezone.utc)
def aware(v):return v if not v or v.tzinfo else v.replace(tzinfo=timezone.utc)
def bearer():return request.headers.get('Authorization','').removeprefix('Bearer ').strip()
def device_auth():return Device.query.filter_by(api_token=bearer(),active=True).first() if bearer() else None
def motion_config(asset):
 cfg=dict((asset.metadata_json or {}).get('motion_safety') or {})
 return {'enabled':bool(cfg.get('enabled')),'profile':cfg.get('profile','VEHICLE'),'permission':cfg.get('permission','UNKNOWN'),'mounted':bool(cfg.get('mounted')),'baseline_roll':cfg.get('baseline_roll'),'baseline_pitch':cfg.get('baseline_pitch'),'baseline_variance':cfg.get('baseline_variance'),'baseline_samples':int(cfg.get('baseline_samples') or 0),'calibrated_at':cfg.get('calibrated_at'),'cancel_seconds':max(10,min(60,int(cfg.get('cancel_seconds') or 30))),'impact_threshold_ms2':max(12,min(40,float(cfg.get('impact_threshold_ms2') or 18))),'tilt_delta_deg':max(35,min(100,float(cfg.get('tilt_delta_deg') or 65))),'tilt_hold_seconds':max(3,min(20,int(cfg.get('tilt_hold_seconds') or 5))),'harsh_brake_ms2':max(2,min(12,float(cfg.get('harsh_brake_ms2') or 4.5))),'severe_brake_ms2':max(4,min(18,float(cfg.get('severe_brake_ms2') or 7.5))),'harsh_accel_ms2':max(2,min(12,float(cfg.get('harsh_accel_ms2') or 4.0)))}
def save_config(asset,cfg):
 meta=dict(asset.metadata_json or {});meta['motion_safety']=cfg;asset.metadata_json=meta
def mobile_api_guard():
 if not request.path.startswith('/api/v1/mobile/'):return None
 if (request.content_length or 0)>262144:return jsonify(error='request_too_large',maximum_bytes=262144),413
 key=(bearer()[-12:] if bearer() else request.remote_addr or 'anonymous')+':'+request.path
 limit=120 if request.path.endswith('/location/batch') else 60;window=60;stamp=time.monotonic()
 with _LOCK:
  q=_BUCKETS[key]
  while q and stamp-q[0]>window:q.popleft()
  if len(q)>=limit:return jsonify(error='rate_limit_exceeded',retry_after_seconds=60),429
  q.append(stamp)
 return None
def confirmation(event,data,device):
 asset=db.session.get(Asset,device.asset_id);cfg=motion_config(asset);detail=dict(event.detail_json or {})
 detail.update({'setup_enabled':cfg['enabled'],'vehicle_profile':cfg['profile'],'mounting_calibrated':cfg['mounted'],'baseline_roll':cfg['baseline_roll'],'baseline_pitch':cfg['baseline_pitch'],'cancel_deadline':(now()+timedelta(seconds=cfg['cancel_seconds'])).isoformat() if event.event_type=='POSSIBLE_ACCIDENT' else None})
 result='CANDIDATE_RECORDED'
 if event.event_type=='POSSIBLE_ACCIDENT':
  speed_drop=max(0,float(event.speed_before_kmh or 0)-float(event.speed_after_kmh or 0));stationary=bool(data.get('stationary_after_impact')) or float(event.speed_after_kmh or 999)<=3;gps_ok=event.accuracy_m is not None and event.accuracy_m<=50;orientation=bool(data.get('orientation_evidence')) or abs(float(detail.get('roll_deg') or 0)-(float(cfg['baseline_roll'] or 0)))>=cfg['tilt_delta_deg']
  gates={'setup':cfg['enabled'] and cfg['mounted'] and cfg['profile']=='VEHICLE','impact':float(event.peak_acceleration_ms2 or 0)>=cfg['impact_threshold_ms2'],'speed_drop':speed_drop>=20,'stationary_after_impact':stationary,'orientation_evidence':orientation,'gps_fresh':gps_ok}
  detail['confirmation_gates']=gates;event.status='CONFIRMATION_PENDING';event.confidence=min(.99,max(event.confidence or 0,sum(gates.values())/len(gates)))
  if all(gates.values()):event.status='CONFIRMED';event.event_type='CRASH_DETECTED';event.severity='CRITICAL';result='CRASH_CONFIRMED'
 elif event.event_type=='ABNORMAL_TILT':
  roll_delta=abs(float(detail.get('roll_deg') or 0)-float(cfg['baseline_roll'] or 0));pitch_delta=abs(float(detail.get('pitch_deg') or 0)-float(cfg['baseline_pitch'] or 0));held=float(data.get('orientation_duration_seconds') or 0)>=cfg['tilt_hold_seconds'];recovered=bool(data.get('orientation_recovered'))
  gates={'setup':cfg['enabled'] and cfg['mounted'] and cfg['profile']=='VEHICLE','sustained':held,'baseline_deviation':max(roll_delta,pitch_delta)>=cfg['tilt_delta_deg'],'vehicle_context':float(event.speed_before_kmh or 0)>=5,'no_recovery':not recovered}
  detail['confirmation_gates']=gates;event.status='CONFIRMATION_PENDING'
  if all(gates.values()):event.status='CONFIRMED';event.event_type='ROLLOVER_DETECTED';event.severity='CRITICAL';result='ROLLOVER_CONFIRMED'
 elif event.event_type in ('HARSH_BRAKING','SEVERE_BRAKING','HARSH_ACCELERATION'):
  gps_delta=abs(float(event.speed_before_kmh or 0)-float(event.speed_after_kmh or 0));gps_ok=event.accuracy_m is not None and event.accuracy_m<=50 and gps_delta>=8;accel=abs(float(event.deceleration_ms2 or event.peak_acceleration_ms2 or 0));threshold=cfg['severe_brake_ms2'] if event.event_type=='SEVERE_BRAKING' else cfg['harsh_brake_ms2'] if event.event_type=='HARSH_BRAKING' else cfg['harsh_accel_ms2'];event.status='RECORDED' if cfg['enabled'] and cfg['profile']=='VEHICLE' and gps_ok and accel>=threshold else 'UNVALIDATED';detail['cross_validation']={'vehicle_profile':cfg['profile'],'gps_speed_delta_kmh':gps_delta,'gps_accuracy_ok':gps_ok,'acceleration_threshold_ms2':threshold}
 event.detail_json=detail
 if event.status=='CONFIRMED':queue_critical_notification(event,device)
 return result
def queue_critical_notification(event,device):
 profile=WorkspaceProfile.query.filter_by(customer_id=device.customer_id).first();recipient=(profile.contact_email if profile else None) or (profile.billing_email if profile else None)
 if not recipient:return
 subject=f'CRITICAL: {event.event_type.replace("_"," ").title()}'
 row=EmailNotificationLog(customer_id=device.customer_id,asset_id=device.asset_id,recipient=recipient,subject=subject,severity='CRITICAL',state='QUEUED',failure_reason='Awaiting provider delivery; retry schedule 5/15/30 minutes')
 db.session.add(row);db.session.add(SecurityAuditEvent(customer_id=device.customer_id,asset_id=device.asset_id,device_id=device.id,event_type='CRITICAL_NOTIFICATION_QUEUED',actor_type='SYSTEM',safe_summary=f'{event.event_type} event {event.sequence}; acknowledgement required'))
@motion_bp.route('/asset/<int:asset_id>/motion-safety-setup',methods=['GET','POST'])
@login_required
def setup(asset_id):
 asset=Asset.query.filter_by(id=asset_id,customer_id=current_user.customer_id).first_or_404();cfg=motion_config(asset)
 if request.method=='POST':
  cfg.update({'enabled':request.form.get('enabled')=='on','profile':request.form.get('profile','VEHICLE') if request.form.get('profile') in ('VEHICLE','WALKING') else 'VEHICLE','permission':request.form.get('permission','UNKNOWN')[:20],'cancel_seconds':max(10,min(60,int(request.form.get('cancel_seconds') or 30)))})
  save_config(asset,cfg);db.session.commit()
 return render_template('motion_safety_setup.html',asset=asset,cfg=cfg)
@motion_bp.post('/api/v1/mobile/motion/calibrate')
def calibrate():
 device=device_auth()
 if not device:return jsonify(error='invalid_mobile_tracker_token'),401
 data=request.get_json(silent=True) or {}
 if str(data.get('device_id','')).upper()!=device.device_uid.upper():return jsonify(error='device_identity_mismatch'),403
 samples=data.get('samples') or []
 if not isinstance(samples,list) or not 20<=len(samples)<=500:return jsonify(error='calibration_samples_required',minimum=20,maximum=500),400
 try:
  rolls=[float(x['roll_deg']) for x in samples];pitches=[float(x['pitch_deg']) for x in samples]
 except (KeyError,TypeError,ValueError):return jsonify(error='invalid_calibration_samples'),400
 avg_r=sum(rolls)/len(rolls);avg_p=sum(pitches)/len(pitches);variance=sum((x-avg_r)**2 for x in rolls)/len(rolls)+sum((x-avg_p)**2 for x in pitches)/len(pitches)
 if variance>25:return jsonify(error='mounting_not_stable',variance=round(variance,3)),409
 asset=db.session.get(Asset,device.asset_id);cfg=motion_config(asset);cfg.update({'mounted':True,'baseline_roll':round(avg_r,3),'baseline_pitch':round(avg_p,3),'baseline_variance':round(variance,3),'baseline_samples':len(samples),'calibrated_at':now().isoformat(),'permission':str(data.get('permission') or 'GRANTED')[:20]});save_config(asset,cfg);db.session.commit();return jsonify(status='calibrated',baseline_roll=cfg['baseline_roll'],baseline_pitch=cfg['baseline_pitch'],variance=cfg['baseline_variance']),202
@motion_bp.get('/api/v1/mobile/motion/setup')
def setup_status():
 device=device_auth()
 if not device:return jsonify(error='invalid_mobile_tracker_token'),401
 return jsonify(status='ok',config=motion_config(db.session.get(Asset,device.asset_id))),200
@motion_bp.post('/api/v1/mobile/token/rotate')
def rotate_token():
 device=device_auth()
 if not device:return jsonify(error='invalid_mobile_tracker_token'),401
 old_last4=device.api_token[-4:];device.api_token=secrets.token_urlsafe(48);db.session.add(SecurityAuditEvent(customer_id=device.customer_id,asset_id=device.asset_id,device_id=device.id,event_type='DEVICE_TOKEN_ROTATED',actor_type='DEVICE',safe_summary=f'Previous token ending {old_last4} revoked immediately'));db.session.commit();return jsonify(status='rotated',device_token=device.api_token),200
@motion_bp.post('/api/v1/mobile/events/<int:event_id>/cancel')
def cancel_event(event_id):
 device=device_auth()
 if not device:return jsonify(error='invalid_mobile_tracker_token'),401
 event=Live360SafetyEvent.query.filter_by(id=event_id,customer_id=device.customer_id,device_id=device.id).first_or_404()
 if event.status!='CONFIRMATION_PENDING':return jsonify(error='event_not_cancellable'),409
 deadline=(event.detail_json or {}).get('cancel_deadline')
 if deadline and now()>datetime.fromisoformat(deadline):return jsonify(error='cancel_window_expired'),409
 event.status='CANCELLED_BY_USER';detail=dict(event.detail_json or {});detail['cancelled_at']=now().isoformat();event.detail_json=detail;db.session.commit();return jsonify(status='cancelled'),200
