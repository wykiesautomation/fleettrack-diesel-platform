import os,json,hashlib,hmac,secrets,urllib.parse,urllib.request
from datetime import datetime,timezone,timedelta
from functools import wraps
from flask import Flask,request,jsonify,render_template,redirect,session,url_for,abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash,check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

app=Flask(__name__);app.wsgi_app=ProxyFix(app.wsgi_app,x_proto=1,x_host=1)
app.config['SECRET_KEY']=os.environ.get('SECRET_KEY','development-only-change-me')
dburl=os.environ.get('DATABASE_URL','sqlite:///fleettrack_dev.db')
if dburl.startswith('postgres://'):dburl='postgresql://'+dburl[len('postgres://'):]
app.config['SQLALCHEMY_DATABASE_URI']=dburl;app.config['SQLALCHEMY_TRACK_MODIFICATIONS']=False
app.config['SESSION_COOKIE_HTTPONLY']=True;app.config['SESSION_COOKIE_SAMESITE']='Lax';app.config['SESSION_COOKIE_SECURE']=os.environ.get('COOKIE_SECURE','0')=='1'
db=SQLAlchemy(app)
PLANS={'Starter':(14900,1,30),'Fleet':(49900,10,365),'Business':(129900,50,1095)}
def utc():return datetime.now(timezone.utc)
class Customer(db.Model):
 id=db.Column(db.Integer,primary_key=True);company=db.Column(db.String(160),nullable=False);contact=db.Column(db.String(120),nullable=False);email=db.Column(db.String(180),unique=True,nullable=False);mobile=db.Column(db.String(40));created=db.Column(db.DateTime(timezone=True),default=utc)
class User(db.Model):
 id=db.Column(db.Integer,primary_key=True);customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'));email=db.Column(db.String(180),unique=True,nullable=False);password_hash=db.Column(db.String(255),nullable=False);role=db.Column(db.String(30),default='CUSTOMER_ADMIN');active=db.Column(db.Boolean,default=True)
class Subscription(db.Model):
 id=db.Column(db.Integer,primary_key=True);customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),unique=True);plan=db.Column(db.String(30));status=db.Column(db.String(30),default='PAYMENT_PENDING');device_limit=db.Column(db.Integer);current_period_end=db.Column(db.DateTime(timezone=True));grace_until=db.Column(db.DateTime(timezone=True));cancel_at_end=db.Column(db.Boolean,default=False);payfast_token=db.Column(db.String(255))
class Device(db.Model):
 id=db.Column(db.Integer,primary_key=True);product=db.Column(db.String(80),unique=True);imei=db.Column(db.String(15),unique=True);serial=db.Column(db.String(80),unique=True);state=db.Column(db.String(20),default='AVAILABLE');customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'));api_key_hash=db.Column(db.String(255));api_key_plain=db.Column(db.String(255))
class Asset(db.Model):
 id=db.Column(db.Integer,primary_key=True);customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'));device_id=db.Column(db.Integer,db.ForeignKey('device.id'),unique=True);name=db.Column(db.String(120));registration=db.Column(db.String(40));capacity=db.Column(db.Float);height=db.Column(db.Float);shape=db.Column(db.String(40),default='Rectangular');low=db.Column(db.Float,default=20);critical=db.Column(db.Float,default=10);drop_alarm=db.Column(db.Float,default=5)
class Telemetry(db.Model):
 id=db.Column(db.BigInteger,primary_key=True);device_id=db.Column(db.Integer,db.ForeignKey('device.id'),index=True);ts=db.Column(db.DateTime(timezone=True),index=True);lat=db.Column(db.Float);lng=db.Column(db.Float);speed=db.Column(db.Float);heading=db.Column(db.Float);ignition=db.Column(db.Boolean);current_ma=db.Column(db.Float);level=db.Column(db.Float);litres=db.Column(db.Float);signal=db.Column(db.Integer);satellites=db.Column(db.Integer);message_id=db.Column(db.String(100))
class Payment(db.Model):
 id=db.Column(db.Integer,primary_key=True);customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'));reference=db.Column(db.String(100),unique=True);amount_cents=db.Column(db.Integer);status=db.Column(db.String(30));pf_payment_id=db.Column(db.String(100));created=db.Column(db.DateTime(timezone=True),default=utc);paid_at=db.Column(db.DateTime(timezone=True));raw_hash=db.Column(db.String(64))
