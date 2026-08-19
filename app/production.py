import os
from datetime import datetime, timezone
from sqlalchemy import text
from . import db
from .payfast import config as payfast_config

TRUE={'1','true','yes','on'}
def flag(name,default='false'): return os.getenv(name,default).strip().lower() in TRUE

def checks(app):
    pf=payfast_config(); live=pf['mode']=='live'; secret=os.getenv('SECRET_KEY','')
    items=[]
    def add(code,ok,detail,required=True): items.append({'code':code,'ok':bool(ok),'detail':detail,'required':required})
    try:
        db.session.execute(text('SELECT 1'));add('database',True,'Database query succeeded')
    except Exception as exc:add('database',False,f'Database unavailable: {type(exc).__name__}')
    add('secret_key',len(secret)>=32 and secret!='dev-only-change-me','SECRET_KEY must be unique and at least 32 characters')
    add('https_base_url',pf['base_url'].startswith('https://'),'APP_BASE_URL must use HTTPS')
    add('cookie_secure',bool(app.config.get('SESSION_COOKIE_SECURE')),'COOKIE_SECURE must be true in production',required=live)
    add('payfast_credentials',all([pf['merchant_id'],pf['merchant_key'],pf['passphrase']]),'PayFast merchant ID, key and passphrase must be configured')
    add('payfast_ip_validation',pf['validate_ip'],'PAYFAST_VALIDATE_IP must be true for live mode',required=live)
    add('production_approval',flag('PRODUCTION_GATE_APPROVED'),'PRODUCTION_GATE_APPROVED must be true for live mode',required=live)
    add('database_postgres',str(app.config.get('SQLALCHEMY_DATABASE_URI','')).startswith('postgresql'),'Production data should use PostgreSQL',required=live)
    add('backup_proof',flag('BACKUP_RESTORE_VERIFIED'),'Set only after a dated backup/restore drill passes',required=live)
    add('sandbox_regression',flag('PAYFAST_SANDBOX_VERIFIED'),'Set only after all sandbox payment gates pass',required=live)
    required_ok=all(x['ok'] for x in items if x['required'])
    live_allowed=(not live) or required_ok
    return {'service':'assettrack360-rev18','time':datetime.now(timezone.utc).isoformat(),'mode':pf['mode'],'ready':required_ok,'live_allowed':live_allowed,'checks':items}

def checkout_allowed(app):
    report=checks(app)
    return report['live_allowed'],report
