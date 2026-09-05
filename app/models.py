from datetime import datetime, timezone
from flask_login import UserMixin
from . import db

def now(): return datetime.now(timezone.utc)

class Customer(db.Model):
    id=db.Column(db.Integer, primary_key=True); name=db.Column(db.String(120),nullable=False)
    slug=db.Column(db.String(80),nullable=False,unique=True,index=True); active=db.Column(db.Boolean,default=True,nullable=False)
    created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)

class User(UserMixin,db.Model):
    id=db.Column(db.Integer,primary_key=True); customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True)
    email=db.Column(db.String(180),nullable=False,unique=True,index=True); name=db.Column(db.String(120),nullable=False)
    role=db.Column(db.String(30),default='customer_admin',nullable=False); password_hash=db.Column(db.String(255),nullable=False)
    active=db.Column(db.Boolean,default=True,nullable=False); created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)
    email_verified=db.Column(db.Boolean,default=False,nullable=False,index=True)
    email_verified_at=db.Column(db.DateTime(timezone=True))
    verification_nonce=db.Column(db.String(80),index=True)
    verification_sent_at=db.Column(db.DateTime(timezone=True))
    customer=db.relationship('Customer')
    @property
    def is_active(self): return self.active

class Site(db.Model):
    id=db.Column(db.Integer,primary_key=True); customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True)
    name=db.Column(db.String(120),nullable=False); location=db.Column(db.String(180)); timezone=db.Column(db.String(60),default='Africa/Johannesburg')
    customer=db.relationship('Customer')

class Asset(db.Model):
    id=db.Column(db.Integer,primary_key=True); customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True)
    site_id=db.Column(db.Integer,db.ForeignKey('site.id'),nullable=False,index=True); name=db.Column(db.String(120),nullable=False)
    asset_type=db.Column(db.String(40),nullable=False,index=True); status=db.Column(db.String(20),default='OFFLINE',nullable=False)
    capacity=db.Column(db.Float); capacity_unit=db.Column(db.String(16),default='L'); metadata_json=db.Column(db.JSON,default=dict)
    last_seen=db.Column(db.DateTime(timezone=True)); site=db.relationship('Site'); customer=db.relationship('Customer')

class Device(db.Model):
    id=db.Column(db.Integer,primary_key=True); customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True)
    asset_id=db.Column(db.Integer,db.ForeignKey('asset.id'),nullable=True,index=True); device_uid=db.Column(db.String(100),unique=True,nullable=False,index=True)
    device_type=db.Column(db.String(60),default='UNIVERSAL'); api_token=db.Column(db.String(100),unique=True,nullable=False,index=True)
    active=db.Column(db.Boolean,default=True); last_seen=db.Column(db.DateTime(timezone=True)); firmware=db.Column(db.String(40)); capabilities=db.Column(db.JSON,default=list)
    asset=db.relationship('Asset')
    @property
    def profile_code(self):
        for capability in (self.capabilities or []):
            if str(capability).startswith('PROFILE:'): return str(capability).split(':',1)[1]
        return {'ESP32_REMOTE_IO':'AT360_ESP32D_PILOT','SIM808_GPS_TRACKER':'AT360_SIM808_TRACKER_2AI_2DO','SIM808_SAMD21':'AT360_SIM808_TRACKER_2AI_2DO'}.get(self.device_type)
class MobileTrackerRegistration(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True)
    asset_id=db.Column(db.Integer,db.ForeignKey('asset.id'),nullable=False,index=True)
    code_hash=db.Column(db.String(64),nullable=False,unique=True,index=True)
    device_uid=db.Column(db.String(100),nullable=False,index=True)
    expires_at=db.Column(db.DateTime(timezone=True),nullable=False,index=True)
    used_at=db.Column(db.DateTime(timezone=True))
    created_by=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
    created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)
    onboarding_kind=db.Column(db.String(30),default='MOBILE',nullable=False,index=True)
    profile_code=db.Column(db.String(80),index=True)
    claimed_board_id=db.Column(db.String(100),index=True)
    provisioning_state=db.Column(db.String(30),default='WAITING',nullable=False,index=True)
    claimed_at=db.Column(db.DateTime(timezone=True))
    asset=db.relationship('Asset')

