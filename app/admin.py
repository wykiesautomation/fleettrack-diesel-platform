from functools import wraps
from datetime import datetime, timezone, timedelta
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import desc, or_
from . import db
from .models import Customer, User, Asset, Device, Subscription, SubscriptionPlan, PaymentRecord, PayFastEvent, SubscriptionAuditEvent, SecurityAuditEvent, DataDeletionRequest, Site, SignalDefinition, Reading, Alarm, Location, WorkspaceProfile, MobileTrackerRegistration, MobileConsent, CoreAlarmState, AssetFeatureOverride, AssetAlertSettings, FleetFeatureDefaults, IntegrationConnector, IntegrationSignalMapping, IntegrationEvent, ConnectorEndpointConfig, UniversalSourceMapping, WebhookReceipt, EdgeGateway, IntegrationJobEvent, MqttSubscription, MqttTopicMapping, MqttMessageEvent

admin_bp=Blueprint('admin',__name__,url_prefix='/platform-admin')
def utcnow(): return datetime.now(timezone.utc)
def aware(v): return v if not v or v.tzinfo else v.replace(tzinfo=timezone.utc)
def owner_only(fn):
 @wraps(fn)
 @login_required
 def wrapped(*args,**kwargs):
  if current_user.role!='platform_admin': abort(403)
  return fn(*args,**kwargs)
 return wrapped
def customer_name_map(): return {c.id:c.name for c in Customer.query.all()}
def admin_audit(kind,cid,summary): db.session.add(SecurityAuditEvent(customer_id=cid or current_user.customer_id,event_type=kind,actor_type='PLATFORM_ADMIN',actor_id=current_user.id,safe_summary=summary[:500],source_ip=(request.headers.get('CF-Connecting-IP') or request.remote_addr or '')[:80]))

def billing_state(sub):
 if not sub:return 'MISSING'
 if sub.access_source=='COMPLIMENTARY' and sub.state=='ACTIVE':return 'COMPLIMENTARY'
 if sub.state=='ACTIVE':return 'PAID'
 return sub.state

@admin_bp.get('/')
@owner_only
def overview():
 now=utcnow();month=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0);payments=PaymentRecord.query.filter(PaymentRecord.created_at>=month).all();names=customer_name_map()
 complete=[p for p in payments if p.status=='COMPLETE'];pending=[p for p in payments if p.status=='PENDING'];failed=[p for p in payments if p.status in ('FAILED','CANCELLED')]
 offline=Device.query.filter(Device.active.is_(True),or_(Device.last_seen.is_(None),Device.last_seen<now-timedelta(minutes=30))).count()
 attention=Subscription.query.join(Customer,Subscription.customer_id==Customer.id).filter(Customer.slug!='platform-admin',Subscription.state.in_(['PAYMENT_REQUIRED','GRACE_PERIOD','SUSPENDED'])).order_by(desc(Subscription.updated_at)).limit(10).all()
 stats={'customers':Customer.query.filter(Customer.slug!='platform-admin').count(),'active_subscriptions':Subscription.query.join(Customer,Subscription.customer_id==Customer.id).filter(Customer.slug!='platform-admin',Subscription.state=='ACTIVE').count(),'paid_month':sum(float(p.amount_gross or 0) for p in complete),'pending_count':len(pending),'failed_count':len(failed),'devices':Device.query.count(),'offline':offline,'notifications':len(attention)+len(failed)}
 return render_template('platform_admin_overview.html',stats=stats,attention=attention,recent=PaymentRecord.query.order_by(desc(PaymentRecord.created_at)).limit(10).all(),names=names)

@admin_bp.get('/customers')
@owner_only
def customers():
 q=request.args.get('q','').strip().lower();state=request.args.get('state','').strip().upper();rows=[];names=customer_name_map()
 for c in Customer.query.filter(Customer.slug!='platform-admin').order_by(desc(Customer.created_at)).all():
  users=User.query.filter_by(customer_id=c.id).all();sub=Subscription.query.filter_by(customer_id=c.id).first()
  if q and q not in c.name.lower() and q not in c.slug.lower() and not any(q in u.email.lower() for u in users):continue
  if state and billing_state(sub)!=state and (not sub or sub.state!=state):continue
  last=PaymentRecord.query.filter_by(customer_id=c.id,status='COMPLETE').order_by(desc(PaymentRecord.paid_at)).first()
  rows.append({'customer':c,'users':users,'sub':sub,'access':billing_state(sub),'assets':Asset.query.filter_by(customer_id=c.id).count(),'devices':Device.query.filter_by(customer_id=c.id).count(),'last':last})
 return render_template('platform_admin_customers.html',rows=rows,q=q,state=state)

