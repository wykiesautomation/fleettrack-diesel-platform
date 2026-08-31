# Verification Email Resend Fix

## Fixed
- Registering again with an existing unverified email now reuses the same account and sends a fresh verification email.
- Resend Verification now reports the real send result instead of always displaying a generic success message.
- Every resend rotates the verification nonce, making the previous link invalid.
- Delivery outcome is logged without exposing API keys, sender secrets, verification tokens or email content.

## Unchanged
- Brevo API endpoint and provider implementation.
- BREVO_API_KEY, EMAIL_FROM_ADDRESS, EMAIL_FROM_NAME and PUBLIC_BASE_URL contracts.
- Existing customer, user, device, token, telemetry, calibration and billing records.
- Device profiles and hardware behavior.
