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
    asset_id=db.Column(db.Integer,db.ForeignKey('asset.id'),nullable=False,index=True); device_uid=db.Column(db.String(100),unique=True,nullable=False,index=True)
    device_type=db.Column(db.String(60),default='UNIVERSAL'); api_token=db.Column(db.String(100),unique=True,nullable=False,index=True)
    active=db.Column(db.Boolean,default=True); last_seen=db.Column(db.DateTime(timezone=True)); firmware=db.Column(db.String(40)); capabilities=db.Column(db.JSON,default=list)
    asset=db.relationship('Asset')

class SignalDefinition(db.Model):
    id=db.Column(db.Integer,primary_key=True); customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True)
    asset_id=db.Column(db.Integer,db.ForeignKey('asset.id'),nullable=False,index=True); key=db.Column(db.String(80),nullable=False)
    label=db.Column(db.String(100),nullable=False); signal_type=db.Column(db.String(40),nullable=False); source_type=db.Column(db.String(40),default='API')
    unit=db.Column(db.String(20),default=''); raw_min=db.Column(db.Float,default=4.0); raw_max=db.Column(db.Float,default=20.0)
    eng_min=db.Column(db.Float,default=0.0); eng_max=db.Column(db.Float,default=100.0); warning_low=db.Column(db.Float)
    warning_high=db.Column(db.Float); critical_low=db.Column(db.Float); critical_high=db.Column(db.Float)
    widget=db.Column(db.String(40),default='numeric'); enabled=db.Column(db.Boolean,default=True); config_json=db.Column(db.JSON,default=dict)
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
    cancel_at_period_end=db.Column(db.Boolean,default=False,nullable=False); payfast_subscription_token=db.Column(db.String(180)); created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False); updated_at=db.Column(db.DateTime(timezone=True),default=now,onupdate=now,nullable=False)
    customer=db.relationship('Customer'); plan=db.relationship('SubscriptionPlan')

class PaymentRecord(db.Model):
    id=db.Column(db.Integer,primary_key=True); customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True); subscription_id=db.Column(db.Integer,db.ForeignKey('subscription.id'),index=True)
    provider=db.Column(db.String(30),default='PAYFAST',nullable=False); provider_reference=db.Column(db.String(180),unique=True,index=True); merchant_payment_id=db.Column(db.String(100),unique=True,index=True)
    amount_gross=db.Column(db.Float,nullable=False,default=0); currency=db.Column(db.String(8),default='ZAR',nullable=False); status=db.Column(db.String(30),default='PENDING',nullable=False,index=True)
    payment_method=db.Column(db.String(40)); raw_summary=db.Column(db.JSON,default=dict); paid_at=db.Column(db.DateTime(timezone=True)); created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)

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
