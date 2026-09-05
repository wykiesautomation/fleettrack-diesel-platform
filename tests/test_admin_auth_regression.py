import importlib

from werkzeug.security import check_password_hash, generate_password_hash


def _build_app(monkeypatch, tmp_path, password="CurrentRenderPassword123!"):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "auth.db"))
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "owner@assettrack360.local")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", password)
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough-123")
    import app as app_package
    application=app_package.create_app({"TESTING":True,"WTF_CSRF_ENABLED":False})
    return application


def test_existing_bootstrap_admin_password_is_synchronised(monkeypatch,tmp_path):
    app=_build_app(monkeypatch,tmp_path,"FirstPassword123!")
    from app import db
    from app.models import User
    with app.app_context():
        user=User.query.filter_by(email="owner@assettrack360.local").one()
        user.password_hash=generate_password_hash("OldPassword123!")
        db.session.commit()
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD","NewRenderPassword123!")
    app2=app.__class__ and importlib.import_module("app").create_app({"TESTING":True})
    with app2.app_context():
        user=User.query.filter_by(email="owner@assettrack360.local").one()
        assert check_password_hash(user.password_hash,"NewRenderPassword123!")
        assert not check_password_hash(user.password_hash,"OldPassword123!")
        assert user.role=="platform_admin"


def test_admin_can_logout_and_login_again(monkeypatch,tmp_path):
    app=_build_app(monkeypatch,tmp_path)
    client=app.test_client()
    credentials={"email":"owner@assettrack360.local","password":"CurrentRenderPassword123!"}
    first=client.post("/login",data=credentials,follow_redirects=False)
    assert first.status_code in (302,303)
    assert "/platform-admin" in first.headers["Location"]
    logout=client.get("/logout",follow_redirects=False)
    assert logout.status_code in (302,303)
    assert "/login" in logout.headers["Location"]
    assert "no-store" in logout.headers.get("Cache-Control","")
    protected=client.get("/platform-admin/",follow_redirects=False)
    assert protected.status_code in (302,401)
    second=client.post("/login",data=credentials,follow_redirects=False)
    assert second.status_code in (302,303)
    assert "/platform-admin" in second.headers["Location"]
