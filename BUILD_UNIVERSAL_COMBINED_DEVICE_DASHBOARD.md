# AssetTrack 360 Universal Combined Device Dashboard

Cumulative on the uploaded GitHub main baseline.

## Completed
- Tracking and assigned process I/O now coexist on one asset dashboard.
- Dynamic cards render assigned analogue, digital and pulse inputs from the selected board profile.
- Diagnostic voltage/raw channels remain separate from customer engineering-value cards.
- Mobile trackers retain virtual/mobile points and do not receive fake GPIO controls.
- Analogue calibration validates normalized 0-100%, protected 0-3.3 V, raw 12-bit ADC and conditioned 4-20 mA ranges.
- Live raw-to-engineering scaling preview added.
- Invalid ranges and alarm ordering fail transactionally without partial save.
- Analogue channel profile defaults now match normalized firmware telemetry (0-100%).
- Output descriptions show mode, pulse duration, safe restart OFF, local-arm requirement and feedback freshness rules.
- Existing GPS, Fleet Safety Live, Tracking History, evidence, integrations, workers and PostgreSQL data contracts are retained.

## Data safety
No destructive database migration is included. Existing customers, assets, devices, readings, locations, assignments and calibrations are preserved.