class SignalDefinition(db.Model):
    id=db.Column(db.Integer,primary_key=True); customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True)
    asset_id=db.Column(db.Integer,db.ForeignKey('asset.id'),nullable=False,index=True); key=db.Column(db.String(80),nullable=False)
    label=db.Column(db.String(100),nullable=False); signal_type=db.Column(db.String(40),nullable=False); source_type=db.Column(db.String(40),default='API')
    unit=db.Column(db.String(20),default=''); raw_min=db.Column(db.Float,default=4.0); raw_max=db.Column(db.Float,default=20.0)
    eng_min=db.Column(db.Float,default=0.0); eng_max=db.Column(db.Float,default=100.0); warning_low=db.Column(db.Float)
    warning_high=db.Column(db.Float); critical_low=db.Column(db.Float); critical_high=db.Column(db.Float)
    widget=db.Column(db.String(40),default='numeric'); enabled=db.Column(db.Boolean,default=True); config_json=db.Column(db.JSON,default=dict); calibration_mode=db.Column(db.String(30),default='LINEAR',nullable=False); offset=db.Column(db.Float,default=0.0,nullable=False); filter_alpha=db.Column(db.Float,default=1.0,nullable=False); deadband=db.Column(db.Float,default=0.0,nullable=False); calibrated_at=db.Column(db.DateTime(timezone=True)); calibrated_by=db.Column(db.Integer)
    asset=db.relationship('Asset'); __table_args__=(db.UniqueConstraint('asset_id','key',name='uq_asset_signal_key'),)

class Reading(db.Model):
    id=db.Column(db.BigInteger,primary_key=True); customer_id=db.Column(db.Integer,nullable=False,index=True)
    asset_id=db.Column(db.Integer,nullable=False,index=True); signal_id=db.Column(db.Integer,nullable=False,index=True)
    sampled_at=db.Column(db.DateTime(timezone=True),nullable=False,index=True); received_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)
    value=db.Column(db.Float,nullable=False); raw_value=db.Column(db.Float); unit=db.Column(db.String(20)); quality=db.Column(db.String(20),default='GOOD')
    sequence=db.Column(db.String(80)); __table_args__=(db.UniqueConstraint('signal_id','sequence',name='uq_signal_sequence'),)

class Alarm(db.Model):
    id=db.Column(db.Integer,primary_key=True); customer_id=db.Column(db.Integer,nullable=False,index=True); asset_id=db.Column(db.Integer,nullable=False,index=True)
    signal_id=db.Column(db.Integer,index=True); severity=db.Column(db.String(20),nullable=False); state=db.Column(db.String(20),default='OPEN',nullable=False)
    message=db.Column(db.String(240),nullable=False); value=db.Column(db.Float); opened_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)
    acknowledged_at=db.Column(db.DateTime(timezone=True)); acknowledged_by=db.Column(db.Integer); note=db.Column(db.Text)

class Location(db.Model):
    id=db.Column(db.BigInteger,primary_key=True); customer_id=db.Column(db.Integer,nullable=False,index=True); asset_id=db.Column(db.Integer,nullable=False,index=True)
    sampled_at=db.Column(db.DateTime(timezone=True),nullable=False,index=True); latitude=db.Column(db.Float,nullable=False); longitude=db.Column(db.Float,nullable=False)
    speed_kmh=db.Column(db.Float); accuracy_m=db.Column(db.Float); heading=db.Column(db.Float); sequence=db.Column(db.String(80))

class WorkspaceProfile(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,unique=True,index=True)
    contact_email=db.Column(db.String(180)); contact_phone=db.Column(db.String(50)); billing_email=db.Column(db.String(180)); address=db.Column(db.String(240))
    country=db.Column(db.String(80),default='South Africa'); terms_accepted_at=db.Column(db.DateTime(timezone=True)); updated_at=db.Column(db.DateTime(timezone=True),default=now,onupdate=now,nullable=False)

class SubscriptionPlan(db.Model):
    id=db.Column(db.Integer,primary_key=True); code=db.Column(db.String(40),nullable=False,unique=True,index=True); name=db.Column(db.String(80),nullable=False)
    monthly_price=db.Column(db.Float,nullable=False,default=0); currency=db.Column(db.String(8),default='ZAR',nullable=False); included_devices=db.Column(db.Integer,default=1,nullable=False)
    features=db.Column(db.JSON,default=list); active=db.Column(db.Boolean,default=True,nullable=False)

