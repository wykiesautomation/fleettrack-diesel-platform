"""AssetTrack 360 read-only OPC UA commissioning simulator."""
import argparse,math,random,signal,time
from datetime import datetime,timezone
from opcua import Server,ua

def build(endpoint='opc.tcp://0.0.0.0:4840/assettrack360/simulator/'):
 server=Server();server.set_endpoint(endpoint);server.set_server_name('AssetTrack 360 OPC UA Commissioning Simulator')
 idx=server.register_namespace('urn:assettrack360:commissioning')
 objects=server.get_objects_node();plant=objects.add_object(idx,'AssetTrack360Simulator')
 groups={}
 for name in ('Booster19','Pump01','Motor01','Tank01','Production'):
  groups[name]=plant.add_object(idx,name)
 specs=[
  ('Booster19','DischargePressure',5.62,ua.VariantType.Double,'bar'),('Booster19','FlowRate',148.4,ua.VariantType.Double,'m3/h'),
  ('Pump01','Running',True,ua.VariantType.Boolean,''),('Pump01','Current',34.7,ua.VariantType.Double,'A'),
  ('Motor01','Temperature',61.3,ua.VariantType.Double,'degC'),('Tank01','Level',72.5,ua.VariantType.Double,'%'),
  ('Production','Total',12846,ua.VariantType.UInt32,'count')]
 nodes={}
 for group,name,value,kind,unit in specs:
  node=groups[group].add_variable(ua.NodeId(f'{group}.{name}',idx),name,ua.Variant(value,kind));node.set_writable(False)
  node.add_property(idx,'EngineeringUnit',unit);nodes[f'{group}.{name}']=node
 return server,nodes

def run(endpoint):
 server,nodes=build(endpoint);server.start();running=True
 def stop(*_):
  nonlocal running;running=False
 signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
 print('AssetTrack 360 OPC UA simulator running READ-ONLY at',endpoint)
 print('Namespace URI: urn:assettrack360:commissioning')
 started=time.time()
 try:
  while running:
   t=time.time()-started
   nodes['Booster19.DischargePressure'].set_value(5.62+0.18*math.sin(t/12))
   nodes['Booster19.FlowRate'].set_value(148.4+4.2*math.sin(t/18))
   nodes['Pump01.Running'].set_value(True)
   nodes['Pump01.Current'].set_value(34.7+1.1*math.sin(t/8))
   nodes['Motor01.Temperature'].set_value(61.3+0.4*math.sin(t/40))
   nodes['Tank01.Level'].set_value(max(0,min(100,72.5+1.5*math.sin(t/90))))
   nodes['Production.Total'].set_value(12846+int(t/5),ua.VariantType.UInt32)
   time.sleep(1)
 finally:server.stop()

def main():
 p=argparse.ArgumentParser();p.add_argument('--endpoint',default='opc.tcp://0.0.0.0:4840/assettrack360/simulator/');a=p.parse_args();run(a.endpoint)
if __name__=='__main__':main()
