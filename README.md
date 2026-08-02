# AssetTrack 360 REV12

Production-oriented MVP for customer registration, universal device signals, dynamic asset dashboards and deployment.

## Included
- Customer self-registration and tenant isolation
- PostgreSQL production / SQLite local database
- Site, asset, device and universal signal registry
- Generic HTTP telemetry ingestion with Bearer device token
- 4-20 mA scaling to engineering units
- Tank, tracking, vibration and generic dashboards
- Dynamic signal widgets, alarm evaluation and acknowledgement
- Device simulator and demo seed
- Dockerfile and Render Blueprint

## Local start
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
export FLASK_APP='app:create_app'
flask run --host 0.0.0.0 --port 5000
```

Seed demo data:
```bash
python scripts/seed_demo.py
```
Demo login: `demo@assettrack360.local` / `DemoPassword123!`

## Register a real or simulated device
1. Register/customer login.
2. Add site and asset.
3. Open Device and register a UID.
4. Copy API token.
5. Send JSON to `POST /api/v1/ingest` with `Authorization: Bearer <token>`.

Example:
```json
{
  "device_id": "PP-TANK-0001",
  "sequence": 1001,
  "timestamp": "2026-08-02T08:30:00Z",
  "firmware": "rev12-device",
  "measurements": [
    {"point":"level_percent","value":78.4,"quality":"GOOD"},
    {"point":"volume_l","value":7840,"quality":"GOOD"},
    {"point":"battery_v","value":3.92,"quality":"GOOD"}
  ],
  "location":{"latitude":-26.70,"longitude":27.80,"accuracy_m":8,"speed_kmh":0}
}
```

For a configured `4-20mA` signal, send the raw current value. The server converts raw minimum/maximum to engineering minimum/maximum.

## Simulator
```bash
python scripts/device_simulator.py --token YOUR_TOKEN --device-id PP-TANK-0001 --mode tank
```
Modes: `tank`, `tracker`, `vibration`, `analog`.

## Render deployment
1. Push this folder to GitHub.
2. In Render, choose New > Blueprint.
3. Select the repository containing `render.yaml`.
4. Set `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` only if a platform bootstrap login is needed.
5. Deploy and verify `/health`.

## Important production hardening after pilot
- Add email verification and password reset provider.
- Add CSRF tokens to all browser forms.
- Replace visible device token display with one-time reveal and token rotation.
- Add MQTT broker adapter, background workers and notification provider.
- Add database migration tooling and managed backup verification.
- Add map tile/provider integration and geofence engine.
- Add subscription billing and entitlement enforcement.

Customer-facing branding is AssetTrack 360. Internal REV numbers are not displayed in the UI.
