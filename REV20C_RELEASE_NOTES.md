# REV20C Production Completion & Operations Fixes

- CSV and SQL cursor deduplication prevents unchanged rows from being queued every scan.
- SQLite queue gains deterministic dedup keys and a configurable maximum row count.
- Cloud failures use exponential backoff with jitter instead of hammering the endpoint.
- Explicit proxy URL can be configured where IT supplies an approved forward proxy.
- Heartbeat shows queue depth and uses agent version 1.0.3.
- Asset Settings corrects tank capacity without database surgery.
- Mapping KPI helper totals general, MQTT and universal mappings.
- Existing REV20A2 secure endpoints, token and gateway registration remain unchanged.
