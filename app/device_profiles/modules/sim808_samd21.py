from ..schema import analog_channel, output_feedback, health_channel

PROFILE = {
    "code": "AT360_SIM808_TRACKER_2AI_2DO",
    "display_name": "SIM808 SAMD21 GPS Tracker 2AI-2DO",
    "device_type": "SIM808_GPS_TRACKER",
    "asset_type": "TRACKER",
    "transport": "GPRS_2G",
    "firmware_family": "AT360_MADUINO_SIM808_V35_SAMD21",
    "capabilities": [
        "GPS", "GPRS", "SMS", "GSM_SIGNAL", "ANALOG_INPUT_2",
        "DIGITAL_OUTPUT_2", "SIM808_POWER_CONTROL_RESERVED",
        "SERIAL_PROVISIONING", "STANDALONE_RECONNECT", "AIRTIME_DATA_BALANCE"
    ],
    "channels": [
        {**analog_channel("analog_1", "Analog Input 1", "SIM808"), "pin": "A0", "pin_notes": "Verified Maduino Zero SIM808 V3.5 analogue input"},
        {**analog_channel("analog_2", "Analog Input 2", "SIM808"), "pin": "A1", "pin_notes": "Verified Maduino Zero SIM808 V3.5 analogue input"},
        {**health_channel("analog_1_volts", "Analog Input 1 Voltage", "VOLTAGE", "SIM808", "V", "numeric"), "pin": "A0"},
        {**health_channel("analog_2_volts", "Analog Input 2 Voltage", "VOLTAGE", "SIM808", "V", "numeric"), "pin": "A1"},
        {**output_feedback("digital_output_1_feedback", "Digital Output 1 Feedback", "SIM808", "DO1"), "pin": "D5"},
        {**output_feedback("digital_output_2_feedback", "Digital Output 2 Feedback", "SIM808", "DO2"), "pin": "D6"},
        health_channel("gsm_signal", "GSM Signal", "SIGNAL", "SIM808", "CSQ", "numeric"),
        health_channel("speed_kmh", "Speed", "SPEED", "SIM808", "km/h", "numeric"),
        health_channel("gps_fix", "GPS Fix", "STATE", "SIM808"),
        health_channel("battery_v", "Battery Voltage", "VOLTAGE", "SIM808", "V", "battery"),
        health_channel("airtime_balance_zar", "Airtime Balance", "CURRENCY", "SIM808", "R", "numeric"),
        health_channel("data_remaining_mb", "Mobile Data Remaining", "DATA", "SIM808", "MB", "numeric"),
    ],
    "output_channels": [
        {"channel":"DO1", "label":"Digital Output 1", "pin":"D5", "mode":"LATCHED_OR_PULSE", "default_mode":"LATCHED", "pulse_seconds":1, "supported_actions":["OUTPUT_ON","OUTPUT_OFF","OUTPUT_PULSE"], "requires_local_arm":False, "safe_boot_state":"OFF", "simulation_physical_lockout":True, "feedback_key":"digital_output_1_feedback"},
        {"channel":"DO2", "label":"Digital Output 2", "pin":"D6", "mode":"LATCHED_OR_PULSE", "default_mode":"LATCHED", "pulse_seconds":1, "supported_actions":["OUTPUT_ON","OUTPUT_OFF","OUTPUT_PULSE"], "requires_local_arm":False, "safe_boot_state":"OFF", "simulation_physical_lockout":True, "feedback_key":"digital_output_2_feedback"},
    ],
    "reserved_pins": [
        {"pin":"D9", "purpose":"SIM808 POWER_KEY control", "customer_output":False, "reason":"Firmware-managed modem power control; never assign as customer I/O"}
    ],
    "board_metadata": {
        "board_family":"Maduino Zero SIM808 V3.5",
        "mcu":"ATSAMD21G18A",
        "board_target":"Arduino Zero (Native USB Port)",
        "console":"SerialUSB 115200",
        "modem":"Serial1 115200",
        "provisioning":"Serial SET commands",
    },
    "profile_notice":"Firmware verified mapping: AI1 A0, AI2 A1, DO1 D5, DO2 D6, SIM808 POWER_KEY D9. Location is transmitted in the telemetry location object.",
}
