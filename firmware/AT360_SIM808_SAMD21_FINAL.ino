/*
  AssetTrack 360 - Maduino Zero SIM808 V3.5 Merged Bench + GSM Firmware
  Final upload-ready baseline for SIM808 SAMD21 profile
  MCU: ATSAMD21G18A
  Board target: Arduino Zero (Native USB Port)

  Confirmed bench map:
    AI1 = A0
    AI2 = A1
    DO1 = D5
    DO2 = D6
    D9  = SIM808 POWER_KEY control

  PC console: Serial @ 115200
  SIM808 modem: Serial1 @ 115200

  Copyright: (c) 2026 JP Van Wyk. All rights reserved.
*/
#include <Arduino.h>
#include <FlashStorage.h>

#define CONSOLE SerialUSB
#define MODEM Serial1
static const uint32_t CONSOLE_BAUD = 115200;
static const uint32_t MODEM_BAUD = 115200;
static const uint8_t PIN_AI1 = A0;
static const uint8_t PIN_AI2 = A1;
static const uint8_t PIN_DO1 = 5;
static const uint8_t PIN_DO2 = 6;
static const uint8_t PIN_SIM808_POWER = 9;
static const uint32_t DEFAULT_PULSE_MS = 1000UL;
static const char FW[] = "AT360-MADUINO-SIM808-V35-SERIALIZED-GNSS-7.6";

struct Config {
  uint32_t marker;
  char apn[48];
  char apnUser[32];
  char apnPass[32];
  char simPin[12];
  char apiHost[96];
  char apiPath[64];
  char deviceUid[96];
  char deviceToken[128];
  char balanceUssd[24];
  char dataUssd[24];
  uint32_t uploadSeconds;
};
FlashStorage(configStore, Config);
Config cfg;
static const uint32_t CFG_MARKER = 0xA7360810;

bool simulationMode = false;
bool do1State = false, do2State = false;
bool simDo1 = false, simDo2 = false;
bool do1PulseMode = false, do2PulseMode = false;
uint32_t do1PulseMs = DEFAULT_PULSE_MS, do2PulseMs = DEFAULT_PULSE_MS;
float simAi1Percent = 0.0f, simAi2Percent = 0.0f;
uint32_t do1Started = 0, do2Started = 0;
uint32_t simDo1Started = 0, simDo2Started = 0;
uint32_t lastStatus = 0, lastUploadMs = 0;
static const uint32_t AUTO_UPLOAD_START_DELAY_MS = 90000UL;
bool autoUpload = false;
float lastAirtimeZar = -1.0f, lastDataMb = -1.0f;
uint32_t lastBalanceCheckMs = 0;
static const uint32_t BALANCE_CHECK_MS = 6UL * 60UL * 60UL * 1000UL;
String lastBalanceRaw;
String consoleLine;
bool gnssPowered = false;
uint32_t modemReadySinceMs = 0;
uint32_t lastGnssPollMs = 0;
static const uint32_t GNSS_POLL_MS = 10000UL;
bool ensureModemReady();
bool ensureGnssPower(bool publish = true);

void emit(const String &key, const String &value) {
  CONSOLE.println(key + "|" + value);
}
void safeCopy(char *dest, size_t size, const String &value) {
  memset(dest, 0, size);
  value.substring(0, size - 1).toCharArray(dest, size);
}
String configured(const char *value) {
  return strlen(value) ? "CONFIGURED" : "NOT_SET";
}
void defaultConfig() {
  memset(&cfg, 0, sizeof(cfg));
  cfg.marker = CFG_MARKER;
  safeCopy(cfg.apiHost, sizeof(cfg.apiHost), "assettrack360.wykiesautomation.co.za");
  safeCopy(cfg.apiPath, sizeof(cfg.apiPath), "/api/v1/ingest");
  safeCopy(cfg.balanceUssd, sizeof(cfg.balanceUssd), "*136#");
  safeCopy(cfg.dataUssd, sizeof(cfg.dataUssd), "*136#");
  cfg.uploadSeconds = 60;
}
void loadConfig() {
  cfg = configStore.read();
  if (cfg.marker != CFG_MARKER) {
    defaultConfig();
    configStore.write(cfg);
  }
}

