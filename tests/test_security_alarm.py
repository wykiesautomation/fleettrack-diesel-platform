from pathlib import Path
r=Path('app/routes.py').read_text();m=Path('app/models.py').read_text();j=Path('app/static/mobile_tracker.js').read_text()
for x in ['MobileConsent','SecurityAuditEvent','AssetAlertSettings','CoreAlarmState','DataDeletionRequest']:assert 'class '+x in m
for x in ['/api/v1/mobile/event','explicit_location_consent_required','consent_inactive','alert-settings']:assert x in r
for x in ['withdrawConsent','unregisterPhone','DATA_DELETION_REQUESTED','TRACKING_STARTED']:assert x in j
print('SECURITY_ALARM PASS')
