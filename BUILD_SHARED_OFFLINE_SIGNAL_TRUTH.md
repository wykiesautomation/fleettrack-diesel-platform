# Shared Offline and Signal Freshness Truth

- All combined device signal cards now evaluate both reading age and device-contact age.
- 0-5 min remains LIVE, 6-15 min is DELAYED, 16-30 min is STALE, and over 30 min is OFFLINE.
- Historical values remain visible as LAST REPORTED evidence but never retain a misleading GOOD/live presentation.
- The fixed page badge now says DASHBOARD LIVE · DEVICE <state>, separating website refresh health from device connectivity.
- Existing output freshness lockouts, telemetry, UID, tokens, device profiles and customer data remain unchanged.
