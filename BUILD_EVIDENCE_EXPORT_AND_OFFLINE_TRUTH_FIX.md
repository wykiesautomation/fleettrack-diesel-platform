# Evidence Export and Offline Truth Fix

- Evidence PDF and ZIP audit entries now store the numeric current user ID in `actor_id`.
- Evidence Report IDs are retained safely in the audit summary.
- Safety Twin now separates connectivity from movement confidence.
- Adds ONLINE, DELAYED, STALE, OFFLINE and NEVER SEEN states.
- Offline pages show last validated state, last known position, stale battery age and last-session confidence.
- No database migration or customer telemetry rewrite is required.
