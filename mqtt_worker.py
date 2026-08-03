from app import create_app
from app.mqtt_service import run_worker
app=create_app()
if __name__=='__main__':run_worker(app)