class Subscription(db.Model):
    id=db.Column(db.Integer,primary_key=True); customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,unique=True,index=True); plan_id=db.Column(db.Integer,db.ForeignKey('subscription_plan.id'),nullable=False,index=True)
    state=db.Column(db.String(30),default='TRIAL',nullable=False,index=True); trial_started_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False); trial_ends_at=db.Column(db.DateTime(timezone=True))
    current_period_start=db.Column(db.DateTime(timezone=True)); current_period_end=db.Column(db.DateTime(timezone=True)); next_payment_at=db.Column(db.DateTime(timezone=True)); grace_ends_at=db.Column(db.DateTime(timezone=True))
    billing_term=db.Column(db.String(20),default='MONTHLY',nullable=False,index=True); paid_from=db.Column(db.DateTime(timezone=True)); paid_until=db.Column(db.DateTime(timezone=True)); auto_renew=db.Column(db.Boolean,default=True,nullable=False)
    cancel_at_period_end=db.Column(db.Boolean,default=False,nullable=False); payfast_subscription_token=db.Column(db.String(180)); created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False); updated_at=db.Column(db.DateTime(timezone=True),default=now,onupdate=now,nullable=False)
    access_source=db.Column(db.String(30),default='PAYMENT_REQUIRED',nullable=False,index=True)
    customer=db.relationship('Customer'); plan=db.relationship('SubscriptionPlan')

class PaymentRecord(db.Model):
    id=db.Column(db.Integer,primary_key=True); customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True); subscription_id=db.Column(db.Integer,db.ForeignKey('subscription.id'),index=True)
    provider=db.Column(db.String(30),default='PAYFAST',nullable=False); provider_reference=db.Column(db.String(180),unique=True,index=True); merchant_payment_id=db.Column(db.String(100),unique=True,index=True)
    amount_gross=db.Column(db.Float,nullable=False,default=0); currency=db.Column(db.String(8),default='ZAR',nullable=False); status=db.Column(db.String(30),default='PENDING',nullable=False,index=True)
    payment_method=db.Column(db.String(40)); invoice_number=db.Column(db.String(60),unique=True,index=True); admin_note=db.Column(db.String(500)); billing_term=db.Column(db.String(20),default='MONTHLY',nullable=False); term_months=db.Column(db.Integer,default=1,nullable=False); raw_summary=db.Column(db.JSON,default=dict); paid_at=db.Column(db.DateTime(timezone=True)); created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)

class PayFastEvent(db.Model):
    id=db.Column(db.Integer,primary_key=True); provider_reference=db.Column(db.String(180),index=True); merchant_payment_id=db.Column(db.String(100),index=True)
    event_hash=db.Column(db.String(64),nullable=False,unique=True,index=True); source_ip=db.Column(db.String(64)); signature_valid=db.Column(db.Boolean,default=False,nullable=False); source_valid=db.Column(db.Boolean,default=False,nullable=False)
    amount_valid=db.Column(db.Boolean,default=False,nullable=False); server_valid=db.Column(db.Boolean,default=False,nullable=False); accepted=db.Column(db.Boolean,default=False,nullable=False)
    reason=db.Column(db.String(240)); payload_summary=db.Column(db.JSON,default=dict); created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)

class SubscriptionAuditEvent(db.Model):
    id=db.Column(db.Integer,primary_key=True); customer_id=db.Column(db.Integer,nullable=False,index=True); subscription_id=db.Column(db.Integer,index=True); previous_state=db.Column(db.String(30)); new_state=db.Column(db.String(30),nullable=False)
    reason=db.Column(db.String(240)); created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)

class ProductionGateEvent(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    gate_name=db.Column(db.String(80),nullable=False,index=True)
    status=db.Column(db.String(20),nullable=False)
    detail=db.Column(db.String(240))
    environment=db.Column(db.String(20),nullable=False,default='sandbox')
    created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)

class IntegrationConnector(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True)
    name=db.Column(db.String(120),nullable=False)
    connector_type=db.Column(db.String(40),nullable=False,index=True)
    transport_mode=db.Column(db.String(30),default='EDGE_OUTBOUND',nullable=False)
    status=db.Column(db.String(30),default='DRAFT',nullable=False,index=True)
    endpoint=db.Column(db.String(500))
    credential_ref=db.Column(db.String(160))
    edge_gateway_id=db.Column(db.String(100))
    read_only=db.Column(db.Boolean,default=True,nullable=False)
    enabled=db.Column(db.Boolean,default=False,nullable=False)
    poll_interval_seconds=db.Column(db.Integer,default=60,nullable=False)
    config_json=db.Column(db.JSON,default=dict)
    last_tested_at=db.Column(db.DateTime(timezone=True))
    last_success_at=db.Column(db.DateTime(timezone=True))
    last_error=db.Column(db.String(500))
    created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)
    updated_at=db.Column(db.DateTime(timezone=True),default=now,onupdate=now,nullable=False)
    customer=db.relationship('Customer')
    mappings=db.relationship('IntegrationSignalMapping',back_populates='connector',cascade='all, delete-orphan')
    __table_args__=(db.UniqueConstraint('customer_id','name',name='uq_customer_integration_name'),)

