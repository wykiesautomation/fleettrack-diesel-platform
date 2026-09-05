# Live GitHub Device Panel Save Fix

Built only from the newly uploaded live GitHub baseline.

- Keeps the existing `_purpose` field fix.
- Removes Application/Asset Picture as a blocking gate for verified I/O assignments on an existing registered asset/device.
- Saves AI1 Tank Level and AI2 Temperature transactionally.
- Uses saved purpose/visual metadata on the same combined tracker dashboard.
- Renders the tank visual without converting the whole asset to Tank or creating a second asset/device/token.
- Preserves SIM808 GPS, identity, telemetry, DO1/DO2 safety and all customer data.
