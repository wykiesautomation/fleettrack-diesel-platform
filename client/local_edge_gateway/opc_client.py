from datetime import datetime,timezone
from opcua import Client
from ..edge_agent.connectors.opcua_browser import browse_nodes,read_node
from ..edge_agent.connectors.opcua_runtime import read_mapped_nodes
class ReadOnlyOpcClient:
 def __init__(self,connector,secrets):self.connector=connector;self.secrets=secrets;self.client=None
 def __enter__(self):
  self.client=Client(self.connector['endpoint'],timeout=int(self.connector.get('opcua',{}).get('timeout_seconds',10)));opc=self.connector.get('opcua',{});mode=opc.get('security_mode','None');policy=opc.get('security_policy','None')
  if policy!='None':
   cert=self.secrets.get('local_secrets',{}).get(opc.get('certificate_ref',''),{});self.client.set_security_string(f"{policy},{mode},{cert.get('certificate','')},{cert.get('private_key','')}")
  if opc.get('auth_mode')=='USERNAME':
   secret=self.secrets.get('local_secrets',{}).get(opc.get('credential_ref',''),{});self.client.set_user(secret.get('username',''));self.client.set_password(secret.get('password',''))
  self.client.connect();return self
 def __exit__(self,*args):
  if self.client:self.client.disconnect()
 def browse(self,job):return browse_nodes(self.client,job.get('root_node','i=85'),job.get('max_depth',2),job.get('max_nodes',250))
 def read(self,job):return read_node(self.client,job['node_id'])
 def live(self):return read_mapped_nodes(self.client,self.connector['connector_id'],self.connector.get('mappings',[]),self.connector.get('opcua',{}).get('stale_seconds',120))
