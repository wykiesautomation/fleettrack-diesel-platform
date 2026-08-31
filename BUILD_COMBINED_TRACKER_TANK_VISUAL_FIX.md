# Combined Tracker + Process I/O + Tank Visual Fix

One physical device retains all of its functions on one combined asset dashboard.

For the SIM808 this means:
- GPS, position, speed and battery remain on the tracker summary.
- AI1 can be assigned as Tank Level and renders the tank visual on the same page.
- AI2 can be assigned independently to another process function.
- DO1 and DO2 retain their safe output controls.
- No second asset, second device, new claim, or new token is created.

The tank visual is driven by the channel assignment purpose `TANK_LEVEL`, not by forcing the whole asset type to `TANK`.
