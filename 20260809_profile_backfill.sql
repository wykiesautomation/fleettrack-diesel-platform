-- No schema change. Profiles use the existing JSON capabilities column.
UPDATE device SET capabilities = COALESCE(capabilities, '[]'::jsonb) || '["PROFILE:AT360_ESP32D_PILOT"]'::jsonb WHERE device_type='ESP32_REMOTE_IO' AND NOT (COALESCE(capabilities, '[]'::jsonb) @> '["PROFILE:AT360_ESP32D_PILOT"]'::jsonb);
