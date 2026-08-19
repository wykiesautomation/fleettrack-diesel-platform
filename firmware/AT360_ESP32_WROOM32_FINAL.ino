/*
  AssetTrack 360 ESP32-WROOM-32 Remote I/O with Live and Simulation modes
  Board: ESP32-WROOM-32 module on the verified AssetTrack 360 carrier mapping
  Copyright: (c) 2026 JP Van Wyk. All rights reserved.

  Live pins:
    GPIO34 analog input, maximum 3.3 V
    GPIO27 digital input, active LOW
    GPIO26 pulse input, falling-edge counter
    GPIO25 isolated one-second test output
    GPIO32 local arm to GND
    GPIO33 Wi-Fi status LED

  Simulation never energises GPIO25. It only sends simulated telemetry.
*/
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Preferences.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <ESPmDNS.h>
#include <mbedtls/sha256.h>

const char *FW="1.6.4-wroom32-claim-feedback-fixed";
const char *PROFILE_CODE="AT360_ESP32_WROOM32";
const char *CLAIM_URL="https://assettrack360.wykiesautomation.co.za/api/v1/device/claim";
const char *DEFAULT_USER="admin";
const char *DEFAULT_PASSWORD="AssetTrack360";
const uint8_t RESET_BUTTON=0;
const char *INGEST_URL="https://assettrack360.wykiesautomation.co.za/api/v1/ingest";
const uint8_t AIN=34,DIN=27,PULSE=26,OUT=25,ARM=32,LED=33;
Preferences prefs;
portMUX_TYPE pulseMux=portMUX_INITIALIZER_UNLOCKED;
volatile uint32_t livePulses=0;
String ssid="",wifiPw="",deviceUid="",deviceToken="";
uint32_t sequenceNo=0,lastSend=0,lastRetry=0,outStarted=0,uploadSeconds=30;
bool outputOn=false,simulation=false;
float simAnalogPercent=0.0f,simAnalogVolts=0.0f;
int simDigital=0,simOutput=0,simArm=0;
uint32_t simPulses=0;
WebServer web(80);
DNSServer dns;
bool setupApActive=false,firstLoginRequired=true,webServerStarted=false,mdnsStarted=false;
String adminHash="",sessionId="";
uint32_t setupApStarted=0,resetPressedAt=0;
const IPAddress SETUP_AP_IP(192,168,4,1);
const IPAddress SETUP_AP_GATEWAY(192,168,4,1);
const IPAddress SETUP_AP_MASK(255,255,255,0);

// Forward declarations keep Arduino's generated prototypes from changing this flow.
void forceAllOutputsOff();
bool connectWifi();
void sendTelemetry();
void startWebServer();
void startSetupPortal();
void stopSetupPortal();


void IRAM_ATTR pulseISR(){portENTER_CRITICAL_ISR(&pulseMux);livePulses++;portEXIT_CRITICAL_ISR(&pulseMux);}
uint32_t pulseCount(){portENTER_CRITICAL(&pulseMux);uint32_t v=livePulses;portEXIT_CRITICAL(&pulseMux);return v;}
bool armed(){return digitalRead(ARM)==LOW;}
void setOutput(bool on){digitalWrite(OUT,on?HIGH:LOW);outputOn=on;if(on)outStarted=millis();else outStarted=0;}
void forceAllOutputsOff(){setOutput(false);simOutput=0;}
String macId(){String v=WiFi.macAddress();v.replace(":","");return v;}
String esc(String v){v.replace("\\","\\\\");v.replace("\"","\\\"");return v;}
void putS(const char*k,const String&v){prefs.begin("at360",false);prefs.putString(k,v);prefs.end();}
void saveSeq(){prefs.begin("at360",false);prefs.putUInt("seq",sequenceNo);prefs.end();}
void loadCfg(){prefs.begin("at360",true);ssid=prefs.getString("ssid","");wifiPw=prefs.getString("wifi_pw","");deviceUid=prefs.getString("uid","");deviceToken=prefs.getString("token","");sequenceNo=prefs.getUInt("seq",0);uploadSeconds=prefs.getUInt("upload_s",30);adminHash=prefs.getString("admin_hash","");firstLoginRequired=prefs.getBool("first_login",true);prefs.end();if(!deviceUid.length())deviceUid="AT360-WROOM32-"+macId();}

