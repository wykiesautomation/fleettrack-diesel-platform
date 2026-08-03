import hashlib,hmac,json,os,time
from datetime import datetime,timezone
from urllib.parse import urljoin
import requests
from . import db
from .models import Asset,IntegrationConnector,IntegrationJobEvent,Reading,UniversalSourceMapping

def utcnow():return datetime.now(timezone.utc)
def path_get(data,path):
 value=data
 for p in (path or '').split('.'):
  if not p:continue
  value=value[int(p)] if isinstance(value,list) else value[p]
 return value
def map_payload(connector,payload,prefix):
 mapped=0
 for m in UniversalSourceMapping.query.filter_by(connector_id=connector.id,enabled=True).all():
  try:
   raw=float(path_get(payload,m.source_path));value=raw*m.scale+m.offset;quality=str(path_get(payload,m.quality_path)) if m.quality_path else 'GOOD';sampled=utcnow()
   if m.timestamp_path:sampled=datetime.fromisoformat(str(path_get(payload,m.timestamp_path)).replace('Z','+00:00'))
   seq=f'{prefix}:{connector.id}:{m.id}:{time.time_ns()}'
   db.session.add(Reading(customer_id=connector.customer_id,asset_id=m.asset_id,signal_id=m.signal_id,sampled_at=sampled,value=value,raw_value=raw,unit=m.signal.unit,quality=quality,sequence=seq));db.session.get(Asset,m.asset_id).last_seen=utcnow();m.last_value=value;m.last_quality=quality;m.last_success_at=utcnow();m.last_error=None;mapped+=1
  except Exception as exc:m.last_error=f'{type(exc).__name__}: mapping failed'
 return mapped
def auth_headers(cfg):
 headers=dict(cfg.headers_json or {});secret=os.getenv(cfg.secret_env_ref or '','');secondary=os.getenv(cfg.secondary_secret_env_ref or '','')
 if cfg.auth_mode=='BEARER' and secret:headers['Authorization']='Bearer '+secret
 elif cfg.auth_mode=='API_KEY' and secret:headers[secondary or 'X-API-Key']=secret
 elif cfg.auth_mode=='BASIC' and secret:
  import base64;headers['Authorization']='Basic '+base64.b64encode(secret.encode()).decode()
 return headers
def poll_rest(connector,cfg):
 started=time.monotonic();last=None
 for attempt in range(1,cfg.retry_limit+2):
  try:
   response=requests.get(connector.endpoint,headers=auth_headers(cfg),params=cfg.query_json or {},timeout=cfg.timeout_seconds);response.raise_for_status();payload=response.json();mapped=map_payload(connector,payload,'rest');connector.status='CONNECTED';connector.last_success_at=utcnow();connector.last_error=None
   db.session.add(IntegrationJobEvent(customer_id=connector.customer_id,connector_id=connector.id,worker_type='REST',status='OK',attempt=attempt,mapped_points=mapped,duration_ms=int((time.monotonic()-started)*1000),detail=f'HTTP {response.status_code}'));db.session.commit();return
  except Exception as exc:
   db.session.rollback();last=f'{type(exc).__name__}: REST poll failed';time.sleep(min(cfg.backoff_seconds*attempt,60))
 connector.status='ERROR';connector.last_error=last;db.session.add(IntegrationJobEvent(customer_id=connector.customer_id,connector_id=connector.id,worker_type='REST',status='ERROR',attempt=cfg.retry_limit+1,detail=last));db.session.commit()