@admin_bp.get('/users')
@owner_only
def users():
 q=request.args.get('q','').strip().lower();rows=User.query.join(Customer,User.customer_id==Customer.id).filter(Customer.slug!='platform-admin').order_by(desc(User.created_at)).all()
 if q:rows=[u for u in rows if q in u.email.lower() or q in u.name.lower() or q in u.customer.name.lower()]
 return render_template('platform_admin_users.html',rows=rows,q=q)

@admin_bp.get('/subscriptions')
@owner_only
def subscriptions():
 rows=Subscription.query.join(Customer,Subscription.customer_id==Customer.id).filter(Customer.slug!='platform-admin').order_by(desc(Subscription.updated_at)).all()
 return render_template('platform_admin_subscriptions.html',rows=rows,billing_state=billing_state)

@admin_bp.get('/payments')
@owner_only
def payments():
 status=request.args.get('status','').strip().upper();q=request.args.get('q','').strip().lower();names=customer_name_map();rows=PaymentRecord.query.order_by(desc(PaymentRecord.created_at)).limit(1000).all()
 if status:rows=[p for p in rows if p.status==status]
 if q:rows=[p for p in rows if q in names.get(p.customer_id,'').lower() or q in str(p.merchant_payment_id or '').lower() or q in str(p.provider_reference or '').lower()]
 return render_template('platform_admin_payments.html',rows=rows,names=names,status=status,q=q,complete=sum(float(p.amount_gross or 0) for p in rows if p.status=='COMPLETE'),pending=sum(float(p.amount_gross or 0) for p in rows if p.status=='PENDING'),failed=sum(1 for p in rows if p.status in ('FAILED','CANCELLED')))

@admin_bp.post('/payments/eft')
@owner_only
def record_eft():
 cid=request.form.get('customer_id',type=int);customer=Customer.query.filter(Customer.id==cid,Customer.slug!='platform-admin').first_or_404();amount=request.form.get('amount',type=float);reference=request.form.get('reference','').strip();status=request.form.get('status','PENDING').upper()
 if not amount or amount<=0 or not reference or status not in ('PENDING','COMPLETE'):flash('Valid customer, amount, reference and status are required.','error');return redirect(url_for('admin.payments'))
 if PaymentRecord.query.filter_by(merchant_payment_id=reference).first():flash('That payment reference already exists.','error');return redirect(url_for('admin.payments'))
 sub=Subscription.query.filter_by(customer_id=cid).first();p=PaymentRecord(customer_id=cid,subscription_id=sub.id if sub else None,provider='MANUAL_EFT',merchant_payment_id=reference,amount_gross=amount,status=status,payment_method='EFT',paid_at=utcnow() if status=='COMPLETE' else None);db.session.add(p)
 if status=='COMPLETE' and sub:
  old=sub.state;sub.state='ACTIVE';sub.access_source='PAID';sub.current_period_start=utcnow();sub.current_period_end=utcnow()+timedelta(days=30);sub.paid_from=sub.current_period_start;sub.paid_until=sub.current_period_end;sub.next_payment_at=sub.current_period_end
  db.session.add(SubscriptionAuditEvent(customer_id=cid,subscription_id=sub.id,previous_state=old,new_state='ACTIVE',reason='Manual EFT recorded by platform owner'))
 admin_audit('MANUAL_EFT_RECORDED',cid,f'{reference} R{amount:.2f} {status}');db.session.commit();flash('EFT payment recorded.','ok');return redirect(url_for('admin.payments'))

@admin_bp.get('/invoices')
@owner_only
def invoices():
 names=customer_name_map();rows=PaymentRecord.query.order_by(desc(PaymentRecord.created_at)).limit(1000).all();return render_template('platform_admin_invoices.html',rows=rows,names=names)

@admin_bp.get('/devices')
@owner_only
def devices():
 now=utcnow();rows=[]
 for d in Device.query.order_by(desc(Device.last_seen)).all():rows.append({'device':d,'online':bool(d.active and d.last_seen and now-aware(d.last_seen)<=timedelta(minutes=30))})
 return render_template('platform_admin_devices.html',rows=rows)

@admin_bp.get('/support')
@owner_only
def support():
 rows=DataDeletionRequest.query.order_by(desc(DataDeletionRequest.requested_at)).limit(500).all();return render_template('platform_admin_support.html',rows=rows,names=customer_name_map())

@admin_bp.get('/audit')
@owner_only
def audit():return render_template('platform_admin_audit.html',rows=SecurityAuditEvent.query.order_by(desc(SecurityAuditEvent.created_at)).limit(1000).all(),names=customer_name_map())

@admin_bp.get('/settings')
@owner_only
def settings():return render_template('platform_admin_settings.html',plans=SubscriptionPlan.query.order_by(SubscriptionPlan.monthly_price).all())

