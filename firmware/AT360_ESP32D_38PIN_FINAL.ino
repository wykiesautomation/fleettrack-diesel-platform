/*
  AssetTrack 360 ESP32-D 38-pin Expanded Remote I/O
  Board: ESP32 Dev Module, 38-pin ESP-32D
  Copyright: (c) 2026 JP Van Wyk. All rights reserved.

  Expanded production mapping:
    AI1 GPIO34, AI2 GPIO35, AI3 GPIO36, AI4 GPIO39 - ADC1 input-only, protected 0-3.3 V
    DI1 GPIO4, DI2 GPIO13, DI3 GPIO18, DI4 GPIO19 - active LOW
    P1 GPIO26, P2 GPIO27 - falling-edge counters
    DO1 GPIO25, DO2 GPIO21, DO3 GPIO22, DO4 GPIO23 - isolated drivers/relays
    Local Arm GPIO32 - active LOW to GND
    Wi-Fi status LED GPIO33

  Every output supports latched ON, latched OFF, and one-second pulse.
  Outputs start safely OFF after restart. Simulation never energises physical outputs.
*/
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Preferences.h>

const char *FW="1.6.0-esp32d-expanded-4ai-4di-4do";
const char *INGEST_URL="https://assettrack360.wykiesautomation.co.za/api/v1/ingest";
const uint8_t AI_PINS[4]={34,35,36,39};
const uint8_t DI_PINS[4]={4,13,18,19};
const uint8_t PULSE_PINS[2]={26,27};
const uint8_t DO_PINS[4]={25,21,22,23};
const uint8_t ARM=32,LED=33;
Preferences prefs;
portMUX_TYPE pulseMux=portMUX_INITIALIZER_UNLOCKED;
volatile uint32_t livePulses[2]={0,0};
String ssid="",wifiPw="",deviceUid="",deviceToken="";
uint32_t sequenceNo=0,lastSend=0,lastRetry=0,uploadSeconds=30;
uint32_t outputStarted[4]={0,0,0,0};
bool outputOn[4]={false,false,false,false};
bool outputPulseActive[4]={false,false,false,false};
bool simulation=false,autoUpload=true,wifiScanActive=false;
uint32_t wifiScanStarted=0;
float simAnalogPercent[4]={0,0,0,0};
float simAnalogVolts[4]={0,0,0,0};
int simDigital[4]={0,0,0,0};
int simOutput[4]={0,0,0,0};
int simArm=0;
uint32_t simPulses[2]={0,0};
void IRAM_ATTR pulseISR1(){portENTER_CRITICAL_ISR(&pulseMux);livePulses[0]++;portEXIT_CRITICAL_ISR(&pulseMux);}
void IRAM_ATTR pulseISR2(){portENTER_CRITICAL_ISR(&pulseMux);livePulses[1]++;portEXIT_CRITICAL_ISR(&pulseMux);}
uint32_t pulseCount(uint8_t index){portENTER_CRITICAL(&pulseMux);uint32_t v=livePulses[index];portEXIT_CRITICAL(&pulseMux);return v;}
bool armed(){return digitalRead(ARM)==LOW;}
void setOutput(uint8_t index,bool on,bool pulse=false){if(index>=4)return;digitalWrite(DO_PINS[index],on?HIGH:LOW);outputOn[index]=on;outputPulseActive[index]=on&&pulse;outputStarted[index]=on?millis():0;}
void forceAllOutputsOff(){for(uint8_t i=0;i<4;i++){digitalWrite(DO_PINS[i],LOW);outputOn[i]=false;outputPulseActive[i]=false;outputStarted[i]=0;simOutput[i]=0;}}
String macId(){String v=WiFi.macAddress();v.replace(":","");return v;}
String esc(String v){v.replace("\\","\\\\");v.replace("\"","\\\"");return v;}
void putS(const char*k,const String&v){prefs.begin("at360",false);prefs.putString(k,v);prefs.end();}
void saveSeq(){prefs.begin("at360",false);prefs.putUInt("seq",sequenceNo);prefs.end();}
void loadCfg(){prefs.begin("at360",true);ssid=prefs.getString("ssid","");wifiPw=prefs.getString("wifi_pw","");deviceUid=prefs.getString("uid","");deviceToken=prefs.getString("token","");sequenceNo=prefs.getUInt("seq",0);uploadSeconds=prefs.getUInt("upload_s",30);autoUpload=prefs.getBool("auto_up",true);prefs.end();if(!deviceUid.length())deviceUid="AT360-ESP32D-"+macId();}

