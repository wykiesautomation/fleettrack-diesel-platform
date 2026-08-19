import os,time,requests
from urllib.parse import urlparse
from app import app,db
from app.models import ConnectorEndpointConfig,IntegrationConnector,IntegrationJobEvent
from app.integration_runtime import map_payload

def auth_headers(cfg):
 h=dict(cfg.headers_json or {});secret=os.getenv(cfg.secret_env_ref or '')
 if cfg.auth_mode=='BEARER' and secret:h['Authorization']='Bearer '+secret
 elif cfg.auth_mode=='API_KEY' and secret:h[os.getenv(cfg.secondary_secret_env_ref or '','X-API-Key')]=secret
 return h
def poll(connector):
 cfg=ConnectorEndpointConfig.query.filter_by(connector_id=connector.id).first()
 if not cfg:raise RuntimeError('endpoint configuration missing')
 parsed=urlparse(connector.endpoint or '')
 if parsed.scheme!='https' and os.getenv('ALLOW_INSECURE_CONNECTORS','false').lower()!='true':raise RuntimeError('HTTPS endpoint required')
 started=time.monotonic();response=requests.get(connector.endpoint,headers=auth_headers(cfg),params=cfg.query_json or {},timeout=cfg.timeout_seconds or 20);response.raise_for_status();payload=response.json();mapped=map_payload(connector,payload,'rest');connector.status='CONNECTED';connector.last_success_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc);connector.last_error=None;db.session.add(IntegrationJobEvent(customer_id=connector.customer_id,connector_id=connector.id,worker_type='REST',status='OK',attempt=1,mapped_points=mapped,duration_ms=int((time.monotonic()-started)*1000),detail=f'{mapped} points mapped'));db.session.commit()
def main():
 while True:
  with app.app_context():
   rows=IntegrationConnector.query.filter_by(connector_type='REST_API',enabled=True).all()
   for c in rows:
    try:poll(c)
    except Exception as exc:c.status='ERROR';c.last_error=f'{type(exc).__name__}: REST poll failed';db.session.add(IntegrationJobEvent(customer_id=c.customer_id,connector_id=c.id,worker_type='REST',status='FAILED',attempt=1,mapped_points=0,detail=c.last_error));db.session.commit()
  time.sleep(10)
if __name__=='__main__':main()
