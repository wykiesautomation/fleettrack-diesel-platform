import json, os, ssl, threading, time
from datetime import datetime, timezone
from urllib.parse import urlparse
import paho.mqtt.client as mqtt
from . import db
from .models import Asset,IntegrationConnector,IntegrationEvent,MqttMessageEvent,MqttSubscription,MqttTopicMapping,Reading

def utcnow(): return datetime.now(timezone.utc)
def path_get(data,path):
    value=data
    for part in (path or '').split('.'):
        if not part: continue
        value=value[int(part)] if isinstance(value,list) else value[part]
    return value
def endpoint(value):
    parsed=urlparse(value if '://' in value else 'mqtt://'+value);tls=parsed.scheme in ('mqtts','ssl','tls')
    return parsed.hostname,parsed.port or (8883 if tls else 1883),tls
class Runtime:
    def __init__(self,app,connector_id): self.app=app;self.connector_id=connector_id;self.client=None
    def run(self):
        with self.app.app_context():
            c=db.session.get(IntegrationConnector,self.connector_id)
            if not c or not c.enabled:return
            host,port,tls=endpoint(c.endpoint or '');cfg=c.config_json or {};client_id=cfg.get('client_id') or f'at360-{c.customer_id}-{c.id}'
            self.client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id=client_id,clean_session=False)
            user=os.getenv(cfg.get('username_env',''), '') if cfg.get('username_env') else ''
            password=os.getenv(cfg.get('password_env',''), '') if cfg.get('password_env') else ''
            if user:self.client.username_pw_set(user,password or None)
            if tls:self.client.tls_set(ca_certs=os.getenv(cfg.get('ca_file_env',''), '') or None,cert_reqs=ssl.CERT_REQUIRED)
            self.client.reconnect_delay_set(min_delay=2,max_delay=120);self.client.on_connect=self.on_connect;self.client.on_disconnect=self.on_disconnect;self.client.on_message=self.on_message
            c.status='CONNECTING';db.session.commit()
        self.client.connect_async(host,port,60);self.client.loop_forever(retry_first_connection=True)
    def on_connect(self,client,userdata,flags,reason_code,properties):
        with self.app.app_context():
            c=db.session.get(IntegrationConnector,self.connector_id)
            if int(reason_code)==0:
                subs=MqttSubscription.query.filter_by(connector_id=c.id,enabled=True).all()
                for sub in subs:client.subscribe(sub.topic_filter,qos=sub.qos)
                c.status='CONNECTED';c.last_success_at=utcnow();c.last_error=None;db.session.add(IntegrationEvent(customer_id=c.customer_id,connector_id=c.id,event_type='MQTT_CONNECTED',status='OK',detail=f'{len(subs)} subscriptions active'))
            else:c.status='ERROR';c.last_error=f'MQTT refused: {reason_code}'
            db.session.commit()
    def on_disconnect(self,client,userdata,disconnect_flags,reason_code,properties):
        with self.app.app_context():
            c=db.session.get(IntegrationConnector,self.connector_id)
            if c:c.status='DEGRADED';c.last_error=f'MQTT disconnected: {reason_code}';db.session.commit()
    def on_message(self,client,userdata,msg):
        with self.app.app_context():
            c=db.session.get(IntegrationConnector,self.connector_id);mapped=0
            try:
                payload=json.loads(msg.payload.decode('utf-8'));subs=[x for x in MqttSubscription.query.filter_by(connector_id=c.id,enabled=True).all() if mqtt.topic_matches_sub(x.topic_filter,msg.topic)]
                for sub in subs:
                    for m in MqttTopicMapping.query.filter_by(subscription_id=sub.id,enabled=True).all():
                        try:
                            raw=float(path_get(payload,m.json_path));value=raw*m.scale+m.offset;quality=str(path_get(payload,m.quality_path)) if m.quality_path else 'GOOD';sampled=utcnow()
                            if m.timestamp_path:sampled=datetime.fromisoformat(str(path_get(payload,m.timestamp_path)).replace('Z','+00:00'))
                            seq=f'mqtt:{c.id}:{msg.mid}:{m.id}:{time.time_ns()}'
                            db.session.add(Reading(customer_id=c.customer_id,asset_id=m.asset_id,signal_id=m.signal_id,sampled_at=sampled,value=value,raw_value=raw,unit=m.signal.unit,quality=quality,sequence=seq))
                            m.last_value=value;m.last_quality=quality;m.last_message_at=utcnow();m.last_error=None;db.session.get(Asset,m.asset_id).last_seen=utcnow();mapped+=1
                        except Exception as exc:m.last_error=f'{type(exc).__name__}: mapping failed'
                c.status='CONNECTED';c.last_success_at=utcnow();c.last_error=None;db.session.add(MqttMessageEvent(customer_id=c.customer_id,connector_id=c.id,topic=msg.topic,payload_size=len(msg.payload),mapped_points=mapped,status='OK',detail=f'{mapped} points mapped'));db.session.commit()
            except Exception as exc:
                db.session.rollback();db.session.add(MqttMessageEvent(customer_id=c.customer_id,connector_id=c.id,topic=msg.topic,payload_size=len(msg.payload),mapped_points=0,status='ERROR',detail=f'{type(exc).__name__}: invalid JSON or mapping'));db.session.commit()
def run_worker(app):
    runtimes={}
    while True:
        with app.app_context():active={c.id for c in IntegrationConnector.query.filter_by(connector_type='MQTT',enabled=True).all()}
        for cid in active-set(runtimes):
            runtime=Runtime(app,cid);thread=threading.Thread(target=runtime.run,daemon=True,name=f'mqtt-{cid}');runtimes[cid]=(runtime,thread);thread.start()
        for cid in set(runtimes)-active:
            runtime,_=runtimes.pop(cid)
            if runtime.client:runtime.client.disconnect()
        time.sleep(15)
