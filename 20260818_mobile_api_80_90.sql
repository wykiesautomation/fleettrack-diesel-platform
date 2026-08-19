-- AssetTrack 360 Mobile API Batch 80-90
CREATE TABLE IF NOT EXISTS mobile_device_state (
 id SERIAL PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customer(id), asset_id INTEGER NOT NULL REFERENCES asset(id), device_id INTEGER NOT NULL REFERENCES device(id),
 platform VARCHAR(20) NOT NULL DEFAULT 'web', app_version VARCHAR(40), tracking_enabled BOOLEAN NOT NULL DEFAULT FALSE, battery_percent DOUBLE PRECISION, charging BOOLEAN,
 last_heartbeat_at TIMESTAMPTZ, last_location_at TIMESTAMPTZ, config_json JSON NOT NULL DEFAULT '{}'::json, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 CONSTRAINT uq_mobile_state_customer_device UNIQUE(customer_id,device_id), CONSTRAINT uq_mobile_state_device UNIQUE(device_id));
CREATE INDEX IF NOT EXISTS ix_mobile_device_state_customer_id ON mobile_device_state(customer_id);
CREATE INDEX IF NOT EXISTS ix_mobile_device_state_asset_id ON mobile_device_state(asset_id);
CREATE INDEX IF NOT EXISTS ix_mobile_device_state_platform ON mobile_device_state(platform);
CREATE INDEX IF NOT EXISTS ix_mobile_device_state_tracking_enabled ON mobile_device_state(tracking_enabled);
CREATE INDEX IF NOT EXISTS ix_mobile_device_state_last_heartbeat_at ON mobile_device_state(last_heartbeat_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_location_asset_sequence_mobile ON location(asset_id,sequence) WHERE sequence IS NOT NULL;
