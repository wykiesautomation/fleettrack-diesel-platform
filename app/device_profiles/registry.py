"""AssetTrack 360 device-profile registry.

Only the three verified physical board modules are loaded and published.
Legacy profile codes and device types are mapped to their current canonical
physical board profiles without loading duplicate compatibility modules.
"""

from importlib import import_module

from .schema import validate_profile


MODULES = (
    "esp32d_38pin",
    "esp32_wroom32",
    "sim808_samd21",
    "lilygo_t_sim7000g",
)

PUBLIC_BOARD_CODES = (
    "AT360_ESP32D_EXPANDED",
    "AT360_ESP32_WROOM32",
    "AT360_SIM808_TRACKER_2AI_2DO",
    "AT360_LILYGO_T_SIM7000G",
)

PROFILE_ALIASES = {
    "AT360_ESP32D_38PIN": "AT360_ESP32D_EXPANDED",
    "AT360_ESP32D_PILOT": "AT360_ESP32D_EXPANDED",
}


DEVICE_PROFILES = {}

for module_name in MODULES:
    module = import_module(f".modules.{module_name}", package=__package__)
    profile = validate_profile(module.PROFILE)
    profile_code = profile["code"]

    if profile_code in DEVICE_PROFILES:
        raise ValueError(f"Duplicate profile code: {profile_code}")

    DEVICE_PROFILES[profile_code] = profile


def get_profile(code):
    """Return a validated profile by canonical code or legacy alias."""
    normalized = str(code or "").strip().upper()
    normalized = PROFILE_ALIASES.get(normalized, normalized)
    return DEVICE_PROFILES.get(normalized)


def public_profiles():
    """Return only the three physical boards shown on Connect Device."""
    return [
        DEVICE_PROFILES[code]
        for code in PUBLIC_BOARD_CODES
        if code in DEVICE_PROFILES
    ]


def profile_for_device(device):
    """Resolve a device profile from capabilities, then legacy device type."""
    if not device:
        return None

    for value in device.capabilities or []:
        if str(value).startswith("PROFILE:"):
            profile = get_profile(str(value).split(":", 1)[1])
            if profile:
                return profile

    legacy = {
        "ESP32_REMOTE_IO": "AT360_ESP32D_EXPANDED",
        "ESP32D_38PIN_REMOTE_IO": "AT360_ESP32D_EXPANDED",
        "ESP32_WROOM32_REMOTE_IO": "AT360_ESP32_WROOM32",
        "SIM808_GPS_TRACKER": "AT360_SIM808_TRACKER_2AI_2DO",
        "SIM808_SAMD21": "AT360_SIM808_TRACKER_2AI_2DO",
        "LILYGO_T_SIM7000G_TRACKER": "AT360_LILYGO_T_SIM7000G",
    }
    return get_profile(legacy.get(str(getattr(device, "device_type", "")).upper()))