class IntegrationSignalMapping(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True)
    connector_id=db.Column(db.Integer,db.ForeignKey('integration_connector.id'),nullable=False,index=True)
    asset_id=db.Column(db.Integer,db.ForeignKey('asset.id'),nullable=False,index=True)
    signal_id=db.Column(db.Integer,db.ForeignKey('signal_definition.id'),nullable=False,index=True)
    source_point=db.Column(db.String(240),nullable=False)
    source_data_type=db.Column(db.String(40),default='FLOAT',nullable=False)
    source_unit=db.Column(db.String(30),default='')
    scale=db.Column(db.Float,default=1.0,nullable=False)
    offset=db.Column(db.Float,default=0.0,nullable=False)
    raw_min=db.Column(db.Float)
    raw_max=db.Column(db.Float)
    eng_min=db.Column(db.Float)
    eng_max=db.Column(db.Float)
    quality_mode=db.Column(db.String(40),default='PASSTHROUGH',nullable=False)
    enabled=db.Column(db.Boolean,default=True,nullable=False)
    last_value=db.Column(db.Float)
    last_quality=db.Column(db.String(20))
    last_sampled_at=db.Column(db.DateTime(timezone=True))
    last_error=db.Column(db.String(500))
    created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)
    updated_at=db.Column(db.DateTime(timezone=True),default=now,onupdate=now,nullable=False)
    connector=db.relationship('IntegrationConnector',back_populates='mappings')
    asset=db.relationship('Asset')
    signal=db.relationship('SignalDefinition')
    __table_args__=(db.UniqueConstraint('connector_id','source_point','signal_id',name='uq_connector_source_signal'),)

class IntegrationEvent(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    customer_id=db.Column(db.Integer,nullable=False,index=True)
    connector_id=db.Column(db.Integer,index=True)
    event_type=db.Column(db.String(50),nullable=False,index=True)
    status=db.Column(db.String(20),nullable=False)
    detail=db.Column(db.String(500))
    created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)

class ConnectorEndpointConfig(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    customer_id=db.Column(db.Integer,nullable=False,index=True)
    connector_id=db.Column(db.Integer,db.ForeignKey('integration_connector.id'),nullable=False,unique=True,index=True)
    auth_mode=db.Column(db.String(30),default='NONE',nullable=False)
    secret_env_ref=db.Column(db.String(120))
    secondary_secret_env_ref=db.Column(db.String(120))
    request_method=db.Column(db.String(10),default='GET',nullable=False)
    headers_json=db.Column(db.JSON,default=dict)
    query_json=db.Column(db.JSON,default=dict)
    timeout_seconds=db.Column(db.Integer,default=20,nullable=False)
    retry_limit=db.Column(db.Integer,default=3,nullable=False)
    backoff_seconds=db.Column(db.Integer,default=5,nullable=False)
    cursor_path=db.Column(db.String(200)); next_url_path=db.Column(db.String(200))
    source_ip_allowlist=db.Column(db.String(500))
    hmac_secret_env_ref=db.Column(db.String(120)); hmac_header=db.Column(db.String(80),default='X-AssetTrack-Signature')
    timestamp_header=db.Column(db.String(80),default='X-AssetTrack-Timestamp'); idempotency_header=db.Column(db.String(80),default='X-Idempotency-Key')
    updated_at=db.Column(db.DateTime(timezone=True),default=now,onupdate=now,nullable=False)
    connector=db.relationship('IntegrationConnector')

class UniversalSourceMapping(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    customer_id=db.Column(db.Integer,nullable=False,index=True)
    connector_id=db.Column(db.Integer,db.ForeignKey('integration_connector.id'),nullable=False,index=True)
    asset_id=db.Column(db.Integer,db.ForeignKey('asset.id'),nullable=False,index=True)
    signal_id=db.Column(db.Integer,db.ForeignKey('signal_definition.id'),nullable=False,index=True)
    source_path=db.Column(db.String(300),nullable=False)
    timestamp_path=db.Column(db.String(200)); quality_path=db.Column(db.String(200))
    data_type=db.Column(db.String(40),default='FLOAT',nullable=False)
    scale=db.Column(db.Float,default=1.0,nullable=False); offset=db.Column(db.Float,default=0.0,nullable=False)
    byte_order=db.Column(db.String(20),default='BIG'); word_order=db.Column(db.String(20),default='BIG')
    enabled=db.Column(db.Boolean,default=True,nullable=False)
    last_value=db.Column(db.Float); last_quality=db.Column(db.String(20)); last_success_at=db.Column(db.DateTime(timezone=True)); last_error=db.Column(db.String(500))
    asset=db.relationship('Asset'); signal=db.relationship('SignalDefinition'); connector=db.relationship('IntegrationConnector')
    __table_args__=(db.UniqueConstraint('connector_id','source_path','signal_id',name='uq_universal_source_signal'),)

class WebhookReceipt(db.Model):
    id=db.Column(db.BigInteger,primary_key=True)
    customer_id=db.Column(db.Integer,nullable=False,index=True); connector_id=db.Column(db.Integer,nullable=False,index=True)
    idempotency_key=db.Column(db.String(160),nullable=False); body_hash=db.Column(db.String(64),nullable=False)
    status=db.Column(db.String(30),nullable=False,index=True); mapped_points=db.Column(db.Integer,default=0,nullable=False)
    source_ip=db.Column(db.String(80)); detail=db.Column(db.String(500)); received_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False,index=True)
    __table_args__=(db.UniqueConstraint('connector_id','idempotency_key',name='uq_webhook_connector_idempotency'),)

class EdgeGateway(db.Model):
    id=db.Column(db.Integer,primary_key=True); customer_id=db.Column(db.Integer,nullable=False,index=True)
    gateway_uid=db.Column(db.String(100),nullable=False,unique=True,index=True); name=db.Column(db.String(120),nullable=False)
    api_token=db.Column(db.String(120),nullable=False,unique=True,index=True); active=db.Column(db.Boolean,default=True,nullable=False)
    version=db.Column(db.String(40)); last_heartbeat_at=db.Column(db.DateTime(timezone=True)); last_ip=db.Column(db.String(80)); capabilities=db.Column(db.JSON,default=list)
    created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)

