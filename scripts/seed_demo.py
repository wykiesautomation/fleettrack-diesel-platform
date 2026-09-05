import os,sys,secrets
from datetime import datetime,timezone,timedelta
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from app import create_app,db
from app.models import *
from werkzeug.security import generate_password_hash
app=create_app()
with app.app_context():
    if Customer.query.filter_by(slug='demo-industries').first(): print('Demo already exists');raise SystemExit
    c=Customer(name='Demo Industries',slug='demo-industries');db.session.add(c);db.session.flush()
    db.session.add(User(customer_id=c.id,email='demo@assettrack360.local',name='Demo Administrator',role='customer_admin',password_hash=generate_password_hash('DemoPassword123!')))
    s=Site(customer_id=c.id,name='Vaal Operations',location='Gauteng');db.session.add(s);db.session.flush()
    specs=[('Diesel Tank 01','TANK',10000),('Mobile Bowser 07','TRACKER',5000),('Cooling Pump P-101','VIBRATION',None),('Universal 4-20 mA Panel','GENERIC',None)]
    for ix,(name,typ,cap) in enumerate(specs):
        a=Asset(customer_id=c.id,site_id=s.id,name=name,asset_type=typ,capacity=cap,last_seen=datetime.now(timezone.utc));db.session.add(a);db.session.flush()
        from app.routes import create_default_signals
        create_default_signals(a);db.session.flush()
        d=Device(customer_id=c.id,asset_id=a.id,device_uid=f'PP-DEMO-{ix+1:04}',device_type='SIMULATOR',api_token=secrets.token_urlsafe(24),active=True,last_seen=datetime.now(timezone.utc),firmware='sim-1.0');db.session.add(d)
        for sig in SignalDefinition.query.filter_by(asset_id=a.id):
            for j in range(24):
                base={'level_percent':67,'volume_l':6700,'battery_v':3.91,'solar_v':6.7,'speed_kmh':0,'vibration_rms':3.2,'temperature_c':48,'analog_1':12.0}.get(sig.key,1)
                val=base+(j%6-3)*(.35 if base>10 else .04)
                db.session.add(Reading(customer_id=c.id,asset_id=a.id,signal_id=sig.id,sampled_at=datetime.now(timezone.utc)-timedelta(hours=23-j),value=val,raw_value=val,unit=sig.unit,quality='GOOD',sequence=f'seed-{j}-{sig.key}'))
        if typ in ('TANK','TRACKER'):db.session.add(Location(customer_id=c.id,asset_id=a.id,sampled_at=datetime.now(timezone.utc),latitude=-26.699,longitude=27.835,speed_kmh=0,accuracy_m=7,sequence='seed-location'))
    db.session.commit();print('Demo login: demo@assettrack360.local / DemoPassword123!')
