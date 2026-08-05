# AssetTrack 360 Firmware API Contract REV02

Base URL: `https://fleettrack.wykiesautomation.co.za`
Authentication: `Authorization: Bearer <device-token>`
Content-Type: `application/json`

## Identity fields
Every device request includes `device_id` and `imei`. The SIM868 IMEI is read with `AT+GSN`.

## Single telemetry
`POST /api/v1/ingest`
Required: device_id, imei, timestamp, sequence, measurements. Optional: location, firmware.
Success: HTTP 202. First IMEI: HTTP 409 until admin approval. Wrong IMEI: HTTP 403 and quarantine.

## Batch telemetry
`POST /api/v1/ingest/batch`
Maximum 100 samples. Top-level device_id and imei. Each sample has timestamp, sequence, measurements and optional location/firmware.

## Device configuration poll
`GET /api/v1/device/config?device_id=<UID>&imei=<IMEI>`
Returns configuration revision, tank geometry, calibration, alarms, reporting intervals and pending commands.

## Configuration acknowledgement
`POST /api/v1/device/config/ack`
Body: device_id, imei, revision, status (APPLIED or REJECTED), detail, commands[].

## Tracking history
Authenticated customer route: `GET /api/v1/assets/<asset_id>/tracking?from=<ISO8601>&to=<ISO8601>&limit=2000`

## Stable response codes
- 202 accepted / batch processed
- 400 invalid payload, missing sequence, invalid acknowledgement
- 401 invalid_device_token
- 402 subscription_inactive
- 403 device_identity_mismatch, imei_mismatch, device_not_allowed
- 409 IMEI_APPROVAL_REQUIRED
