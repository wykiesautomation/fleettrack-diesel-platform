import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

from flask import Flask, jsonify, request, send_from_directory
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash


db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "main.login"

@contextmanager
def schema_startup_lock(app):
    """Allow only one process to initialise or migrate the schema."""
    database_url=app.config["SQLALCHEMY_DATABASE_URI"]
    if database_url.startswith("sqlite"):
        import fcntl
        os.makedirs(app.instance_path,exist_ok=True)
        path=os.path.join(app.instance_path,"assettrack360-schema.lock")
        with open(path,"w",encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
    else:
        with db.engine.connect() as connection:
            connection.execute(text("SELECT pg_advisory_lock(:key)"),{"key":3602026})
            try:
                yield
            finally:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"),{"key":3602026})
                connection.commit()

def initialise_schema_safely(app):
    with schema_startup_lock(app):
        for attempt in range(3):
            try:
                db.create_all()
                from .payment_entitlement_migration import ensure_payment_entitlement_schema
                ensure_payment_entitlement_schema(db)
                ensure_email_verification_schema(app)
                db.create_all()
                return
            except OperationalError as error:
                db.session.rollback()
                if "already exists" in str(error).lower():
                    return
                if attempt==2:
                    raise
                time.sleep(attempt+1)


def ensure_email_verification_schema(app):
    """Add verification fields safely for existing production databases."""
    inspector=db.inspect(db.engine)
    columns={column["name"] for column in inspector.get_columns("user")}
    statements=[]
    dialect=db.engine.dialect.name
    boolean_type="BOOLEAN" if dialect=="postgresql" else "BOOLEAN"
    if "email_verified" not in columns:
        statements.append(f'ALTER TABLE "user" ADD COLUMN email_verified {boolean_type} NOT NULL DEFAULT TRUE')
    if "email_verified_at" not in columns:
        statements.append('ALTER TABLE "user" ADD COLUMN email_verified_at TIMESTAMP')
    if "verification_nonce" not in columns:
        statements.append('ALTER TABLE "user" ADD COLUMN verification_nonce VARCHAR(80)')
    if "verification_sent_at" not in columns:
        statements.append('ALTER TABLE "user" ADD COLUMN verification_sent_at TIMESTAMP')
    with db.engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        connection.execute(text('UPDATE "user" SET email_verified = TRUE WHERE email_verified IS NULL'))
    sub_columns={column['name'] for column in inspector.get_columns('subscription')}
    if 'access_source' not in sub_columns:
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE subscription ADD COLUMN access_source VARCHAR(30) NOT NULL DEFAULT 'PAYMENT_REQUIRED'"))
            connection.execute(text("UPDATE subscription SET access_source = CASE WHEN state = 'ACTIVE' THEN 'PAID' ELSE 'PAYMENT_REQUIRED' END"))

def create_app(test_config=None):
    app = Flask(__name__)

    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        if os.getenv("RENDER", "").lower() == "true":
            raise RuntimeError("DATABASE_URL is required on Render; refusing production SQLite fallback")
        db_url = "sqlite:///assettrack360.db"
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    engine_options = {}
    if db_url.startswith("postgresql+psycopg://"):
        engine_options = {
            "pool_pre_ping": True,
            "pool_recycle": 300,
            "pool_timeout": 30,
            "pool_size": 5,
            "max_overflow": 5,
        }

    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-only-change-me"),
        SQLALCHEMY_DATABASE_URI=db_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS=engine_options,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        MAX_CONTENT_LENGTH=1024 * 1024,
        SERVER_NAME=os.getenv("SERVER_NAME") or None,
        PREFERRED_URL_SCHEME="https",
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager.init_app(app)

    @app.errorhandler(OperationalError)
    def handle_database_disconnect(error):
        db.session.rollback()
        app.logger.warning(
            "Temporary database connection failure: %s",
            type(error).__name__,
        )
        if request.path.startswith("/api/"):
            return jsonify(
                error="database_temporarily_unavailable",
                retry_after_seconds=5,
            ), 503
        return (
            "Database connection is recovering. Please wait five seconds and refresh.",
            503,
            {
                "Retry-After": "5",
                "Content-Type": "text/plain; charset=utf-8",
            },
        )

    from .models import Customer, Subscription, SubscriptionPlan, User, WorkspaceProfile

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from .routes import bp

    app.register_blueprint(bp)
    from .edge_gateway_registry import edge_bp
    app.register_blueprint(edge_bp)
    from .admin import admin_bp
    app.register_blueprint(admin_bp)

    with app.app_context():
        from . import edge_models  # Registers REV20A tables before create_all.
        initialise_schema_safely(app)

        email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
        password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
        if email and password and not User.query.filter_by(email=email).first():
            customer = Customer(
                name="AssetTrack 360 Administration",
                slug="platform-admin",
                active=True,
            )
            db.session.add(customer)
            db.session.flush()
            db.session.add(
                User(
                    customer_id=customer.id,
                    email=email,
                    name="Platform Administrator",
                    role="platform_admin",
                    password_hash=generate_password_hash(password),
                    active=True,
                    email_verified=True,
                    email_verified_at=datetime.now(timezone.utc),
                )
            )
            db.session.commit()

        plan_specs = [
            ("essential", "Essential", 299.0, 1, ["Email alarms", "90-day history"]),
            ("monitor", "Monitor", 599.0, 1, ["Tracking or tank dashboard", "One-year history"]),
            ("business", "Business", 999.0, 3, ["Multi-site", "Universal signals"]),
            ("industrial", "Industrial", 0.0, 5, ["PLC/OPC gateway", "Managed onboarding"]),
        ]
        for code, name, price, devices, features in plan_specs:
            if not SubscriptionPlan.query.filter_by(code=code).first():
                db.session.add(
                    SubscriptionPlan(
                        code=code,
                        name=name,
                        monthly_price=price,
                        included_devices=devices,
                        features=features,
                    )
                )
        db.session.commit()

        for customer in Customer.query.filter_by(active=True).all():
            if customer.slug == 'platform-admin':
                continue
            if not WorkspaceProfile.query.filter_by(customer_id=customer.id).first():
                db.session.add(WorkspaceProfile(customer_id=customer.id))
            if not Subscription.query.filter_by(customer_id=customer.id).first():
                plan = SubscriptionPlan.query.filter_by(code="monitor").first()
                started = datetime.now(timezone.utc)
                db.session.add(
                    Subscription(
                        customer_id=customer.id,
                        plan_id=plan.id,
                        state="PAYMENT_REQUIRED",
                        access_source="PAYMENT_REQUIRED",
                        trial_started_at=started,
                        trial_ends_at=None,
                    )
                )
        db.session.commit()

    @app.get("/BingSiteAuth.xml")
    def bing_site_auth():
        repository_root = os.path.dirname(app.root_path)
        return send_from_directory(
            repository_root,
            "BingSiteAuth.xml",
            mimetype="application/xml",
        )

    return app

# WSGI entry point used by Render: gunicorn app:app
app = create_app()
