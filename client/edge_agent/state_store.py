import json,sqlite3,time
from .config import BASE,ensure
DB=BASE/'queue'/'state.db'
def connect():
 ensure();c=sqlite3.connect(DB);c.execute('create table if not exists cursor(key text primary key,value text,updated real)');c.commit();return c
def get(key,default=None):
 c=connect();row=c.execute('select value from cursor where key=?',(key,)).fetchone();c.close();return json.loads(row[0]) if row else default
def set(key,value):
 c=connect();c.execute('insert into cursor(key,value,updated) values(?,?,?) on conflict(key) do update set value=excluded.value,updated=excluded.updated',(key,json.dumps(value),time.time()));c.commit();c.close()
