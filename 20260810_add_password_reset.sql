ALTER TABLE "user" ADD COLUMN IF NOT EXISTS password_reset_nonce VARCHAR(80);
ALTER TABLE "user" ADD COLUMN IF NOT EXISTS password_reset_sent_at TIMESTAMPTZ;
ALTER TABLE "user" ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS ix_user_password_reset_nonce ON "user"(password_reset_nonce);
