# Device Panel Purpose Save Fix

Corrects the Device Engineering Studio backend field name from `_measurement` to `_purpose`, matching the existing HTML form.

After Save, Validate & Deploy:
- AI1 Tank Level persists as LEVEL / tank / EASY_TANK.
- AI2 Temperature persists as TEMPERATURE / temperature / TEMPERATURE.
- Existing device identity, token, telemetry, outputs and customer data remain unchanged.
