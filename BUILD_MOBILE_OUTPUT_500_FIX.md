# Mobile Responsive Output 500 Fix

The full mobile-responsive production pass is retained. The asset output template no longer directly introspects the latest DeviceCommand runtime object after a command is queued. Immediate button feedback still displays COMMAND SENT in the browser, while confirmed OUTPUT ON/OFF remains driven only by fresh firmware feedback. Backend command queueing, Local Arm, Simulation lockout, telemetry, tank calibration and mobile navigation are unchanged.