class IntegrationJobEvent(db.Model):
    id=db.Column(db.BigInteger,primary_key=True); customer_id=db.Column(db.Integer,nullable=False,index=True); connector_id=db.Column(db.Integer,index=True)
    worker_type=db.Column(db.String(30),nullable=False); status=db.Column(db.String(30),nullable=False,index=True)
    attempt=db.Column(db.Integer,default=1,nullable=False); mapped_points=db.Column(db.Integer,default=0,nullable=False)
    duration_ms=db.Column(db.Integer); detail=db.Column(db.String(500)); created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False,index=True)

class MqttSubscription(db.Model):
 id=db.Column(db.Integer,primary_key=True);customer_id=db.Column(db.Integer,nullable=False,index=True);connector_id=db.Column(db.Integer,db.ForeignKey('integration_connector.id'),nullable=False,index=True);topic_filter=db.Column(db.String(300),nullable=False);qos=db.Column(db.Integer,default=1);enabled=db.Column(db.Boolean,default=True);created_at=db.Column(db.DateTime(timezone=True),default=now)
class MqttTopicMapping(db.Model):
 id=db.Column(db.Integer,primary_key=True);customer_id=db.Column(db.Integer,nullable=False,index=True);connector_id=db.Column(db.Integer,nullable=False,index=True);subscription_id=db.Column(db.Integer,db.ForeignKey('mqtt_subscription.id'),nullable=False,index=True);asset_id=db.Column(db.Integer,db.ForeignKey('asset.id'),nullable=False);signal_id=db.Column(db.Integer,db.ForeignKey('signal_definition.id'),nullable=False);json_path=db.Column(db.String(240),default='value');timestamp_path=db.Column(db.String(240));quality_path=db.Column(db.String(240));scale=db.Column(db.Float,default=1.0);offset=db.Column(db.Float,default=0.0);enabled=db.Column(db.Boolean,default=True);last_value=db.Column(db.Float);last_quality=db.Column(db.String(20));last_message_at=db.Column(db.DateTime(timezone=True));last_error=db.Column(db.String(500));subscription=db.relationship('MqttSubscription');asset=db.relationship('Asset');signal=db.relationship('SignalDefinition')
class MqttMessageEvent(db.Model):
 id=db.Column(db.BigInteger,primary_key=True);customer_id=db.Column(db.Integer,nullable=False,index=True);connector_id=db.Column(db.Integer,nullable=False,index=True);topic=db.Column(db.String(300),nullable=False);payload_size=db.Column(db.Integer,default=0);mapped_points=db.Column(db.Integer,default=0);status=db.Column(db.String(20));detail=db.Column(db.String(500));received_at=db.Column(db.DateTime(timezone=True),default=now)


