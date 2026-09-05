import json
from .runtime import windows_preflight,list_servers
if __name__=='__main__':
 r=windows_preflight()
 if r['ready']:
  try:r['servers']=list_servers()
  except Exception as exc:r['server_scan_error']=type(exc).__name__+': '+str(exc)
 print(json.dumps(r,indent=2))
