# OPC UA Part 5: Local Edge Gateway Agent

- Builds on `AssetTrack360_Universal_Integration_Platform_ASSET_500_FINAL_FIXED.zip`.
- Adds secure runtime configuration, work queue and live-batch APIs using the rotatable Edge Gateway registry token.
- Adds a Windows-capable local OPC UA agent with Browse, Read Test, mapped-node polling, SQLite WAL queue, retry, heartbeat and rotating logs.
- Adds startup-task tooling and a compact local diagnostics desktop view.
- Permanently enforces read-only operation. No OPC write, method, setpoint, alarm acknowledgement or PLC command path exists.
