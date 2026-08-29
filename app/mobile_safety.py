"""AssetTrack 360 advisory mobile motion safety and production API hardening."""
import os,secrets,time,requests
from datetime import datetime,timezone,timedelta
from flask import Blueprint,jsonify,render_template,request
from flask_login import current_user,login_required
from sqlalchemy import UniqueConstraint
from . import db
from .models import Asset,Device,EmailNotificationLog,Live360SafetyEvent,Location,SecurityAuditEvent,WorkspaceProfile
motion_bp=Blueprint('motion_safety',__name__)
def now():return datetime.now(timezone.utc)
def aware(v):return v if not v or v.tzinfo else v.replace(tzinfo=timezone.utc)
def bearer():return request.headers.get('Authorization','').removeprefix('Bearer ').strip()
def device_auth():return Device.query.filter_by(api_token=bearer(),active=True).first() if bearer() else None
class MotionSafetySample(db.Model):
 __tablename__='motion_safety_sample';id=db.Column(db.BigInteger,primary_key=True);customer_id=db.Column(db.Integer,nullable=False,index=True);asset_id=db.Column(db.Integer,nullable=False,index=True);device_id=db.Column(db.Integer,nullable=False,index=True);sampled_at=db.Column(db.DateTime(timezone=True),nullable=False,index=True);dynamic_acceleration_ms2=db.Column(db.Float);roll_deg=db.Column(db.Float);pitch_deg=db.Column(db.Float);speed_kmh=db.Column(db.Float);accuracy_m=db.Column(db.Float);sequence=db.Column(db.String(140),nullable=False,unique=True,index=True)
class MobileRateBucket(db.Model):
 __tablename__='mobile_rate_bucket';id=db.Column(db.BigInteger,primary_key=True);device_id=db.Column(db.Integer,nullable=False,index=True);bucket_key=db.Column(db.String(100),nullable=False);window_start=db.Column(db.DateTime(timezone=True),nullable=False,index=True);request_count=db.Column(db.Integer,default=0,nullable=False);__table_args__=(UniqueConstraint('device_id','bucket_key','window_start',name='uq_mobile_rate_bucket'),)
class SafetyNotificationState(db.Model):
 __tablename__='safety_notification_state';id=db.Column(db.BigInteger,primary_key=True);customer_id=db.Column(db.Integer,nullable=False,index=True);event_id=db.Column(db.BigInteger,nullable=False,unique=True,index=True);recipient=db.Column(db.String(180),nullable=False);state=db.Column(db.String(30),default='QUEUED',nullable=False,index=True);attempts=db.Column(db.Integer,default=0,nullable=False);max_attempts=db.Column(db.Integer,default=4,nullable=False);next_attempt_at=db.Column(db.DateTime(timezone=True),nullable=False,index=True);acknowledged_at=db.Column(db.DateTime(timezone=True));acknowledged_by=db.Column(db.Integer);last_error=db.Column(db.String(500));created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)
def motion_config(asset):
 cfg=dict((asset.metadata_json or {}).get('motion_safety') or {})
 return {'enabled':bool(cfg.get('enabled')),'profile':cfg.get('profile','VEHICLE'),'permission':cfg.get('permission','UNKNOWN'),'mounted':bool(cfg.get('mounted')),'baseline_roll':cfg.get('baseline_roll'),'baseline_pitch':cfg.get('baseline_pitch'),'baseline_variance':cfg.get('baseline_variance'),'baseline_samples':int(cfg.get('baseline_samples') or 0),'calibrated_at':cfg.get('calibrated_at'),'cancel_seconds':max(10,min(60,int(cfg.get('cancel_seconds') or 30))),'impact_threshold_ms2':max(12,min(40,float(cfg.get('impact_threshold_ms2') or 18))),'tilt_delta_deg':max(35,min(100,float(cfg.get('tilt_delta_deg') or 65))),'tilt_hold_seconds':max(3,min(20,int(cfg.get('tilt_hold_seconds') or 5))),'harsh_brake_ms2':max(2,min(12,float(cfg.get('harsh_brake_ms2') or 4.5))),'severe_brake_ms2':max(4,min(18,float(cfg.get('severe_brake_ms2') or 7.5))),'harsh_accel_ms2':max(2,min(12,float(cfg.get('harsh_accel_ms2') or 4.0)))}
