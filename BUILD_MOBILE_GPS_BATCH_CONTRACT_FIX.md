# Mobile GPS Batch Contract Fix

Built cumulatively from the uploaded live GitHub baseline.

- Heartbeat and GPS batch now use the same authenticated device identity contract.
- GPS batches accept device_id once at batch level or on each point.
- If neither contains device_id, the authenticated bearer-token device is used.
- A conflicting supplied ID remains rejected.
- Accepts latitude/longitude and legacy lat/lon/lng aliases.
- Accepts accuracy_m/accuracy and speed_kmh/speed aliases.
- Existing duplicate protection, consent, subscription, range validation, route analysis and tenant isolation remain active.
- No customer, device, token, telemetry or database migration is changed.