class MobileConsent(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    customer_id=db.Column(db.Integer,nullable=False,index=True);asset_id=db.Column(db.Integer,nullable=False,index=True);device_id=db.Column(db.Integer,index=True)
    device_uid=db.Column(db.String(100),nullable=False,index=True);policy_version=db.Column(db.String(30),nullable=False,default='2026.1')
    active=db.Column(db.Boolean,default=True,nullable=False,index=True);accepted_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)
    withdrawn_at=db.Column(db.DateTime(timezone=True));last_tracking_started_at=db.Column(db.DateTime(timezone=True));last_tracking_stopped_at=db.Column(db.DateTime(timezone=True))
    user_agent_summary=db.Column(db.String(240));created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)



class Live360SafetyEvent(db.Model):
    __tablename__ = 'live360_safety_event'
    id = db.Column(db.BigInteger, primary_key=True)
    customer_id = db.Column(db.Integer, nullable=False, index=True)
    asset_id = db.Column(db.Integer, nullable=False, index=True)
    device_id = db.Column(db.Integer, nullable=False, index=True)
    event_type = db.Column(db.String(40), nullable=False, index=True)
    severity = db.Column(db.String(20), nullable=False, default='WARNING')
    confidence = db.Column(db.Float, nullable=False, default=0)
    status = db.Column(db.String(24), nullable=False, default='RECORDED', index=True)
    sampled_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    received_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False, index=True)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    accuracy_m = db.Column(db.Float)
    speed_before_kmh = db.Column(db.Float)
    speed_after_kmh = db.Column(db.Float)
    peak_acceleration_ms2 = db.Column(db.Float)
    deceleration_ms2 = db.Column(db.Float)
    sequence = db.Column(db.String(140), nullable=False, unique=True, index=True)
    detail_json = db.Column(db.JSON, default=dict)

class SecurityAuditEvent(db.Model):
    id=db.Column(db.BigInteger,primary_key=True);customer_id=db.Column(db.Integer,nullable=False,index=True);asset_id=db.Column(db.Integer,index=True);device_id=db.Column(db.Integer,index=True)
    event_type=db.Column(db.String(60),nullable=False,index=True);actor_type=db.Column(db.String(30),nullable=False,default='SYSTEM');actor_id=db.Column(db.Integer)
    safe_summary=db.Column(db.String(500));source_ip=db.Column(db.String(80));created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False,index=True)

class AssetAlertSettings(db.Model):
    id=db.Column(db.Integer,primary_key=True);customer_id=db.Column(db.Integer,nullable=False,index=True);asset_id=db.Column(db.Integer,nullable=False,unique=True,index=True)
    battery_warning=db.Column(db.Float,default=20,nullable=False);battery_critical=db.Column(db.Float,default=10,nullable=False);battery_recovered=db.Column(db.Float,default=25,nullable=False)
    offline_warning_minutes=db.Column(db.Integer,default=5,nullable=False);offline_critical_minutes=db.Column(db.Integer,default=15,nullable=False)
    gps_accuracy_limit_m=db.Column(db.Float,default=50,nullable=False);speed_warning_kmh=db.Column(db.Float,default=100,nullable=False);speed_critical_kmh=db.Column(db.Float,default=120,nullable=False);extended_stop_minutes=db.Column(db.Integer,default=30,nullable=False)
    battery_enabled=db.Column(db.Boolean,default=True,nullable=False);offline_enabled=db.Column(db.Boolean,default=True,nullable=False);gps_enabled=db.Column(db.Boolean,default=True,nullable=False);speed_enabled=db.Column(db.Boolean,default=True,nullable=False);extended_stop_enabled=db.Column(db.Boolean,default=True,nullable=False)
    updated_at=db.Column(db.DateTime(timezone=True),default=now,onupdate=now,nullable=False);updated_by=db.Column(db.Integer)

class CoreAlarmState(db.Model):
    id=db.Column(db.Integer,primary_key=True);customer_id=db.Column(db.Integer,nullable=False,index=True);asset_id=db.Column(db.Integer,nullable=False,index=True);condition_key=db.Column(db.String(80),nullable=False)
    alarm_id=db.Column(db.Integer,index=True);active=db.Column(db.Boolean,default=True,nullable=False,index=True);severity=db.Column(db.String(20),nullable=False);last_value=db.Column(db.Float)
    opened_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False);last_seen_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False);recovered_at=db.Column(db.DateTime(timezone=True))
    __table_args__=(db.UniqueConstraint('asset_id','condition_key',name='uq_asset_alarm_condition'),)

