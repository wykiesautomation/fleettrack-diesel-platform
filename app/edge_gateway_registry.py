import hashlib,hmac,json,secrets,time
from datetime import datetime,timezone,timedelta
from flask import Blueprint,abort,flash,jsonify,redirect,render_template,request,session,url_for
from flask_login import current_user,login_required
from . import db
from .edge_models import EdgeGatewayAudit,EdgeGatewayReceipt,EdgeGatewayRegistration
from .models import Asset,Customer,Reading,SignalDefinition,Site

edge_bp=Blueprint('edge',__name__)
def now():return datetime.now(timezone.utc)
def tenant_id():return current_user.customer_id
def token_hash(token):return hashlib.sha256(token.encode()).hexdigest()
def new_token():return 'atg_'+secrets.token_urlsafe(42)
def tenant_gateway(gateway_id):return EdgeGatewayRegistration.query.filter_by(id=gateway_id,customer_id=tenant_id()).first_or_404()
def authenticate():
    token=request.headers.get('Authorization','').removeprefix('Bearer ').strip()
    if not token:return None
    candidate=token_hash(token)
    gateway=EdgeGatewayRegistration.query.filter_by(token_hash=candidate,active=True).first()
    return gateway if gateway and hmac.compare_digest(gateway.token_hash,candidate) else None

def audit(g,event,status='OK',detail=''):
    db.session.add(EdgeGatewayAudit(customer_id=g.customer_id,gateway_id=g.id,event_type=event,status=status,detail=detail[:500],source_ip=request.remote_addr))

@edge_bp.get('/edge-gateways')
@login_required
def registry():
    gateways=EdgeGatewayRegistration.query.filter_by(customer_id=tenant_id()).order_by(EdgeGatewayRegistration.name).all()
    current=now()
    for g in gateways:
        if not g.active:g.display_status='DISABLED'
        elif not g.last_heartbeat_at:g.display_status='PROVISIONED'
        else:
            seen=g.last_heartbeat_at if g.last_heartbeat_at.tzinfo else g.last_heartbeat_at.replace(tzinfo=timezone.utc)
            g.display_status='ONLINE' if current-seen<=timedelta(minutes=3) else 'OFFLINE'
    token=session.pop('edge_one_time_token',None);token_uid=session.pop('edge_one_time_uid',None)
    return render_template('edge_gateways.html',gateways=gateways,one_time_token=token,token_uid=token_uid)

@edge_bp.route('/edge-gateways/new',methods=['GET','POST'])
@login_required
def register():
    sites=Site.query.filter_by(customer_id=tenant_id()).order_by(Site.name).all()
    if request.method=='POST':
        uid=request.form.get('gateway_uid','').strip().upper();name=request.form.get('name','').strip();site_id=request.form.get('site_id',type=int)
        if len(uid)<5 or len(name)<2:flash('Gateway ID and name are required.','error');return redirect(url_for('edge.register'))
        if EdgeGatewayRegistration.query.filter_by(gateway_uid=uid).first():flash('Gateway ID already exists.','error');return redirect(url_for('edge.register'))
        if site_id and not Site.query.filter_by(id=site_id,customer_id=tenant_id()).first():abort(404)
        token=new_token();g=EdgeGatewayRegistration(customer_id=tenant_id(),site_id=site_id,gateway_uid=uid,name=name,token_hash=token_hash(token),token_last4=token[-4:],active=True,status='PROVISIONED')
        db.session.add(g);db.session.flush();audit(g,'REGISTERED',detail='Gateway registered and one-time token issued');db.session.commit();session['edge_one_time_token']=token;session['edge_one_time_uid']=uid;return redirect(url_for('edge.registry'))
    return render_template('edge_gateway_new.html',sites=sites)

@edge_bp.get('/edge-gateways/<int:gateway_id>')
@login_required
def detail(gateway_id):
    g=tenant_gateway(gateway_id);events=EdgeGatewayAudit.query.filter_by(customer_id=tenant_id(),gateway_id=g.id).order_by(EdgeGatewayAudit.created_at.desc()).limit(40).all();receipts=EdgeGatewayReceipt.query.filter_by(customer_id=tenant_id(),gateway_id=g.id).order_by(EdgeGatewayReceipt.received_at.desc()).limit(30).all()
    return render_template('edge_gateway_detail.html',gateway=g,events=events,receipts=receipts)

