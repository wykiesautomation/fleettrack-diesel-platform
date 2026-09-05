# Route Segmentation and Delete Centralization Final
- Never draws or measures route fragments with fewer than three consecutive validated movement points.
- Breaks route continuity at rejected observations, gaps over 120 seconds, out-of-order timestamps and implausible jumps.
- Keeps last-known context without presenting it as a validated route.
- Returns WAITING_FOR_VALIDATED_ROUTE when evidence is insufficient.
- Keeps asset/device/site deletion only in Account → Data Management.
- Moves permanent customer deletion out of Customer Detail into Platform Administration → Data Management.
- Preserves Motion Safety, mobile APIs, telemetry, calibration, board profiles and existing data.