class DataDeletionRequest(db.Model):
    id=db.Column(db.Integer,primary_key=True);customer_id=db.Column(db.Integer,nullable=False,index=True);asset_id=db.Column(db.Integer,nullable=False,index=True);device_id=db.Column(db.Integer,index=True)
    request_type=db.Column(db.String(40),default='TRACKING_DATA',nullable=False);state=db.Column(db.String(30),default='REQUESTED',nullable=False,index=True);requested_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False);reviewed_at=db.Column(db.DateTime(timezone=True));reviewed_by=db.Column(db.Integer);note=db.Column(db.String(500))


class EmailNotificationLog(db.Model):
    __tablename__='email_notification_log'
    id=db.Column(db.BigInteger,primary_key=True)
    customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True)
    asset_id=db.Column(db.Integer,db.ForeignKey('asset.id'),index=True)
    alarm_id=db.Column(db.Integer,db.ForeignKey('alarm.id'),index=True)
    recipient=db.Column(db.String(180),nullable=False,index=True)
    subject=db.Column(db.String(240),nullable=False)
    severity=db.Column(db.String(20),default='INFO',nullable=False,index=True)
    state=db.Column(db.String(30),default='QUEUED',nullable=False,index=True)
    provider_message_id=db.Column(db.String(180))
    failure_reason=db.Column(db.String(500))
    created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False,index=True)
    sent_at=db.Column(db.DateTime(timezone=True))

class FleetFeatureDefaults(db.Model):
    id=db.Column(db.Integer,primary_key=True);customer_id=db.Column(db.Integer,nullable=False,unique=True,index=True)
    battery_enabled=db.Column(db.Boolean,default=True,nullable=False);offline_enabled=db.Column(db.Boolean,default=True,nullable=False);gps_enabled=db.Column(db.Boolean,default=True,nullable=False);speed_enabled=db.Column(db.Boolean,default=True,nullable=False);extended_stop_enabled=db.Column(db.Boolean,default=False,nullable=False);unexpected_movement_enabled=db.Column(db.Boolean,default=False,nullable=False)
    matched_routes_enabled=db.Column(db.Boolean,default=True,nullable=False);possible_addresses_enabled=db.Column(db.Boolean,default=True,nullable=False);email_notifications_enabled=db.Column(db.Boolean,default=False,nullable=False);push_notifications_enabled=db.Column(db.Boolean,default=False,nullable=False)
    updated_at=db.Column(db.DateTime(timezone=True),default=now,onupdate=now,nullable=False);updated_by=db.Column(db.Integer)

class AssetFeatureOverride(db.Model):
    id=db.Column(db.Integer,primary_key=True);customer_id=db.Column(db.Integer,nullable=False,index=True);asset_id=db.Column(db.Integer,nullable=False,unique=True,index=True);use_fleet_defaults=db.Column(db.Boolean,default=True,nullable=False)
    features_json=db.Column(db.JSON,default=dict,nullable=False);updated_at=db.Column(db.DateTime(timezone=True),default=now,onupdate=now,nullable=False);updated_by=db.Column(db.Integer)

class RegistrationAttempt(db.Model):
    id=db.Column(db.BigInteger,primary_key=True)
    email_hash=db.Column(db.String(64),nullable=False,index=True)
    ip_hash=db.Column(db.String(64),nullable=False,index=True)
    action=db.Column(db.String(30),nullable=False,index=True)
    accepted=db.Column(db.Boolean,default=False,nullable=False)
    created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False,index=True)

class AdvancedAccessGrant(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True)
    device_id=db.Column(db.Integer,db.ForeignKey('device.id'),index=True)
    active=db.Column(db.Boolean,default=True,nullable=False,index=True)
    source=db.Column(db.String(30),default='PAID',nullable=False,index=True)
    note=db.Column(db.String(300))
    expires_at=db.Column(db.DateTime(timezone=True),index=True)
    granted_by=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
    created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)
    updated_at=db.Column(db.DateTime(timezone=True),default=now,onupdate=now,nullable=False)
    customer=db.relationship('Customer');device=db.relationship('Device')
    __table_args__=(db.UniqueConstraint('customer_id','device_id',name='uq_advanced_access_customer_device'),)