@edge_bp.post('/edge-gateways/<int:gateway_id>/rotate')
@login_required
def rotate(gateway_id):
    g=tenant_gateway(gateway_id);token=new_token();g.token_hash=token_hash(token);g.token_last4=token[-4:];g.status='PROVISIONED';audit(g,'TOKEN_ROTATED',detail='Previous token revoked immediately');db.session.commit();session['edge_one_time_token']=token;session['edge_one_time_uid']=g.gateway_uid;return redirect(url_for('edge.registry'))

@edge_bp.post('/edge-gateways/<int:gateway_id>/toggle')
@login_required
def toggle(gateway_id):
    g=tenant_gateway(gateway_id);g.active=not g.active;g.status='PROVISIONED' if g.active else 'DISABLED';audit(g,'ENABLED' if g.active else 'DISABLED');db.session.commit();flash('Gateway state updated.','ok');return redirect(url_for('edge.detail',gateway_id=g.id))

@edge_bp.post('/api/v1/edge/heartbeat')
def heartbeat():
    g=authenticate()
    if not g:return jsonify(error='unauthorized'),401
    data=request.get_json(silent=True) or {};g.last_heartbeat_at=now();g.last_ip=request.remote_addr;g.version=str(data.get('version',''))[:40];g.capabilities=data.get('capabilities',[])[:30];g.queue_depth=max(0,int(data.get('queue_depth') or 0));g.status='ONLINE';g.last_error=None;audit(g,'HEARTBEAT',detail=f'Version {g.version}; queue {g.queue_depth}');db.session.commit();return jsonify(status='ok',gateway_id=g.gateway_uid,server_time=now().isoformat())

@edge_bp.post('/api/v1/edge/ingest')
def ingest():
    g=authenticate()
    if not g:return jsonify(error='unauthorized'),401
    raw=request.get_data(cache=True);data=request.get_json(silent=True) or {};connector_key=str(data.get('connector_key','')).strip();points=data.get('points') or []
    if not connector_key or not isinstance(points,list):return jsonify(error='invalid_payload'),400
    body_hash=hashlib.sha256(raw).hexdigest();duplicate=EdgeGatewayReceipt.query.filter_by(gateway_id=g.id,body_hash=body_hash).first()
    if duplicate:return jsonify(status='duplicate',mapped_points=duplicate.mapped_count),200
    mapped=0;errors=[]
    # Optional mapping through REV19C-G if those models are present.
    try:
        from .models import IntegrationConnector,UniversalSourceMapping
        connector=IntegrationConnector.query.filter_by(customer_id=g.customer_id,edge_gateway_id=connector_key).first()
        if connector:
            timestamp=str(data.get('timestamp') or now().isoformat()).replace('Z','+00:00')
            try:sampled=datetime.fromisoformat(timestamp)
            except Exception:sampled=now()
            for point in points:
                for mapping in UniversalSourceMapping.query.filter_by(connector_id=connector.id,source_path=point.get('source_path'),enabled=True).all():
                    try:
                        raw_value=float(point['value']);value=raw_value*mapping.scale+mapping.offset
                        db.session.add(Reading(customer_id=g.customer_id,asset_id=mapping.asset_id,signal_id=mapping.signal_id,sampled_at=sampled,value=value,raw_value=raw_value,unit=mapping.signal.unit,quality=str(point.get('quality','GOOD')),sequence=f'edge:{g.id}:{body_hash[:16]}:{mapping.id}'))
                        asset=db.session.get(Asset,mapping.asset_id);asset.last_seen=now();mapping.last_value=value;mapping.last_quality=str(point.get('quality','GOOD'));mapping.last_success_at=now();mapping.last_error=None;mapped+=1
                    except Exception as exc:errors.append(type(exc).__name__)
            connector.last_success_at=now();connector.status='CONNECTED';connector.last_error=None
    except (ImportError,AttributeError):
        errors.append('mapping_module_unavailable')
    g.last_upload_at=now();g.last_heartbeat_at=now();g.last_ip=request.remote_addr;g.status='ONLINE';detail=f'{len(points)} points received; {mapped} mapped'
    db.session.add(EdgeGatewayReceipt(customer_id=g.customer_id,gateway_id=g.id,connector_key=connector_key,point_count=len(points),mapped_count=mapped,status='ACCEPTED',body_hash=body_hash,detail=detail));audit(g,'INGEST','OK',detail);db.session.commit();return jsonify(status='accepted',received_points=len(points),mapped_points=mapped,errors=errors[:5]),202
