# Universal Analogue Input and Tank Level Fix

## Corrected
- The shared Signals & I/O Studio now recognises a verified physical analogue channel by its profile contract: `direction=INPUT`, `calibratable=True`, and a verified physical pin.
- It no longer depends only on the channel signal type containing the word `ANALOG`.
- Added the explicit `Tank Level` application to the function selector.
- Tank Level reuses the selected existing physical telemetry channel. It does not create a second device, token, or duplicate input channel.
- Tank Level applies `LEVEL`, `%`, tank widget, and normalized `0-100` scaling to the existing signal definition.

## Boards covered by the shared rule
- SIM808 / SAMD21: AI1 A0, AI2 A1
- ESP32-WROOM-32: AI1 GPIO34
- ESP32D 38-pin: AI1 GPIO34, AI2 GPIO35, AI3 GPIO36, AI4 GPIO39

## Preserved safety behavior
- Assigned points remain excluded from the available list.
- Reserved and undefined points remain blocked.
- Generic digital inputs are not treated as analogue inputs.
- Mobile trackers receive no fake GPIO.
- SIM808 DO1 D5 and DO2 D6 remain safe-boot OFF with Simulation physical lockout.
- SIM808 D9 remains reserved for modem POWER_KEY control.

## Expected SIM808 test
1. Open Signals & Inputs for the connected SIM808 device.
2. Select `Tank Level`.
3. Select `A0 - Analog Input 1`.
4. Enter `Tank Level` as the customer point name.
5. Select the Tank asset and click `Add I/O`.
6. Save the I/O configuration.
7. Send `analog_1` telemetry from the Hardware Bench.
8. Confirm the Tank Level card displays the existing AI1 value as a percentage.
9. Confirm A1 remains available and D5/D6 output assignments remain unchanged.
