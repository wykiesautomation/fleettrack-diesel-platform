# AssetTrack 360 Tracker Onboarding Stabilisation

## Fixed

- Vehicle / Fleet Tracking now uses the canonical `VEHICLE_FLEET_TRACKING` solution code.
- Selecting a tracker hides and disables tank monitoring visuals and Tank Setup fields.
- The backend derives the asset type from the selected solution profile before considering any visual value.
- Stale tank visual values are normalised for non-tank assets.
- The hardware claim waiting page shows the claim code once and does not expose a device token.

## Regression protection

`tests/test_tracker_onboarding_regression.py` protects the completed tracker onboarding and claim-page behaviour from being overwritten by future changes.

## Deployment

Deploy the complete cumulative project. No database migration is required for this stabilisation.
