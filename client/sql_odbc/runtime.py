import hashlib,re
from datetime import date,datetime,timezone
READ=re.compile(r'^\s*(SELECT|WITH)\b',re.I)
BLOCKED=re.compile(r'\b(INSERT|UPDATE|DELETE|MERGE|UPSERT|REPLACE|ALTER|DROP|CREATE|TRUNCATE|GRANT|REVOKE|EXEC(?:UTE)?|CALL|COPY|BULK|LOAD\s+DATA|VACUUM|ATTACH|DETACH|PRAGMA|SET|USE|LOCK|UNLOCK|COMMIT|ROLLBACK|SAVEPOINT)\b',re.I)
COMMENT=re.compile(r'(--[^\n]*|/\*.*?\*/)',re.S)
def validate_query(sql,max_chars=12000):
 text=str(sql or '').strip()
 if not text:raise ValueError('query_required')
 if len(text)>max_chars:raise ValueError('query_too_long')
 clean=COMMENT.sub(' ',text).strip();body=clean[:-1].strip() if clean.endswith(';') else clean
 if not READ.match(body):raise ValueError('select_or_with_required')
 if ';' in body:raise ValueError('multiple_statements_blocked')
 if BLOCKED.search(body) or re.search(r'\bSELECT\b[\s\S]*\bINTO\b',body,re.I):raise ValueError('write_or_admin_statement_blocked')
 return body
def _pyodbc():
 try:import pyodbc
 except ImportError as exc:raise RuntimeError('pyodbc_not_installed_on_edge_gateway') from exc
 return pyodbc
def connect(connection_string,timeout_seconds=10):
 p=_pyodbc();conn=p.connect(connection_string,timeout=max(1,min(60,int(timeout_seconds))),autocommit=False)
 try:conn.set_attr(p.SQL_ATTR_ACCESS_MODE,p.SQL_MODE_READ_ONLY)
 except Exception:pass
 return conn
def execute_read(connection_string,sql,parameters=None,timeout_seconds=10,max_rows=500):
 query=validate_query(sql);limit=max(1,min(5000,int(max_rows)));conn=connect(connection_string,timeout_seconds)
 try:
  cur=conn.cursor();cur.timeout=max(1,min(120,int(timeout_seconds)));cur.execute(query,tuple(parameters or []));cols=[d[0] for d in (cur.description or [])];rows=[]
  for item in cur.fetchmany(limit+1):
   if len(rows)>=limit:break
   vals=[]
   for v in item:
    if isinstance(v,(datetime,date)):v=v.isoformat()
    elif isinstance(v,(bytes,bytearray)):v=v.hex()
    elif v is not None and not isinstance(v,(str,int,float,bool)):v=str(v)
    vals.append(v)
   rows.append(dict(zip(cols,vals)))
  return {'columns':cols,'rows':rows,'row_count':len(rows),'truncated':len(rows)>=limit,'read_only':True}
 finally:
  try:conn.rollback()
  finally:conn.close()
def discover_schema(connection_string,timeout_seconds=10,max_objects=250):
 conn=connect(connection_string,timeout_seconds);objects=[]
 try:
  cur=conn.cursor()
  for row in cur.tables(tableType='TABLE,VIEW'):
   if len(objects)>=max_objects:break
   catalog=getattr(row,'table_cat',None);schema=getattr(row,'table_schem',None);name=getattr(row,'table_name',None);kind=getattr(row,'table_type',None);columns=[]
   try:
    for col in cur.columns(table=name,schema=schema,catalog=catalog):columns.append({'name':getattr(col,'column_name',None),'type':getattr(col,'type_name',None),'nullable':bool(getattr(col,'nullable',True))})
   except Exception:pass
   objects.append({'catalog':catalog,'schema':schema,'name':name,'type':kind,'columns':columns[:200]})
  return {'objects':objects,'object_count':len(objects),'read_only':True}
 finally:
  try:conn.rollback()
  finally:conn.close()
def rows_to_points(rows,mappings,sampled_at=None):
 stamp=sampled_at or datetime.now(timezone.utc).isoformat();points=[]
 for m in mappings:
  row=rows[-1] if m.get('row_mode')=='LAST' and rows else rows[0] if rows else None
  if not row or m['column'] not in row:continue
  try:value=float(row[m['column']])
  except (TypeError,ValueError):continue
  seq='sqlodbc:'+hashlib.sha256(f"{m['mapping_id']}:{stamp}:{value}".encode()).hexdigest()[:48];points.append({'source_path':m['source_path'],'value':value,'quality':'GOOD','source_timestamp':stamp,'sequence':seq})
 return points