def save_config(asset,cfg):meta=dict(asset.metadata_json or {});meta['motion_safety']=cfg;asset.metadata_json=meta
def mobile_api_guard():
 if not request.path.startswith('/api/v1/mobile/'):return None
 if (request.content_length or 0)>262144:return jsonify(error='request_too_large',maximum_bytes=262144),413
 dev=device_auth()
 if not dev:return None
 start=now().replace(second=0,microsecond=0);key=(request.endpoint or request.path)[:100];limit=120 if request.path.endswith('/location/batch') else 90
 try:
  row=MobileRateBucket.query.filter_by(device_id=dev.id,bucket_key=key,window_start=start).with_for_update().first()
  if not row:row=MobileRateBucket(device_id=dev.id,bucket_key=key,window_start=start,request_count=0);db.session.add(row)
  row.request_count+=1
  if row.request_count>limit:db.session.rollback();return jsonify(error='rate_limit_exceeded',retry_after_seconds=60),429
  db.session.commit()
 except Exception:db.session.rollback()
 return None
def evidence(event):
 start=aware(event.sampled_at)-timedelta(seconds=10);end=aware(event.sampled_at)+timedelta(seconds=90)
 locations=Location.query.filter(Location.asset_id==event.asset_id,Location.sampled_at>=start,Location.sampled_at<=end).order_by(Location.sampled_at).all()
 samples=MotionSafetySample.query.filter(MotionSafetySample.device_id==event.device_id,MotionSafetySample.sampled_at>=start,MotionSafetySample.sampled_at<=end).order_by(MotionSafetySample.sampled_at).all()
 return locations,samples
def confirmation(event,data,device):
 asset=db.session.get(Asset,device.asset_id);cfg=motion_config(asset);detail=dict(event.detail_json or {});locations,samples=evidence(event)
 speeds=[float(x.speed_kmh or 0) for x in locations if x.accuracy_m is None or x.accuracy_m<=50];before=float(event.speed_before_kmh or (speeds[0] if speeds else 0));after=min(speeds[-3:] or [float(event.speed_after_kmh or 0)]);speed_drop=max(0,before-after);stationary=bool(speeds and max(speeds[-3:] or speeds)<=3);gps_ok=bool(locations and any((x.accuracy_m or 999)<=50 for x in locations));dynamic=max([float(x.dynamic_acceleration_ms2 or 0) for x in samples]+[float(event.peak_acceleration_ms2 or 0)]);base_r=float(cfg['baseline_roll'] or 0);base_p=float(cfg['baseline_pitch'] or 0);delta=max([max(abs(float(x.roll_deg or 0)-base_r),abs(float(x.pitch_deg or 0)-base_p)) for x in samples]+[max(abs(float(detail.get('roll_deg') or 0)-base_r),abs(float(detail.get('pitch_deg') or 0)-base_p))]);vehicle=cfg['enabled'] and cfg['mounted'] and cfg['profile']=='VEHICLE'
 detail.update({'setup_enabled':cfg['enabled'],'vehicle_profile':cfg['profile'],'mounting_calibrated':cfg['mounted'],'baseline_roll':cfg['baseline_roll'],'baseline_pitch':cfg['baseline_pitch'],'server_evidence':{'location_count':len(locations),'motion_sample_count':len(samples),'speed_drop_kmh':round(speed_drop,2),'orientation_delta_deg':round(delta,2),'peak_dynamic_acceleration_ms2':round(dynamic,2)}})
 result='CANDIDATE_RECORDED'
 if event.event_type=='POSSIBLE_ACCIDENT':
  gates={'setup':vehicle,'impact':dynamic>=cfg['impact_threshold_ms2'],'speed_drop':speed_drop>=20,'stationary_after_impact':stationary,'orientation_evidence':delta>=35,'gps_fresh':gps_ok};detail['confirmation_gates']=gates;detail['cancel_deadline']=(now()+timedelta(seconds=cfg['cancel_seconds'])).isoformat();event.status='CONFIRMATION_PENDING'
  if all(gates.values()):event.status='CONFIRMED';event.event_type='CRASH_DETECTED';event.severity='CRITICAL';result='CRASH_CONFIRMED'
 elif event.event_type=='ABNORMAL_TILT':
  sustained=sum(1 for x in samples if max(abs(float(x.roll_deg or 0)-base_r),abs(float(x.pitch_deg or 0)-base_p))>=cfg['tilt_delta_deg'])>=5;orientation_recovered=bool(samples and max(abs(float(samples[-1].roll_deg or 0)-base_r),abs(float(samples[-1].pitch_deg or 0)-base_p))<20);gates={'setup':vehicle,'sustained':sustained,'baseline_deviation':delta>=cfg['tilt_delta_deg'],'vehicle_context':before>=5,'no_recovery':not orientation_recovered};detail['confirmation_gates']=gates;event.status='CONFIRMATION_PENDING'
  if all(gates.values()):event.status='CONFIRMED';event.event_type='ROLLOVER_DETECTED';event.severity='CRITICAL';result='ROLLOVER_CONFIRMED'
 elif event.event_type in ('HARSH_BRAKING','SEVERE_BRAKING','HARSH_ACCELERATION'):
  gps_delta=abs(before-after);threshold=cfg['severe_brake_ms2'] if event.event_type=='SEVERE_BRAKING' else cfg['harsh_brake_ms2'] if event.event_type=='HARSH_BRAKING' else cfg['harsh_accel_ms2'];event.status='RECORDED' if vehicle and gps_ok and gps_delta>=8 and abs(float(event.deceleration_ms2 or event.peak_acceleration_ms2 or 0))>=threshold else 'UNVALIDATED';detail['cross_validation']={'gps_speed_delta_kmh':gps_delta,'gps_accuracy_ok':gps_ok,'acceleration_threshold_ms2':threshold}
 event.detail_json=detail
 if event.status=='CONFIRMED':queue_critical_notification(event,device)
 return result
