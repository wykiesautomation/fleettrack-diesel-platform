from sqlalchemy import inspect,text
SUB_COLS={'billing_term':"VARCHAR(20) DEFAULT 'MONTHLY' NOT NULL",'paid_from':'TIMESTAMP','paid_until':'TIMESTAMP','auto_renew':'BOOLEAN DEFAULT TRUE NOT NULL'}
PAY_COLS={'billing_term':"VARCHAR(20) DEFAULT 'MONTHLY' NOT NULL",'term_months':'INTEGER DEFAULT 1 NOT NULL'}
def ensure_payment_entitlement_schema(db):
    inspector=inspect(db.engine);tables=set(inspector.get_table_names())
    with db.engine.begin() as connection:
        if 'subscription' in tables:
            existing={c['name'] for c in inspector.get_columns('subscription')}
            for name,definition in SUB_COLS.items():
                if name not in existing:connection.execute(text(f'ALTER TABLE subscription ADD COLUMN {name} {definition}'))
        if 'payment_record' in tables:
            existing={c['name'] for c in inspector.get_columns('payment_record')}
            for name,definition in PAY_COLS.items():
                if name not in existing:connection.execute(text(f'ALTER TABLE payment_record ADD COLUMN {name} {definition}'))
