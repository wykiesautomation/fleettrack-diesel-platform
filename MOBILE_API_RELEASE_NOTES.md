# AssetTrack 360 Mobile Tracking API Build

## Added

- `GET /api/v1/mobile/config`
- `POST /api/v1/mobile/heartbeat`
- `POST /api/v1/mobile/location/batch`
- `POST /api/v1/mobile/tracking/start`
- `POST /api/v1/mobile/tracking/stop`
- Batch uploads of up to 100 points.
- Duplicate-safe sequence handling.
- Server-provided queue and heartbeat limits.
- Offline queue increased to 1,000 points.
- Mobile platform identity for web, Android and iPhone.
- Battery and charging heartbeat updates.
- Automatic route-history enablement for mobile tracking.

## Preserved

- Explicit location consent.
- Subscription entitlement checks.
- Device token and identity checks.
- Start/stop controls.
- Consent withdrawal, unregister and deletion request.
- Existing single-point location API for immediate live uploads.
