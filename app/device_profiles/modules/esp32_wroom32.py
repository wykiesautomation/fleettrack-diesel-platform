from ..schema import analog_channel, input_channel, output_feedback

# Separate profile for a loose ESP32-WROOM-32 module or a custom carrier board.
# Pin assignments are intentionally not inherited from the ESP32-D 38-pin board.
PROFILE = {
    "code": "AT360_ESP32_WROOM32",
    "display_name": "ESP32-WROOM-32 Module",
    "device_type": "ESP32_WROOM32_REMOTE_IO",
    "asset_type": "GENERIC",
    "transport": "WIFI",
    "firmware_family": "AT360_ESP32_WROOM32",
    "capabilities": [
        "WIFI",
        "BLE",
        "ANALOG_INPUT_1",
        "DIGITAL_INPUT_1",
        "PULSE_COUNTER_1",
        "DIGITAL_OUTPUT_1",
        "LOCAL_ARM",
        "VERIFIED_FIRMWARE_PINMAP",
    ],
    "channels": [
        {
            **analog_channel("analog_1", "Analog Input 1", "ESP32_WROOM32"),
            "pin": "GPIO34",
            "pin_notes": "ADC1 input-only; protected 0-3.3 V maximum",
        },
        {
            "key": "analog_1_volts",
            "label": "Analog Input 1 Voltage",
            "signal_type": "VOLTAGE",
            "source_type": "ESP32_WROOM32",
            "unit": "V",
            "widget": "numeric",
            "direction": "HEALTH",
            "calibratable": False,
            "pin": "GPIO34",
            "linked_to": "analog_1",
            "diagnostic_only": True,
        },
        {
            **input_channel("digital_1", "Digital Input 1", "STATE", "ESP32_WROOM32"),
            "pin": "GPIO27",
        },
        {
            **input_channel("pulse_1_count", "Pulse Counter 1", "COUNT", "ESP32_WROOM32", "pulses", "numeric"),
            "pin": "GPIO26",
        },
        {
            **input_channel("local_arm_status", "Local Arm Status", "STATE", "ESP32_WROOM32"),
            "pin": "GPIO32",
            "safety_interlock": True,
        },
        {
            **output_feedback("digital_output_1_feedback", "Digital Output 1 Feedback", "ESP32_WROOM32", "DO1"),
            "pin": "GPIO25",
        },
        {
            "key": "wifi_rssi",
            "label": "Wi-Fi Signal",
            "signal_type": "SIGNAL",
            "source_type": "ESP32_WROOM32",
            "unit": "dBm",
            "widget": "numeric",
            "direction": "HEALTH",
            "calibratable": False,
        },
    ],
    "output_channels": [
        {
            "channel": "DO1",
            "label": "Digital Output 1",
            "mode": "LATCHED_OR_PULSE",
            "default_mode": "LATCHED",
            "pulse_seconds": 1,
            "supported_actions": ["OUTPUT_ON", "OUTPUT_OFF", "OUTPUT_PULSE"],
            "requires_local_arm": True,
            "safe_boot_state": "OFF",
            "simulation_physical_lockout": True,
            "feedback_key": "digital_output_1_feedback",
            "pin": "GPIO25",
        }
    ],
    "reserved_pins": [{"pin": "GPIO33", "customer_output": False, "reason": "Wi-Fi status LED managed by firmware"}],
    "profile_notice": "Verified against the deployed AT360 WROOM firmware pin map: AI1 GPIO34, DI1 GPIO27, Pulse 1 GPIO26, DO1 GPIO25, Local Arm GPIO32, Wi-Fi LED GPIO33.",
}