String sha256(const String &value){
 byte hash[32];mbedtls_sha256((const unsigned char*)value.c_str(),value.length(),hash,0);String out;
 for(byte b:hash){if(b<16)out+='0';out+=String(b,HEX);}return out;
}
String htmlEscape(String v){v.replace("&","&amp;");v.replace("<","&lt;");v.replace(">","&gt;");v.replace("\"","&quot;");return v;}
String page(const String &title,const String &body){return String("<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>")+title+"</title><style>body{font-family:Arial;background:#061522;color:#fff;margin:0}.wrap{max-width:760px;margin:auto;padding:22px}.card{background:#0d2a42;border-radius:14px;padding:18px;margin:12px 0}input,select,button{width:100%;padding:12px;margin:6px 0;border-radius:8px;border:1px solid #3a647f;box-sizing:border-box}button{background:#19c5e3;color:#04131f;font-weight:bold}.ok{color:#8fe388}.warn{color:#ffd166}</style></head><body><div class='wrap'><h1>AssetTrack 360</h1>"+body+"</div></body></html>";}
bool authenticated(){if(!sessionId.length())return false;String cookie=web.header("Cookie");return cookie.indexOf("AT360SESSION="+sessionId)>=0;}
void redirectTo(const String &path){web.sendHeader("Location",path);web.send(302,"text/plain","");}
String wifiOptions(){
 int n=WiFi.scanNetworks(false,true);String out;
 for(int i=0;i<n;i++){String name=htmlEscape(WiFi.SSID(i));if(name.length())out+="<option value='"+name+"'>"+name+" ("+String(WiFi.RSSI(i))+" dBm)</option>";}
 WiFi.scanDelete();return out;
}
String accessAddresses(){
 String text="<p><strong>Permanent setup address:</strong> <a href='http://192.168.4.1'>http://192.168.4.1</a></p>";
 text+="<p class='warn'>For 192.168.4.1, connect to the AssetTrack360-Setup Wi-Fi. For the LAN address, connect this phone or PC to the same customer Wi-Fi as the board.</p>";
 if(WiFi.status()==WL_CONNECTED){
  String lan=WiFi.localIP().toString();
  text+="<p><strong>LAN address:</strong> <a href='http://"+lan+"/login'>http://"+lan+"/login</a></p>";
  text+="<p><strong>Local name, if supported by the device:</strong> <a href='http://assettrack360.local/login'>http://assettrack360.local/login</a></p>";
 }
 return text;
}
void handleRoot(){
 if(!authenticated()){redirectTo("/login");return;}
 if(firstLoginRequired){redirectTo("/change-password");return;}
 bool wifiConnected=WiFi.status()==WL_CONNECTED;
 String state=wifiConnected?"Connected: "+WiFi.localIP().toString()+" | Signal: "+String(WiFi.RSSI())+" dBm":"Not connected";
 String claimed=deviceToken.length()?"Registered / token installed":"Not registered";
 String body;
 body+="<div class='card'><h2>WROOM Device Setup</h2>";
 body+="<p>Board profile: "+String(PROFILE_CODE)+"</p><p>Firmware: "+String(FW)+"</p>";
 body+="<p>Board ID: "+macId()+"</p><p>Wi-Fi: "+state+"</p>"+accessAddresses();
 body+="<p>AssetTrack 360: "+claimed+"</p><p>Device UID: "+htmlEscape(deviceUid)+"</p></div>";
 body+="<div class='card'><h2>Step 1: Scan and connect to Wi-Fi</h2>";
 body+="<p>Select a detected network, or enter the SSID manually.</p>";
 body+="<form method='get' action='/scan-wifi'><button type='submit'>Scan for Wi-Fi networks</button></form>";
 body+="<form method='post' action='/save-wifi'><select name='ssid'>"+wifiOptions()+"</select>";
 body+="<input name='manual_ssid' placeholder='Or enter SSID manually'>";
 body+="<input type='password' name='password' placeholder='Wi-Fi password'>";
 body+="<button type='submit'>Save and connect</button></form></div>";
 body+="<div class='card'><h2>Step 2: Register with AssetTrack 360</h2>";
 if(wifiConnected){
  body+="<p class='ok'>Wi-Fi is connected. Device registration is now available.</p>";
  body+="<form method='post' action='/claim'><input name='claim_code' placeholder='One-time AssetTrack 360 claim code' required>";
  body+="<button type='submit'>Register device</button>";
  body+="<p class='warn'>Registration can take up to 15 seconds. Press the button only once.</p></form>";
 }else{
  body+="<p class='warn'>Connect this WROOM device to Wi-Fi before registering it with AssetTrack 360.</p>";
  body+="<button type='button' disabled style='opacity:.45'>Register device</button>";
 }
 body+="</div><div class='card'>";
 if(wifiConnected&&deviceToken.length())body+="<form method='post' action='/send-now'><button>Send telemetry now</button></form>";
 body+="<form method='post' action='/logout'><button>Log out</button></form></div>";
 web.send(200,"text/html",page("Device Setup",body));
}
void handleLogin(){
 if(web.method()==HTTP_GET){web.send(200,"text/html",page("Login","<div class='card'><h2>Local administrator login</h2><form method='post'><input name='user' value='admin'><input type='password' name='password' placeholder='Password'><button>Login</button></form>"+accessAddresses()+"</div>"));return;}
 String expected=adminHash.length()?adminHash:sha256(DEFAULT_PASSWORD);if(web.arg("user")!=DEFAULT_USER||sha256(web.arg("password"))!=expected){web.send(403,"text/html",page("Login failed","<div class='card warn'>Invalid login.</div>"));return;}
 sessionId=String((uint32_t)esp_random(),HEX)+String((uint32_t)esp_random(),HEX);web.sendHeader("Set-Cookie","AT360SESSION="+sessionId+"; Path=/; HttpOnly; SameSite=Lax");redirectTo(firstLoginRequired?"/change-password":"/");
}
void handleChangePassword(){
 if(!authenticated()){redirectTo("/login");return;}
 if(web.method()==HTTP_GET){web.send(200,"text/html",page("Change password","<div class='card'><h2>Default password must be changed</h2><form method='post'><input type='password' name='current' placeholder='Current password'><input type='password' name='new1' placeholder='New password, minimum 8 characters'><input type='password' name='new2' placeholder='Confirm new password'><button>Save new password</button></form></div>"));return;}
 String expected=adminHash.length()?adminHash:sha256(DEFAULT_PASSWORD),n1=web.arg("new1");if(sha256(web.arg("current"))!=expected||n1.length()<8||n1!=web.arg("new2")){web.send(400,"text/html",page("Password error","<div class='card warn'>Current password or new password confirmation is invalid.</div>"));return;}
 adminHash=sha256(n1);firstLoginRequired=false;prefs.begin("at360",false);prefs.putString("admin_hash",adminHash);prefs.putBool("first_login",false);prefs.end();redirectTo("/");
}
void handleSaveWifi(){
 if(!authenticated()||firstLoginRequired){redirectTo("/login");return;}
 String selected=web.arg("manual_ssid");if(!selected.length())selected=web.arg("ssid");selected.trim();
 String newPassword=web.arg("password");
 if(!selected.length()){web.send(400,"text/html",page("Wi-Fi error","<div class='card warn'>Select or enter a Wi-Fi network. The setup network remains available.</div><a href='/'><button>Back</button></a>"));return;}
 String previousSsid=ssid,previousPassword=wifiPw;ssid=selected;wifiPw=newPassword;forceAllOutputsOff();
 if(!connectWifi()){ssid=previousSsid;wifiPw=previousPassword;web.send(400,"text/html",page("Wi-Fi connection failed","<div class='card warn'><h2>Could not connect to "+htmlEscape(selected)+"</h2><p>Check the Wi-Fi password and try again.</p><p>The setup network remains available at <strong>http://192.168.4.1</strong>.</p></div><a href='/'><button>Try again</button></a>"));return;}
 putS("ssid",ssid);putS("wifi_pw",wifiPw);
 String lan="http://"+WiFi.localIP().toString();
 String body="<div class='card ok'><h2>Wi-Fi connected successfully</h2><p>The board is connected to <strong>"+htmlEscape(ssid)+"</strong>.</p><p>The setup network remains permanently available at <strong>http://192.168.4.1</strong>.</p><p>To use the LAN address, first connect this phone or computer to <strong>"+htmlEscape(ssid)+"</strong>, then open:</p><p><a href='"+lan+"/login'><strong>"+lan+"/login</strong></a></p><p>You can also try <strong>http://assettrack360.local/login</strong>. If the local name does not resolve, use the LAN IP above.</p><p>Sign in with <strong>admin</strong> and the new password you created.</p><p>Both the setup AP and LAN web access remain active.</p><p><a href='/'><button>Continue to AssetTrack 360 registration</button></a></p></div>";
 web.send(200,"text/html",page("Wi-Fi handover",body));
}
void handleClaim(){
 if(!authenticated()||firstLoginRequired){redirectTo("/login");return;}
 String code=web.arg("claim_code");code.trim();code.toUpperCase();
 Serial.println("CLAIM_BEGIN|"+code);
 if(!code.length()){web.send(400,"text/html",page("Claim failed","<div class='card warn'>Claim code required.</div><a href='/'><button>Back</button></a>"));return;}
 if(WiFi.status()!=WL_CONNECTED){web.send(400,"text/html",page("Claim failed","<div class='card warn'><h2>Wi-Fi is not connected</h2><p>Scan for Wi-Fi, connect the WROOM board, and then register the device.</p></div><a href='/'><button>Back</button></a>"));return;}
 WiFiClientSecure c;c.setInsecure();c.setTimeout(15);
 HTTPClient h;h.setConnectTimeout(10000);h.setTimeout(15000);
 if(!h.begin(c,CLAIM_URL)){Serial.println("CLAIM_FAILED|BEGIN");web.send(500,"text/html",page("Claim failed","<div class='card warn'>Could not open the AssetTrack 360 claim service.</div><a href='/'><button>Back</button></a>"));return;}
 h.addHeader("Content-Type","application/json");h.addHeader("Accept","application/json");h.addHeader("User-Agent","AssetTrack360-WROOM/1.6.4");
 String body="{\"claim_code\":\""+esc(code)+"\",\"board_id\":\""+macId()+"\",\"profile_code\":\""+String(PROFILE_CODE)+"\",\"firmware\":\""+String(FW)+"\"}";
 int status=h.POST(body);String response=h.getString();String httpError=status<0?h.errorToString(status):String("");h.end();
 Serial.println("CLAIM_HTTP|"+String(status));if(response.length())Serial.println("CLAIM_RESPONSE|"+response.substring(0,300));
 if(status<0){web.send(504,"text/html",page("Claim failed","<div class='card warn'><h2>Could not reach AssetTrack 360</h2><p>Network error: "+htmlEscape(httpError)+"</p><p>Check that customer Wi-Fi has internet access, then try again.</p></div><a href='/'><button>Back</button></a>"));return;}
 if(status<200||status>=300){String safe=response.length()?htmlEscape(response.substring(0,300)):String("No response body");web.send(status,"text/html",page("Claim rejected","<div class='card warn'><h2>AssetTrack 360 rejected the claim</h2><p>HTTP "+String(status)+"</p><p>"+safe+"</p><p>Confirm the claim code is unused and belongs to this customer.</p></div><a href='/'><button>Back</button></a>"));return;}
 int u=response.indexOf("\"device_uid\"");int t=response.indexOf("\"device_token\"");
 auto field=[&](int pos){if(pos<0)return String("");int colon=response.indexOf(':',pos),q1=response.indexOf('\"',colon+1),q2=response.indexOf('\"',q1+1);return q1>=0&&q2>q1?response.substring(q1+1,q2):String("");};
 String newUid=field(u),newToken=field(t);
 if(!newUid.length()||!newToken.length()){web.send(502,"text/html",page("Claim failed","<div class='card warn'><h2>Invalid claim response</h2><p>The service accepted the request but did not return both device credentials.</p></div><a href='/'><button>Back</button></a>"));return;}
 deviceUid=newUid;deviceToken=newToken;putS("uid",deviceUid);putS("token",deviceToken);Serial.println("CLAIM_SUCCESS|"+deviceUid);
 web.send(200,"text/html",page("Claim complete","<div class='card ok'><h2>Device claimed</h2><p>Device UID: "+htmlEscape(deviceUid)+"</p><p>Token: Installed securely</p><a href='/'><button>Continue</button></a></div>"));
 sendTelemetry();
}
void startWebServer(){
 if(webServerStarted)return;
 const char* headerKeys[]={"Cookie"};web.collectHeaders(headerKeys,1);
 web.on("/",handleRoot);
 web.on("/health",HTTP_GET,[]{String lan=WiFi.status()==WL_CONNECTED?WiFi.localIP().toString():"OFFLINE";web.send(200,"text/plain","AT360_OK|"+String(FW)+"|AP=192.168.4.1|LAN="+lan);});
 web.on("/login",HTTP_ANY,handleLogin);web.on("/change-password",HTTP_ANY,handleChangePassword);web.on("/scan-wifi",HTTP_GET,[](){if(!authenticated()){redirectTo("/login");return;}WiFi.scanDelete();redirectTo("/");});web.on("/save-wifi",HTTP_POST,handleSaveWifi);web.on("/claim",HTTP_POST,handleClaim);
 web.on("/send-now",HTTP_POST,[]{if(!authenticated()){redirectTo("/login");return;}sendTelemetry();redirectTo("/");});
 web.on("/logout",HTTP_POST,[]{sessionId="";web.sendHeader("Set-Cookie","AT360SESSION=; Max-Age=0; SameSite=Strict");redirectTo("/login");});
 web.onNotFound([](){redirectTo("/");});web.begin();webServerStarted=true;Serial.println("LOCAL_WEB_SERVER|STARTED_PORT_80");
}
void startSetupPortal(){
 forceAllOutputsOff();WiFi.mode(WIFI_AP_STA);
 String ap="AssetTrack360-Setup-"+macId().substring(8);
 if(!setupApActive){
  WiFi.softAPConfig(SETUP_AP_IP,SETUP_AP_GATEWAY,SETUP_AP_MASK);
  WiFi.softAP(ap.c_str(),DEFAULT_PASSWORD);
  dns.start(53,"*",SETUP_AP_IP);setupApActive=true;
 }
 setupApStarted=millis();startWebServer();Serial.println("SETUP_AP|"+ap+"|192.168.4.1");
}
void stopSetupPortal(){
 // Production rule: keep the recovery/setup AP available. Do not strand the installer.
 setupApActive=true;
 Serial.println("SETUP_AP|KEPT_ACTIVE|192.168.4.1");
}
void resetLocalPassword(){adminHash="";firstLoginRequired=true;sessionId="";prefs.begin("at360",false);prefs.remove("admin_hash");prefs.putBool("first_login",true);prefs.end();startSetupPortal();Serial.println("LOCAL_PASSWORD_RESET|DEFAULT_RESTORED");}
void factoryReset(){forceAllOutputsOff();prefs.begin("at360",false);prefs.clear();prefs.end();delay(300);ESP.restart();}
void serviceResetButton(){bool down=digitalRead(RESET_BUTTON)==LOW;if(down&&!resetPressedAt)resetPressedAt=millis();if(!down&&resetPressedAt){uint32_t held=millis()-resetPressedAt;resetPressedAt=0;if(held>=20000)factoryReset();else if(held>=10000)resetLocalPassword();}}
void scanWifi(){
 Serial.println("WIFI_SCAN_BEGIN");
 WiFi.setAutoReconnect(false);
 WiFi.disconnect(false,false);
 delay(200);
 WiFi.mode(setupApActive?WIFI_AP_STA:WIFI_STA);
 delay(150);
 int n=WiFi.scanNetworks(false,true,false,500);
 if(n<0){Serial.println("WIFI_SCAN_FAILED|"+String(n));n=0;}
 for(int i=0;i<n;i++){String name=WiFi.SSID(i);name.replace("|"," ");Serial.printf("WIFI_RESULT|%s|%d|%d|%d\n",name.c_str(),WiFi.RSSI(i),(int)WiFi.encryptionType(i),WiFi.channel(i));}
 WiFi.scanDelete();
 Serial.printf("WIFI_SCAN_END|%d\n",n);
 WiFi.setAutoReconnect(true);
}
bool connectWifi(){
 if(!ssid.length()){Serial.println("WIFI_FAILED|SSID_MISSING");return false;}
 WiFi.setAutoReconnect(false);
 // Keep AP_STA during handover so the browser receives the result page.
 WiFi.mode(setupApActive?WIFI_AP_STA:WIFI_STA);
 WiFi.disconnect(false,false);delay(200);
 Serial.println("WIFI_CONNECTING|"+ssid);WiFi.begin(ssid.c_str(),wifiPw.c_str());
 uint32_t t=millis();while(WiFi.status()!=WL_CONNECTED&&millis()-t<20000){web.handleClient();if(setupApActive)dns.processNextRequest();delay(50);}
 if(WiFi.status()==WL_CONNECTED){
  WiFi.setAutoReconnect(true);lastRetry=millis();startWebServer();
  if(!mdnsStarted){MDNS.end();delay(20);if(MDNS.begin("assettrack360")){MDNS.addService("http","tcp",80);mdnsStarted=true;Serial.println("MDNS|assettrack360.local");}}
  Serial.println("WIFI_CONNECTED|"+WiFi.localIP().toString()+"|"+String(WiFi.RSSI()));Serial.println("LOCAL_WEB|http://"+WiFi.localIP().toString()+"/login");Serial.println("SETUP_WEB|http://192.168.4.1/login");return true;
 }
 int reason=(int)WiFi.status();WiFi.disconnect(false,false);WiFi.setAutoReconnect(true);lastRetry=millis();Serial.println("WIFI_FAILED|"+String(reason));return false;
}
void maintainWifi(){
 if(WiFi.status()==WL_CONNECTED){
  if(!mdnsStarted&&MDNS.begin("assettrack360")){MDNS.addService("http","tcp",80);mdnsStarted=true;}
  return;
 }
 if(!ssid.length()||millis()-lastRetry<30000)return;lastRetry=millis();WiFi.mode(setupApActive?WIFI_AP_STA:WIFI_STA);WiFi.disconnect(false,false);delay(100);WiFi.begin(ssid.c_str(),wifiPw.c_str());Serial.println("WIFI_RETRY|"+ssid);
}
float liveVolts(){return (analogRead(AIN)/4095.0f)*3.30f;}
float livePercent(){float v=liveVolts()/3.30f*100.0f;return constrain(v,0.0f,100.0f);}