def queue_critical_notification(event,device):
 if SafetyNotificationState.query.filter_by(event_id=event.id).first():return
 profile=WorkspaceProfile.query.filter_by(customer_id=device.customer_id).first();recipient=(profile.contact_email if profile else None) or (profile.billing_email if profile else None)
 if not recipient:return
 db.session.add(SafetyNotificationState(customer_id=device.customer_id,event_id=event.id,recipient=recipient,next_attempt_at=now()));db.session.add(EmailNotificationLog(customer_id=device.customer_id,asset_id=device.asset_id,recipient=recipient,subject=f'CRITICAL: {event.event_type.replace("_"," ")}',severity='CRITICAL',state='QUEUED'));db.session.add(SecurityAuditEvent(customer_id=device.customer_id,asset_id=device.asset_id,device_id=device.id,event_type='CRITICAL_NOTIFICATION_QUEUED',actor_type='SYSTEM',safe_summary=f'{event.event_type} event {event.sequence}; acknowledgement required'))
def send_due_notifications(limit=10):
 states=SafetyNotificationState.query.filter(SafetyNotificationState.state.in_(['QUEUED','RETRY']),SafetyNotificationState.next_attempt_at<=now()).limit(limit).all()
 for state in states:
  event=db.session.get(Live360SafetyEvent,state.event_id);state.attempts+=1
  try:
   key=os.getenv('BREVO_API_KEY','').strip();sender=os.getenv('EMAIL_FROM_ADDRESS','').strip()
   if not key or not sender:raise RuntimeError('email_provider_not_configured')
   response=requests.post('https://api.brevo.com/v3/smtp/email',headers={'api-key':key,'content-type':'application/json'},json={'sender':{'name':os.getenv('EMAIL_FROM_NAME','AssetTrack 360'),'email':sender},'to':[{'email':state.recipient}],'subject':f'CRITICAL AssetTrack 360 {event.event_type.replace("_"," ")}', 'textContent':f'Confirmed safety event on asset {event.asset_id}. Event ID {event.id}. Review Fleet Safety Live and acknowledge the event.'},timeout=20);response.raise_for_status();state.state='SENT';state.last_error=None
  except Exception as exc:
   state.last_error=f'{type(exc).__name__}: {str(exc)[:400]}';state.state='FAILED' if state.attempts>=state.max_attempts else 'RETRY';state.next_attempt_at=now()+timedelta(minutes=[5,15,30,60][min(state.attempts-1,3)])
 db.session.commit()
@motion_bp.route('/asset/<int:asset_id>/motion-safety-setup',methods=['GET','POST'])
@login_required
def setup(asset_id):
 asset=Asset.query.filter_by(id=asset_id,customer_id=current_user.customer_id).first_or_404();cfg=motion_config(asset)
 if request.method=='POST':cfg.update({'enabled':request.form.get('enabled')=='on','profile':request.form.get('profile','VEHICLE') if request.form.get('profile') in ('VEHICLE','WALKING') else 'VEHICLE','permission':request.form.get('permission','UNKNOWN')[:20],'cancel_seconds':max(10,min(60,int(request.form.get('cancel_seconds') or 30)))});save_config(asset,cfg);db.session.commit()
 return render_template('motion_safety_setup.html',asset=asset,cfg=cfg)
@motion_bp.get('/api/v1/mobile/motion/setup')
def setup_status():
 device=device_auth();return (jsonify(error='invalid_mobile_tracker_token'),401) if not device else (jsonify(status='ok',config=motion_config(db.session.get(Asset,device.asset_id))),200)
