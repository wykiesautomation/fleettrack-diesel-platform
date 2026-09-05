# AssetTrack 360 Mobile Batch and Neon Stability Fix

- Removes the per-point location duplicate query.
- Loads mobile telemetry signal definitions once per batch.
- Loads existing reading sequences once per batch.
- Evaluates mobile alert settings once using the newest accepted observation.
- Bounds PostgreSQL connection wait to 10 seconds and statement execution to 25 seconds.
- Preserves the 100-point batch contract, duplicate handling, tenant/device identity validation, consent, subscription gating, raw location evidence, telemetry, alarms and tracking history.
- No database migration and no customer/device/token/data reset.
