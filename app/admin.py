from functools import wraps
from datetime import datetime, timezone, timedelta
import secrets
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for, Response
from flask_login import current_user, login_required
from sqlalchemy import desc, or_
from werkzeug.security import generate_password_hash
from . import db
from .models import *
from .security_privacy import audit
from .device_profiles import profile_for_device
admin_bp=Blueprint('admin',__name__,url_prefix='/platform-admin')
def utcnow():return datetime.now(timezone.utc)
def aware(v):return v if not v or v.tzinfo else v.replace(tzinfo=timezone.utc)
def owner_only(fn):
 @wraps(fn)
 @login_required
 def wrapped(*a,**k):
  if current_user.role!='platform_admin':abort(403)
  return fn(*a,**k)
 return wrapped
def cname(cid):
 c=db.session.get(Customer,cid);return c.name if c else f'Customer #{cid}'
def access_label(sub):
 if not sub:return 'MISSING'
 if sub.state=='ACTIVE' and sub.access_source=='COMPLIMENTARY':return 'COMPLIMENTARY'
 if sub.state=='ACTIVE':return 'PAID'
 return sub.state
def log(kind,cid,summary):audit(cid or current_user.customer_id,kind,actor_type='PLATFORM_ADMIN',actor_id=current_user.id,summary=summary)
def next_invoice(payment):return payment.invoice_number or f'AT360-INV-{payment.id:07d}'
@admin_bp.get('/')
@owner_only
def dashboard():
 n=utcnow();month=n.replace(day=1,hour=0,minute=0,second=0,microsecond=0);pay=PaymentRecord.query.filter(PaymentRecord.created_at>=month).all();bad=Subscription.query.join(Customer,Subscription.customer_id==Customer.id).filter(Customer.slug!='platform-admin',Subscription.state.in_(['PAYMENT_REQUIRED','GRACE_PERIOD','SUSPENDED'])).order_by(desc(Subscription.updated_at)).limit(10).all();offline=Device.query.filter(Device.active.is_(True),or_(Device.last_seen.is_(None),Device.last_seen<n-timedelta(minutes=30))).count();stats={'customers':Customer.query.filter(Customer.slug!='platform-admin').count(),'users':User.query.join(Customer,User.customer_id==Customer.id).filter(Customer.slug!='platform-admin').count(),'active':Subscription.query.join(Customer,Subscription.customer_id==Customer.id).filter(Customer.slug!='platform-admin',Subscription.state=='ACTIVE').count(),'paid':sum(float(x.amount_gross or 0) for x in pay if x.status=='COMPLETE'),'pending':sum(1 for x in pay if x.status=='PENDING'),'failed':sum(1 for x in pay if x.status in ('FAILED','CANCELLED')),'devices':Device.query.count(),'offline':offline,'notifications':len(bad)};return render_template('platform_admin_overview.html',stats=stats,attention=bad,recent=PaymentRecord.query.order_by(desc(PaymentRecord.created_at)).limit(10).all(),cname=cname)