class Event(db.Model):
 id=db.Column(db.Integer,primary_key=True);asset_id=db.Column(db.Integer,db.ForeignKey('asset.id'));ts=db.Column(db.DateTime(timezone=True),default=utc);type=db.Column(db.String(50));severity=db.Column(db.String(20));message=db.Column(db.String(300));ack=db.Column(db.Boolean,default=False)
class Command(db.Model):
 id=db.Column(db.Integer,primary_key=True);device_id=db.Column(db.Integer,db.ForeignKey('device.id'));ts=db.Column(db.DateTime(timezone=True),default=utc);type=db.Column(db.String(50));payload=db.Column(db.Text);status=db.Column(db.String(20),default='PENDING')
class Webhook(db.Model):
 id=db.Column(db.Integer,primary_key=True);provider_id=db.Column(db.String(120),unique=True);kind=db.Column(db.String(50));received=db.Column(db.DateTime(timezone=True),default=utc);payload_hash=db.Column(db.String(64))
def current_user():return db.session.get(User,session.get('uid')) if session.get('uid') else None
def login_required(fn):
 @wraps(fn)
 def w(*a,**k):
  if not current_user():return redirect(url_for('home'))
  return fn(*a,**k)
 return w
def admin_required(fn):
 @wraps(fn)
 def w(*a,**k):
  u=current_user()
  if not u or u.role!='PLATFORM_ADMIN':abort(403)
  return fn(*a,**k)
 return w
def active_required(fn):
 @wraps(fn)
 def w(*a,**k):
  u=current_user();s=Subscription.query.filter_by(customer_id=u.customer_id).first() if u else None
  if not u:return jsonify(ok=False,code='AUTH_REQUIRED'),401
  if not s or s.status not in ('ACTIVE','TRIAL'):return jsonify(ok=False,code='SUBSCRIPTION_REQUIRED',status=s.status if s else None),402
  return fn(*a,**k)
 return w
def pf_encode(values):return '&'.join(f'{urllib.parse.quote_plus(str(k))}={urllib.parse.quote_plus(str(v).strip())}' for k,v in values.items() if v not in (None,''))
def pf_signature(values):
 clean={k:v for k,v in values.items() if k!='signature' and v not in (None,'')};base=pf_encode(clean);phrase=os.environ.get('PAYFAST_PASSPHRASE','')
 if phrase:base+='&passphrase='+urllib.parse.quote_plus(phrase)
 return hashlib.md5(base.encode()).hexdigest()
def pf_valid_signature(values):return hmac.compare_digest(pf_signature(values),values.get('signature',''))
def seed():
 if not User.query.filter_by(email='admin@fleettrack.local').first():db.session.add(User(email='admin@fleettrack.local',password_hash=generate_password_hash(os.environ.get('ADMIN_PASSWORD','ChangeMe123!')),role='PLATFORM_ADMIN'))
 if not Device.query.filter_by(serial='SIM868-000124').first():
  key=secrets.token_hex(24);db.session.add(Device(product='FTD-2026-00124',imei='867234051234567',serial='SIM868-000124',api_key_plain=key,api_key_hash=generate_password_hash(key)))
 if not Device.query.filter_by(serial='SIM868-000138').first():
  key=secrets.token_hex(24);db.session.add(Device(product='FTD-2026-00138',imei='867234051234568',serial='SIM868-000138',api_key_plain=key,api_key_hash=generate_password_hash(key)))
 db.session.commit()
@app.route('/health')
def health():return jsonify(ok=True,revision='REV08',database=db.engine.url.get_backend_name(),payfast_mode=os.environ.get('PAYFAST_MODE','sandbox'))
@app.route('/')
def home():return render_template('index.html')
@app.post('/auth/login')
def login():
 d=request.get_json() or request.form;u=User.query.filter_by(email=str(d.get('email','')).lower(),active=True).first()
 if not u or not check_password_hash(u.password_hash,str(d.get('password',''))):return jsonify(ok=False,code='INVALID_CREDENTIALS'),401
 session.clear();session['uid']=u.id;return jsonify(ok=True,role=u.role,next='/admin' if u.role=='PLATFORM_ADMIN' else '/dashboard')
