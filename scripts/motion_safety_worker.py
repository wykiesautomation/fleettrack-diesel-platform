#!/usr/bin/env python3
import signal,time
from app import create_app,db
from app.mobile_safety import reevaluate_pending_safety_events,send_due_notifications
running=True
def stop(*_):
 global running;running=False
def run_once(app):
 with app.app_context():
  try:
   processed=reevaluate_pending_safety_events();send_due_notifications()
   if processed:app.logger.info('Motion Safety reevaluated %s pending event(s)',processed)
   return processed
  except Exception:
   db.session.rollback();app.logger.exception('Motion Safety worker cycle failed safely');return 0
def main():
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop);app=create_app()
 while running:run_once(app);time.sleep(10)
if __name__=='__main__':main()
