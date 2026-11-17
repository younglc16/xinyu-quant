"""Immutable price datasets and reproducible research records in the existing SQLite DB."""
import hashlib,json,uuid
import pandas as pd
import v3_store as store

def init():
    with store.connection() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS research_datasets(id TEXT PRIMARY KEY,symbol TEXT NOT NULL,source TEXT NOT NULL,adjustment TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS research_latest(symbol TEXT PRIMARY KEY,dataset_id TEXT NOT NULL REFERENCES research_datasets(id),checked_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS research_records(id TEXT PRIMARY KEY,kind TEXT NOT NULL,symbol TEXT NOT NULL,dataset_id TEXT NOT NULL REFERENCES research_datasets(id),rule_version TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS research_symbol_time ON research_records(symbol,created_at DESC);
        ''')

def save_dataset(symbol,raw,source,adjustment):
    rows=[{'date':pd.Timestamp(t).isoformat(),**{k:float(r[k]) if pd.notna(r[k]) else None for k in ['open','high','low','close','volume']}} for t,r in raw.iterrows()]
    payload=json.dumps(rows,allow_nan=False,separators=(',',':'))
    ident=hashlib.sha256((symbol+source+adjustment+payload).encode()).hexdigest()
    with store.connection() as c:
        c.execute('INSERT OR IGNORE INTO research_datasets VALUES(?,?,?,?,?,?)',(ident,symbol,source,adjustment,payload,store.now()))
        c.execute('INSERT INTO research_latest VALUES(?,?,?) ON CONFLICT(symbol) DO UPDATE SET dataset_id=excluded.dataset_id,checked_at=excluded.checked_at',(symbol,ident,store.now()))
    return ident

def dataset(symbol, dataset_id=None):
    with store.connection() as c:
        if dataset_id is not None:
            row=c.execute('SELECT * FROM research_datasets WHERE symbol=? AND id=?',(symbol,dataset_id)).fetchone()
        else:
            row=c.execute('SELECT d.*,l.checked_at FROM research_latest l JOIN research_datasets d ON d.id=l.dataset_id WHERE l.symbol=?',(symbol,)).fetchone()
    if not row:raise ValueError('请先在交易工作台加载该股票日线')
    meta=dict(row);frame=pd.DataFrame(json.loads(meta.pop('payload'))).set_index('date');frame.index=pd.to_datetime(frame.index)
    return frame,meta

def record(kind,symbol,dataset_id,payload):
    ident=uuid.uuid4().hex
    with store.connection() as c:
        c.execute('INSERT INTO research_records VALUES(?,?,?,?,?,?,?)',(ident,kind,symbol,dataset_id,payload['version'],json.dumps(payload,ensure_ascii=False,allow_nan=False),store.now()))
        store.audit(c,'research_'+kind,ident,{'symbol':symbol,'dataset_id':dataset_id,'version':payload['version']})
    return ident

def records(symbol=None):
    with store.connection() as c:
        rows=c.execute('SELECT id,kind,symbol,dataset_id,rule_version,created_at FROM research_records '+('WHERE symbol=? ' if symbol else '')+'ORDER BY created_at DESC LIMIT 30',(symbol,) if symbol else ()).fetchall()
    return [dict(x) for x in rows]

def detail(ident):
    with store.connection() as c:row=c.execute('SELECT * FROM research_records WHERE id=?',(ident,)).fetchone()
    if not row:raise ValueError('研究记录不存在')
    item=dict(row);item['payload']=json.loads(item['payload']);return item
