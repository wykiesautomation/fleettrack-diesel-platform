from datetime import datetime, timezone
from . import db

def now(): return datetime.now(timezone.utc)

class EdgeGatewayRegistration(db.Model):
    __tablename__='edge_gateway_registration'
    id=db.Column(db.Integer,primary_key=True)
    customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True)
    site_id=db.Column(db.Integer,db.ForeignKey('site.id'),index=True)
    gateway_uid=db.Column(db.String(100),nullable=False,unique=True,index=True)
    name=db.Column(db.String(120),nullable=False)
    token_hash=db.Column(db.String(64),nullable=False,index=True)
    token_last4=db.Column(db.String(4),nullable=False)
    active=db.Column(db.Boolean,default=True,nullable=False)
    status=db.Column(db.String(30),default='PROVISIONED',nullable=False,index=True)
    version=db.Column(db.String(40)); capabilities=db.Column(db.JSON,default=list)
    queue_depth=db.Column(db.Integer,default=0,nullable=False)
    last_heartbeat_at=db.Column(db.DateTime(timezone=True)); last_upload_at=db.Column(db.DateTime(timezone=True))
    last_ip=db.Column(db.String(80)); last_error=db.Column(db.String(500))
    created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)
    updated_at=db.Column(db.DateTime(timezone=True),default=now,onupdate=now,nullable=False)
    customer=db.relationship('Customer');site=db.relationship('Site')

class EdgeGatewayAudit(db.Model):
    __tablename__='edge_gateway_audit'
    id=db.Column(db.BigInteger,primary_key=True)
    customer_id=db.Column(db.Integer,nullable=False,index=True)
    gateway_id=db.Column(db.Integer,nullable=False,index=True)
    event_type=db.Column(db.String(50),nullable=False,index=True)
    status=db.Column(db.String(20),nullable=False)
    detail=db.Column(db.String(500)); source_ip=db.Column(db.String(80))
    created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False,index=True)

class EdgeGatewayReceipt(db.Model):
    __tablename__='edge_gateway_receipt'
    id=db.Column(db.BigInteger,primary_key=True)
    customer_id=db.Column(db.Integer,nullable=False,index=True)
    gateway_id=db.Column(db.Integer,nullable=False,index=True)
    connector_key=db.Column(db.String(120),nullable=False,index=True)
    point_count=db.Column(db.Integer,default=0,nullable=False)
    mapped_count=db.Column(db.Integer,default=0,nullable=False)
    status=db.Column(db.String(30),nullable=False,index=True)
    body_hash=db.Column(db.String(64),nullable=False,index=True)
    detail=db.Column(db.String(500))
    received_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False,index=True)
