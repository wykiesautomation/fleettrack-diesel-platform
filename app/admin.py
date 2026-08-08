from functools import wraps
from datetime import datetime,timezone,timedelta
from flask import Blueprint,abort,flash,redirect,render_template,request,url_for
from flask_login import current_user,login_required
from sqlalchemy import desc,or_
from . import db
from .models import *
admin_bp=Blueprint("admin",__name__,url_prefix="/platform-admin")
def now():return datetime.now(timezone.utc)
def aware(v):return v if not v or v.tzinfo else v.replace(tzinfo=timezone.utc)
def owner(fn):
 @wraps(fn)
 @login_required
 def w(*a,**k):
  if current_user.role!="platform_admin":abort(403)
  return fn(*a,**k)
 return w
def log(kind,cid,msg):db.session.add(SecurityAuditEvent(customer_id=cid,event_type=kind,actor_type="PLATFORM_ADMIN",actor_id=current_user.id,safe_summary=msg[:500],source_ip=(request.remote_addr or "")[:80]))
@admin_bp.get("/")
@owner
def dashboard():
 n=now();ms=n.replace(day=1,hour=0,minute=0,second=0,microsecond=0);pay=PaymentRecord.query.filter(PaymentRecord.created_at>=ms).all();att=Subscription.query.join(Customer).filter(Customer.slug!="platform-admin",Subscription.state.in_(["PAYMENT_REQUIRED","GRACE_PERIOD","SUSPENDED"])).limit(8).all();tot={"customers":Customer.query.filter(Customer.slug!="platform-admin").count(),"active":Subscription.query.filter_by(state="ACTIVE").count(),"received":sum(x.amount_gross for x in pay if x.status=="COMPLETE"),"pending":sum(x.amount_gross for x in pay if x.status=="PENDING"),"failed":sum(1 for x in pay if x.status in ("FAILED","CANCELLED")),"devices":Device.query.count()};return render_template("platform_admin_overview.html",tot=tot,att=att,recent=PaymentRecord.query.order_by(desc(PaymentRecord.created_at)).limit(8).all())
@admin_bp.get("/customers")
@owner
def customers():
 q=request.args.get("q","").strip();cs=Customer.query.filter(Customer.slug!="platform-admin").order_by(desc(Customer.created_at)).all();rows=[]
 for c in cs:
  us=User.query.filter_by(customer_id=c.id).all();ds=Device.query.filter_by(customer_id=c.id).all();sub=Subscription.query.filter_by(customer_id=c.id).first();lp=PaymentRecord.query.filter_by(customer_id=c.id,status="COMPLETE").order_by(desc(PaymentRecord.paid_at)).first();rows.append(dict(c=c,users=us,assets=Asset.query.filter_by(customer_id=c.id).count(),devices=len(ds),sub=sub,last=lp))
 if q:rows=[x for x in rows if q.lower() in x["c"].name.lower() or any(q.lower() in u.email.lower() for u in x["users"])]
 return render_template("platform_admin_customers.html",rows=rows,q=q)
@admin_bp.get("/customers/<int:cid>")
@owner
def customer(cid):
 c=Customer.query.filter(Customer.id==cid,Customer.slug!="platform-admin").first_or_404();return render_template("platform_admin_customer.html",c=c,users=User.query.filter_by(customer_id=cid).all(),assets=Asset.query.filter_by(customer_id=cid).all(),devices=Device.query.filter_by(customer_id=cid).all(),sub=Subscription.query.filter_by(customer_id=cid).first(),payments=PaymentRecord.query.filter_by(customer_id=cid).order_by(desc(PaymentRecord.created_at)).all())
@admin_bp.post("/customers/<int:cid>/access")
@owner
def access(cid):
 c=Customer.query.filter(Customer.id==cid,Customer.slug!="platform-admin").first_or_404();s=Subscription.query.filter_by(customer_id=cid).first_or_404();a=request.form.get("action");old=s.state
 if a=="complimentary":s.state="ACTIVE";s.access_source="COMPLIMENTARY";c.active=True
 elif a=="payment":s.state="PAYMENT_REQUIRED";s.access_source="PAYMENT_REQUIRED"
 elif a=="suspend":s.state="SUSPENDED";s.access_source="SUSPENDED"
 else:abort(400)
 db.session.add(SubscriptionAuditEvent(customer_id=cid,subscription_id=s.id,previous_state=old,new_state=s.state,reason="Platform owner: "+a));log("PLATFORM_ACCESS_CHANGED",cid,a);db.session.commit();flash("Access updated.","ok");return redirect(url_for("admin.customer",cid=cid))
@admin_bp.post("/users/<int:uid>/verify")
@owner
def verify(uid):
 u=User.query.get_or_404(uid);u.email_verified=True;u.email_verified_at=now();u.verification_nonce=None;u.customer.active=True;db.session.commit();return redirect(url_for("admin.customer",cid=u.customer_id))
@admin_bp.get("/payments")
@owner
def payments():
 st=request.args.get("status","");rows=PaymentRecord.query.order_by(desc(PaymentRecord.created_at)).limit(500).all();rows=[x for x in rows if not st or x.status==st];return render_template("platform_admin_payments.html",rows=rows,st=st,complete=sum(x.amount_gross for x in rows if x.status=="COMPLETE"),pending=sum(x.amount_gross for x in rows if x.status=="PENDING"))
@admin_bp.get("/subscriptions")
@owner
def subscriptions():return render_template("platform_admin_subscriptions.html",rows=Subscription.query.join(Customer).filter(Customer.slug!="platform-admin").order_by(desc(Subscription.updated_at)).all())
@admin_bp.get("/devices")
@owner
def devices():return render_template("platform_admin_devices.html",rows=Device.query.order_by(desc(Device.last_seen)).all())
@admin_bp.get("/audit")
@owner
def audit():return render_template("platform_admin_audit.html",rows=SecurityAuditEvent.query.order_by(desc(SecurityAuditEvent.created_at)).limit(500).all())
@admin_bp.post("/customers/<int:cid>/delete")
@owner
def delete(cid):
 c=Customer.query.filter(Customer.id==cid,Customer.slug!="platform-admin").first_or_404()
 if request.form.get("name")!=c.name or request.form.get("word","").upper()!="DELETE":flash("Confirmation did not match.","error");return redirect(url_for("admin.customer",cid=cid))
 try:
  for model in [Reading,Location,Alarm,CoreAlarmState,DataDeletionRequest,MobileConsent,MobileTrackerRegistration,SecurityAuditEvent,AssetFeatureOverride,AssetAlertSettings,FleetFeatureDefaults,MqttMessageEvent,MqttTopicMapping,MqttSubscription,WebhookReceipt,IntegrationJobEvent,UniversalSourceMapping,IntegrationSignalMapping,IntegrationEvent,EdgeGateway,PaymentRecord,SubscriptionAuditEvent,SignalDefinition,Device,Asset,Site,WorkspaceProfile,Subscription,User]:
   if hasattr(model,"customer_id"):model.query.filter_by(customer_id=cid).delete(synchronize_session=False)
  name=c.name;db.session.delete(c);db.session.commit();flash(name+" deleted.","ok");return redirect(url_for("admin.customers"))
 except Exception as e:db.session.rollback();flash("Delete blocked safely: "+type(e).__name__,"error");return redirect(url_for("admin.customer",cid=cid))