@app.post('/auth/logout')
def logout():session.clear();return jsonify(ok=True)
@app.post('/register')
def register():
 d=request.get_json() or {};required=['company','contact','email','mobile','password','product','imei','serial','asset','capacity','height','plan']
 if any(not str(d.get(x,'')).strip() for x in required):return jsonify(ok=False,code='REQUIRED_FIELDS'),400
 dev=Device.query.filter_by(product=d['product'],imei=d['imei'],serial=str(d['serial']).upper(),state='AVAILABLE').first()
 if not dev:return jsonify(ok=False,code='DEVICE_NOT_AVAILABLE'),409
 try:
  plan=d['plan'] if d['plan'] in PLANS else 'Starter';c=Customer(company=d['company'],contact=d['contact'],email=d['email'].lower(),mobile=d['mobile']);db.session.add(c);db.session.flush();u=User(customer_id=c.id,email=c.email,password_hash=generate_password_hash(d['password']));db.session.add(u);sub=Subscription(customer_id=c.id,plan=plan,status='PAYMENT_PENDING',device_limit=PLANS[plan][1]);db.session.add(sub);dev.state='CLAIMED';dev.customer_id=c.id;a=Asset(customer_id=c.id,device_id=dev.id,name=d['asset'],registration=d.get('registration',''),capacity=float(d['capacity']),height=float(d['height']),shape=d.get('shape','Rectangular'));db.session.add(a);db.session.commit();session['uid']=u.id;return jsonify(ok=True,next='/billing'),201
 except Exception:db.session.rollback();return jsonify(ok=False,code='ACCOUNT_EXISTS'),409
@app.route('/dashboard')
@login_required
def dashboard_page():return render_template('dashboard.html')
@app.route('/billing')
@login_required
def billing_page():return render_template('billing.html')
@app.route('/admin')
@admin_required
def admin_page():return render_template('admin.html')
@app.get('/api/dashboard')
@active_required
def dashboard_data():
 u=current_user();out=[]
 for a in Asset.query.filter_by(customer_id=u.customer_id).all():
  t=Telemetry.query.filter_by(device_id=a.device_id).order_by(Telemetry.id.desc()).first();hist=Telemetry.query.filter_by(device_id=a.device_id).order_by(Telemetry.id.desc()).limit(50).all();events=Event.query.filter_by(asset_id=a.id).order_by(Event.id.desc()).limit(30).all();dev=db.session.get(Device,a.device_id)
  out.append({'asset':{'id':a.id,'name':a.name,'registration':a.registration,'capacity':a.capacity,'height':a.height,'shape':a.shape,'low':a.low,'critical':a.critical,'drop_alarm':a.drop_alarm,'serial':dev.serial,'imei':dev.imei},'telemetry':telemetry_dict(t),'history':[telemetry_dict(x) for x in hist],'events':[{'id':x.id,'ts':x.ts.isoformat(),'type':x.type,'severity':x.severity,'message':x.message,'ack':x.ack} for x in events]})
 return jsonify(ok=True,fleet=out)
def telemetry_dict(t):return {} if not t else {k:getattr(t,k) for k in ['lat','lng','speed','heading','ignition','current_ma','level','litres','signal','satellites']}|{'ts':t.ts.isoformat()}
@app.get('/api/billing')
@login_required
def billing_data():
 u=current_user();s=Subscription.query.filter_by(customer_id=u.customer_id).first();p=Payment.query.filter_by(customer_id=u.customer_id).order_by(Payment.id.desc()).all();return jsonify(ok=True,subscription={'plan':s.plan,'status':s.status,'amount_cents':PLANS[s.plan][0],'period_end':s.current_period_end.isoformat() if s.current_period_end else None},payments=[{'reference':x.reference,'amount_cents':x.amount_cents,'status':x.status,'created':x.created.isoformat()} for x in p])
@app.post('/billing/payfast/start')
@login_required
def payfast_start():
 u=current_user();c=db.session.get(Customer,u.customer_id);s=Subscription.query.filter_by(customer_id=c.id).first();ref='FT-'+secrets.token_hex(8).upper();pay=Payment(customer_id=c.id,reference=ref,amount_cents=PLANS[s.plan][0],status='PENDING');db.session.add(pay);db.session.commit();base=os.environ.get('PUBLIC_BASE_URL',request.url_root.rstrip('/'));vals={'merchant_id':os.environ.get('PAYFAST_MERCHANT_ID','10000100'),'merchant_key':os.environ.get('PAYFAST_MERCHANT_KEY','46f0cd694581a'),'return_url':base+'/billing/payfast/return','cancel_url':base+'/billing/payfast/cancel','notify_url':base+'/billing/payfast/notify','name_first':c.contact[:100],'email_address':c.email,'m_payment_id':ref,'amount':f'{pay.amount_cents/100:.2f}','item_name':f'FleetTrack {s.plan} Subscription','subscription_type':'1','billing_date':utc().date().isoformat(),'recurring_amount':f'{pay.amount_cents/100:.2f}','frequency':'3','cycles':'0'};vals['signature']=pf_signature(vals);endpoint='https://sandbox.payfast.co.za/eng/process' if os.environ.get('PAYFAST_MODE','sandbox')=='sandbox' else 'https://www.payfast.co.za/eng/process';return jsonify(ok=True,endpoint=endpoint,fields=vals,reference=ref)
