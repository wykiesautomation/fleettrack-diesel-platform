from app.device_profiles import DEVICE_PROFILES
print(f"Validated {len(DEVICE_PROFILES)} profiles")
for code,p in DEVICE_PROFILES.items():print(code,len(p["channels"]),len(p["output_channels"]))