float rawToVolts(int raw) {
  return raw * 3.3f / 4095.0f;
}
float rawToPercent(int raw) {
  return constrain(raw * 100.0f / 4095.0f, 0.0f, 100.0f);
}
int percentToRaw(float value) {
  return int(constrain(value, 0.0f, 100.0f) * 4095.0f / 100.0f + 0.5f);
}
void forceOutputsOff() {
  digitalWrite(PIN_DO1, LOW);
  digitalWrite(PIN_DO2, LOW);
  do1State = false;
  do2State = false;
}
void setOutput(uint8_t pin, bool &state, uint32_t &started, bool on) {
  if (simulationMode) {
    digitalWrite(pin, LOW);
    state = false;
    return;
  }
  digitalWrite(pin, on ? HIGH : LOW);
  state = on;
  if (on) started = millis();
}

String modemCommand(const String &command, uint32_t timeoutMs = 3000, bool publish = true) {
  while (MODEM.available()) MODEM.read();
  MODEM.println(command);
  String response;
  uint32_t started = millis();
  while (millis() - started < timeoutMs) {
    while (MODEM.available()) response += char(MODEM.read());
    if (response.indexOf("OK") >= 0 || response.indexOf("ERROR") >= 0 || response.indexOf("DOWNLOAD") >= 0) break;
    delay(2);
  }
  response.trim();
  if (publish) emit("AT_RESPONSE", response.length() ? response : "TIMEOUT");
  return response;
}
bool hasOK(const String &response) {
  return response.indexOf("OK") >= 0;
}

String responseLine(const String &response, const String &prefix) {
  int start = response.indexOf(prefix);
  if (start < 0) return "";
  int end = response.indexOf('\n', start);
  String line = end < 0 ? response.substring(start) : response.substring(start, end);
  line.replace("\r", "");
  line.trim();
  return line;
}

String csvField(const String &line, int index) {
  int field = 0, start = 0;
  for (int i = 0; i <= line.length(); i++) {
    if (i == line.length() || line.charAt(i) == ',') {
      if (field == index) return line.substring(start, i);
      field++; start = i + 1;
    }
  }
  return "";
}

struct LiveTelemetry {
  bool gpsRunning = false;
  bool gpsFix = false;
  float latitude = 0;
  float longitude = 0;
  float speedKmh = 0;
  float heading = 0;
  float accuracyM = 15;
  int satellites = 0;
  String gpsTime;
  int gsmCsq = 0;
  float batteryVolts = 0;
  int batteryPercent = 0;
};
LiveTelemetry cachedTelemetry;
bool cachedTelemetryValid = false;

LiveTelemetry readLiveTelemetry(bool publish = true) {
  LiveTelemetry t;
  String csq = modemCommand("AT+CSQ", 3000, false);
  String csqLine = responseLine(csq, "+CSQ:");
  if (csqLine.length()) {
    int colon = csqLine.indexOf(':');
    t.gsmCsq = csvField(csqLine.substring(colon + 1), 0).toInt();
    if (t.gsmCsq == 99) t.gsmCsq = 0;
  }

  String cbc = modemCommand("AT+CBC", 3000, false);
  String cbcLine = responseLine(cbc, "+CBC:");
  if (cbcLine.length()) {
    int colon = cbcLine.indexOf(':');
    String values = cbcLine.substring(colon + 1); values.trim();
    t.batteryPercent = constrain(csvField(values, 1).toInt(), 0, 100);
    t.batteryVolts = csvField(values, 2).toFloat() / 1000.0f;
  }

  if (!gnssPowered) ensureGnssPower(false);
  String gps = modemCommand("AT+CGNSINF", 5000, false);
  String gpsLine = responseLine(gps, "+CGNSINF:");
  if (gpsLine.length()) {
    int colon = gpsLine.indexOf(':');
    String values = gpsLine.substring(colon + 1); values.trim();
    t.gpsRunning = csvField(values, 0).toInt() == 1;
    if (!t.gpsRunning) gnssPowered = false;
    t.gpsFix = csvField(values, 1).toInt() == 1;
    t.gpsTime = csvField(values, 2);
    t.latitude = csvField(values, 3).toFloat();
    t.longitude = csvField(values, 4).toFloat();
    t.speedKmh = max(0.0f, csvField(values, 6).toFloat());
    t.heading = csvField(values, 7).toFloat();
    t.satellites = csvField(values, 14).toInt();
    if (abs(t.latitude) < 0.000001f && abs(t.longitude) < 0.000001f) t.gpsFix = false;
  }

  if (publish) {
    emit("GPS_FIX", t.gpsFix ? "YES" : "NO");
    emit("LATITUDE", String(t.latitude, 6));
    emit("LONGITUDE", String(t.longitude, 6));
    emit("SPEED_KMH", String(t.speedKmh, 1));
    emit("HEADING", String(t.heading, 1));
    emit("GSM_CSQ", String(t.gsmCsq));
    emit("BATTERY_V", String(t.batteryVolts, 3));
    emit("BATTERY_PERCENT", String(t.batteryPercent));
    emit("SATELLITES", String(t.satellites));
    emit("GPS_TIME", t.gpsTime.length() ? t.gpsTime : "NOT_REPORTED");
    emit("GNSS_STATUS", !t.gpsRunning ? "NOT_RUNNING" : t.gpsFix ? "FIXED" : "SEARCHING");
    emit("GNSS_RAW", gpsLine.length() ? gpsLine : "NO_CGNSINF_RESPONSE");
  }
  cachedTelemetry = t;
  cachedTelemetryValid = true;
  lastGnssPollMs = millis();
  return t;
}

