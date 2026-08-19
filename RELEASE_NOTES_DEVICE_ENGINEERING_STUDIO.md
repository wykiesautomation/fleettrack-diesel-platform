# AssetTrack 360 Device Engineering Studio Fix

This cumulative fix aligns the live Device Studio with the approved Device Engineering Studio mockup.

## Corrected workflow
- Select Board -> Configure I/O -> Validate -> Deploy.
- The registered physical board profile is the source of truth.
- Only profile-declared physical I/O is buildable.

## Fixed defects
- The Device Studio route now supplies analog, digital, pulse, system and output channel collections required by the template.
- Missing template libraries and configured-choice data are now supplied.
- The save handler now persists analog, digital, pulse and safe-output assignments, instead of analog channels only.
- Every save is transactional. A failed validation rolls back all partial changes.
- Reserved pins, absent physical pins and duplicate active pin assignments are blocked.
- Outputs must declare safe boot OFF, Simulation physical lockout and a feedback key.
- Firmware identity is displayed and a missing reported firmware version produces a visible validation warning.
- Successful validation is stored with the asset commissioning metadata and shown as a deploy gate.

## Safety retained
- Simulation cannot energise physical outputs.
- Output firmware and local interlocks remain authoritative.
- No unsupported board capability is added by the Studio.
