# AssetTrack 360 Firmware API Contract

Bearer auth. Every SIM868 request includes device_id and 15-digit imei.

- POST /api/v1/ingest
- POST /api/v1/ingest/batch, max 100 samples
- GET /api/v1/device/config?device_id=UID&imei=IMEI
- POST /api/v1/device/config/ack

Responses: 202 accepted, 400 invalid, 401 token, 402 subscription, 403 identity/quarantine/archive, 409 IMEI approval required.
