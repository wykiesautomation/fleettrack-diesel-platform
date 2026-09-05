# Predictive Safety Twin Batch 1-2

- Adds `/asset/<asset_id>/safety-twin` as a production, tenant-scoped page.
- Uses real Location, Device, Reading and geofence data only.
- Adds an evidence-aware stationary engine: accuracy envelope, three consecutive points and 20-second confirmation.
- Keeps prediction as presentation-only. No predicted reading, location, alarm or safety event is stored.
- Existing Live Asset and Tracking History pages remain available during staged rollout.
