# Universal Wi-Fi RSSI Visual Fix

- Adds a percentage and horizontal strength bar for `wifi_rssi`.
- Separates transport quality (`GOOD`/`SIMULATED`) from radio strength.
- Classifies -72 dBm as FAIR.
- Supports ESP32-WROOM-32 and ESP32D through the shared `wifi_rssi` capability key.
- Uses green, cyan, amber and red bands for strong through unreliable signal levels.
