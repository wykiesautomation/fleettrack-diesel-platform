import os
from app import create_app,db

def app():
 return create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:','SESSION_COOKIE_SECURE':False})
def test_health_and_legal():
 a=app()
 with a.test_client() as c:
  assert c.get('/health').status_code==200
  assert c.get('/terms').status_code==200
  assert c.get('/privacy').status_code==200
  assert c.get('/payment-policy').status_code==200
def test_ready_fails_without_production_configuration():
 a=app()
 with a.test_client() as c: assert c.get('/ready').status_code in (200,503)
