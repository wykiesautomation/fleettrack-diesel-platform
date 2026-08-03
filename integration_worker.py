import time
from app import create_app,db
from app.integration_runtime import poll_rest
from app.mqtt_service import run_worker as run_mqtt_worker
from app.models import ConnectorEndpointConfig,IntegrationConnector
import threading
app=create_app();threading.Thread(target=run_mqtt_worker,args=(app,),daemon=True).start();last={}
while True:
 with app.app_context():
  now=time.time()
  for c in IntegrationConnector.query.filter_by(connector_type='REST_API',enabled=True).all():
   if now-last.get(c.id,0)>=max(c.poll_interval_seconds,10):
    cfg=ConnectorEndpointConfig.query.filter_by(connector_id=c.id).first()
    if cfg:poll_rest(c,cfg)
    last[c.id]=now
 time.sleep(5)