@app.post('/billing/payfast/notify')
def payfast_notify():
 vals=request.form.to_dict(flat=True);raw=request.get_data(cache=True);ref=vals.get('m_payment_id','');pay=Payment.query.filter_by(reference=ref).first()
 if not pay:return 'unknown payment',404
 if not pf_valid_signature(vals):return 'bad signature',400
 expected=f'{pay.amount_cents/100:.2f}';received=vals.get('amount_gross',vals.get('amount',''))
 if received and received!=expected:return 'amount mismatch',400
 provider_id=vals.get('pf_payment_id',hashlib.sha256(raw).hexdigest());
 if Webhook.query.filter_by(provider_id=provider_id).first():return 'duplicate',200
 db.session.add(Webhook(provider_id=provider_id,kind=vals.get('payment_status','UNKNOWN'),payload_hash=hashlib.sha256(raw).hexdigest()));pay.pf_payment_id=provider_id;pay.raw_hash=hashlib.sha256(raw).hexdigest()
 if vals.get('payment_status')=='COMPLETE':
  pay.status='PAID';pay.paid_at=utc();s=Subscription.query.filter_by(customer_id=pay.customer_id).first();s.status='ACTIVE';s.current_period_end=utc()+timedelta(days=30);s.payfast_token=vals.get('token')
 else:pay.status=vals.get('payment_status','FAILED');s=Subscription.query.filter_by(customer_id=pay.customer_id).first();s.status='PAST_DUE';s.grace_until=utc()+timedelta(days=5)
 db.session.commit();return 'OK',200
@app.get('/billing/payfast/return')
def payfast_return():return render_template('payment_result.html',title='Payment submitted',message='Payment confirmation is being verified by PayFast. Access activates only after the verified ITN is processed.')
@app.get('/billing/payfast/cancel')
def payfast_cancel():return render_template('payment_result.html',title='Payment cancelled',message='No subscription change was made.')
@app.get('/api/admin/customers')
@admin_required
def admin_customers():
 rows=[]
 for c in Customer.query.order_by(Customer.id).all():
  s=Subscription.query.filter_by(customer_id=c.id).first();rows.append({'id':c.id,'company':c.company,'email':c.email,'plan':s.plan if s else None,'status':s.status if s else None,'devices':Asset.query.filter_by(customer_id=c.id).count()})
 return jsonify(ok=True,customers=rows)
@app.post('/api/admin/subscription')
@admin_required
def admin_subscription():
 d=request.get_json() or {};s=Subscription.query.filter_by(customer_id=int(d.get('customer_id',0))).first();status=d.get('status')
 if not s or status not in ('TRIAL','ACTIVE','PAYMENT_PENDING','PAST_DUE','SUSPENDED','CANCELLED'):return jsonify(ok=False),400
 s.status=status;db.session.commit();return jsonify(ok=True)
def device_auth():
 serial=request.headers.get('X-Device-Serial','');key=request.headers.get('X-Device-Key','');dev=Device.query.filter_by(serial=serial,state='CLAIMED').first();return dev if dev and check_password_hash(dev.api_key_hash,key) else None
@app.post('/api/device/telemetry')
def device_telemetry():
 dev=device_auth()
 if not dev:return jsonify(ok=False,code='INVALID_DEVICE'),401
 d=request.get_json() or {};samples=d.get('samples',[d]);asset=Asset.query.filter_by(device_id=dev.id).first();accepted=0
 for x in samples[:100]:
  ma=float(x.get('current_ma',-1));lat=float(x.get('lat',999));lng=float(x.get('lng',999));speed=float(x.get('speed',0))
  if not(0<=ma<=24 and -90<=lat<=90 and -180<=lng<=180 and 0<=speed<=250):continue
  level=max(0,min(100,(ma-4)/16*100));db.session.add(Telemetry(device_id=dev.id,ts=utc(),lat=lat,lng=lng,speed=speed,heading=x.get('heading',0),ignition=bool(x.get('ignition')),current_ma=ma,level=level,litres=asset.capacity*level/100,signal=x.get('signal',0),satellites=x.get('satellites',0),message_id=request.headers.get('X-Message-Id')));accepted+=1
 db.session.commit();return jsonify(ok=True,accepted=accepted),201
@app.cli.command('init-db')
def init_db():db.create_all();seed();print('Database initialized')
with app.app_context():db.create_all();seed()
