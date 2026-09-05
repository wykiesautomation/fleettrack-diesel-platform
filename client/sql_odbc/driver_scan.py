import json
try:
 import pyodbc
 result={'drivers':pyodbc.drivers(),'data_sources':pyodbc.dataSources()}
except Exception as exc:result={'drivers':[],'data_sources':{},'error':type(exc).__name__}
if __name__=='__main__':print(json.dumps(result,indent=2))
