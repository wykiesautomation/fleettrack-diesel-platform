# Asset Dashboard SIM808 Firmware Field Fix

- Fixes HTTP 500 on `/asset/<id>` caused by reading the nonexistent `Device.firmware_version` attribute.
- Uses the actual `Device.firmware` model field with a backward-compatible guarded fallback.
- Keeps SIM808 detection through device type, firmware identity, or verified profile code.
- Safely handles assets with no device, devices with no firmware report, and malformed or missing profile context.
- Preserves OPC UA Parts 1-4, integration navigation, output safety, telemetry, and customer data.
- No database migration is required.
