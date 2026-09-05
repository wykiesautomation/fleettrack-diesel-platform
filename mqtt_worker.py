import os,ssl,time
from urllib.parse import urlparse
import requests
import paho.mqtt.client as mqtt

BASE=os.environ['ASSETTRACK_BASE_URL'].rstrip('/')
WORKER_TOKEN=os.environ['MQTT_WORKER_TOKEN']
CONNECTOR_ID=int(os.environ['MQTT_CONNECTOR_ID'])
BROKER=os.environ['MQTT_BROKER_URL']
TOPICS=[x.strip() for x in os.environ.get('MQTT_TOPICS','#').split(',') if x.strip()]
USERNAME=os.environ.get('MQTT_USERNAME')
PASSWORD=os.environ.get('MQTT_PASSWORD')

def on_connect(client,userdata,flags,reason_code,properties=None):
    if int(reason_code)!=0:print('MQTT connect failed',reason_code);return
    for topic in TOPICS:client.subscribe(topic,qos=1)
    print('MQTT connected; subscribed',TOPICS)

def on_message(client,userdata,msg):
    try:
        r=requests.post(f'{BASE}/api/v1/integrations/{CONNECTOR_ID}/mqtt/message',headers={'Authorization':'Bearer '+WORKER_TOKEN,'X-MQTT-Topic':msg.topic},data=msg.payload,timeout=20)
        print(msg.topic,r.status_code,r.text[:120])
    except Exception as exc:print('Forward failed',type(exc).__name__,str(exc)[:160])

u=urlparse(BROKER if '://' in BROKER else 'mqtts://'+BROKER)
client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id=os.environ.get('MQTT_CLIENT_ID',f'at360-{CONNECTOR_ID}'))
if USERNAME:client.username_pw_set(USERNAME,PASSWORD)
if u.scheme in ('mqtts','ssl','tls'):
    client.tls_set(ca_certs=os.environ.get('MQTT_CA_FILE') or None,cert_reqs=ssl.CERT_REQUIRED)
client.on_connect=on_connect;client.on_message=on_message
client.connect(u.hostname,u.port or (8883 if u.scheme in ('mqtts','ssl','tls') else 1883),keepalive=60)
client.reconnect_delay_set(min_delay=2,max_delay=120)
client.loop_forever()
