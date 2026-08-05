from sqlalchemy import inspect,text
COLS={'expected_imei':'VARCHAR(15)','reported_imei':'VARCHAR(15)', 'imei_status':"VARCHAR(30) DEFAULT 'NOT_BOUND' NOT NULL",'device_state':"VARCHAR(30) DEFAULT 'WAITING' NOT NULL",'imei_bound_at':'TIMESTAMP','identity_checked_at':'TIMESTAMP','quarantine_reason':'VARCHAR(240)','last_ip':'VARCHAR(80)'}
def ensure_device_identity_schema(db):
 i=inspect(db.engine)
 if 'device' not in i.get_table_names():return
 have={x['name'] for x in i.get_columns('device')}
 with db.engine.begin() as c:
  for n,t in COLS.items():
   if n not in have:c.execute(text(f'ALTER TABLE device ADD COLUMN {n} {t}'))
  c.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ux_device_expected_imei ON device (expected_imei)'))
