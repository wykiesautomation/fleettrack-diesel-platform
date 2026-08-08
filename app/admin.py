from functools import wraps
from datetime import datetime, timezone, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import desc, or_

from . import db
from .models import (
    Alarm,
    Asset,
    Customer,
    Device,
    PaymentRecord,
    SecurityAuditEvent,
    Site,
    Subscription,
    SubscriptionAuditEvent,
    User,
)

admin_bp = Blueprint('admin', __name__, url_prefix='/platform-admin')


def utcnow():
    return datetime.now(timezone.utc)


def platform_admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != 'platform_admin':
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def record_admin_action(event_type, customer_id=None, safe_summary=None):
    db.session.add(SecurityAuditEvent(
        customer_id=customer_id or current_user.customer_id,
        event_type=event_type,
        actor_type='PLATFORM_ADMIN',
        actor_id=current_user.id,
        safe_summary=(safe_summary or '')[:500],
        source_ip=(request.headers.get('CF-Connecting-IP') or request.remote_addr or '')[:80],
    ))


@admin_bp.get('/')
@platform_admin_required
def dashboard():
    query = request.args.get('q', '').strip()
    state = request.args.get('state', '').strip().upper()

    customers_query = Customer.query.filter(Customer.slug != 'platform-admin')
    if query:
        pattern = f'%{query}%'
        customer_ids = db.session.query(User.customer_id).filter(User.email.ilike(pattern))
        customers_query = customers_query.filter(
            or_(Customer.name.ilike(pattern), Customer.slug.ilike(pattern), Customer.id.in_(customer_ids))
        )

    customers = customers_query.order_by(desc(Customer.created_at)).all()
    rows = []
    now = utcnow()
    for customer in customers:
        subscription = Subscription.query.filter_by(customer_id=customer.id).first()
        if state and (not subscription or subscription.state != state):
            continue
        users = User.query.filter_by(customer_id=customer.id).order_by(User.created_at).all()
        devices = Device.query.filter_by(customer_id=customer.id).all()
        assets = Asset.query.filter_by(customer_id=customer.id).count()
        online = sum(
            1 for device in devices
            if device.active and device.last_seen and now - _aware(device.last_seen) <= timedelta(minutes=30)
        )
        rows.append({
            'customer': customer,
            'subscription': subscription,
            'users': users,
            'assets': assets,
            'devices': len(devices),
            'online': online,
        })

    totals = {
        'customers': Customer.query.filter(Customer.slug != 'platform-admin').count(),
        'active_customers': Customer.query.filter(Customer.slug != 'platform-admin', Customer.active.is_(True)).count(),
        'users': User.query.join(Customer, User.customer_id == Customer.id).filter(Customer.slug != 'platform-admin').count(),
        'devices': Device.query.join(Customer, Device.customer_id == Customer.id).filter(Customer.slug != 'platform-admin').count(),
        'online_devices': Device.query.join(Customer, Device.customer_id == Customer.id).filter(
            Customer.slug != 'platform-admin', Device.active.is_(True), Device.last_seen >= now - timedelta(minutes=30)
        ).count(),
        'pending_verification': User.query.join(Customer, User.customer_id == Customer.id).filter(
            Customer.slug != 'platform-admin', User.email_verified.is_(False)
        ).count(),
    }
    return render_template('platform_admin.html', rows=rows, totals=totals, query=query, state=state, now=now)


@admin_bp.get('/customers/<int:customer_id>')
@platform_admin_required
def customer_detail(customer_id):
    customer = Customer.query.filter(Customer.id == customer_id, Customer.slug != 'platform-admin').first_or_404()
    users = User.query.filter_by(customer_id=customer.id).order_by(User.name).all()
    sites = Site.query.filter_by(customer_id=customer.id).order_by(Site.name).all()
    assets = Asset.query.filter_by(customer_id=customer.id).order_by(Asset.name).all()
    devices = Device.query.filter_by(customer_id=customer.id).order_by(Device.device_uid).all()
    subscription = Subscription.query.filter_by(customer_id=customer.id).first()
    payments = PaymentRecord.query.filter_by(customer_id=customer.id).order_by(desc(PaymentRecord.created_at)).limit(20).all()
    alarms = Alarm.query.filter_by(customer_id=customer.id).order_by(desc(Alarm.opened_at)).limit(20).all()
    return render_template(
        'platform_admin_customer.html', customer=customer, users=users, sites=sites,
        assets=assets, devices=devices, subscription=subscription, payments=payments, alarms=alarms,
        now=utcnow(),
    )


