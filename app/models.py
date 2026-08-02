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
