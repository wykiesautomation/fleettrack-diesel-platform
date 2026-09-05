# AssetTrack 360 Quick Calibration Wizard

- Adds a separate two-point installer workflow for assigned analogue channels.
- Supports Tank Level, Temperature, Pressure, Flow and Custom Analogue presets.
- Supports normalised 0-100%, conditioned 4-20 mA, conditioned 0-10 V, protected 0-3.3 V ADC and custom verified conditioning.
- Captures current telemetry as Zero or Span when available.
- Preserves the previous calibration in a bounded revision history before deployment.
- Validates ranges, board limits and signal type transactionally.
- Rolls back completely on any error.
- Keeps the existing Advanced Calibration & Alarms editor unchanged and available.
- Restricts calibration changes to customer admins, platform admins or explicitly authorised advanced users.