void printIo(){
 float volts=simulation?simAnalogVolts:liveVolts();float percent=simulation?simAnalogPercent:livePercent();
 int raw=simulation?(int)(volts/3.3f*4095.0f):analogRead(AIN);int digital=simulation?simDigital:(digitalRead(DIN)==LOW);uint32_t pulses=simulation?simPulses:pulseCount();int arm=simulation?simArm:armed();int out=simulation?simOutput:outputOn;
 Serial.println("IO_BEGIN");Serial.println("MODE|"+String(simulation?"Simulation":"Live"));Serial.println("ANALOG_RAW|"+String(raw));Serial.println("ANALOG_VOLTS|"+String(volts,3));Serial.println("ANALOG_PERCENT|"+String(percent,1));Serial.println("DIGITAL_INPUT|"+String(digital?"ON":"OFF"));Serial.println("PULSE_COUNT|"+String(pulses));Serial.println("LOCAL_ARM|"+String(arm?"ARMED":"NOT_ARMED"));Serial.println("OUTPUT_FEEDBACK|"+String(out?"ON":"OFF"));Serial.println("IO_END");
}
void showCfg(){Serial.println("CONFIG_BEGIN");Serial.println("FIRMWARE|"+String(FW));Serial.println("DEVICE_UID|"+deviceUid);Serial.println("SSID|"+ssid);Serial.println("WIFI_PASSWORD|"+String(wifiPw.length()?"SET":"MISSING"));Serial.println("WIFI_STATUS|"+String(WiFi.status()==WL_CONNECTED?"ONLINE":"OFFLINE"));Serial.println("IP_ADDRESS|"+(WiFi.status()==WL_CONNECTED?WiFi.localIP().toString():"-"));Serial.println("RSSI|"+String(WiFi.status()==WL_CONNECTED?WiFi.RSSI():0));Serial.println("DEVICE_TOKEN|"+String(deviceToken.length()?"SET":"MISSING"));Serial.println("MODE|"+String(simulation?"Simulation":"Live"));Serial.println("CONFIG_END");printIo();}
String telemetry(){
 float volts=simulation?simAnalogVolts:liveVolts();float percent=simulation?simAnalogPercent:livePercent();int digital=simulation?simDigital:(digitalRead(DIN)==LOW);uint32_t pulses=simulation?simPulses:pulseCount();int arm=simulation?simArm:armed();int out=simulation?simOutput:outputOn;
 sequenceNo++;saveSeq();String uniqueSequence=macId()+"-"+String(sequenceNo);String j="{\"device_id\":\""+esc(deviceUid)+"\",\"sequence\":\""+uniqueSequence+"\",\"firmware\":\""+FW+"\",\"measurements\":[";
 j+="{\"point\":\"analog_1\",\"value\":"+String(percent,2)+",\"quality\":\"GOOD\"},";
 j+="{\"point\":\"analog_1_volts\",\"value\":"+String(volts,3)+",\"quality\":\"GOOD\"},";
 j+="{\"point\":\"digital_1\",\"value\":"+String(digital)+",\"quality\":\"GOOD\"},";
 j+="{\"point\":\"pulse_1_count\",\"value\":"+String(pulses)+",\"quality\":\"GOOD\"},";
 j+="{\"point\":\"local_arm_status\",\"value\":"+String(arm)+",\"quality\":\"GOOD\"},";
 j+="{\"point\":\"digital_output_1_feedback\",\"value\":"+String(out)+",\"quality\":\"GOOD\"},";
 j+="{\"point\":\"wifi_rssi\",\"value\":"+String(WiFi.status()==WL_CONNECTED?WiFi.RSSI():0)+",\"quality\":\"GOOD\"}]}";return j;
}
void sendTelemetry(){if(WiFi.status()!=WL_CONNECTED){Serial.println("SEND_BLOCKED|WIFI_OFFLINE");return;}if(!deviceToken.length()){Serial.println("SEND_BLOCKED|DEVICE_TOKEN_MISSING");return;}WiFiClientSecure c;c.setInsecure();HTTPClient h;if(!h.begin(c,INGEST_URL)){Serial.println("TELEMETRY_STATUS|-1");return;}h.addHeader("Content-Type","application/json");h.addHeader("Authorization","Bearer "+deviceToken);int code=h.POST(telemetry());String body=code>0?h.getString():"";h.end();Serial.println("TELEMETRY_STATUS|"+String(code));if(body.length())Serial.println("TELEMETRY_RESPONSE|"+body);}