void scanWifi(){
 if(wifiScanActive){Serial.println("WIFI_SCAN_BUSY|1");return;}
 Serial.println("WIFI_SCAN_PREPARE|1");
 WiFi.scanDelete();
 WiFi.setAutoReconnect(false);
 WiFi.disconnect(false,false);
 delay(250);
 WiFi.mode(WIFI_OFF);
 delay(250);
 WiFi.mode(WIFI_STA);
 delay(500);
 int rc=WiFi.scanNetworks(true,true,false,300);
 if(rc==WIFI_SCAN_FAILED){
  Serial.println("WIFI_SCAN_RETRY|1");
  WiFi.scanDelete();delay(500);WiFi.mode(WIFI_STA);delay(500);
  rc=WiFi.scanNetworks(true,true,false,500);
 }
 if(rc==WIFI_SCAN_FAILED){
  WiFi.setAutoReconnect(true);
  Serial.println("WIFI_SCAN_FAILED|START_FAILED_AFTER_RETRY");
  return;
 }
 wifiScanActive=true;wifiScanStarted=millis();
 Serial.println("WIFI_SCAN_BEGIN|ASYNC");
}
void serviceWifiScan(){
 if(!wifiScanActive)return;
 int n=WiFi.scanComplete();
 if(n==WIFI_SCAN_RUNNING){
  if(millis()-wifiScanStarted>15000){WiFi.scanDelete();wifiScanActive=false;Serial.println("WIFI_SCAN_FAILED|TIMEOUT");}
  return;
 }
 wifiScanActive=false;WiFi.setAutoReconnect(true);
 if(n<0){Serial.println("WIFI_SCAN_FAILED|"+String(n));WiFi.scanDelete();return;}
 for(int i=0;i<n;i++){
  String name=WiFi.SSID(i);name.replace("|"," ");
  if(name.length())Serial.printf("WIFI_RESULT|%s|%d|%d|%d\n",name.c_str(),WiFi.RSSI(i),(int)WiFi.encryptionType(i),WiFi.channel(i));
 }
 Serial.printf("WIFI_SCAN_END|%d\n",n);
 WiFi.scanDelete();
 if(WiFi.status()==WL_CONNECTED)Serial.println("WIFI_CONNECTED|"+WiFi.localIP().toString()+"|"+String(WiFi.RSSI()));
 else Serial.println("WIFI_STATUS|OFFLINE_READY_FOR_SELECTION");
}
void connectWifi(){
 if(!ssid.length()){Serial.println("WIFI_FAILED|SSID_MISSING");return;}
 WiFi.setAutoReconnect(false);
 WiFi.disconnect(true,false);
 delay(500);
 WiFi.mode(WIFI_STA);
 delay(150);
 Serial.println("WIFI_CONNECTING|"+ssid);
 WiFi.begin(ssid.c_str(),wifiPw.c_str());
 uint32_t t=millis();
 while(WiFi.status()!=WL_CONNECTED&&millis()-t<20000)delay(250);
 if(WiFi.status()==WL_CONNECTED){WiFi.setAutoReconnect(true);lastRetry=millis();Serial.println("WIFI_CONNECTED|"+WiFi.localIP().toString()+"|"+String(WiFi.RSSI()));}
 else{int reason=(int)WiFi.status();WiFi.disconnect(false,false);WiFi.setAutoReconnect(true);lastRetry=millis();Serial.println("WIFI_FAILED|"+String(reason));}
}
void maintainWifi(){
 if(WiFi.status()==WL_CONNECTED||!ssid.length()||millis()-lastRetry<30000)return;
 lastRetry=millis();
 WiFi.disconnect(false,false);
 delay(100);
 WiFi.begin(ssid.c_str(),wifiPw.c_str());
 Serial.println("WIFI_RETRY|"+ssid);
}
float liveVolts(uint8_t index){return (analogRead(AI_PINS[index])/4095.0f)*3.30f;}
float livePercent(uint8_t index){return constrain(liveVolts(index)/3.30f*100.0f,0.0f,100.0f);}
void printIo(){
 Serial.println("IO_BEGIN");
 Serial.println("MODE|"+String(simulation?"Simulation":"Live"));
 for(uint8_t i=0;i<4;i++){
  float volts=simulation?simAnalogVolts[i]:liveVolts(i);
  float percent=simulation?simAnalogPercent[i]:livePercent(i);
  int raw=simulation?(int)(volts/3.3f*4095.0f):analogRead(AI_PINS[i]);
  Serial.println("AI"+String(i+1)+"_RAW|"+String(raw));
  Serial.println("AI"+String(i+1)+"_VOLTS|"+String(volts,3));
  Serial.println("AI"+String(i+1)+"_PERCENT|"+String(percent,1));
 }
 for(uint8_t i=0;i<4;i++)Serial.println("DI"+String(i+1)+"|"+String((simulation?simDigital[i]:(digitalRead(DI_PINS[i])==LOW))?"ON":"OFF"));
 for(uint8_t i=0;i<2;i++)Serial.println("PULSE"+String(i+1)+"_COUNT|"+String(simulation?simPulses[i]:pulseCount(i)));
 Serial.println("LOCAL_ARM|"+String((simulation?simArm:armed())?"ARMED":"NOT_ARMED"));
 for(uint8_t i=0;i<4;i++){
  int value=simulation?simOutput[i]:outputOn[i];
  Serial.println("DO"+String(i+1)+"_FEEDBACK|"+String(value?"ON":"OFF"));
  Serial.println("DO"+String(i+1)+"_MODE|"+String(outputPulseActive[i]?"PULSE_ACTIVE":"LATCHED"));
 }
 Serial.println("IO_END");
}
void showCfg(){Serial.println("CONFIG_BEGIN");Serial.println("FIRMWARE|"+String(FW));Serial.println("DEVICE_UID|"+deviceUid);Serial.println("SSID|"+ssid);Serial.println("WIFI_PASSWORD|"+String(wifiPw.length()?"SET":"MISSING"));Serial.println("WIFI_STATUS|"+String(WiFi.status()==WL_CONNECTED?"ONLINE":"OFFLINE"));Serial.println("IP_ADDRESS|"+(WiFi.status()==WL_CONNECTED?WiFi.localIP().toString():"-"));Serial.println("RSSI|"+String(WiFi.status()==WL_CONNECTED?WiFi.RSSI():0));Serial.println("DEVICE_TOKEN|"+String(deviceToken.length()?"SET":"MISSING"));Serial.println("MODE|"+String(simulation?"Simulation":"Live"));Serial.println("AUTO_UPLOAD_STATUS|"+String(autoUpload?"ON":"OFF"));Serial.println("CONFIG_END");printIo();}
String telemetry(){
 sequenceNo++;saveSeq();String uniqueSequence=macId()+"-"+String(sequenceNo);String quality=simulation?"SIMULATED":"GOOD";
 String j="{\"device_id\":\""+esc(deviceUid)+"\",\"sequence\":\""+uniqueSequence+"\",\"firmware\":\""+FW+"\",\"measurements\":[";
 bool first=true;
 #define ADD_MEASUREMENT(point,value) do{if(!first)j+=",";first=false;j+="{\"point\":\""+String(point)+"\",\"value\":"+String(value)+",\"quality\":\""+quality+"\"}";}while(0)
 for(uint8_t i=0;i<4;i++){
  float volts=simulation?simAnalogVolts[i]:liveVolts(i);float percent=simulation?simAnalogPercent[i]:livePercent(i);
  ADD_MEASUREMENT("analog_"+String(i+1),String(percent,2));
  ADD_MEASUREMENT("analog_"+String(i+1)+"_volts",String(volts,3));
 }
 for(uint8_t i=0;i<4;i++)ADD_MEASUREMENT("digital_"+String(i+1),String(simulation?simDigital[i]:(digitalRead(DI_PINS[i])==LOW)));
 for(uint8_t i=0;i<2;i++)ADD_MEASUREMENT("pulse_"+String(i+1)+"_count",String(simulation?simPulses[i]:pulseCount(i)));
 for(uint8_t i=0;i<4;i++)ADD_MEASUREMENT("digital_output_"+String(i+1)+"_feedback",String(simulation?simOutput[i]:outputOn[i]));
 ADD_MEASUREMENT("local_arm_status",String(simulation?simArm:armed()));
 ADD_MEASUREMENT("wifi_rssi",String(WiFi.status()==WL_CONNECTED?WiFi.RSSI():0));
 ADD_MEASUREMENT("simulation_mode",String(simulation?1:0));
 #undef ADD_MEASUREMENT
 j+="]}";return j;
}
void postTelemetryBody(const String &body){
 if(WiFi.status()!=WL_CONNECTED){Serial.println("SEND_BLOCKED|WIFI_OFFLINE");return;}
 if(!deviceToken.length()){Serial.println("SEND_BLOCKED|DEVICE_TOKEN_MISSING");return;}
 WiFiClientSecure c;c.setInsecure();HTTPClient h;
 if(!h.begin(c,INGEST_URL)){Serial.println("TELEMETRY_STATUS|-1");return;}
 h.addHeader("Content-Type","application/json");h.addHeader("Authorization","Bearer "+deviceToken);
 h.setConnectTimeout(3000);h.setTimeout(5000);
 uint32_t started=millis();int code=h.POST(body);String response=code>0?h.getString():"";h.end();
 Serial.println("TELEMETRY_STATUS|"+String(code));
 Serial.println("UPLOAD_MS|"+String(millis()-started));
 if(response.length())Serial.println("TELEMETRY_RESPONSE|"+response);
}
void sendTelemetry(){postTelemetryBody(telemetry());}

