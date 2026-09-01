# New Board Claim Flow Fix

Built from the uploaded live GitHub baseline.

- New Board is now an explicit selection and the default for physical hardware.
- New Board always generates a fresh claim code and waits for the new physical board to claim its own UID and token.
- An existing matching board is reused only when the user explicitly selects Use Existing Device.
- Creating a new asset name no longer silently opens the first existing board of the same profile.
- Existing boards, assets, UID values, tokens, assignments and telemetry are not modified.
