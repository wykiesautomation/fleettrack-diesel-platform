import json,sqlite3,time
from .config import BASE,ensure
DB=BASE/'data'/'queue.sqlite3'
def connect():
 ensure();c=sqlite3.connect(DB);c.execute('PRAGMA journal_mode=WAL');c.execute('CREATE TABLE IF NOT EXISTS queue(id INTEGER PRIMARY KEY AUTOINCREMENT,dedupe TEXT UNIQUE,payload TEXT NOT NULL,attempts INTEGER DEFAULT 0,last_error TEXT,created REAL NOT NULL)');return c
def put(payload,dedupe):
 with connect() as c:c.execute('INSERT OR IGNORE INTO queue(dedupe,payload,created) VALUES(?,?,?)',(dedupe,json.dumps(payload,separators=(',',':')),time.time()))
def rows(limit=25):
 with connect() as c:return c.execute('SELECT id,payload,attempts FROM queue ORDER BY id LIMIT?',(limit,)).fetchall()
def ok(row_id):
 with connect() as c:c.execute('DELETE FROM queue WHERE id=?',(row_id,))
def fail(row_id,error):
 with connect() as c:c.execute('UPDATE queue SET attempts=attempts+1,last_error=? WHERE id=?',(str(error)[:500],row_id))
def depth():
 with connect() as c:return c.execute('SELECT COUNT(*) FROM queue').fetchone()[0]
