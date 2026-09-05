from app import create_app,db

def test_health():
 app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:','WTF_CSRF_ENABLED':False})
 with app.test_client() as c:
  r=c.get('/health');assert r.status_code==200;assert r.json['status']=='ok'

def test_register():
 app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:','WTF_CSRF_ENABLED':False})
 with app.test_client() as c:
  r=c.post('/register',data={'company':'Test Co','name':'Test User','email':'test@example.com','password':'StrongPass123!'},follow_redirects=False);assert r.status_code==302