@admin_bp.post('/customers/<int:customer_id>/toggle')
@platform_admin_required
def toggle_customer(customer_id):
    customer = Customer.query.filter(Customer.id == customer_id, Customer.slug != 'platform-admin').first_or_404()
    customer.active = not customer.active
    for user in User.query.filter_by(customer_id=customer.id).all():
        user.active = customer.active
    record_admin_action(
        'PLATFORM_CUSTOMER_REACTIVATED' if customer.active else 'PLATFORM_CUSTOMER_SUSPENDED',
        customer.id,
        f'{customer.name} was {"reactivated" if customer.active else "suspended"} by the platform owner.',
    )
    db.session.commit()
    flash(f'{customer.name} {"reactivated" if customer.active else "suspended"}.', 'ok')
    return redirect(request.referrer or url_for('admin.dashboard'))


@admin_bp.post('/users/<int:user_id>/toggle')
@platform_admin_required
def toggle_user(user_id):
    user = User.query.join(Customer, User.customer_id == Customer.id).filter(
        User.id == user_id, Customer.slug != 'platform-admin'
    ).first_or_404()
    user.active = not user.active
    record_admin_action(
        'PLATFORM_USER_ENABLED' if user.active else 'PLATFORM_USER_DISABLED',
        user.customer_id,
        f'User {user.email} was {"enabled" if user.active else "disabled"}.',
    )
    db.session.commit()
    flash(f'{user.email} {"enabled" if user.active else "disabled"}.', 'ok')
    return redirect(request.referrer or url_for('admin.customer_detail', customer_id=user.customer_id))


@admin_bp.post('/users/<int:user_id>/verify')
@platform_admin_required
def verify_user(user_id):
    user = User.query.join(Customer, User.customer_id == Customer.id).filter(
        User.id == user_id, Customer.slug != 'platform-admin'
    ).first_or_404()
    user.email_verified = True
    user.email_verified_at = utcnow()
    user.verification_nonce = None
    user.customer.active = True
    record_admin_action('PLATFORM_EMAIL_VERIFIED', user.customer_id, f'{user.email} was manually verified by the platform owner.')
    db.session.commit()
    flash(f'{user.email} verified and customer account activated.', 'ok')
    return redirect(request.referrer or url_for('admin.customer_detail', customer_id=user.customer_id))


@admin_bp.post('/customers/<int:customer_id>/subscription')
@platform_admin_required
def update_subscription(customer_id):
    customer = Customer.query.filter(Customer.id == customer_id, Customer.slug != 'platform-admin').first_or_404()
    subscription = Subscription.query.filter_by(customer_id=customer.id).first_or_404()
    new_state = request.form.get('state', '').strip().upper()
    allowed = {'TRIAL', 'ACTIVE', 'GRACE_PERIOD', 'SUSPENDED', 'CANCELLED'}
    if new_state not in allowed:
        abort(400)
    old_state = subscription.state
    subscription.state = new_state
    db.session.add(SubscriptionAuditEvent(
        customer_id=customer.id,
        subscription_id=subscription.id,
        previous_state=old_state,
        new_state=new_state,
        reason='Platform owner administrative update',
    ))
    record_admin_action('PLATFORM_SUBSCRIPTION_CHANGED', customer.id, f'Subscription changed from {old_state} to {new_state}.')
    db.session.commit()
    flash(f'{customer.name} subscription changed to {new_state}.', 'ok')
    return redirect(request.referrer or url_for('admin.customer_detail', customer_id=customer.id))


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
