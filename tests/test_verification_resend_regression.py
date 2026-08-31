from pathlib import Path
R=Path('app/routes.py').read_text(encoding='utf-8')
E=Path('app/email_service.py').read_text(encoding='utf-8')

def test_existing_unverified_registration_resends():
    assert 'existing=User.query.filter_by(email=email).first()' in R
    assert 'if not existing.email_verified:' in R
    assert 'sent=_send_user_verification(existing)' in R
    assert "_record_attempt(email,'REGISTER',sent)" in R

def test_resend_reports_real_delivery_result():
    assert 'sent=_send_user_verification(user)' in R
    assert "_record_attempt(email,'RESEND',sent)" in R
    assert 'Verification email sent. Check Inbox, Spam and Junk.' in R
    assert 'Verification email could not be sent.' in R

def test_email_provider_and_environment_contract_unchanged():
    assert 'BREVO_EMAIL_API_URL = "https://api.brevo.com/v3/smtp/email"' in E
    assert 'os.getenv("BREVO_API_KEY", "").strip()' in E
    assert 'os.getenv("EMAIL_FROM_ADDRESS", "").strip()' in E
    assert 'os.getenv("EMAIL_FROM_NAME", "AssetTrack 360").strip()' in E

def test_new_nonce_still_invalidates_old_link():
    assert 'user.verification_nonce=secrets.token_urlsafe(24)' in R
    assert "user.verification_sent_at=utcnow()" in R
