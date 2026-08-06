from datetime import datetime, timezone
from flask import request
from . import db
from .models import MobileConsent,SecurityAuditEvent,AssetAlertSettings,CoreAlarmState,DataDeletionRequest,Alarm
POLICY_VERSION='2026.1'
def now():return datetime.now(timezone.utc)
def audit(customer_id,event_type,asset_id=None,device_id=None,actor_type='SYSTEM',actor_id=None,summary=None):
    db.session.add(SecurityAuditEvent(customer_id=customer_id,asset_id=asset_id,device_id=device_id,event_type=event_type,actor_type=actor_type,actor_id=actor_id,safe_summary=(summary or '')[:500],source_ip=request.remote_addr if request else None))
def consent_for_device(device):
    return MobileConsent.query.filter_by(customer_id=device.customer_id,device_uid=device.device_uid).order_by(MobileConsent.id.desc()).first()
def settings_for(asset):
    item=AssetAlertSettings.query.filter_by(customer_id=asset.customer_id,asset_id=asset.id).first()
    if not item:item=AssetAlertSettings(customer_id=asset.customer_id,asset_id=asset.id);db.session.add(item);db.session.flush()
    return item
def set_condition(asset,key,active,severity,message,value=None):
    state=CoreAlarmState.query.filter_by(asset_id=asset.id,condition_key=key).first()
    if active:
        if not state:
            alarm=Alarm(customer_id=asset.customer_id,asset_id=asset.id,severity=severity,state='OPEN',message=message,value=value);db.session.add(alarm);db.session.flush()
            state=CoreAlarmState(customer_id=asset.customer_id,asset_id=asset.id,condition_key=key,alarm_id=alarm.id,active=True,severity=severity,last_value=value);db.session.add(state)
        else:
            state.active=True;state.severity=severity;state.last_value=value;state.last_seen_at=now();state.recovered_at=None
            alarm=db.session.get(Alarm,state.alarm_id) if state.alarm_id else None
            if alarm:alarm.severity=severity;alarm.message=message;alarm.value=value;alarm.state='OPEN'
    elif state and state.active:
        state.active=False;state.recovered_at=now();state.last_seen_at=now();alarm=db.session.get(Alarm,state.alarm_id) if state.alarm_id else None
        if alarm:alarm.state='CLOSED';alarm.note=((alarm.note or '')+' Auto-closed after recovery.').strip()
def evaluate_mobile(device,data):
    asset=device.asset;cfg=settings_for(asset);battery=data.get('battery_percent');accuracy=data.get('accuracy_m');speed=data.get('speed_kmh')
    if cfg.battery_enabled and battery is not None:
        b=float(battery);level='CRITICAL' if b<=cfg.battery_critical else 'WARNING' if b<=cfg.battery_warning else None
        set_condition(asset,'PHONE_BATTERY',bool(level),level or 'WARNING',f'Phone battery {level.lower()}' if level else 'Phone battery recovered',b)
    if cfg.gps_enabled and accuracy is not None:set_condition(asset,'GPS_ACCURACY_POOR',float(accuracy)>cfg.gps_accuracy_limit_m,'WARNING','GPS accuracy poor',float(accuracy))
    if cfg.speed_enabled and speed is not None:
        s=float(speed);level='CRITICAL' if s>=cfg.speed_critical_kmh else 'WARNING' if s>=cfg.speed_warning_kmh else None
        set_condition(asset,'SPEED_LIMIT',bool(level),level or 'WARNING',f'Speed {level.lower()}' if level else 'Speed normal',s)
