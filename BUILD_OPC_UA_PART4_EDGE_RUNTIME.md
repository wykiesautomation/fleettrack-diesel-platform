# OPC UA Part 4: Edge Gateway Runtime & Live Data Flow

- Adds a read-only runtime configuration API for the assigned gateway.
- Adds local mapped-node reads with OPC quality and source/server timestamps.
- Adds deterministic duplicate-safe point sequences.
- Adds SQLite WAL queue integration, bounded batches, retry and recovery glue.
- Adds tenant/gateway-scoped live batch ingest with scaling, stale detection and quality preservation.
- Adds a live runtime diagnostics dashboard for gateway, connector, mappings and upload events.
- Does not contain OPC write, method call, setpoint or alarm-acknowledgement capabilities.
