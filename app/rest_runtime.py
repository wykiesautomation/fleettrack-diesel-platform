import os,time,requests
from datetime import datetime,timezone
from . import db
from .models import IntegrationJobEvent
from .integration_runtime import map_payload

def utcnow():return datetime.now(timezone.utc)

def _headers(cfg):
    headers=dict(cfg.headers_json or {})
    secret=os.getenv(cfg.secret_env_ref or '', '')
    secondary=os.getenv(cfg.secondary_secret_env_ref or '', '')
    mode=str(cfg.auth_mode or 'NONE').upper()
    if mode=='BEARER' and secret:headers['Authorization']='Bearer '+secret
    elif mode=='API_KEY' and secret:headers[secondary or 'X-API-Key']=secret
    elif mode=='BASIC' and secret:
        import base64
        headers['Authorization']='Basic '+base64.b64encode(secret.encode()).decode()
    return headers

def pull_once(connector,cfg):
    started=time.monotonic();attempt=0;last=None
    for attempt in range(1,max(1,int(cfg.retry_limit or 0)+1)+1):
        try:
            response=requests.request(cfg.request_method or 'GET',connector.endpoint,headers=_headers(cfg),params=cfg.query_json or {},timeout=max(5,int(cfg.timeout_seconds or 20)))
            response.raise_for_status();payload=response.json();mapped=map_payload(connector,payload,'rest')
            connector.last_success_at=utcnow();connector.last_error=None;connector.status='CONNECTED'
            db.session.add(IntegrationJobEvent(customer_id=connector.customer_id,connector_id=connector.id,worker_type='REST_API',status='OK',attempt=attempt,mapped_points=mapped,duration_ms=int((time.monotonic()-started)*1000),detail=f'HTTP {response.status_code}; {mapped} points mapped'))
            db.session.commit();return {'ok':True,'status_code':response.status_code,'mapped':mapped,'preview':payload}
        except Exception as exc:
            last=exc
            if attempt<=int(cfg.retry_limit or 0):time.sleep(min(10,max(1,int(cfg.backoff_seconds or 1))))
    connector.status='ERROR';connector.last_error=f'{type(last).__name__}: {str(last)[:420]}'
    db.session.add(IntegrationJobEvent(customer_id=connector.customer_id,connector_id=connector.id,worker_type='REST_API',status='FAILED',attempt=attempt,duration_ms=int((time.monotonic()-started)*1000),detail=connector.last_error));db.session.commit()
    return {'ok':False,'error':connector.last_error}