@motion_bp.post('/api/v1/mobile/motion/calibrate')
def calibrate():
 device=device_auth()
 if not device:return jsonify(error='invalid_mobile_tracker_token'),401
 data=request.get_json(silent=True) or {};samples=data.get('samples') or []
 if str(data.get('device_id','')).upper()!=device.device_uid.upper():return jsonify(error='device_identity_mismatch'),403
 if not isinstance(samples,list) or not 20<=len(samples)<=500:return jsonify(error='calibration_samples_required',minimum=20,maximum=500),400
 try:rolls=[float(x['roll_deg']) for x in samples];pitches=[float(x['pitch_deg']) for x in samples]
 except (KeyError,TypeError,ValueError):return jsonify(error='invalid_calibration_samples'),400
 ar=sum(rolls)/len(rolls);ap=sum(pitches)/len(pitches);variance=sum((x-ar)**2 for x in rolls)/len(rolls)+sum((x-ap)**2 for x in pitches)/len(pitches)
 if variance>25:return jsonify(error='mounting_not_stable',variance=round(variance,3)),409
 asset=db.session.get(Asset,device.asset_id);cfg=motion_config(asset);cfg.update({'mounted':True,'baseline_roll':round(ar,3),'baseline_pitch':round(ap,3),'baseline_variance':round(variance,3),'baseline_samples':len(samples),'calibrated_at':now().isoformat(),'permission':str(data.get('permission') or 'GRANTED')[:20]});save_config(asset,cfg);db.session.commit();return jsonify(status='calibrated',config=cfg),202
@motion_bp.post('/api/v1/mobile/motion/samples')
def store_samples():
 device=device_auth()
 if not device:return jsonify(error='invalid_mobile_tracker_token'),401
 rows=(request.get_json(silent=True) or {}).get('samples') or []
 if not isinstance(rows,list) or len(rows)>100:return jsonify(error='invalid_sample_batch',maximum=100),400
 accepted=[]
 for item in rows:
  seq=str(item.get('sequence') or '')[:140]
  if not seq or MotionSafetySample.query.filter_by(sequence=seq).first():continue
  try:db.session.add(MotionSafetySample(customer_id=device.customer_id,asset_id=device.asset_id,device_id=device.id,sampled_at=datetime.fromisoformat(str(item.get('timestamp') or now().isoformat()).replace('Z','+00:00')),dynamic_acceleration_ms2=max(0,min(100,float(item.get('dynamic_acceleration_ms2') or 0))),roll_deg=max(-180,min(180,float(item.get('roll_deg') or 0))),pitch_deg=max(-180,min(180,float(item.get('pitch_deg') or 0))),speed_kmh=max(0,min(300,float(item.get('speed_kmh') or 0))),accuracy_m=max(0,min(5000,float(item.get('accuracy_m') or 0))),sequence=seq));accepted.append(seq)
  except (TypeError,ValueError):continue
 db.session.commit();return jsonify(status='accepted',accepted=accepted),202
@motion_bp.post('/api/v1/mobile/token/rotate')
def rotate_token():
 device=device_auth()
 if not device:return jsonify(error='invalid_mobile_tracker_token'),401
 old=device.api_token[-4:];device.api_token=secrets.token_urlsafe(48);db.session.add(SecurityAuditEvent(customer_id=device.customer_id,asset_id=device.asset_id,device_id=device.id,event_type='DEVICE_TOKEN_ROTATED',actor_type='DEVICE',safe_summary=f'Previous token ending {old} revoked immediately'));db.session.commit();return jsonify(status='rotated',device_token=device.api_token),200
@motion_bp.post('/api/v1/mobile/events/<int:event_id>/cancel')
def cancel_event(event_id):
 device=device_auth()
 if not device:return jsonify(error='invalid_mobile_tracker_token'),401
 event=Live360SafetyEvent.query.filter_by(id=event_id,customer_id=device.customer_id,device_id=device.id).first_or_404();deadline=(event.detail_json or {}).get('cancel_deadline')
 if event.status!='CONFIRMATION_PENDING' or (deadline and now()>datetime.fromisoformat(deadline)):return jsonify(error='event_not_cancellable'),409
 event.status='CANCELLED_BY_USER';db.session.commit();return jsonify(status='cancelled'),200
@motion_bp.post('/safety-events/<int:event_id>/acknowledge')
@login_required
def acknowledge(event_id):
 event=Live360SafetyEvent.query.filter_by(id=event_id,customer_id=current_user.customer_id).first_or_404();state=SafetyNotificationState.query.filter_by(event_id=event.id).first()
 if state:state.state='ACKNOWLEDGED';state.acknowledged_at=now();state.acknowledged_by=current_user.id
 event.status='ACKNOWLEDGED';db.session.add(SecurityAuditEvent(customer_id=event.customer_id,asset_id=event.asset_id,device_id=event.device_id,event_type='SAFETY_EVENT_ACKNOWLEDGED',actor_type='USER',actor_id=current_user.id,safe_summary=f'Event {event.id} acknowledged; escalation stopped'));db.session.commit();return jsonify(status='acknowledged'),200
