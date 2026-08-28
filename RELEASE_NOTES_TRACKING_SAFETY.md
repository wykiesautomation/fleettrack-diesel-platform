# AssetTrack 360 Tracking Safety Release

Adds customer-configurable fleet safety controls to Tracking History:
- Per-asset speed limit with speeding event detection.
- Circular KEEP IN and KEEP OUT geofences.
- Safety zones rendered on the map.
- Operational event feed for speeding and geofence breaches.
- Tenant isolation, admin-only rule changes, validated coordinates/radii and non-destructive metadata storage.
- Fixes the missing `analysis.last` value used by Last Known Position.

This release provides monitoring and alert evidence only. It does not remotely control or immobilise vehicles.
