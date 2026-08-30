# AssetTrack 360 Admin Login Lockout Final Fix

- Login lockout counts failed attempts only. Successful logins no longer accumulate toward lockout.
- A successful login clears previous failed attempts for that account and source IP.
- Fresh login session is created after stale session state is cleared.
- Logout clears Flask-Login identity, application session and browser session cookie.
- Existing bootstrap administrator password synchronization is retained.
- Python and pytest cache files are excluded from the production ZIP.
