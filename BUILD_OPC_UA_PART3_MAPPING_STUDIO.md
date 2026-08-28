# OPC UA Part 3: Mapping Studio

- Maps a selected OPC UA Node ID to an existing tenant asset and enabled signal.
- Validates datatype, scale, offset, asset ownership and signal ownership.
- Uses `UniversalSourceMapping`, which is already consumed by the Edge ingest API.
- Adds transformation preview without persisting synthetic readings.
- Adds enable/disable and delete management.
- Maintains the read-only OPC policy. Values flow OPC → Edge → AssetTrack telemetry only.
