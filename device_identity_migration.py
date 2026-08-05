from sqlalchemy import inspect, text

DEVICE_IDENTITY_COLUMNS = {
    'expected_imei': 'VARCHAR(15)',
    'reported_imei': 'VARCHAR(15)',
    'imei_status': "VARCHAR(30) DEFAULT 'NOT_BOUND' NOT NULL",
    'device_state': "VARCHAR(30) DEFAULT 'WAITING' NOT NULL",
    'imei_bound_at': 'TIMESTAMP',
    'identity_checked_at': 'TIMESTAMP',
    'quarantine_reason': 'VARCHAR(240)',
    'last_ip': 'VARCHAR(80)',
}

def ensure_device_identity_schema(db):
    inspector = inspect(db.engine)
    if 'device' not in inspector.get_table_names():
        return
    existing = {column['name'] for column in inspector.get_columns('device')}
    with db.engine.begin() as connection:
        for name, ddl in DEVICE_IDENTITY_COLUMNS.items():
            if name not in existing:
                connection.execute(text(f'ALTER TABLE device ADD COLUMN {name} {ddl}'))
        connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ux_device_expected_imei ON device (expected_imei)'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS ix_device_reported_imei ON device (reported_imei)'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS ix_device_imei_status ON device (imei_status)'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS ix_device_device_state ON device (device_state)'))
