import argparse,json,random,time,urllib.request
p=argparse.ArgumentParser();p.add_argument('--url',default='http://localhost:5000/api/v1/ingest');p.add_argument('--token',required=True);p.add_argument('--device-id',required=True);p.add_argument('--mode',choices=['tank','tracker','vibration','analog'],default='tank');p.add_argument('--interval',type=int,default=10);a=p.parse_args();seq=0;level=72.0
while True:
 seq+=1; level=max(2,min(98,level+random.uniform(-.5,.3)))
 points={'tank':[{'point':'level_percent','value':level},{'point':'volume_l','value':level*100},{'point':'battery_v','value':3.9+random.uniform(-.03,.03)},{'point':'solar_v','value':6.8+random.uniform(-.5,.5)}],'tracker':[{'point':'speed_kmh','value':random.choice([0,0,12,24])},{'point':'battery_v','value':3.88}],'vibration':[{'point':'vibration_rms','value':3.1+random.uniform(-.3,1.2)},{'point':'temperature_c','value':48+random.uniform(-2,4)},{'point':'battery_v','value':3.86}],'analog':[{'point':'analog_1','value':random.uniform(4,20)}]}[a.mode]
 data={'device_id':a.device_id,'sequence':seq,'timestamp':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'firmware':'sim-rev12','measurements':points}
 if a.mode in ('tank','tracker'):data['location']={'latitude':-26.699+random.uniform(-.002,.002),'longitude':27.835+random.uniform(-.002,.002),'accuracy_m':8,'speed_kmh':points[0]['value'] if a.mode=='tracker' else 0}
 req=urllib.request.Request(a.url,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+a.token},method='POST')
 try:print(urllib.request.urlopen(req).read().decode())
 except Exception as e:print('send failed',e)
 time.sleep(a.interval)