@admin_bp.get('/customers/<int:customer_id>')
@owner_only
def customer_detail(customer_id):
 c=Customer.query.filter(Customer.id==customer_id,Customer.slug!='platform-admin').first_or_404();sub=Subscription.query.filter_by(customer_id=c.id).first()
 return render_template('platform_admin_customer.html',customer=c,users=User.query.filter_by(customer_id=c.id).all(),assets=Asset.query.filter_by(customer_id=c.id).all(),devices=Device.query.filter_by(customer_id=c.id).all(),sub=sub,access=billing_state(sub),payments=PaymentRecord.query.filter_by(customer_id=c.id).order_by(desc(PaymentRecord.created_at)).all())

@admin_bp.post('/customers/<int:customer_id>/access')
@owner_only
def access(customer_id):
 c=Customer.query.filter(Customer.id==customer_id,Customer.slug!='platform-admin').first_or_404();sub=Subscription.query.filter_by(customer_id=c.id).first_or_404();action=request.form.get('action');old=sub.state
 if action=='complimentary':sub.state='ACTIVE';sub.access_source='COMPLIMENTARY';c.active=True
 elif action=='payment_required':sub.state='PAYMENT_REQUIRED';sub.access_source='PAYMENT_REQUIRED'
 elif action=='suspend':sub.state='SUSPENDED';sub.access_source='SUSPENDED'
 else:abort(400)
 db.session.add(SubscriptionAuditEvent(customer_id=c.id,subscription_id=sub.id,previous_state=old,new_state=sub.state,reason='Platform owner: '+action));admin_audit('PLATFORM_ACCESS_CHANGED',c.id,action);db.session.commit();flash('Customer access updated.','ok');return redirect(url_for('admin.customer_detail',customer_id=c.id))

@admin_bp.post('/users/<int:user_id>/verify')
@owner_only
def verify_user(user_id):
 u=User.query.join(Customer,User.customer_id==Customer.id).filter(User.id==user_id,Customer.slug!='platform-admin').first_or_404();u.email_verified=True;u.email_verified_at=utcnow();u.verification_nonce=None;u.customer.active=True;admin_audit('PLATFORM_EMAIL_VERIFIED',u.customer_id,u.email);db.session.commit();flash('User verified.','ok');return redirect(request.referrer or url_for('admin.users'))

@admin_bp.post('/users/<int:user_id>/toggle')
@owner_only
def toggle_user(user_id):
 u=User.query.join(Customer,User.customer_id==Customer.id).filter(User.id==user_id,Customer.slug!='platform-admin').first_or_404();u.active=not u.active;admin_audit('PLATFORM_USER_TOGGLED',u.customer_id,f'{u.email}: {u.active}');db.session.commit();return redirect(request.referrer or url_for('admin.users'))

@admin_bp.post('/customers/<int:customer_id>/delete')
@owner_only
def delete_customer(customer_id):
 c=Customer.query.filter(Customer.id==customer_id,Customer.slug!='platform-admin').first_or_404()
 if request.form.get('confirm_name','').strip()!=c.name or request.form.get('confirm_word','').strip().upper()!='DELETE':flash('Exact customer name and DELETE are required.','error');return redirect(url_for('admin.customer_detail',customer_id=c.id))
 cid=c.id
 try:
  connector_ids=[x.id for x in IntegrationConnector.query.filter_by(customer_id=cid).all()]
  if connector_ids:
   ConnectorEndpointConfig.query.filter(ConnectorEndpointConfig.connector_id.in_(connector_ids)).delete(synchronize_session=False)
  for model in (Reading,Location,Alarm,CoreAlarmState,DataDeletionRequest,MobileConsent,MobileTrackerRegistration,SecurityAuditEvent,AssetFeatureOverride,AssetAlertSettings,FleetFeatureDefaults,MqttMessageEvent,MqttTopicMapping,MqttSubscription,WebhookReceipt,IntegrationJobEvent,UniversalSourceMapping,IntegrationSignalMapping,IntegrationEvent,EdgeGateway,PaymentRecord,SubscriptionAuditEvent,SignalDefinition,Device,Asset,Site,WorkspaceProfile,Subscription,User):
   if hasattr(model,'customer_id'):model.query.filter_by(customer_id=cid).delete(synchronize_session=False)
  IntegrationConnector.query.filter_by(customer_id=cid).delete(synchronize_session=False);name=c.name;db.session.delete(c);db.session.commit();flash(name+' permanently deleted.','ok');return redirect(url_for('admin.customers'))
 except Exception as exc:db.session.rollback();flash('Delete blocked safely: '+type(exc).__name__+'. No partial deletion committed.','error');return redirect(url_for('admin.customer_detail',customer_id=cid))
