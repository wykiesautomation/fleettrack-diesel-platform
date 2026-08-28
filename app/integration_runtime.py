import hashlib,json,time
from datetime import datetime,timezone
from . import db
from .models import Asset,Reading,SignalDefinition,UniversalSourceMapping

def utcnow():return datetime.now(timezone.utc)
def path_get(data,path,default=None):
    if not path:return default
    cur=data
    for part in str(path).replace('[','.').replace(']','').split('.'):
        if part=='':continue
        try:cur=cur[int(part)] if isinstance(cur,list) else cur[part]
        except (KeyError,IndexError,TypeError,ValueError):return default
    return cur
def map_payload(connector,payload,source='connector'):
    mapped=0
    for m in UniversalSourceMapping.query.filter_by(customer_id=connector.customer_id,connector_id=connector.id,enabled=True).all():
        raw=path_get(payload,m.source_path)
        if raw is None:continue
        try:value=float(raw)*float(m.scale or 1)+float(m.offset or 0)
        except (TypeError,ValueError):m.last_error='Non-numeric source value';continue
        stamp=path_get(payload,m.timestamp_path) if m.timestamp_path else None
        try:sampled=datetime.fromisoformat(str(stamp).replace('Z','+00:00')) if stamp else utcnow()
        except ValueError:sampled=utcnow()
        quality=str(path_get(payload,m.quality_path,'GOOD') if m.quality_path else 'GOOD')[:20]
        fingerprint=hashlib.sha256(f'{connector.id}:{m.id}:{sampled.isoformat()}:{raw}'.encode()).hexdigest()[:40]
        if Reading.query.filter_by(signal_id=m.signal_id,sequence=f'{source}:{fingerprint}').first():continue
        signal=db.session.get(SignalDefinition,m.signal_id);asset=db.session.get(Asset,m.asset_id)
        db.session.add(Reading(customer_id=connector.customer_id,asset_id=m.asset_id,signal_id=m.signal_id,sampled_at=sampled,value=value,raw_value=float(raw),unit=signal.unit if signal else '',quality=quality,sequence=f'{source}:{fingerprint}'))
        if asset:asset.last_seen=utcnow()
        m.last_value=value;m.last_quality=quality;m.last_success_at=utcnow();m.last_error=None;mapped+=1
    return mapped