@admin_bp.route('/customers',methods=['GET','POST'])
@owner_only
def customers():
 if request.method=='POST':
  company=request.form.get('company','').strip();name=request.form.get('name','').strip();email=request.form.get('email','').strip().lower();password=request.form.get('password','')
  if len(company)<2 or len(name)<2 or '@' not in email or len(password)<10:flash('Complete all fields. Password must be at least 10 characters.','error')
  elif User.query.filter_by(email=email).first():flash('That email already exists.','error')
  else:
   slug=''.join(ch.lower() if ch.isalnum() else '-' for ch in company).strip('-')[:70] or 'customer';base=slug;i=1
   while Customer.query.filter_by(slug=slug).first():i+=1;slug=f'{base}-{i}'
   c=Customer(name=company,slug=slug,active=True);db.session.add(c);db.session.flush();u=User(customer_id=c.id,email=email,name=name,role='customer_admin',password_hash=generate_password_hash(password),active=True,email_verified=True,email_verified_at=utcnow());db.session.add(u);plan=SubscriptionPlan.query.filter_by(code='monitor').first() or SubscriptionPlan.query.filter_by(active=True).first();db.session.add(Subscription(customer_id=c.id,plan_id=plan.id,state='PAYMENT_REQUIRED',access_source='PAYMENT_REQUIRED',trial_started_at=utcnow()));db.session.add(WorkspaceProfile(customer_id=c.id,contact_email=email,billing_email=email));log('PLATFORM_CUSTOMER_CREATED',c.id,email);db.session.commit();flash('Customer created. Payment is required before operational access.','ok');return redirect(url_for('admin.customer_detail',customer_id=c.id))
 q=request.args.get('q','').strip().lower();state=request.args.get('state','').strip().upper();rows=[]
 for c in Customer.query.filter(Customer.slug!='platform-admin').order_by(desc(Customer.created_at)).all():
  us=User.query.filter_by(customer_id=c.id).all();sub=Subscription.query.filter_by(customer_id=c.id).first()
  if q and q not in c.name.lower() and q not in c.slug.lower() and not any(q in u.email.lower() for u in us):continue
  if state and access_label(sub)!=state and (not sub or sub.state!=state):continue
  rows.append({'c':c,'users':us,'sub':sub,'access':access_label(sub),'assets':Asset.query.filter_by(customer_id=c.id).count(),'devices':Device.query.filter_by(customer_id=c.id).count(),'last':PaymentRecord.query.filter_by(customer_id=c.id,status='COMPLETE').order_by(desc(PaymentRecord.paid_at)).first()})
 return render_template('platform_admin_customers.html',rows=rows,q=q,state=state)
@admin_bp.get('/customers/<int:customer_id>')
@owner_only
def customer_detail(customer_id):
 c=Customer.query.filter(Customer.id==customer_id,Customer.slug!='platform-admin').first_or_404();sub=Subscription.query.filter_by(customer_id=customer_id).first();grants=AdvancedAccessGrant.query.filter_by(customer_id=customer_id).order_by(desc(AdvancedAccessGrant.updated_at)).all();return render_template('platform_admin_customer.html',c=c,sub=sub,access=access_label(sub),users=User.query.filter_by(customer_id=customer_id).all(),assets=Asset.query.filter_by(customer_id=customer_id).all(),devices=Device.query.filter_by(customer_id=customer_id).all(),payments=PaymentRecord.query.filter_by(customer_id=customer_id).order_by(desc(PaymentRecord.created_at)).all(),next_invoice=next_invoice,advanced_grants=grants,now=utcnow())
@admin_bp.post('/customers/<int:customer_id>/advanced-access')
@owner_only
def advanced_access(customer_id):
 c=Customer.query.filter(Customer.id==customer_id,Customer.slug!='platform-admin').first_or_404();device_id=request.form.get('device_id',type=int);device=Device.query.filter_by(id=device_id,customer_id=customer_id).first() if device_id else None
 if device_id and not device:abort(400)
 grant=AdvancedAccessGrant.query.filter_by(customer_id=customer_id,device_id=device.id if device else None).first();action=request.form.get('action','grant');source=request.form.get('source','PAID').upper();allowed={'PAID','COMPLIMENTARY','INCLUDED_IN_PLAN','INSTALLER','TEMPORARY'}
 if source not in allowed:abort(400)
 if not grant:grant=AdvancedAccessGrant(customer_id=customer_id,device_id=device.id if device else None,granted_by=current_user.id);db.session.add(grant)
 if action=='revoke':grant.active=False
 elif action=='grant':
  grant.active=True;grant.source=source;grant.note=request.form.get('note','').strip()[:300] or None;grant.granted_by=current_user.id
  expiry=request.form.get('expires_at','').strip();grant.expires_at=datetime.fromisoformat(expiry).replace(tzinfo=timezone.utc) if expiry else None
 else:abort(400)
 log('ADVANCED_ACCESS_'+action.upper(),customer_id,f"{source}; device={device.id if device else 'customer'}");db.session.commit();flash('Advanced access updated.','ok');return redirect(url_for('admin.customer_detail',customer_id=customer_id))

