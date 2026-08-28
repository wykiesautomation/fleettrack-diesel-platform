from datetime import datetime,timezone,timedelta
from sqlalchemy import text
from . import db
from .models import Device,DeviceTrendPolicy,Reading,Location,SignalDefinition,SignalTrendPolicy,TrendCleanupState

JOB_NAME="trend-retention-daily-v1"
def utcnow():return datetime.now(timezone.utc)
def _aware(v):return v if not v or v.tzinfo else v.replace(tzinfo=timezone.utc)
def _keep_latest_reading(signal_id,cutoff):
    latest=db.session.query(Reading.id).filter_by(signal_id=signal_id).order_by(Reading.sampled_at.desc(),Reading.id.desc()).first()
    q=Reading.query.filter(Reading.signal_id==signal_id,Reading.sampled_at<cutoff)
    if latest:q=q.filter(Reading.id!=latest[0])
    return q.delete(synchronize_session=False)
def _keep_latest_location(asset_id,cutoff):
    latest=db.session.query(Location.id).filter_by(asset_id=asset_id).order_by(Location.sampled_at.desc(),Location.id.desc()).first()
    q=Location.query.filter(Location.asset_id==asset_id,Location.sampled_at<cutoff)
    if latest:q=q.filter(Location.id!=latest[0])
    return q.delete(synchronize_session=False)
def cleanup_due(force=False):
    now=utcnow();state=TrendCleanupState.query.filter_by(job_name=JOB_NAME).first()
    if not state:state=TrendCleanupState(job_name=JOB_NAME);db.session.add(state);db.session.flush()
    if not force and state.last_completed_at and now-_aware(state.last_completed_at)<timedelta(hours=23):return {'ran':False,'readings':0,'locations':0}
    # PostgreSQL protects multiple Gunicorn processes. SQLite uses the single-process development path.
    locked=True
    if db.engine.dialect.name=='postgresql':locked=bool(db.session.execute(text('SELECT pg_try_advisory_lock(:key)'),{'key':3602093}).scalar())
    if not locked:return {'ran':False,'readings':0,'locations':0}
    state.last_started_at=now;state.last_error=None;db.session.commit();deleted_readings=deleted_locations=0
    try:
        for device in Device.query.all():
            policy=DeviceTrendPolicy.query.filter_by(device_id=device.id).first()
            trend_on=bool(policy and policy.trend_enabled);reading_days=policy.retention_days if policy else 93
            gps_on=bool(policy and policy.gps_history_enabled);gps_days=policy.gps_retention_days if policy else 31
            for sig in SignalDefinition.query.filter_by(asset_id=device.asset_id).all():
                selected=SignalTrendPolicy.query.filter_by(device_id=device.id,signal_id=sig.id,enabled=True).first()
                days=reading_days if trend_on and selected else 0
                cutoff=now-timedelta(days=days) if days else now
                deleted_readings+=_keep_latest_reading(sig.id,cutoff)
            gps_cutoff=now-timedelta(days=gps_days) if gps_on else now
            deleted_locations+=_keep_latest_location(device.asset_id,gps_cutoff)
        state=TrendCleanupState.query.filter_by(job_name=JOB_NAME).first();state.last_completed_at=utcnow();state.last_deleted_readings=deleted_readings;state.last_deleted_locations=deleted_locations;db.session.commit()
        return {'ran':True,'readings':deleted_readings,'locations':deleted_locations}
    except Exception as exc:
        db.session.rollback();state=TrendCleanupState.query.filter_by(job_name=JOB_NAME).first() or TrendCleanupState(job_name=JOB_NAME);state.last_error=f'{type(exc).__name__}: cleanup failed';db.session.add(state);db.session.commit();raise
    finally:
        if db.engine.dialect.name=='postgresql':db.session.execute(text('SELECT pg_advisory_unlock(:key)'),{'key':3602093});db.session.commit()
