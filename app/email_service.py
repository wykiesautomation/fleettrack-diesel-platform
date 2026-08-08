import os
import smtplib
import ssl
from email.message import EmailMessage
from flask import current_app


def send_verification_email(recipient, recipient_name, verification_url):
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM_EMAIL", username).strip()
    sender_name = os.getenv("SMTP_FROM_NAME", "AssetTrack 360").strip()
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
    if not host or not sender:
        current_app.logger.error("Verification email not sent: SMTP configuration is incomplete")
        return False

    message = EmailMessage()
    message["Subject"] = "Verify your AssetTrack 360 email address"
    message["From"] = f"{sender_name} <{sender}>"
    message["To"] = recipient
    message.set_content(
        f"Hello {recipient_name},\n\n"
        "Confirm your AssetTrack 360 email address by opening this link:\n"
        f"{verification_url}\n\n"
        "This link expires in 30 minutes and can only be used once. "
        "If you did not request this account, ignore this email.\n\n"
        "AssetTrack 360\n"
        "Copyright: © 2026 JP Van Wyk. All rights reserved."
    )
    message.add_alternative(
        f"""<!doctype html><html><body style='font-family:Arial,sans-serif;background:#061622;color:#eaf8ff;padding:30px'>
        <div style='max-width:620px;margin:auto;background:#0c2638;border:1px solid #28516a;border-radius:16px;padding:28px'>
        <h1 style='color:#08c7e7'>AssetTrack 360</h1><p>Hello {recipient_name},</p>
        <p>Confirm your email address to activate your account.</p>
        <p><a href='{verification_url}' style='display:inline-block;background:#08c7e7;color:#061622;padding:13px 18px;border-radius:10px;text-decoration:none;font-weight:bold'>Verify email address</a></p>
        <p style='color:#9bb5c3'>The link expires in 30 minutes and can only be used once. If you did not request this account, ignore this email.</p>
        <hr style='border:0;border-top:1px solid #28516a'><small>Copyright: © 2026 JP Van Wyk. All rights reserved.</small>
        </div></body></html>""",
        subtype="html",
    )
    context = ssl.create_default_context()
    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as server:
                if username:
                    server.login(username, password)
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.ehlo()
                if use_tls:
                    server.starttls(context=context)
                    server.ehlo()
                if username:
                    server.login(username, password)
                server.send_message(message)
        return True
    except Exception as error:
        current_app.logger.exception("Verification email delivery failed: %s", type(error).__name__)
        return False