bool modemResponding() {
  String response = modemCommand("AT", 1500, false);
  return hasOK(response);
}

void pulseSIM808PowerKey() {
  // Makerfabs V3.5 reference: POWER_KEY is D9, active LOW pulse.
  pinMode(PIN_SIM808_POWER, OUTPUT);
  digitalWrite(PIN_SIM808_POWER, HIGH);  // idle state
  delay(100);
  digitalWrite(PIN_SIM808_POWER, LOW);
  delay(3000);
  digitalWrite(PIN_SIM808_POWER, HIGH);
  emit("MODEM_POWER", "PULSE_SENT");
}

bool ensureModemReady() {
  if (modemResponding()) {
    if (!modemReadySinceMs) modemReadySinceMs = millis();
    emit("MODEM", "READY");
    return true;
  }
  // Stability rule: never toggle the SIM808 POWER_KEY automatically.
  // The modem may already be ON but temporarily busy. A power-key pulse is a toggle
  // and could switch an active modem OFF.
  emit("MODEM", "NOT_RESPONDING_POWER_KEY_NOT_TOUCHED");
  return false;
}

bool ensureGnssPower(bool publish) {
  // Never touch POWER_KEY here. Verify GNSS really reports running state = 1.
  if (!modemResponding()) {
    gnssPowered = false;
    if (publish) emit("GNSS_STATUS", "MODEM_TEMPORARILY_UNAVAILABLE");
    return false;
  }

  String before = modemCommand("AT+CGNSPWR?", 3000, false);
  if (before.indexOf("+CGNSPWR: 1") >= 0) {
    gnssPowered = true;
    if (publish) {
      emit("GNSS_POWER", "ON_VERIFIED");
      emit("GNSS_STATUS_RAW", before);
    }
    return true;
  }

  emit("GNSS_POWER", "START_REQUESTED");
  modemCommand("AT+CGNSPWR=1", 5000, false);
  delay(750);
  String after = modemCommand("AT+CGNSPWR?", 3000, false);
  gnssPowered = after.indexOf("+CGNSPWR: 1") >= 0;

  if (publish) {
    emit("GNSS_POWER", gnssPowered ? "ON_VERIFIED" : "START_FAILED");
    emit("GNSS_STATUS_RAW", after.length() ? after : "NO_RESPONSE");
  }
  return gnssPowered;
}