class DeviceTrendPolicy(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True)
    device_id=db.Column(db.Integer,db.ForeignKey('device.id'),nullable=False,unique=True,index=True)
    trend_enabled=db.Column(db.Boolean,default=False,nullable=False,index=True)
    retention_days=db.Column(db.Integer,default=93,nullable=False)
    gps_history_enabled=db.Column(db.Boolean,default=False,nullable=False,index=True)
    gps_retention_days=db.Column(db.Integer,default=31,nullable=False)
    updated_at=db.Column(db.DateTime(timezone=True),default=now,onupdate=now,nullable=False)
    updated_by=db.Column(db.Integer,db.ForeignKey('user.id'))
    device=db.relationship('Device')

class SignalTrendPolicy(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True)
    device_id=db.Column(db.Integer,db.ForeignKey('device.id'),nullable=False,index=True)
    signal_id=db.Column(db.Integer,db.ForeignKey('signal_definition.id'),nullable=False,index=True)
    enabled=db.Column(db.Boolean,default=False,nullable=False,index=True)
    updated_at=db.Column(db.DateTime(timezone=True),default=now,onupdate=now,nullable=False)
    device=db.relationship('Device');signal=db.relationship('SignalDefinition')
    __table_args__=(db.UniqueConstraint('device_id','signal_id',name='uq_device_signal_trend'),)

class TrendCleanupState(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    job_name=db.Column(db.String(80),nullable=False,unique=True,index=True)
    last_started_at=db.Column(db.DateTime(timezone=True))
    last_completed_at=db.Column(db.DateTime(timezone=True))
    last_deleted_readings=db.Column(db.Integer,default=0,nullable=False)
    last_deleted_locations=db.Column(db.Integer,default=0,nullable=False)
    last_error=db.Column(db.String(500))

class DeviceCommand(db.Model):
 id=db.Column(db.BigInteger,primary_key=True);customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True);asset_id=db.Column(db.Integer,db.ForeignKey('asset.id'),nullable=False,index=True);device_id=db.Column(db.Integer,db.ForeignKey('device.id'),nullable=False,index=True);channel=db.Column(db.String(30),default='DO1',nullable=False);action=db.Column(db.String(30),nullable=False,index=True);state=db.Column(db.String(30),default='PENDING',nullable=False,index=True);simulation_only=db.Column(db.Boolean,default=True,nullable=False);requested_by=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False);request_token=db.Column(db.String(64),nullable=False,unique=True,index=True);created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False,index=True);expires_at=db.Column(db.DateTime(timezone=True),nullable=False,index=True);delivered_at=db.Column(db.DateTime(timezone=True));acknowledged_at=db.Column(db.DateTime(timezone=True));completed_at=db.Column(db.DateTime(timezone=True));feedback_value=db.Column(db.Float);failure_reason=db.Column(db.String(240));device=db.relationship('Device');asset=db.relationship('Asset')


class HardwareDeviceRegistration(db.Model):
    __tablename__='hardware_device_registration'
    id=db.Column(db.Integer,primary_key=True)
    customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True)
    profile_code=db.Column(db.String(80),nullable=False,index=True)
    code_hash=db.Column(db.String(64),nullable=False,unique=True,index=True)
    expires_at=db.Column(db.DateTime(timezone=True),nullable=False,index=True)
    provisioning_state=db.Column(db.String(30),default='WAITING',nullable=False,index=True)
    claimed_device_id=db.Column(db.Integer,db.ForeignKey('device.id'),index=True)
    claimed_board_id=db.Column(db.String(100),index=True)
    claimed_at=db.Column(db.DateTime(timezone=True))
    created_by=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
    created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)
    device=db.relationship('Device')

class DeviceChannelAssignment(db.Model):
    __tablename__='device_channel_assignment'
    id=db.Column(db.Integer,primary_key=True)
    customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True)
    device_id=db.Column(db.Integer,db.ForeignKey('device.id'),nullable=False,index=True)
    channel_key=db.Column(db.String(80),nullable=False)
    direction=db.Column(db.String(20),nullable=False)
    asset_id=db.Column(db.Integer,db.ForeignKey('asset.id'),index=True)
    signal_id=db.Column(db.Integer,db.ForeignKey('signal_definition.id'),index=True)
    purpose=db.Column(db.String(50),default='UNUSED',nullable=False,index=True)
    customer_label=db.Column(db.String(100))
    enabled=db.Column(db.Boolean,default=False,nullable=False,index=True)
    config_json=db.Column(db.JSON,default=dict,nullable=False)
    created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)
    updated_at=db.Column(db.DateTime(timezone=True),default=now,onupdate=now,nullable=False)
    device=db.relationship('Device');asset=db.relationship('Asset');signal=db.relationship('SignalDefinition')
    __table_args__=(db.UniqueConstraint('device_id','channel_key',name='uq_device_channel_assignment'),)
