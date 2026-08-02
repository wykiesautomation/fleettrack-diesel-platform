import os
from datetime import datetime, timezone
from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "main.login"


def create_app(test_config=None):
    app = Flask(__name__)
    db_url = os.getenv("DATABASE_URL", "sqlite:///assettrack360.db")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-only-change-me"),
        SQLALCHEMY_DATABASE_URI=db_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower()=="true",
        MAX_CONTENT_LENGTH=1024*1024,
    )
    if test_config:
        app.config.update(test_config)
    db.init_app(app); login_manager.init_app(app)
    from .models import User, Customer
    @login_manager.user_loader
    def load_user(user_id): return db.session.get(User, int(user_id))
    from .routes import bp
    app.register_blueprint(bp)
    with app.app_context():
        db.create_all()
        email=os.getenv("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
        password=os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
        if email and password and not User.query.filter_by(email=email).first():
            customer=Customer(name="AssetTrack 360 Administration", slug="platform-admin", active=True)
            db.session.add(customer); db.session.flush()
            db.session.add(User(customer_id=customer.id,email=email,name="Platform Administrator",role="platform_admin",password_hash=generate_password_hash(password),active=True))
            db.session.commit()
    return app
