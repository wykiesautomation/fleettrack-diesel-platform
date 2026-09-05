"""Customer-facing AssetTrack 360 solution profiles.

Physical board profiles describe hardware. Solution profiles describe what a
selected phone/board will monitor or control. Keep these registries separate.
"""

SOLUTION_PROFILES = {
    "GENERAL_REMOTE_IO": {
        "code": "GENERAL_REMOTE_IO", "display_name": "General Remote I/O",
        "category": "MONITORING", "asset_type": "GENERIC", "icon": "IO",
        "description": "Build a custom project from verified analog, digital, pulse and output channels.",
        "badges": ["Flexible I/O", "Custom Tags", "Board-aware"],
        "boards": ["AT360_ESP32D_EXPANDED", "AT360_ESP32_WROOM32", "AT360_SIM808_TRACKER_2AI_2DO", "AT360_LILYGO_T_SIM7000G"],
        "default_signals": [],
    },
    "TANK_LEVEL_VOLUME": {
        "code": "TANK_LEVEL_VOLUME", "display_name": "Tank Level & Volume",
        "category": "MONITORING", "asset_type": "TANK", "icon": "TANK",
        "description": "Tank level, calibration, strapping, volume, available space and inventory alarms.",
        "badges": ["Analog Level", "Strapping", "Tank HMI"],
        "boards": ["AT360_ESP32D_EXPANDED", "AT360_ESP32_WROOM32", "AT360_SIM808_TRACKER_2AI_2DO", "AT360_LILYGO_T_SIM7000G"],
        "default_signals": [
            ("level_percent", "Tank Level", "LEVEL", "%", "tank", 20, 10, 90, 95),
            ("volume_l", "Volume", "LEVEL", "L", "numeric", None, None, None, None),
            ("battery_v", "Battery", "VOLTAGE", "V", "battery", 3.6, 3.4, None, None),
        ],
    },
    "FLOW_TOTALIZER": {
        "code": "FLOW_TOTALIZER", "display_name": "Flow Monitoring & Totalizer",
        "category": "MONITORING", "asset_type": "GENERIC", "icon": "FLOW",
        "description": "Analog or pulse flow measurement, instantaneous rate, totalizer and flow alarms.",
        "badges": ["Analog/Pulse", "Rate", "Totalizer"],
        "boards": ["AT360_ESP32D_EXPANDED", "AT360_ESP32_WROOM32", "AT360_SIM808_TRACKER_2AI_2DO", "AT360_LILYGO_T_SIM7000G"],
        "default_signals": [("flow_rate", "Flow Rate", "FLOW", "L/min", "numeric", None, None, None, None), ("flow_total", "Flow Total", "COUNT", "L", "numeric", None, None, None, None)],
    },
    "PRESSURE_MONITORING": {
        "code": "PRESSURE_MONITORING", "display_name": "Pressure Monitoring",
        "category": "MONITORING", "asset_type": "GENERIC", "icon": "PRESS",
        "description": "Conditioned pressure input with engineering scaling, trends and alarm limits.",
        "badges": ["Analog Input", "Scaling", "Alarms"],
        "boards": ["AT360_ESP32D_EXPANDED", "AT360_ESP32_WROOM32", "AT360_SIM808_TRACKER_2AI_2DO", "AT360_LILYGO_T_SIM7000G"],
        "default_signals": [("pressure", "Pressure", "PRESSURE", "bar", "numeric", None, None, None, None)],
    },
    "TEMPERATURE_MONITORING": {
        "code": "TEMPERATURE_MONITORING", "display_name": "Temperature Monitoring",
        "category": "MONITORING", "asset_type": "GENERIC", "icon": "TEMP",
        "description": "Analog or supported sensor-module temperature monitoring with high and low alarms.",
        "badges": ["Analog/I2C", "High/Low", "Sensor Fault"],
        "boards": ["AT360_ESP32D_EXPANDED", "AT360_ESP32_WROOM32"],
        "default_signals": [("temperature_c", "Temperature", "TEMPERATURE", "°C", "temperature", None, None, 70, 85)],
    },
    "HUMIDITY_MONITORING": {
        "code": "HUMIDITY_MONITORING", "display_name": "Humidity Monitoring",
        "category": "MONITORING", "asset_type": "GENERIC", "icon": "HUM",
        "description": "Humidity sensing, environmental alarms and optional temperature pairing.",
        "badges": ["I2C Sensor", "Environment", "Alarms"],
        "boards": ["AT360_ESP32D_EXPANDED", "AT360_ESP32_WROOM32"],
        "default_signals": [("humidity_percent", "Humidity", "PERCENT", "%", "numeric", None, None, 80, 90)],
    },
    "PUMP_CONTROL": {
        "code": "PUMP_CONTROL", "display_name": "Pump Control & Monitoring",
        "category": "CONTROL", "asset_type": "GENERIC", "icon": "PUMP",
        "description": "Safe pump start/stop, run feedback, interlocks, fault handling and runtime tracking.",
        "badges": ["Safe Output", "Run Feedback", "Interlocks"],
        "boards": ["AT360_ESP32D_EXPANDED", "AT360_ESP32_WROOM32", "AT360_SIM808_TRACKER_2AI_2DO", "AT360_LILYGO_T_SIM7000G"],
        "default_signals": [("pump_run_feedback", "Pump Run Feedback", "STATE", "", "state", None, None, None, None), ("pump_fault", "Pump Fault", "STATE", "", "state", None, None, None, None)],
    },
    "MOTOR_MONITORING": {
        "code": "MOTOR_MONITORING", "display_name": "Motor Monitoring",
        "category": "MONITORING", "asset_type": "GENERIC", "icon": "MOTOR",
        "description": "Run state, start count, runtime, trip feedback and equipment condition.",
        "badges": ["Digital Inputs", "Runtime", "Trips"],
        "boards": ["AT360_ESP32D_EXPANDED", "AT360_ESP32_WROOM32", "AT360_SIM808_TRACKER_2AI_2DO", "AT360_LILYGO_T_SIM7000G"],
        "default_signals": [("motor_run", "Motor Run", "STATE", "", "state", None, None, None, None), ("motor_trip", "Motor Trip", "STATE", "", "state", None, None, None, None)],
    },
    "GATE_LIMIT_MONITORING": {
        "code": "GATE_LIMIT_MONITORING", "display_name": "Gate & Limit Monitoring",
        "category": "CONTROL", "asset_type": "GENERIC", "icon": "GATE",
        "description": "Open/close commands with optional limit switches, position state and safe output control.",
        "badges": ["Open/Close", "Optional Limits", "Safe Outputs"],
        "boards": ["AT360_ESP32D_EXPANDED", "AT360_ESP32_WROOM32"],
        "default_signals": [("gate_open_limit", "Gate Open Limit", "STATE", "", "state", None, None, None, None), ("gate_closed_limit", "Gate Closed Limit", "STATE", "", "state", None, None, None, None)],
    },
    "ALARM_PANEL": {
        "code": "ALARM_PANEL", "display_name": "Alarm Panel",
        "category": "CONTROL", "asset_type": "GENERIC", "icon": "ALARM",
        "description": "Digital zones, alarm state, acknowledgement, output control and event history.",
        "badges": ["Digital Zones", "Events", "Safe Output"],
        "boards": ["AT360_ESP32D_EXPANDED", "AT360_ESP32_WROOM32", "AT360_SIM808_TRACKER_2AI_2DO", "AT360_LILYGO_T_SIM7000G"],
        "default_signals": [("alarm_state", "Alarm State", "STATE", "", "state", None, None, None, None)],
    },
    "PULSE_PRODUCTION_TOTALIZER": {
        "code": "PULSE_PRODUCTION_TOTALIZER", "display_name": "Pulse Counter & Production Totalizer",
        "category": "MONITORING", "asset_type": "GENERIC", "icon": "COUNT",
        "description": "High-speed pulse counting for meters, cycles, production and accumulated totals.",
        "badges": ["Pulse Input", "Count", "Rate"],
        "boards": ["AT360_ESP32D_EXPANDED", "AT360_ESP32_WROOM32"],
        "default_signals": [("production_count", "Production Count", "COUNT", "count", "numeric", None, None, None, None)],
    },
    "BATTERY_POWER": {
        "code": "BATTERY_POWER", "display_name": "Battery & Power Monitoring",
        "category": "MONITORING", "asset_type": "GENERIC", "icon": "POWER",
        "description": "Battery voltage, low battery status, power source and supply-fault monitoring.",
        "badges": ["Battery", "Power State", "Low Alarm"],
        "boards": ["AT360_ESP32D_EXPANDED", "AT360_ESP32_WROOM32", "AT360_SIM808_TRACKER_2AI_2DO", "AT360_LILYGO_T_SIM7000G"],
        "default_signals": [("battery_v", "Battery Voltage", "VOLTAGE", "V", "battery", 3.6, 3.4, None, None)],
    },
    "GPS_ASSET_TRACKING": {
        "code": "GPS_ASSET_TRACKING", "display_name": "GPS Asset Tracking",
        "category": "TRACKING", "asset_type": "TRACKER", "icon": "GPS",
        "description": "Position, speed, heading, route history, stops and geofence-ready tracking.",
        "badges": ["GPS/GNSS", "Route", "Movement"],
        "boards": ["AT360_SIM808_TRACKER_2AI_2DO", "AT360_LILYGO_T_SIM7000G"],
        "default_signals": [("speed_kmh", "Speed", "SPEED", "km/h", "numeric", None, None, 100, 120), ("battery_v", "Battery", "VOLTAGE", "V", "battery", 3.6, 3.4, None, None)],
    },
    "GSM_GPRS_TELEMETRY": {
        "code": "GSM_GPRS_TELEMETRY", "display_name": "GSM/GPRS Telemetry",
        "category": "COMMUNICATIONS", "asset_type": "GENERIC", "icon": "GSM",
        "description": "SIM, signal quality, APN, mobile data session and remote telemetry status.",
        "badges": ["GSM", "GPRS", "Signal"],
        "boards": ["AT360_SIM808_TRACKER_2AI_2DO", "AT360_LILYGO_T_SIM7000G"], "default_signals": [],
    },
    "WIFI_TELEMETRY": {
        "code": "WIFI_TELEMETRY", "display_name": "Wi-Fi Telemetry Node",
        "category": "COMMUNICATIONS", "asset_type": "GENERIC", "icon": "WIFI",
        "description": "Wi-Fi provisioning, RSSI, AssetTrack API telemetry and reconnect diagnostics.",
        "badges": ["Wi-Fi", "API", "RSSI"],
        "boards": ["AT360_ESP32D_EXPANDED", "AT360_ESP32_WROOM32"], "default_signals": [],
    },
    "MQTT_TELEMETRY": {
        "code": "MQTT_TELEMETRY", "display_name": "MQTT Sensor & Control Node",
        "category": "COMMUNICATIONS", "asset_type": "GENERIC", "icon": "MQTT",
        "description": "Publish telemetry, subscribe to approved commands and monitor broker health.",
        "badges": ["MQTT", "Topics", "Commands"],
        "boards": ["AT360_ESP32D_EXPANDED", "AT360_ESP32_WROOM32"], "default_signals": [],
    },
    "RS485_MODBUS_GATEWAY": {
        "code": "RS485_MODBUS_GATEWAY", "display_name": "RS-485 / Modbus Gateway",
        "category": "COMMUNICATIONS", "asset_type": "GENERIC", "icon": "485",
        "description": "Read supported Modbus devices and map registers to AssetTrack 360 tags.",
        "badges": ["RS-485", "Modbus RTU", "Mapping"],
        "boards": ["AT360_ESP32D_EXPANDED"], "default_signals": [],
    },
    "I2C_SENSOR_NODE": {
        "code": "I2C_SENSOR_NODE", "display_name": "I2C Sensor Node",
        "category": "MONITORING", "asset_type": "GENERIC", "icon": "I2C",
        "description": "Connect verified I2C sensors using board-safe pin and address validation.",
        "badges": ["I2C", "Sensors", "Address Check"],
        "boards": ["AT360_ESP32D_EXPANDED", "AT360_ESP32_WROOM32"], "default_signals": [],
    },
    "CUSTOM_DEVICE_PROJECT": {
        "code": "CUSTOM_DEVICE_PROJECT", "display_name": "Custom Device Project",
        "category": "CONTROL", "asset_type": "GENERIC", "icon": "CUSTOM",
        "description": "Combine verified modules, I/O assignments and visual device logic.",
        "badges": ["Modules", "Visual Logic", "Custom Build"],
        "boards": ["AT360_ESP32D_EXPANDED", "AT360_ESP32_WROOM32", "AT360_SIM808_TRACKER_2AI_2DO", "AT360_LILYGO_T_SIM7000G"],
        "default_signals": [],
    },
}


def get_solution_profile(code):
    return SOLUTION_PROFILES.get(str(code or "").strip().upper())


def public_solution_profiles():
    return [SOLUTION_PROFILES[key] for key in SOLUTION_PROFILES]


def compatible_solution_profiles(board_code):
    board_code = str(board_code or "").strip().upper()
    return [p for p in public_solution_profiles() if board_code in p["boards"]]


def validate_solution_selection(board_code, codes):
    selected = []
    for code in dict.fromkeys(str(value or "").strip().upper() for value in codes):
        profile = get_solution_profile(code)
        if not profile or board_code not in profile["boards"]:
            return [], f"Solution profile {code or 'UNKNOWN'} is not supported by the selected board."
        selected.append(profile)
    return selected, None
