import hashlib,json,sqlite3,time
from .config import BASE,ensure
DB=BASE/'queue'/'store.db'
def connect():
 ensure();c=sqlite3.connect(DB,timeout=20);c.execute('pragma journal_mode=WAL');c.execute('create table if not exists outbound(id integer primary key,payload text not null,created real not null,attempts integer default 0,last_error text,dedup_key text)')
 cols={x[1] for x in c.execute('pragma table_info(outbound)')}
 if 'dedup_key' not in cols:c.execute('alter table outbound add column dedup_key text')
 c.execute('create unique index if not exists uq_outbound_dedup on outbound(dedup_key) where dedup_key is not null');c.commit();return c
def payload_key(payload):return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def put(payload,dedup_key=None):
 c=connect();key=dedup_key or payload_key(payload)
 try:c.execute('insert or ignore into outbound(payload,created,dedup_key) values(?,?,?)',(json.dumps(payload),time.time(),key));inserted=c.total_changes>0;c.commit();return inserted
 finally:c.close()
def batch(limit=100):
 c=connect()
 try:return c.execute('select id,payload,attempts from outbound order by id limit?',(limit,)).fetchall()
 finally:c.close()
def ok(i):
 c=connect();c.execute('delete from outbound where id=?',(i,));c.commit();c.close()
def fail(i,error):
 c=connect();c.execute('update outbound set attempts=attempts+1,last_error=? where id=?',(str(error)[:400],i));c.commit();c.close()
def depth():
 c=connect()
 try:return c.execute('select count(*) from outbound').fetchone()[0]
 finally:c.close()
def prune(max_rows=10000):
 c=connect();count=c.execute('select count(*) from outbound').fetchone()[0]
 if count>max_rows:c.execute('delete from outbound where id in (select id from outbound order by id limit ?)',(count-max_rows,));c.commit()
 c.close()