void readIdentity() {
  if (!ensureModemReady()) { emit("MODEM_IMEI", "NOT_AVAILABLE"); return; }
  String response=modemCommand("AT+GSN",3000,false);String digits;
  for(unsigned int i=0;i<response.length();i++)if(isDigit(response[i]))digits+=response[i];
  emit("MODEM_IMEI",digits.length()>=14?digits:"NOT_AVAILABLE");
}
void checkSIM() {
  if (!ensureModemReady()) {
    emit("SIM_STATUS", "MODEM_NOT_RESPONDING");
    return;
  }
  String response = modemCommand("AT+CPIN?");
  emit("SIM_STATUS", response.indexOf("READY") >= 0 ? "READY" : response);
}
void checkNetwork() {
  if (!ensureModemReady()) {
    emit("NETWORK", "MODEM_NOT_RESPONDING");
    return;
  }
  String response = modemCommand("AT+CREG?");
  bool registered = response.indexOf(",1") >= 0 || response.indexOf(",5") >= 0;
  emit("NETWORK", registered ? "REGISTERED" : "NOT_REGISTERED");
  emit("OPERATOR", responseLine(modemCommand("AT+COPS?", 5000, false), "+COPS:"));
  LiveTelemetry telemetry = readLiveTelemetry(false);
  emit("SIGNAL", String(telemetry.gsmCsq));
}
bool connectGPRS() {
  if (!ensureModemReady()) {
    emit("GPRS", "MODEM_NOT_RESPONDING");
    return false;
  }
  if (!strlen(cfg.apn)) {
    emit("GPRS", "APN_NOT_SET");
    return false;
  }
  modemCommand("AT+CGATT=1", 15000);
  modemCommand("AT+SAPBR=3,1,\"CONTYPE\",\"GPRS\"");
  modemCommand(String("AT+SAPBR=3,1,\"APN\",\"") + cfg.apn + "\"");
  if (strlen(cfg.apnUser)) modemCommand(String("AT+SAPBR=3,1,\"USER\",\"") + cfg.apnUser + "\"");
  if (strlen(cfg.apnPass)) modemCommand(String("AT+SAPBR=3,1,\"PWD\",\"") + cfg.apnPass + "\"");
  String openResult = modemCommand("AT+SAPBR=1,1", 30000);
  String bearer = modemCommand("AT+SAPBR=2,1", 6000, false);
  bool ok = bearer.indexOf("+SAPBR: 1,1") >= 0 && bearer.indexOf("0.0.0.0") < 0 && bearer.indexOf("ERROR") < 0;
  emit("GPRS", ok ? "ATTACHED" : "FAILED");
  emit("GPRS_IP", bearer.length() ? bearer : "NO_RESPONSE");
  return ok;
}

String jsonPayload() {
  int raw1 = simulationMode ? percentToRaw(simAi1Percent) : analogRead(PIN_AI1);
  int raw2 = simulationMode ? percentToRaw(simAi2Percent) : analogRead(PIN_AI2);
  float p1 = rawToPercent(raw1), p2 = rawToPercent(raw2);
  LiveTelemetry t = readLiveTelemetry(true);
  String body = "{\"device_id\":\"" + String(cfg.deviceUid) + "\",\"sequence\":\"gsm-" + String(millis()) + "\",\"firmware\":\"" + String(FW) + "\",\"measurements\":[" +
    "{\"point\":\"analog_1\",\"value\":" + String(p1, 2) + ",\"quality\":\"GOOD\"}," +
    "{\"point\":\"analog_2\",\"value\":" + String(p2, 2) + ",\"quality\":\"GOOD\"}," +
    "{\"point\":\"analog_1_volts\",\"value\":" + String(rawToVolts(raw1), 3) + ",\"quality\":\"GOOD\"}," +
    "{\"point\":\"analog_2_volts\",\"value\":" + String(rawToVolts(raw2), 3) + ",\"quality\":\"GOOD\"}," +
    "{\"point\":\"battery_v\",\"value\":" + String(t.batteryVolts, 3) + ",\"quality\":\"GOOD\"}," +
    "{\"point\":\"digital_output_1_feedback\",\"value\":" + String(do1State ? 1 : 0) + ",\"quality\":\"GOOD\"}," +
    "{\"point\":\"digital_output_2_feedback\",\"value\":" + String(do2State ? 1 : 0) + ",\"quality\":\"GOOD\"}," +
    "{\"point\":\"gps_fix\",\"value\":" + String(t.gpsFix ? 1 : 0) + ",\"quality\":\"GOOD\"}," +
    "{\"point\":\"gsm_signal\",\"value\":" + String(t.gsmCsq) + ",\"quality\":\"GOOD\"}," +
    "{\"point\":\"speed_kmh\",\"value\":" + String(t.speedKmh, 1) + ",\"quality\":\"GOOD\"}";
  if(lastAirtimeZar>=0)body += ",{\"point\":\"airtime_balance_zar\",\"value\":" + String(lastAirtimeZar,2) + ",\"quality\":\"GOOD\"}";
  if(lastDataMb>=0)body += ",{\"point\":\"data_remaining_mb\",\"value\":" + String(lastDataMb,1) + ",\"quality\":\"GOOD\"}";
  body += "]";
  if (t.gpsFix) {
    body += ",\"location\":{\"latitude\":" + String(t.latitude, 6) + ",\"longitude\":" + String(t.longitude, 6) + ",\"speed_kmh\":" + String(t.speedKmh, 1) + ",\"heading\":" + String(t.heading, 1) + ",\"accuracy_m\":" + String(t.accuracyM, 1) + "}";
  }
  body += "}";
  return body;
}

