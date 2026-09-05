# Mobile Walking Route Validation

- Aligns Mobile API evidence acceptance to 150 m while requiring <=50 m route-grade accuracy for movement.
- Retains 50-150 m fixes as low-confidence last-known evidence, not route distance.
- Adds WAITING_FOR_GPS and GPS_QUALITY_INSUFFICIENT states.
- Prevents rejected raw speed from appearing as validated current speed.
- Adds visible GPS rejection categories.
- Does not fabricate a 30 m route inside a 126 m uncertainty radius.
