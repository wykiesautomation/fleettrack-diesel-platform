import hashlib,json
from datetime import datetime,timezone
from . import db
from .models import Asset,Reading,SignalDefinition,MqttTopicMapping,MqttMessageEvent
from .integration_runtime import path_get

def utcnow():return datetime.now(timezone.utc)
def topic_matches(pattern,topic):
    p=pattern.split('/');t=topic.split('/')
    for i,x in enumerate(p):
        if x=='#':return True
        if i>=len(t) or (x!='+' and x!=t[i]):return False
    return len(p)==len(t)
def process_message(connector,topic,raw_payload):
    try:payload=json.loads(raw_payload.decode('utf-8') if isinstance(raw_payload,(bytes,bytearray)) else str(raw_payload));status='OK';detail=None
    except Exception as exc:
        db.session.add(MqttMessageEvent(customer_id=connector.customer_id,connector_id=connector.id,topic=topic,payload_size=len(raw_payload),mapped_points=0,status='REJECTED',detail='Invalid JSON'));db.session.commit();return 0
    mapped=0
    for m in MqttTopicMapping.query.filter_by(customer_id=connector.customer_id,connector_id=connector.id,enabled=True).all():
        if not m.subscription or not m.subscription.enabled or not topic_matches(m.subscription.topic_filter,topic):continue
        raw=path_get(payload,m.json_path)
        if raw is None:continue
        try:value=float(raw)*float(m.scale or 1)+float(m.offset or 0)
        except (TypeError,ValueError):m.last_error='Non-numeric mapped value';continue
        stamp=path_get(payload,m.timestamp_path) if m.timestamp_path else None
        try:sampled=datetime.fromisoformat(str(stamp).replace('Z','+00:00')) if stamp else utcnow()
        except ValueError:sampled=utcnow()
        quality=str(path_get(payload,m.quality_path,'GOOD') if m.quality_path else 'GOOD')[:20]
        fp=hashlib.sha256(f'{connector.id}:{m.id}:{topic}:{sampled.isoformat()}:{raw}'.encode()).hexdigest()[:40]
        if Reading.query.filter_by(signal_id=m.signal_id,sequence='mqtt:'+fp).first():continue
        signal=db.session.get(SignalDefinition,m.signal_id);asset=db.session.get(Asset,m.asset_id)
        db.session.add(Reading(customer_id=connector.customer_id,asset_id=m.asset_id,signal_id=m.signal_id,sampled_at=sampled,value=value,raw_value=float(raw),unit=signal.unit if signal else '',quality=quality,sequence='mqtt:'+fp))
        if asset:asset.last_seen=utcnow()
        m.last_value=value;m.last_quality=quality;m.last_message_at=utcnow();m.last_error=None;mapped+=1
    connector.last_success_at=utcnow();connector.status='CONNECTED';connector.last_error=None
    db.session.add(MqttMessageEvent(customer_id=connector.customer_id,connector_id=connector.id,topic=topic,payload_size=len(raw_payload),mapped_points=mapped,status=status,detail=detail));db.session.commit();return mapped
