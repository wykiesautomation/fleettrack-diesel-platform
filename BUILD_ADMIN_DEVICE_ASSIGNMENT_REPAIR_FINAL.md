# Platform Admin Device Assignment Repair

- Adds a platform-admin-only repair action on the Devices page.
- Validates active device, linked asset, tenant ownership and verified profile.
- Reuses exact existing signals and creates only disabled profile placeholders where needed.
- Performs one transactional commit and rolls back fully on any error.
- Never changes UID, token, readings, locations, calibration or history.
- Includes the WROOM output summary, Local Arm interlock and Simulation physical lockout fixes.