bool sendGSM() {
  if (!strlen(cfg.deviceUid) || !strlen(cfg.deviceToken)) {
    emit("UPLOAD", "DEVICE_IDENTITY_NOT_SET");
    return false;
  }
  if (!connectGPRS()) return false;
  modemCommand("AT+HTTPTERM", 2000, false);
  if (!hasOK(modemCommand("AT+HTTPINIT", 5000))) {
    emit("UPLOAD", "HTTP_INIT_FAILED");
    return false;
  }
  modemCommand("AT+HTTPPARA=\"CID\",1");
  String ssl = modemCommand("AT+HTTPSSL=1", 5000);
  if (!hasOK(ssl)) {
    emit("UPLOAD", "HTTPS_UNSUPPORTED_BY_MODEM_FIRMWARE");
    modemCommand("AT+HTTPTERM", 2000, false);
    return false;
  }
  String url = "https://" + String(cfg.apiHost) + String(cfg.apiPath);
  modemCommand(String("AT+HTTPPARA=\"URL\",\"") + url + "\"");
  modemCommand("AT+HTTPPARA=\"CONTENT\",\"application/json\"");
  modemCommand(String("AT+HTTPPARA=\"USERDATA\",\"Authorization: Bearer ") + cfg.deviceToken + "\"");
  String body = jsonPayload();
  String ready = modemCommand("AT+HTTPDATA=" + String(body.length()) + ",15000", 7000);
  if (ready.indexOf("DOWNLOAD") < 0) {
    emit("UPLOAD", "HTTP_DATA_NOT_READY");
    modemCommand("AT+HTTPTERM", 2000, false);
    return false;
  }
  MODEM.print(body);
  delay(1200);
  String result = modemCommand("AT+HTTPACTION=1", 40000, false);
  emit("HTTP_ACTION", result.length() ? result : "NO_RESPONSE");
  bool accepted = result.indexOf(",200,") >= 0 || result.indexOf(",201,") >= 0 || result.indexOf(",202,") >= 0;
  emit("UPLOAD", accepted ? "ACCEPTED" : "FAILED");
  modemCommand("AT+HTTPTERM", 3000, false);
  return accepted;
}

float firstNumberAfter(const String &text, const String &marker) {
  String upper=text; upper.toUpperCase(); String target=marker; target.toUpperCase();
  int pos=upper.indexOf(target); if(pos<0)return -1.0f; pos+=target.length();
  while(pos<(int)text.length() && !(isDigit(text[pos]) || text[pos]=='.' || text[pos]==','))pos++;
  String n; while(pos<(int)text.length() && (isDigit(text[pos]) || text[pos]=='.' || text[pos]==',')){char c=text[pos++];if(c!=',')n+=c;}
  return n.length()?n.toFloat():-1.0f;
}
void parseBalanceResponse(const String &response) {
  lastBalanceRaw=response;
  float airtime=firstNumberAfter(response,"R");
  float data=firstNumberAfter(response,"DATA");
  String upper=response; upper.toUpperCase();
  if(data < 0) data=firstNumberAfter(response,"MB");
  if(data >= 0 && upper.indexOf("GB")>=0 && upper.indexOf("MB")<0)data*=1024.0f;
  if(airtime>=0)lastAirtimeZar=airtime;
  if(data>=0)lastDataMb=data;
  emit("AIRTIME_ZAR",lastAirtimeZar>=0?String(lastAirtimeZar,2):"NOT_PARSED");
  emit("DATA_MB",lastDataMb>=0?String(lastDataMb,1):"NOT_PARSED");
}
String runUSSDQuery(const char *code, const String &label) {
  if (!strlen(code)) { emit(label, "USSD_CODE_NOT_SET"); return ""; }
  modemCommand("AT+CUSD=2",2000,false);
  modemCommand("AT+CMGF=1",2000,false);
  String result=modemCommand(String("AT+CUSD=1,\"")+code+"\",15",30000,false);
  delay(1500);
  while(MODEM.available())result+=char(MODEM.read());
  result.trim(); emit(label,result.length()?result:"NO_RESPONSE");
  parseBalanceResponse(result); return result;
}
void checkBalances() {
  if(!ensureModemReady())return;
  runUSSDQuery(strlen(cfg.dataUssd)?cfg.dataUssd:cfg.balanceUssd,"BALANCE_DETAIL");
  lastBalanceCheckMs=millis();
}
void runUSSD(const char *code, const String &label) {
  if (!strlen(code)) {
    emit(label, "USSD_CODE_NOT_SET");
    return;
  }
  modemCommand("AT+CUSD=1", 3000, false);
  String result = modemCommand(String("AT+CUSD=1,\"") + code + "\",15", 25000, false);
  emit(label, result.length() ? result : "NO_RESPONSE");
  parseBalanceResponse(result);
}

