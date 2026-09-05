# AssetTrack 360 Three Priority Fixes Final

1. GPS selector remains tenant-scoped and capability-aware for mobile, GPS, GNSS and LOCATION devices, preserving exact device selection.
2. Tracking History now deterministically sorts observations, breaks continuity at every rejected point, computes distance only inside valid segments, and returns real journey and stop collections.
3. Motion Safety pending crash/tilt candidates are reevaluated after their cancellation deadline, finalised as confirmed, unconfirmed or insufficient evidence, audited, and logged by the worker.

No customer, device, token, telemetry or calibration records are destructively migrated.