void printIdentity(){Serial.println("BOARD_ID|"+macId());Serial.println("DEVICE_UID|"+deviceUid);Serial.println("FIRMWARE|"+String(FW));}
void command(String x){
 x.trim();if(!x.length())return;
 if(x=="HELLO"){Serial.println("AT360_READY|"+String(FW)+"|"+macId());printIdentity();}
 else if(x=="READ_IDENTITY")printIdentity();
 else if(x=="SCAN_WIFI")scanWifi();
 else if(x.startsWith("SET_SSID=")){ssid=x.substring(9);putS("ssid",ssid);Serial.println("SAVED|SSID");}
 else if(x.startsWith("SET_WIFI_PASSWORD=")){wifiPw=x.substring(18);putS("wifi_pw",wifiPw);Serial.println("SAVED|WIFI_PASSWORD");}
 else if(x.startsWith("SET_DEVICE_UID=")){deviceUid=x.substring(15);putS("uid",deviceUid);Serial.println("SAVED|DEVICE_UID");}
 else if(x.startsWith("SET_DEVICE_TOKEN=")){deviceToken=x.substring(17);putS("token",deviceToken);Serial.println("SAVED|DEVICE_TOKEN");}
 else if(x.startsWith("SET_UPLOAD_SECONDS=")){uploadSeconds=max(10UL,(uint32_t)x.substring(19).toInt());prefs.begin("at360",false);prefs.putUInt("upload_s",uploadSeconds);prefs.end();Serial.println("SAVED|UPLOAD_SECONDS");}
 else if(x=="CONNECT_WIFI")connectWifi();
 else if(x=="SHOW_CONFIG"||x=="READ_STATUS"||x=="READ_CONFIG")showCfg();
 else if(x=="READ_IO"||x=="READ_TRACKING")printIo();
 else if(x=="SEND_NOW")sendTelemetry();
 else if(x=="AUTO_OFF"){autoUpload=false;prefs.begin("at360",false);prefs.putBool("auto_up",false);prefs.end();Serial.println("AUTO_UPLOAD_STATUS|OFF");}
 else if(x=="AUTO_ON"){autoUpload=true;lastSend=millis();prefs.begin("at360",false);prefs.putBool("auto_up",true);prefs.end();Serial.println("AUTO_UPLOAD_STATUS|ON");}
 else if(x=="MODE_LIVE"){simulation=false;forceAllOutputsOff();Serial.println("MODE|Live");printIo();}
 else if(x=="MODE_SIMULATION"){simulation=true;forceAllOutputsOff();Serial.println("MODE|Simulation");printIo();}
 else if(x.startsWith("SIM_AI")){
  int eq=x.indexOf('=');int channel=x.substring(6,eq).toInt();if(channel>=1&&channel<=4){simAnalogPercent[channel-1]=constrain(x.substring(eq+1).toFloat(),0.0f,100.0f);simAnalogVolts[channel-1]=simAnalogPercent[channel-1]/100.0f*3.3f;Serial.println("SIM_SAVED|AI"+String(channel));}}
 else if(x.startsWith("SIM_DI")){
  int eq=x.indexOf('=');int channel=x.substring(6,eq).toInt();if(channel>=1&&channel<=4){simDigital[channel-1]=x.substring(eq+1).toInt()?1:0;Serial.println("SIM_SAVED|DI"+String(channel));}}
 else if(x.startsWith("SIM_PULSE")){
  int eq=x.indexOf('=');int channel=x.substring(9,eq).toInt();if(channel>=1&&channel<=2){long value=x.substring(eq+1).toInt();simPulses[channel-1]=(uint32_t)max(0L,value);Serial.println("SIM_SAVED|PULSE"+String(channel));}}
 else if(x.startsWith("SIM_ARM=")){simArm=x.substring(8).toInt()?1:0;Serial.println("SIM_SAVED|ARM");}
 else if(x.startsWith("SIM_DO")){
  int eq=x.indexOf('=');int channel=x.substring(6,eq).toInt();if(channel>=1&&channel<=4){simOutput[channel-1]=x.substring(eq+1).toInt()?1:0;setOutput(channel-1,false);Serial.println("SIM_SAVED|DO"+String(channel));}}
 else if(x.startsWith("SEND_SELECTED_JSON=")){
  if(!simulation){Serial.println("SEND_BLOCKED|NOT_IN_SIMULATION");return;}String body=x.substring(19);if(!body.startsWith("{")||body.length()<40){Serial.println("SEND_BLOCKED|INVALID_SELECTED_JSON");return;}Serial.println("SELECTED_PAYLOAD_RECEIVED|"+String(body.length()));postTelemetryBody(body);
 }
 else if(x=="SEND_SIMULATED"){if(!simulation){Serial.println("SEND_BLOCKED|NOT_IN_SIMULATION");return;}printIo();sendTelemetry();}
 else if(x.startsWith("DO")){
  int underscore=x.indexOf('_');int channel=x.substring(2,underscore).toInt();String action=x.substring(underscore+1);if(channel<1||channel>4){Serial.println("OUTPUT_REJECTED|INVALID_CHANNEL");return;}uint8_t index=channel-1;
  if(action=="OFF"){
   setOutput(index,false);simOutput[index]=0;Serial.println(String(simulation?"SIM_OUTPUT_STATE|DO":"OUTPUT_STATE|DO")+channel+"=OFF");
  }else if(action=="ON"){
   if(simulation){simOutput[index]=1;setOutput(index,false);Serial.println("SIM_OUTPUT_STATE|DO"+String(channel)+"=ON");}
   else if(!armed())Serial.println("OUTPUT_REJECTED|LOCAL_ARM_OFF");
   else{setOutput(index,true,false);Serial.println("OUTPUT_STATE|DO"+String(channel)+"=ON");}
  }else if(action=="PULSE"){
   if(simulation){simOutput[index]=1;setOutput(index,false);Serial.println("SIM_OUTPUT_STATE|DO"+String(channel)+"=PULSE_ACTIVE");delay(1000);simOutput[index]=0;Serial.println("SIM_OUTPUT_STATE|DO"+String(channel)+"=OFF");}
   else if(!armed())Serial.println("OUTPUT_REJECTED|LOCAL_ARM_OFF");
   else{setOutput(index,true,true);Serial.println("OUTPUT_STATE|DO"+String(channel)+"=PULSE_ACTIVE");}
  }else Serial.println("OUTPUT_REJECTED|INVALID_ACTION");
 }
 else if(x=="ALL_OFF"){forceAllOutputsOff();Serial.println("OUTPUT_STATE|ALL=OFF");}
 else if(x=="RESTART")ESP.restart();else Serial.println("UNKNOWN_COMMAND|"+x);
}
void setup(){
 Serial.begin(115200);Serial.setTimeout(250);
 for(uint8_t i=0;i<4;i++){pinMode(AI_PINS[i],INPUT);analogSetPinAttenuation(AI_PINS[i],ADC_11db);pinMode(DI_PINS[i],INPUT_PULLUP);pinMode(DO_PINS[i],OUTPUT);digitalWrite(DO_PINS[i],LOW);}
 for(uint8_t i=0;i<2;i++)pinMode(PULSE_PINS[i],INPUT_PULLUP);
 pinMode(ARM,INPUT_PULLUP);pinMode(LED,OUTPUT);forceAllOutputsOff();analogReadResolution(12);
 attachInterrupt(digitalPinToInterrupt(PULSE_PINS[0]),pulseISR1,FALLING);attachInterrupt(digitalPinToInterrupt(PULSE_PINS[1]),pulseISR2,FALLING);
 WiFi.mode(WIFI_STA);loadCfg();Serial.println("AT360_READY|"+String(FW)+"|"+macId());printIdentity();Serial.println("PIN_MAP|AI1=34;AI2=35;AI3=36;AI4=39;DI1=4;DI2=13;DI3=18;DI4=19;P1=26;P2=27;DO1=25;DO2=21;DO3=22;DO4=23;ARM=32;LED=33");Serial.println("AUTO_UPLOAD_STATUS|"+String(autoUpload?"ON":"OFF"));if(ssid.length())WiFi.begin(ssid.c_str(),wifiPw.c_str());
}
void loop(){
 if(Serial.available())command(Serial.readStringUntil('\n'));serviceWifiScan();maintainWifi();
 for(uint8_t i=0;i<4;i++){
  if(outputOn[i]&&!armed()){setOutput(i,false);Serial.println("OUTPUT_STATE|DO"+String(i+1)+"=OFF");Serial.println("OUTPUT_INTERLOCK|LOCAL_ARM_OFF");}
  else if(outputOn[i]&&outputPulseActive[i]&&millis()-outputStarted[i]>=1000){setOutput(i,false);Serial.println("OUTPUT_STATE|DO"+String(i+1)+"=OFF");Serial.println("OUTPUT_PULSE|DO"+String(i+1)+"_COMPLETED");}
 }
 digitalWrite(LED,WiFi.status()==WL_CONNECTED?HIGH:((millis()/500)%2));
 if(autoUpload&&millis()-lastSend>=uploadSeconds*1000UL){lastSend=millis();if(WiFi.status()==WL_CONNECTED&&deviceToken.length())sendTelemetry();}
 delay(5);
}