@admin_bp.post('/customers/<int:customer_id>/access')
@owner_only
def access(customer_id):
 c=Customer.query.filter(Customer.id==customer_id,Customer.slug!='platform-admin').first_or_404();s=Subscription.query.filter_by(customer_id=customer_id).first_or_404();a=request.form.get('action');old=s.state
 if a=='complimentary':s.state='ACTIVE';s.access_source='COMPLIMENTARY';c.active=True
 elif a=='payment_required':s.state='PAYMENT_REQUIRED';s.access_source='PAYMENT_REQUIRED'
 elif a=='suspend':s.state='SUSPENDED';s.access_source='SUSPENDED'
 else:abort(400)
 db.session.add(SubscriptionAuditEvent(customer_id=customer_id,subscription_id=s.id,previous_state=old,new_state=s.state,reason='Platform owner: '+a));log('PLATFORM_ACCESS_CHANGED',customer_id,a);db.session.commit();flash('Access updated.','ok');return redirect(url_for('admin.customer_detail',customer_id=customer_id))
@admin_bp.get('/users')
@owner_only
def users():
 q=request.args.get('q','').strip().lower();rows=User.query.join(Customer,User.customer_id==Customer.id).filter(Customer.slug!='platform-admin').order_by(desc(User.created_at)).all();rows=[x for x in rows if not q or q in x.email.lower() or q in x.name.lower() or q in x.customer.name.lower()];return render_template('platform_admin_users.html',rows=rows,q=q)
@admin_bp.post('/users/<int:user_id>/<action>')
@owner_only
def user_action(user_id,action):
 u=User.query.join(Customer,User.customer_id==Customer.id).filter(User.id==user_id,Customer.slug!='platform-admin').first_or_404()
 if action=='verify':u.email_verified=True;u.email_verified_at=utcnow();u.verification_nonce=None;u.customer.active=True
 elif action=='toggle':u.active=not u.active
 else:abort(400)
 log('PLATFORM_USER_'+action.upper(),u.customer_id,u.email);db.session.commit();return redirect(request.referrer or url_for('admin.users'))
@admin_bp.get('/subscriptions')
@owner_only
def subscriptions():return render_template('platform_admin_subscriptions.html',rows=Subscription.query.join(Customer,Subscription.customer_id==Customer.id).filter(Customer.slug!='platform-admin').order_by(desc(Subscription.updated_at)).all(),access_label=access_label)
@admin_bp.route('/payments',methods=['GET','POST'])
@owner_only
def payments():
 if request.method=='POST':
  cid=request.form.get('customer_id',type=int);c=Customer.query.filter(Customer.id==cid,Customer.slug!='platform-admin').first();amount=request.form.get('amount',type=float);ref=request.form.get('reference','').strip();status=request.form.get('status','PENDING').upper()
  if not c or not amount or amount<=0 or not ref or status not in ('PENDING','COMPLETE'):flash('Valid customer, amount, reference and status required.','error')
  elif PaymentRecord.query.filter_by(merchant_payment_id=ref).first():flash('Reference already exists.','error')
  else:
   sub=Subscription.query.filter_by(customer_id=cid).first();p=PaymentRecord(customer_id=cid,subscription_id=sub.id if sub else None,provider='MANUAL_EFT',merchant_payment_id=ref,amount_gross=amount,status=status,payment_method='EFT',paid_at=utcnow() if status=='COMPLETE' else None,admin_note=request.form.get('note','')[:500]);db.session.add(p);db.session.flush();p.invoice_number=next_invoice(p)
   if status=='COMPLETE' and sub:
    old=sub.state;sub.state='ACTIVE';sub.access_source='PAID';sub.current_period_start=utcnow();sub.current_period_end=utcnow()+timedelta(days=30);sub.paid_from=sub.current_period_start;sub.paid_until=sub.current_period_end;sub.next_payment_at=sub.current_period_end;db.session.add(SubscriptionAuditEvent(customer_id=cid,subscription_id=sub.id,previous_state=old,new_state='ACTIVE',reason='Manual EFT recorded'))
   log('MANUAL_EFT_RECORDED',cid,ref);db.session.commit();flash('EFT payment recorded.','ok');return redirect(url_for('admin.payments'))
 st=request.args.get('status','').upper();q=request.args.get('q','').lower();rows=PaymentRecord.query.order_by(desc(PaymentRecord.created_at)).limit(1000).all();rows=[x for x in rows if (not st or x.status==st) and (not q or q in cname(x.customer_id).lower() or q in str(x.merchant_payment_id or '').lower())];return render_template('platform_admin_payments.html',rows=rows,st=st,q=q,cname=cname,next_invoice=next_invoice,complete=sum(float(x.amount_gross or 0) for x in rows if x.status=='COMPLETE'),pending=sum(float(x.amount_gross or 0) for x in rows if x.status=='PENDING'),failed=sum(1 for x in rows if x.status in ('FAILED','CANCELLED')))