void printIdentity(){Serial.println("BOARD_ID|"+macId());Serial.println("BOARD_PROFILE|AT360_ESP32_WROOM32");Serial.println("BOARD_FAMILY|ESP32-WROOM-32");Serial.println("DEVICE_UID|"+deviceUid);Serial.println("FIRMWARE|"+String(FW));}
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
 else if(x=="CONNECT_WIFI")connectWifi();else if(x=="SHOW_CONFIG"||x=="READ_STATUS")showCfg();else if(x=="READ_IO"||x=="READ_TRACKING")printIo();else if(x=="SEND_NOW")sendTelemetry();
 else if(x=="MODE_LIVE"){simulation=false;simOutput=0;setOutput(false);Serial.println("MODE|Live");printIo();}
 else if(x=="MODE_SIMULATION"){simulation=true;setOutput(false);Serial.println("MODE|Simulation");printIo();}
 else if(x.startsWith("SIM_ANALOG_PERCENT=")){simAnalogPercent=constrain(x.substring(19).toFloat(),0.0f,100.0f);simAnalogVolts=simAnalogPercent/100.0f*3.3f;Serial.println("SIM_SAVED|ANALOG");}
 else if(x.startsWith("SIM_DIGITAL=")){simDigital=x.substring(12).toInt()?1:0;Serial.println("SIM_SAVED|DIGITAL");}
 else if(x.startsWith("SIM_PULSES=")){
  long requestedPulses=x.substring(11).toInt();
  if(requestedPulses<0)requestedPulses=0;
  simPulses=(uint32_t)requestedPulses;
  Serial.println("SIM_SAVED|PULSES");
}
 else if(x.startsWith("SIM_ARM=")){simArm=x.substring(8).toInt()?1:0;Serial.println("SIM_SAVED|ARM");}
 else if(x.startsWith("SIM_OUTPUT=")){simOutput=x.substring(11).toInt()?1:0;setOutput(false);Serial.println("SIM_SAVED|OUTPUT");}
 else if(x=="SEND_SIMULATED"){if(!simulation){Serial.println("SEND_BLOCKED|NOT_IN_SIMULATION");return;}printIo();sendTelemetry();}
 else if(x=="DO1_ON"){if(simulation){simOutput=1;setOutput(false);Serial.println("SIM_OUTPUT_STATE|DO1=ON");}else if(!armed()){Serial.println("OUTPUT_REJECTED|LOCAL_ARM_OFF");}else{setOutput(true);outStarted=0;Serial.println("OUTPUT_STATE|DO1=ON");}}
 else if(x=="TEST_OUTPUT_PULSE"||x=="DO1_PULSE"){if(simulation){simOutput=1;setOutput(false);Serial.println("SIM_OUTPUT_STATE|DO1=PULSE_ACTIVE");delay(1000);simOutput=0;Serial.println("SIM_OUTPUT_STATE|DO1=OFF");}else if(!armed()){Serial.println("OUTPUT_REJECTED|LOCAL_ARM_OFF");}else{setOutput(true);Serial.println("OUTPUT_STATE|DO1=PULSE_ACTIVE");}}
 else if(x=="OUTPUT_OFF"||x=="DO1_OFF"||x=="ALL_OFF"){setOutput(false);simOutput=0;Serial.println(simulation?"SIM_OUTPUT_STATE|DO1=OFF":"OUTPUT_STATE|DO1=OFF");}
 else if(x=="RESTART")ESP.restart();else Serial.println("UNKNOWN_COMMAND|"+x);
}
void setup(){Serial.begin(115200);Serial.setTimeout(250);pinMode(RESET_BUTTON,INPUT_PULLUP);pinMode(AIN,INPUT);pinMode(DIN,INPUT_PULLUP);pinMode(PULSE,INPUT_PULLUP);pinMode(OUT,OUTPUT);pinMode(ARM,INPUT_PULLUP);pinMode(LED,OUTPUT);setOutput(false);analogReadResolution(12);analogSetPinAttenuation(AIN,ADC_11db);attachInterrupt(digitalPinToInterrupt(PULSE),pulseISR,FALLING);loadCfg();WiFi.mode(WIFI_AP_STA);startWebServer();startSetupPortal();Serial.println("AT360_READY|"+String(FW)+"|"+macId());printIdentity();if(ssid.length()){WiFi.begin(ssid.c_str(),wifiPw.c_str());lastRetry=millis();}}
void loop(){
 if(Serial.available())command(Serial.readStringUntil('\n'));
 // The web server is always serviced on both AP and LAN interfaces.
 web.handleClient();if(setupApActive)dns.processNextRequest();
 serviceResetButton();maintainWifi();
 if(outputOn&&!armed()){setOutput(false);Serial.println("OUTPUT_STATE|DO1=OFF");Serial.println("OUTPUT_INTERLOCK|LOCAL_ARM_OFF");}
 else if(outputOn&&outStarted&&millis()-outStarted>=1000){setOutput(false);Serial.println("OUTPUT_STATE|DO1=OFF");Serial.println("OUTPUT_PULSE|COMPLETED");}
 digitalWrite(LED,WiFi.status()==WL_CONNECTED?HIGH:((millis()/500)%2));
 if(millis()-lastSend>=uploadSeconds*1000UL){lastSend=millis();if(WiFi.status()==WL_CONNECTED&&deviceToken.length())sendTelemetry();}
 delay(5);
}
