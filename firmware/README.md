# AssetTrack 360 Firmware Pack

Targets: ESP32-D 38-pin, ESP32-WROOM-32, and Maduino Zero SIM808 V3.5 SAMD21.

SIM808 verified map: AI1 A0, AI2 A1, DO1 D5, DO2 D6, POWER_KEY D9 reserved.

SIM808 provisioning commands:

```text
SET|APN|YOUR_APN
SET|DEVICE_UID|YOUR_DEVICE_UID
SET|DEVICE_TOKEN|YOUR_DEVICE_TOKEN
SET|UPLOAD_SECONDS|60
CHECK_SIM
CHECK_NETWORK
READ_TRACKING
CONNECT_GPRS
SEND_GSM
AUTO_ON
```

Outputs start OFF. Simulation never energises physical outputs.