@admin_bp.get('/invoices')
@owner_only
def invoices():return render_template('platform_admin_invoices.html',rows=PaymentRecord.query.order_by(desc(PaymentRecord.created_at)).limit(1000).all(),cname=cname,next_invoice=next_invoice)
@admin_bp.get('/devices')
@owner_only
def devices():
 n=utcnow();rows=[{'d':d,'online':bool(d.active and d.last_seen and n-aware(d.last_seen)<=timedelta(minutes=30))} for d in Device.query.order_by(desc(Device.last_seen)).all()];return render_template('platform_admin_devices.html',rows=rows,cname=cname)
@admin_bp.post('/devices/<int:device_id>/repair-assignments')
@owner_only
def repair_device_assignments(device_id):
 """Safely reconcile a linked device profile with existing tenant signals."""
 device=Device.query.filter_by(id=device_id).first_or_404()
 asset=device.asset
 profile=profile_for_device(device)
 if not device.active or not asset or asset.customer_id!=device.customer_id:
  flash('Repair blocked: device must be active and linked to an asset in the same customer workspace.','error');return redirect(url_for('admin.devices'))
 if not profile or not isinstance(profile,dict):
  flash('Repair blocked: no verified device profile is available.','error');return redirect(url_for('admin.devices'))
 linked=0;placeholders=0;preserved=0
 try:
  for spec in profile.get('channels',[]):
   if not isinstance(spec,dict) or not spec.get('key'):continue
   key=str(spec['key']);assignment=DeviceChannelAssignment.query.filter_by(device_id=device.id,channel_key=key).first()
   if not assignment:
    assignment=DeviceChannelAssignment(customer_id=device.customer_id,device_id=device.id,channel_key=key,direction=spec.get('direction','HEALTH'),purpose='UNUSED',customer_label=spec.get('label',key),enabled=False,config_json={})
    db.session.add(assignment);placeholders+=1
   elif assignment.customer_id!=device.customer_id:
    raise ValueError(f'Tenant mismatch on assignment {key}')
   signal=SignalDefinition.query.filter_by(customer_id=device.customer_id,asset_id=asset.id,key=key).first()
   config=dict(assignment.config_json or {})
   config.update({'profile_code':profile.get('code'),'physical_pin':spec.get('pin'),'pin_notes':spec.get('pin_notes'),'reconciled_by_platform_admin':current_user.id,'reconciled_at':utcnow().isoformat()})
   assignment.direction=spec.get('direction','HEALTH');assignment.config_json=config
   if signal:
    assignment.asset_id=asset.id;assignment.signal_id=signal.id;assignment.customer_label=signal.label;assignment.enabled=True
    if assignment.purpose in (None,'','UNUSED'):
     assignment.purpose={'INPUT':'PROCESS_INPUT','OUTPUT':'OUTPUT_FEEDBACK','HEALTH':'DEVICE_HEALTH','LOCATION':'LOCATION'}.get(spec.get('direction'),'DEVICE_POINT')
    signal.enabled=True
    signal_config=dict(signal.config_json or {});signal_config.update({'device_id':device.id,'profile_code':profile.get('code'),'physical_pin':spec.get('pin')});signal.config_json=signal_config
    linked+=1
   else:
    # Preserve an existing intentional assignment; never invent customer process signals.
    if assignment.enabled and assignment.signal_id:preserved+=1
  log('PLATFORM_DEVICE_ASSIGNMENTS_REPAIRED',device.customer_id,f'device={device.id}; asset={asset.id}; linked={linked}; placeholders={placeholders}; preserved={preserved}')
  db.session.commit()
 except Exception as exc:
  db.session.rollback();flash('Assignment repair rolled back safely: '+type(exc).__name__,'error');return redirect(url_for('admin.devices'))
 flash(f'Device {device.id} repaired safely: {linked} existing signal links restored, {placeholders} profile placeholders created, {preserved} existing assignments preserved.','ok')
 return redirect(url_for('admin.devices'))

