from app import app
from app.trend_cleanup import cleanup_due
with app.app_context():print(cleanup_due(force=True))