void printStatus() {
  int raw1 = simulationMode ? percentToRaw(simAi1Percent) : analogRead(PIN_AI1);
  int raw2 = simulationMode ? percentToRaw(simAi2Percent) : analogRead(PIN_AI2);
  emit("FIRMWARE", FW);
  emit("PROFILE", "AT360_SIM808_TRACKER_2AI_2DO");
  emit("MODE", simulationMode ? "Simulation" : "Live");
  emit("AI1_RAW", String(raw1));
  emit("AI1_VOLTS", String(rawToVolts(raw1), 3));
  emit("AI1_PERCENT", String(rawToPercent(raw1), 1));
  emit("AI2_RAW", String(raw2));
  emit("AI2_VOLTS", String(rawToVolts(raw2), 3));
  emit("AI2_PERCENT", String(rawToPercent(raw2), 1));
  emit("DO1_FEEDBACK", (simulationMode ? simDo1 : do1State) ? "ON" : "OFF");
  emit("DO2_FEEDBACK", (simulationMode ? simDo2 : do2State) ? "ON" : "OFF");
  emit("DO1_MODE", do1PulseMode ? "PULSE" : "LATCHED");
  emit("DO2_MODE", do2PulseMode ? "PULSE" : "LATCHED");
  // READ_STATUS is intentionally modem-free. It must never overlap a GNSS/GSM AT transaction.
  if (!simulationMode && cachedTelemetryValid) {
    emit("GPS_FIX", cachedTelemetry.gpsFix ? "YES" : "NO");
    emit("LATITUDE", String(cachedTelemetry.latitude, 6));
    emit("LONGITUDE", String(cachedTelemetry.longitude, 6));
    emit("SPEED_KMH", String(cachedTelemetry.speedKmh, 1));
    emit("HEADING", String(cachedTelemetry.heading, 1));
    emit("GSM_CSQ", String(cachedTelemetry.gsmCsq));
    emit("BATTERY_V", String(cachedTelemetry.batteryVolts, 3));
    emit("BATTERY_PERCENT", String(cachedTelemetry.batteryPercent));
    emit("SATELLITES", String(cachedTelemetry.satellites));
    emit("GPS_TIME", cachedTelemetry.gpsTime.length() ? cachedTelemetry.gpsTime : "NOT_REPORTED");
  } else if (!simulationMode) {
    emit("GPS_FIX", "NO");
    emit("GNSS_STATUS", "WAITING_FOR_READ_TRACKING");
  }
  emit("APN", configured(cfg.apn));
  emit("DEVICE_UID", configured(cfg.deviceUid));
  emit("DEVICE_TOKEN", configured(cfg.deviceToken));
  emit("UPLOAD_INTERVAL", String(cfg.uploadSeconds));
  emit("PIN_MAP", "AI1=A0;AI2=A1;DO1=D5;DO2=D6;D9=SIM808_POWER_KEY");
}

void saveField(const String &key, const String &value) {
  if (key == "APN") safeCopy(cfg.apn, sizeof(cfg.apn), value);
  else if (key == "APN_USER") safeCopy(cfg.apnUser, sizeof(cfg.apnUser), value);
  else if (key == "APN_PASS") safeCopy(cfg.apnPass, sizeof(cfg.apnPass), value);
  else if (key == "SIM_PIN") safeCopy(cfg.simPin, sizeof(cfg.simPin), value);
  else if (key == "DEVICE_UID") safeCopy(cfg.deviceUid, sizeof(cfg.deviceUid), value);
  else if (key == "DEVICE_TOKEN") safeCopy(cfg.deviceToken, sizeof(cfg.deviceToken), value);
  else if (key == "BALANCE_USSD") safeCopy(cfg.balanceUssd, sizeof(cfg.balanceUssd), value);
  else if (key == "DATA_USSD") safeCopy(cfg.dataUssd, sizeof(cfg.dataUssd), value);
  else if (key == "UPLOAD_SECONDS") cfg.uploadSeconds = constrain(value.toInt(), 30, 86400);
  else {
    emit("SET", "UNKNOWN_FIELD");
    return;
  }
  configStore.write(cfg);
  autoUpload = strlen(cfg.deviceUid) && strlen(cfg.deviceToken) && strlen(cfg.apn);
  emit("SET", key + "_SAVED");
}