@admin_bp.get('/support')
@owner_only
def support():return render_template('platform_admin_support.html',rows=DataDeletionRequest.query.order_by(desc(DataDeletionRequest.requested_at)).limit(500).all(),cname=cname)
@admin_bp.get('/audit')
@owner_only
def audit_log():return render_template('platform_admin_audit.html',rows=SecurityAuditEvent.query.order_by(desc(SecurityAuditEvent.created_at)).limit(1000).all(),cname=cname)
@admin_bp.get('/settings')
@owner_only
def settings():return render_template('platform_admin_settings.html',plans=SubscriptionPlan.query.order_by(SubscriptionPlan.monthly_price).all())
@admin_bp.get('/data-management')
@owner_only
def data_management():
 rows=[]
 for c in Customer.query.filter(Customer.slug!='platform-admin').order_by(Customer.name).all():rows.append({'customer':c,'users':User.query.filter_by(customer_id=c.id).count(),'assets':Asset.query.filter_by(customer_id=c.id).count(),'devices':Device.query.filter_by(customer_id=c.id).count()})
 return render_template('platform_admin_data_management.html',rows=rows)
@admin_bp.post('/customers/<int:customer_id>/delete')
@owner_only
def delete_customer(customer_id):
 c=Customer.query.filter(Customer.id==customer_id,Customer.slug!='platform-admin').first_or_404()
 if request.form.get('confirm_name','').strip()!=c.name or request.form.get('confirm_word','').strip().upper()!='DELETE':flash('Exact customer name and DELETE required.','error');return redirect(url_for('admin.data_management'))
 cid=c.id
 try:
  connector_ids=[x.id for x in IntegrationConnector.query.filter_by(customer_id=cid).all()]
  if connector_ids:ConnectorEndpointConfig.query.filter(ConnectorEndpointConfig.connector_id.in_(connector_ids)).delete(synchronize_session=False)
  for model in (Reading,Location,Alarm,CoreAlarmState,DataDeletionRequest,MobileConsent,MobileTrackerRegistration,SecurityAuditEvent,AssetFeatureOverride,AssetAlertSettings,FleetFeatureDefaults,MqttMessageEvent,MqttTopicMapping,MqttSubscription,WebhookReceipt,IntegrationJobEvent,UniversalSourceMapping,IntegrationSignalMapping,IntegrationEvent,EdgeGateway,PaymentRecord,SubscriptionAuditEvent,SignalDefinition,Device,Asset,Site,WorkspaceProfile,Subscription,User):
   if hasattr(model,'customer_id'):model.query.filter_by(customer_id=cid).delete(synchronize_session=False)
  IntegrationConnector.query.filter_by(customer_id=cid).delete(synchronize_session=False);name=c.name;db.session.delete(c);db.session.commit();flash(name+' deleted.','ok');return redirect(url_for('admin.data_management'))
 except Exception as exc:db.session.rollback();flash('Delete blocked safely: '+type(exc).__name__+'. No partial deletion committed.','error');return redirect(url_for('admin.data_management'))


@admin_bp.get('/search')
@owner_only
def global_search():
 q=request.args.get('q','').strip();results={'customers':[],'users':[],'devices':[],'payments':[]}
 if q:
  pat=f'%{q}%'
  results['customers']=Customer.query.filter(Customer.slug!='platform-admin',or_(Customer.name.ilike(pat),Customer.slug.ilike(pat))).limit(30).all()
  results['users']=User.query.join(Customer,User.customer_id==Customer.id).filter(Customer.slug!='platform-admin',or_(User.email.ilike(pat),User.name.ilike(pat))).limit(30).all()
  results['devices']=Device.query.filter(or_(Device.device_uid.ilike(pat),Device.device_type.ilike(pat),Device.firmware.ilike(pat))).limit(30).all()
  results['payments']=PaymentRecord.query.filter(or_(PaymentRecord.merchant_payment_id.ilike(pat),PaymentRecord.provider_reference.ilike(pat),PaymentRecord.invoice_number.ilike(pat))).limit(30).all()
 return render_template('platform_admin_search.html',q=q,results=results,cname=cname,next_invoice=next_invoice)

