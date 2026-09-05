# SIM808 Asset Truth and Output Safety Fix

- One shared connectivity state drives the header, Tracker Summary and output lock.
- ONLINE ≤5 min, DELAYED 6–15 min, STALE 16–30 min, OFFLINE >30 min, NEVER SEEN when no contact exists.
- Battery wording uses the reading timestamp and cannot show `STALE · Just now` from page refresh time.
- SIM808 GPS accuracy is explicitly labelled estimated.
- Output controls remain disabled unless the device is ONLINE and fresh firmware feedback exists.
- DO1/DO2 remain separate profile-defined output channels; firmware feedback is authoritative.