void commandOutput(uint8_t channel, bool on, bool pulse = false) {
  if (simulationMode) {
    if (channel == 1) {
      simDo1 = true;
      simDo1Started = pulse ? millis() : 0;
    } else {
      simDo2 = true;
      simDo2Started = pulse ? millis() : 0;
    }
    emit("SIM_OUTPUT_STATE", "DO" + String(channel) + "=" + (on ? "ON" : "OFF"));
    return;
  }
  if (channel == 1) setOutput(PIN_DO1, do1State, do1Started, on);
  else setOutput(PIN_DO2, do2State, do2Started, on);
  emit("OUTPUT_STATE", "DO" + String(channel) + "=" + (on ? "ON" : "OFF"));
}

void handleCommand(String command) {
  command.trim();
  if (!command.length()) return;
  if (command == "HELLO" || command == "READ_STATUS" || command == "READ_IO") printStatus();
  else if (command == "MODE_LIVE") {
    simulationMode = false;
    simDo1 = simDo2 = false;
    forceOutputsOff();
    emit("MODE", "Live");
  } else if (command == "MODE_SIMULATION") {
    simulationMode = true;
    forceOutputsOff();
    simDo1 = simDo2 = false;
    emit("MODE", "Simulation");
  } else if (command.startsWith("SIM_AI1=")) {
    simAi1Percent = constrain(command.substring(8).toFloat(), 0.0f, 100.0f);
    emit("SIM_SAVED", "AI1");
  } else if (command.startsWith("SIM_AI2=")) {
    simAi2Percent = constrain(command.substring(8).toFloat(), 0.0f, 100.0f);
    emit("SIM_SAVED", "AI2");
  } else if (command == "DO1_ON") commandOutput(1, true, false);
  else if (command == "DO2_ON") commandOutput(2, true, false);
  else if (command == "DO1_PULSE") commandOutput(1, true, true);
  else if (command == "DO2_PULSE") commandOutput(2, true, true);
  else if (command == "DO1_OFF") {
    simDo1 = false;
    setOutput(PIN_DO1, do1State, do1Started, false);
    emit("OUTPUT_STATE", "DO1=OFF");
  } else if (command == "DO2_OFF") {
    simDo2 = false;
    setOutput(PIN_DO2, do2State, do2Started, false);
    emit("OUTPUT_STATE", "DO2=OFF");
  } else if (command == "ALL_OFF") {
    simDo1 = simDo2 = false;
    forceOutputsOff();
    emit("OUTPUT_STATE", "ALL=OFF");
  } else if (command == "READ_TRACKING" || command == "CHECK_GPS") {
    emit("MODEM_TRANSACTION", "TRACKING_BEGIN");
    if (ensureGnssPower(true)) readLiveTelemetry(true);
    else emit("GNSS_STATUS", "START_NOT_VERIFIED");
    emit("MODEM_TRANSACTION", "TRACKING_END");
  } else if (command == "GNSS_RESTART") {
    modemCommand("AT+CGNSPWR=0", 3000, false);
    delay(500);
    gnssPowered = false;
    ensureGnssPower(true);
    emit("GNSS_STATUS", "RESTARTED_SEARCHING");
  }
  else if (command == "MODEM_POWER_PULSE") {
    emit("MODEM_POWER", "MANUAL_PULSE_REQUESTED");
    pulseSIM808PowerKey();
    emit("MODEM", "MANUAL_START_WAIT_16_SECONDS");
    delay(16000);
    bool ready = modemResponding();
    if (ready) modemReadySinceMs = millis();
    emit("MODEM", ready ? "READY" : "NOT_RESPONDING_AFTER_MANUAL_PULSE");
  }
  else if (command == "READ_IDENTITY") readIdentity();
  else if (command == "CHECK_SIM") checkSIM();
  else if (command == "CHECK_NETWORK") checkNetwork();
  else if (command == "CONNECT_GPRS") connectGPRS();
  else if (command == "SEND_GSM") sendGSM();
  else if (command == "CHECK_BALANCE") checkBalances();
  else if (command == "CHECK_DATA") checkBalances();
  else if (command == "FULL_GSM_TEST") {
    checkSIM();
    checkNetwork();
    if (connectGPRS()) sendGSM();
  } else if (command == "AUTO_ON") {
    autoUpload = true;
    lastUploadMs = millis();
    emit("AUTO_UPLOAD", "ON");
  } else if (command == "AUTO_OFF") {
    autoUpload = false;
    emit("AUTO_UPLOAD", "OFF");
  } else if (command.startsWith("SET|")) {
    int separator = command.indexOf('|', 4);
    if (separator > 4) saveField(command.substring(4, separator), command.substring(separator + 1));
    else emit("SET", "INVALID_FORMAT");
  } else emit("UNKNOWN_COMMAND", command);
}

