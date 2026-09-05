import hashlib,json
from datetime import datetime,timezone
from .models import IntegrationConnector,UniversalSourceMapping,EdgeGateway
def utcnow():return datetime.now(timezone.utc)
def aware(v):return v if not v or v.tzinfo else v.replace(tzinfo=timezone.utc)
def age(v):return None if not v else max(0,int((utcnow()-aware(v)).total_seconds()))
def grade(s):return 'PRODUCTION READY' if s>=90 else 'READY WITH WARNINGS' if s>=75 else 'COMMISSIONING REQUIRED' if s>=50 else 'NOT READY'
def connector_diagnostic(c):
 maps=UniversalSourceMapping.query.filter_by(customer_id=c.customer_id,connector_id=c.id,enabled=True).all();fresh=[m for m in maps if m.last_success_at and age(m.last_success_at)<=max(120,int(c.poll_interval_seconds or 60)*3)];bad=[m for m in maps if str(m.last_quality or '').upper() in ('BAD','STALE','UNKNOWN') or m.last_error]
 checks=[('READ_ONLY','PASS' if c.read_only else 'FAIL','Monitoring-only enforcement'),('EDGE','PASS' if c.edge_gateway_id or c.transport_mode!='EDGE_OUTBOUND' else 'FAIL','Edge assignment'),('ENDPOINT','PASS' if c.endpoint else 'WARN','Source configured'),('ENABLED','PASS' if c.enabled else 'WARN','Runtime enabled'),('MAPPINGS','PASS' if maps else 'WARN',f'{len(maps)} mappings'),('FRESHNESS','PASS' if fresh else 'WARN',f'{len(fresh)}/{len(maps)} fresh'),('QUALITY','PASS' if not bad else 'WARN',f'{len(bad)} quality/error exceptions'),('LAST_ERROR','PASS' if not c.last_error else 'FAIL',c.last_error or 'No current error')]
 rows=[{'code':a,'status':b,'detail':d} for a,b,d in checks];score=max(0,100-sum(20 for x in rows if x['status']=='FAIL')-sum(5 for x in rows if x['status']=='WARN'))
 return {'connector_id':c.id,'name':c.name,'type':c.connector_type,'status':c.status,'score':score,'grade':grade(score),'last_success_age_seconds':age(c.last_success_at),'mapping_count':len(maps),'fresh_mapping_count':len(fresh),'checks':rows,'read_only':bool(c.read_only)}
def tenant_report(cid):
 rows=[connector_diagnostic(c) for c in IntegrationConnector.query.filter_by(customer_id=cid).order_by(IntegrationConnector.name).all()];gws=[]
 for g in EdgeGateway.query.filter_by(customer_id=cid,active=True).all():
  a=age(g.last_heartbeat_at);gws.append({'uid':g.gateway_uid,'name':g.name,'state':'ONLINE' if a is not None and a<=180 else 'STALE' if a is not None and a<=900 else 'OFFLINE','heartbeat_age_seconds':a,'version':g.version,'capabilities':g.capabilities or []})
 score=round(sum(x['score'] for x in rows)/len(rows)) if rows else 0;now=utcnow();p={'report_version':'PART11-1.0','generated_at':now.isoformat(),'customer_id':cid,'overall_score':score,'overall_grade':grade(score),'connectors':rows,'gateways':gws,'safety':{'all_read_only':all(x['read_only'] for x in rows),'write_paths_enabled':any(not x['read_only'] for x in rows),'contract':'MONITORING_ONLY'},'counts':{'connectors':len(rows),'gateways':len(gws),'pass':sum(x['status']=='PASS' for r in rows for x in r['checks']),'warn':sum(x['status']=='WARN' for r in rows for x in r['checks']),'fail':sum(x['status']=='FAIL' for r in rows for x in r['checks'])}}
 p['report_id']='AT360-PROD-'+now.strftime('%Y%m%dT%H%M%SZ')+'-'+hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()[:12].upper();return p
