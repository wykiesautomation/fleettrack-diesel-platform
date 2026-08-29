# Asset Dashboard 500 Profile Guard Fix

- Prevents unknown, incomplete or legacy device profiles from crashing `/asset/<id>`.
- Normalizes missing/non-dictionary profile context to a safe empty profile.
- Ignores malformed output-channel entries without a feedback key.
- Preserves SIM808 status truth, output safety, OPC UA Parts 1-4 and existing telemetry.