@admin_bp.get('/payments/<int:payment_id>')
@owner_only
def payment_detail(payment_id):
 payment=PaymentRecord.query.get_or_404(payment_id)
 customer=db.session.get(Customer,payment.customer_id)
 subscription=Subscription.query.filter_by(customer_id=payment.customer_id).first()
 events=PayFastEvent.query.filter_by(merchant_payment_id=payment.merchant_payment_id).order_by(desc(PayFastEvent.created_at)).all()
 return render_template('platform_admin_payment_detail.html',payment=payment,customer=customer,subscription=subscription,events=events,next_invoice=next_invoice)

@admin_bp.post('/payments/<int:payment_id>/note')
@owner_only
def payment_note(payment_id):
 payment=PaymentRecord.query.get_or_404(payment_id)
 payment.admin_note=request.form.get('admin_note','').strip()[:500]
 log('PAYMENT_ADMIN_NOTE',payment.customer_id,next_invoice(payment));db.session.commit();flash('Payment note saved.','ok')
 return redirect(url_for('admin.payment_detail',payment_id=payment.id))

@admin_bp.get('/invoices/<int:payment_id>')
@owner_only
def invoice_detail(payment_id):
 payment=PaymentRecord.query.get_or_404(payment_id);customer=db.session.get(Customer,payment.customer_id);profile=WorkspaceProfile.query.filter_by(customer_id=payment.customer_id).first()
 return render_template('platform_admin_invoice_detail.html',payment=payment,customer=customer,profile=profile,next_invoice=next_invoice)

@admin_bp.get('/invoices/<int:payment_id>/print')
@owner_only
def invoice_print(payment_id):
 payment=PaymentRecord.query.get_or_404(payment_id);customer=db.session.get(Customer,payment.customer_id);profile=WorkspaceProfile.query.filter_by(customer_id=payment.customer_id).first()
 html=render_template('platform_admin_invoice_print.html',payment=payment,customer=customer,profile=profile,next_invoice=next_invoice)
 return Response(html,200,{'Content-Type':'text/html; charset=utf-8','Content-Disposition':f'inline; filename={next_invoice(payment)}.html'})

@admin_bp.post('/support/<int:request_id>/update')
@owner_only
def support_update(request_id):
 item=DataDeletionRequest.query.get_or_404(request_id);state=request.form.get('state','').upper();allowed={'REQUESTED','IN_REVIEW','APPROVED','REJECTED','COMPLETED'}
 if state not in allowed:abort(400)
 item.state=state;item.note=request.form.get('note','').strip()[:500];item.reviewed_at=utcnow();item.reviewed_by=current_user.id
 log('SUPPORT_REQUEST_UPDATED',item.customer_id,f'{item.id}: {state}');db.session.commit();flash('Support request updated.','ok')
 return redirect(url_for('admin.support'))

@admin_bp.get('/notifications')
@owner_only
def notifications():
 rows=[]
 for sub in Subscription.query.join(Customer,Subscription.customer_id==Customer.id).filter(Customer.slug!='platform-admin',Subscription.state.in_(['PAYMENT_REQUIRED','GRACE_PERIOD','SUSPENDED'])).order_by(desc(Subscription.updated_at)).limit(50):
  rows.append({'type':'BILLING','title':sub.customer.name,'detail':sub.state.replace('_',' '),'created_at':sub.updated_at,'url':url_for('admin.customer_detail',customer_id=sub.customer_id)})
 for req in DataDeletionRequest.query.filter(DataDeletionRequest.state.in_(['REQUESTED','IN_REVIEW'])).order_by(desc(DataDeletionRequest.requested_at)).limit(50):
  rows.append({'type':'SUPPORT','title':cname(req.customer_id),'detail':req.request_type+' · '+req.state,'created_at':req.requested_at,'url':url_for('admin.support')})
 rows.sort(key=lambda x: aware(x['created_at']) or utcnow(),reverse=True)
 return render_template('platform_admin_notifications.html',rows=rows)
