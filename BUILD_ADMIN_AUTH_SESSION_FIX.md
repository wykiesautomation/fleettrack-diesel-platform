# AssetTrack 360 Admin Authentication and Session Fix

- Existing bootstrap platform administrator password now follows the current `BOOTSTRAP_ADMIN_PASSWORD` Render environment value.
- Platform administrator role, active state and email verification remain restored safely at startup.
- Logout now clears Flask-Login identity, all Flask session state and the session cookie.
- Logout responses use no-store/no-cache headers to prevent browser Back from exposing an authenticated page.
- Customer accounts, device tokens, telemetry and customer data are unchanged.
- Regression coverage verifies password synchronization and login -> logout -> protected route -> login again.
