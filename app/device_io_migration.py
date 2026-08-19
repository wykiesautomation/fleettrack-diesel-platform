from sqlalchemy import text

def ensure_device_io_schema(db):
    dialect=db.engine.dialect.name
    with db.engine.begin() as c:
        if dialect=='postgresql':
            c.execute(text("ALTER TABLE device ALTER COLUMN asset_id DROP NOT NULL"))
        # SQLite cannot alter nullability in place; fresh/dev DBs use updated model.
        # Production SQLite users must use the documented rebuild procedure.