void setup() {
  pinMode(PIN_AI1, INPUT);
  pinMode(PIN_AI2, INPUT);
  pinMode(PIN_DO1, OUTPUT);
  pinMode(PIN_DO2, OUTPUT);
  pinMode(PIN_SIM808_POWER, OUTPUT);
  digitalWrite(PIN_SIM808_POWER, HIGH);  // POWER_KEY idle state
  forceOutputsOff();
  analogReadResolution(12);
  CONSOLE.begin(CONSOLE_BAUD);
  MODEM.begin(MODEM_BAUD);
  loadConfig();
  uint32_t started = millis();
  while (!CONSOLE && millis() - started < 8000UL) delay(10);
  delay(500);
  emit("AT360_READY", FW);
  emit("BOARD", "MADUINO_ZERO_SIM808_V35_SAMD21");
  emit("SAFETY", "DO1_DO2_DEFAULT_OFF;LATCH_OR_PULSE;SIMULATION_PHYSICAL_LOCKOUT;D9_SIM808_POWER_KEY");
  emit("MODEM_POWER_POLICY", "MANUAL_POWER_KEY_ONLY");
  if (modemResponding()) {
    emit("MODEM", "READY_AT_STARTUP");
    ensureGnssPower(true);
  } else {
    emit("MODEM", "NOT_RESPONDING_POWER_KEY_NOT_TOUCHED");
    emit("GNSS_STATUS", "WAITING_FOR_MODEM");
  }
  lastGnssPollMs = millis();
  lastBalanceCheckMs = millis() - BALANCE_CHECK_MS + 60000UL;
  autoUpload = strlen(cfg.deviceUid) && strlen(cfg.deviceToken) && strlen(cfg.apn);
  lastUploadMs = millis();
  emit("AUTO_UPLOAD_START_DELAY", "90_SECONDS");
  emit("PROVISIONING_STATE", autoUpload ? "PROVISIONED_AUTO_UPLOAD_ON" : "UNPROVISIONED");
  printStatus();
}

void loop() {
  while (CONSOLE.available()) {
    char c = CONSOLE.read();
    if (c == '\n') {
      handleCommand(consoleLine);
      consoleLine = "";
    } else if (c != '\r') {
      if (consoleLine.length() < 240) consoleLine += c;
      else { consoleLine = ""; emit("COMMAND", "BUFFER_RESET"); }
    }
  }
  if (do1State && do1Started && millis() - do1Started >= do1PulseMs) {
    setOutput(PIN_DO1, do1State, do1Started, false);
    emit("OUTPUT_STATE", "DO1=OFF");
  }
  if (do2State && do2Started && millis() - do2Started >= do2PulseMs) {
    setOutput(PIN_DO2, do2State, do2Started, false);
    emit("OUTPUT_STATE", "DO2=OFF");
  }
  if (simDo1 && simDo1Started && millis() - simDo1Started >= do1PulseMs) {
    simDo1 = false;
    emit("SIM_OUTPUT_STATE", "DO1=OFF");
  }
  if (simDo2 && simDo2Started && millis() - simDo2Started >= do2PulseMs) {
    simDo2 = false;
    emit("SIM_OUTPUT_STATE", "DO2=OFF");
  }
  // GNSS/GSM modem reads are serialized through READ_TRACKING from the HMI.
  // No autonomous modem polling here, preventing overlapping AT transactions.
  if (!simulationMode && millis() - lastBalanceCheckMs >= BALANCE_CHECK_MS) checkBalances();
  if (autoUpload && millis() >= AUTO_UPLOAD_START_DELAY_MS && millis() - lastUploadMs >= cfg.uploadSeconds * 1000UL) {
    lastUploadMs = millis();
    if (modemResponding()) sendGSM();
    else emit("UPLOAD", "SKIPPED_MODEM_NOT_READY_NO_REPULSE");
  }
  delay(5);
}
