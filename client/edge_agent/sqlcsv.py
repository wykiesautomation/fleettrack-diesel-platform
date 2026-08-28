import csv,hashlib,json,pyodbc
from pathlib import Path
from ..state_store import get,set
def sql(cfg,secrets):
 with pyodbc.connect(secrets[cfg['connection_secret']],timeout=cfg.get('timeout',15)) as cn:
  cur=cn.cursor();cur.execute(cfg['query']);row=cur.fetchone()
  if row is None:return [],None
  cols=[x[0] for x in cur.description];d=dict(zip(cols,row));key=cfg.get('cursor_column');cursor=d.get(key) if key else hashlib.sha256(repr(tuple(row)).encode()).hexdigest()
  return ([{'source_path':m['source_path'],'value':d[m['column']],'quality':'GOOD'} for m in cfg.get('mappings',[])],str(cursor))
def csv_read(cfg):
 path=Path(cfg['path'])
 with path.open(newline='',encoding='utf-8-sig') as f:rows=list(csv.DictReader(f,delimiter=cfg.get('delimiter',',')))
 if not rows:return [],None
 d=rows[-1];cursor_col=cfg.get('cursor_column','timestamp');cursor=d.get(cursor_col) or hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()
 return ([{'source_path':m['source_path'],'value':d[m['column']],'quality':'GOOD'} for m in cfg.get('mappings',[])],str(cursor))
def changed(connector_key,cursor):
 if cursor is None:return False
 key='source:'+connector_key;old=get(key)
 if old==cursor:return False
 set(key,cursor);return True
