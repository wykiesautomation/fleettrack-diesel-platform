import html
import os

import requests
from flask import current_app


BREVO_EMAIL_API_URL = "https://api.brevo.com/v3/smtp/email"


def send_verification_email(recipient, recipient_name, verification_url):
    """Send an AssetTrack 360 verification email through Brevo HTTPS API."""
    api_key = os.getenv("BREVO_API_KEY", "").strip()
    sender_email = os.getenv("EMAIL_FROM_ADDRESS", "").strip()
    sender_name = os.getenv("EMAIL_FROM_NAME", "AssetTrack 360").strip()

    if not api_key or not sender_email:
        current_app.logger.error(
            "Verification email not sent: Brevo API configuration is incomplete"
        )
        return False

    safe_name = html.escape(recipient_name or "Customer")
    safe_url = html.escape(verification_url, quote=True)

    text_content = (
        f"Hello {recipient_name or 'Customer'},\n\n"
        "Confirm your AssetTrack 360 email address by opening this link:\n"
        f"{verification_url}\n\n"
        "This link expires in 30 minutes and can only be used once. "
        "If you did not request this account, ignore this email.\n\n"
        "AssetTrack 360\n"
        "Copyright: © 2026 JP Van Wyk. All rights reserved."
    )

    html_content = f"""<!doctype html>
<html lang="en">
<body style="margin:0;background:#061622;color:#eaf8ff;font-family:Arial,sans-serif;padding:30px">
  <div style="max-width:620px;margin:auto;background:#0c2638;border:1px solid #28516a;border-radius:16px;padding:28px">
    <h1 style="margin-top:0;color:#08c7e7">AssetTrack 360</h1>
    <p>Hello {safe_name},</p>
    <p>Confirm your email address to activate your account.</p>
    <p style="margin:26px 0">
      <a href="{safe_url}" style="display:inline-block;background:#08c7e7;color:#061622;padding:13px 18px;border-radius:10px;text-decoration:none;font-weight:bold">
        Verify email address
      </a>
    </p>
    <p style="color:#9bb5c3;line-height:1.5">
      This link expires in 30 minutes and can only be used once.
      If you did not request this account, ignore this email.
    </p>
    <hr style="border:0;border-top:1px solid #28516a;margin:24px 0">
    <small>Copyright: © 2026 JP Van Wyk. All rights reserved.</small>
  </div>
</body>
</html>"""

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": recipient, "name": recipient_name or "Customer"}],
        "subject": "Verify your AssetTrack 360 email address",
        "htmlContent": html_content,
        "textContent": text_content,
    }

    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }

    try:
        response = requests.post(
            BREVO_EMAIL_API_URL,
            headers=headers,
            json=payload,
            timeout=20,
        )
        if 200 <= response.status_code < 300:
            message_id = ""
            try:
                message_id = str(response.json().get("messageId", ""))[:120]
            except ValueError:
                pass
            current_app.logger.info(
                "Verification email accepted by Brevo message_id=%s",
                message_id or "not-returned",
            )
            return True

        safe_detail = response.text.replace("\n", " ")[:300]
        current_app.logger.error(
            "Brevo verification email rejected status=%s detail=%s",
            response.status_code,
            safe_detail,
        )
        return False
    except requests.RequestException as error:
        current_app.logger.exception(
            "Brevo verification email request failed: %s",
            type(error).__name__,
        )
        return False
