"""Local business data. One SQLite store shared by every desktop screen."""
from __future__ import annotations
import json, os, re, sqlite3, threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('XINYU_DATA_DIR', str(ROOT.parent / 'data')))
DB = DATA / 'xinyu.sqlite3'
_INIT_LOCK = threading.Lock()
CATALOG = [
 ('NVDA','英伟达','NVIDIA','NASDAQ','股票','科技,半导体'),('MU','美光','Micron','NASDAQ','股票','科技,半导体'),
 ('AMD','超威半导体','Advanced Micro Devices','NASDAQ','股票','科技,半导体'),('TSM','台积电','Taiwan Semiconductor','NYSE','ADR','科技,半导体'),
 ('SPIR','Spire','Spire Global','NYSE','股票','航天'),('SMCI','超微电脑','Super Micro Computer','NASDAQ','股票','科技'),
 ('AVGO','博通','Broadcom','NASDAQ','股票','科技,半导体'),('VRT','Vertiv','Vertiv','NYSE','股票','科技,能源'),
 ('MSFT','微软','Microsoft','NASDAQ','股票','科技'),('AAPL','苹果','Apple','NASDAQ','股票','科技'),
 ('GOOGL','谷歌','Alphabet','NASDAQ','股票','科技'),('AMZN','亚马逊','Amazon','NASDAQ','股票','科技'),
 ('META','Meta','Meta Platforms','NASDAQ','股票','科技'),('TSLA','特斯拉','Tesla','NASDAQ','股票','科技'),
 ('PLTR','Palantir','Palantir Technologies','NASDAQ','股票','科技'),('COIN','Coinbase','Coinbase Global','NASDAQ','股票','Web3,科技'),
 ('MSTR','Strategy','Strategy Bitcoin','NASDAQ','股票','Web3,科技'),('HOOD','Robinhood','Robinhood Markets','NASDAQ','股票','Web3,金融'),
 ('GLD','黄金ETF','SPDR Gold Shares','NYSE Arca','ETF','黄金,避险观察'),('IAU','黄金信托ETF','iShares Gold Trust','NYSE Arca','ETF','黄金,避险观察'),
 ('GDX','黄金矿业ETF','VanEck Gold Miners','NYSE Arca','ETF','黄金'),('TLT','长期美债ETF','iShares 20+ Year Treasury Bond','NASDAQ','ETF','避险观察'),
 ('SGOV','短期美债ETF','iShares 0-3 Month Treasury Bond','NYSE Arca','ETF','避险观察'),('SHY','短期美国国债ETF','iShares 1-3 Year Treasury Bond','NASDAQ','ETF','避险观察'),
 ('QQQ','纳斯达克100ETF','Invesco QQQ','NASDAQ','ETF','指数,科技'),('SPY','标普500ETF','SPDR S&P 500','NYSE Arca','ETF','指数'),
 ('DIA','道琼斯ETF','SPDR Dow Jones','NYSE Arca','ETF','指数'),('SOXX','半导体ETF','iShares Semiconductor','NASDAQ','ETF','半导体'),
 ('SMH','半导体ETF','VanEck Semiconductor','NASDAQ','ETF','半导体'),('IBIT','比特币信托ETF','iShares Bitcoin Trust','NASDAQ','ETF','Web3'),
 ('ETHA','以太坊信托ETF','iShares Ethereum Trust','NASDAQ','ETF','Web3'),('XLK','科技板块ETF','Technology Select Sector','NYSE Arca','ETF','科技'),
 ('XLU','公用事业ETF','Utilities Select Sector','NYSE Arca','ETF','避险观察'),('XLE','能源板块ETF','Energy Select Sector','NYSE Arca','ETF','能源'),
 ('FCX','自由港麦克莫兰','Freeport McMoRan','NYSE','股票','资源'),('CEG','星座能源','Constellation Energy','NASDAQ','股票','能源'),
 ('LUNR','直觉机器','Intuitive Machines','NASDAQ','股票','航天'),('RKLB','火箭实验室','Rocket Lab','NASDAQ','股票','航天'),
 ('ANET','Arista','Arista Networks','NYSE','股票','科技'),('CRDO','Credo','Credo Technology','NASDAQ','股票','科技,半导体'),
 ('BRK.B','伯克希尔B','Berkshire Hathaway','NYSE','股票','金融'),('JPM','摩根大通','JPMorgan Chase','NYSE','股票','金融'),
 ('JNJ','强生','Johnson & Johnson','NYSE','股票','避险观察'),('KO','可口可乐','Coca Cola','NYSE','股票','避险观察'),
 ('COST','好市多','Costco','NASDAQ','股票','消费'),('WMT','沃尔玛','Walmart','NASDAQ','股票','消费'),
]

def now(): return datetime.now(timezone.utc).isoformat()
def symbol(value):
    value = str(value).strip().upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,14}', value): raise ValueError('请输入有效的美股代码')
    return value

@contextmanager
def connection():
    DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=10000')
    try:
        with c: yield c
    finally: c.close()

def audit(c, kind, ident, detail):
    c.execute('INSERT INTO audit(kind,entity_id,detail,created_at) VALUES(?,?,?,?)',(kind,str(ident),json.dumps(detail,ensure_ascii=False),now()))

def init():
    with _INIT_LOCK, connection() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS instruments(symbol TEXT PRIMARY KEY,name TEXT NOT NULL,en TEXT NOT NULL DEFAULT '',exchange TEXT NOT NULL DEFAULT '',asset_type TEXT NOT NULL DEFAULT '股票',currency TEXT NOT NULL DEFAULT 'USD',verified INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS tags(id INTEGER PRIMARY KEY,name TEXT UNIQUE COLLATE NOCASE NOT NULL);
        CREATE TABLE IF NOT EXISTS watchlist(symbol TEXT PRIMARY KEY REFERENCES instruments(symbol),direction TEXT NOT NULL CHECK(direction IN ('long','short','watch')),note TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS watch_tags(symbol TEXT REFERENCES watchlist(symbol) ON DELETE CASCADE,tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,PRIMARY KEY(symbol,tag_id));
        CREATE TABLE IF NOT EXISTS snapshots(key TEXT PRIMARY KEY,payload TEXT NOT NULL,fetched_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS plans(id INTEGER PRIMARY KEY,symbol TEXT NOT NULL REFERENCES instruments(symbol),mode TEXT NOT NULL CHECK(mode IN ('swing','intraday')),direction TEXT NOT NULL CHECK(direction IN ('long','short')),cost REAL NOT NULL CHECK(cost>0),quantity INTEGER NOT NULL CHECK(quantity>0),stop_pct REAL NOT NULL CHECK(stop_pct>0 AND stop_pct<100),started_on TEXT,notes TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','closed')),version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,entity_id TEXT,detail TEXT,created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_audit_date ON audit(created_at);
        ''')
        for s,n,en,ex,typ,tags in CATALOG:
            c.execute('INSERT OR IGNORE INTO instruments(symbol,name,en,exchange,asset_type) VALUES(?,?,?,?,?)',(s,n,en,ex,typ))
        if not c.execute("SELECT 1 FROM meta WHERE key='migrated_v3'").fetchone():
            for t in ['科技','半导体','黄金','避险观察','Web3','指数','航天','能源','金融','资源','消费']:
                c.execute('INSERT OR IGNORE INTO tags(name) VALUES(?)',(t,))
            raw = {}
            old = ROOT / 'watchlist.json'
            if old.exists():
                # Malformed legacy data must not be marked successfully migrated.
                raw=json.loads(old.read_text(encoding='utf-8-sig'))
                if not isinstance(raw,dict) or not isinstance(raw.get('groups',{}),dict): raise ValueError('旧自选文件格式错误，已保留原文件')
            seed={x[0]:x[5].split(',') for x in CATALOG[:8]}
            for group,codes in raw.get('groups',{}).items():
                if not isinstance(codes,list): raise ValueError('旧自选分组不是列表，已保留原文件')
                c.execute('INSERT OR IGNORE INTO tags(name) VALUES(?)',(str(group),))
                for code in codes:
                    code=str(code).strip().upper()
                    if not code: continue
                    seed.setdefault(code,[]).append(str(group))
            for s,tags in seed.items():
                c.execute('INSERT OR IGNORE INTO instruments(symbol,name,verified) VALUES(?,?,0)',(s,s))
                c.execute('INSERT OR IGNORE INTO watchlist(symbol,direction,created_at,updated_at) VALUES(?,?,?,?)',(s,'watch',now(),now()))
                for t in set(tags):
                    c.execute('INSERT OR IGNORE INTO tags(name) VALUES(?)',(t,))
                    tid=c.execute('SELECT id FROM tags WHERE name=?',(t,)).fetchone()[0]
                    c.execute('INSERT OR IGNORE INTO watch_tags VALUES(?,?)',(s,tid))
            c.execute('INSERT INTO meta VALUES(?,?)',('migrated_v3',now()))
            audit(c,'migration','v3',{'legacy_file':str(old),'symbols':len(seed),'groups':len(raw.get('groups',{}))})

def tags():
    with connection() as c: return [dict(r) for r in c.execute('SELECT t.*,COUNT(wt.symbol) AS count FROM tags t LEFT JOIN watch_tags wt ON wt.tag_id=t.id GROUP BY t.id ORDER BY t.id')]

def add_tag(name):
    name=name.strip()
    if not name or len(name)>40: raise ValueError('标签名称须为1至40个字符')
    with connection() as c:
        c.execute('INSERT OR IGNORE INTO tags(name) VALUES(?)',(name,))
        return dict(c.execute('SELECT * FROM tags WHERE name=?',(name,)).fetchone())

def delete_tag(tid):
    with connection() as c:
        # Invalidate affected editor versions so a stale editor cannot resurrect a removed tag.
        c.execute('UPDATE watchlist SET version=version+1,updated_at=? WHERE symbol IN (SELECT symbol FROM watch_tags WHERE tag_id=?)',(now(),tid))
        c.execute('DELETE FROM tags WHERE id=?',(tid,));audit(c,'tag_delete',tid,{})

def search(q):
    q=q.strip().lower()
    with connection() as c:
        rows=[dict(r) for r in c.execute('SELECT i.*,EXISTS(SELECT 1 FROM watchlist w WHERE w.symbol=i.symbol) AS in_watchlist FROM instruments i')]
    matches=[r for r in rows if q in (r['symbol']+' '+r['name']+' '+r['en']).lower()]
    return sorted(matches,key=lambda r:(r['symbol'].lower()!=q,not r['symbol'].lower().startswith(q),r['symbol']))[:30]

def instrument(s):
    with connection() as c:
        r=c.execute('SELECT * FROM instruments WHERE symbol=?',(s,)).fetchone()
        return dict(r) if r else None

def register(data):
    with connection() as c:
        # Only verified US listings returned by the resolver reach this function.
        c.execute('INSERT INTO instruments(symbol,name,en,exchange,asset_type,verified) VALUES(?,?,?,?,?,1) ON CONFLICT(symbol) DO UPDATE SET name=excluded.name,en=excluded.en,exchange=excluded.exchange,asset_type=excluded.asset_type,verified=1',(symbol(data['symbol']),data['name'],data.get('en',''),data['exchange'],data['asset_type']))

def watchlist():
    with connection() as c:
        rows=[dict(r) for r in c.execute('SELECT i.*,w.direction,w.note,w.version,w.created_at,w.updated_at FROM watchlist w JOIN instruments i USING(symbol) ORDER BY w.created_at,w.symbol')]
        for r in rows:
            r['tags']=[dict(x) for x in c.execute('SELECT t.id,t.name FROM tags t JOIN watch_tags wt ON wt.tag_id=t.id WHERE wt.symbol=? ORDER BY t.id',(r['symbol'],))]
    return rows

def save_watch(s,direction,note,tag_ids,version=None):
    with connection() as c:
        if not c.execute('SELECT 1 FROM instruments WHERE symbol=?',(s,)).fetchone(): raise ValueError('请先搜索并选择已识别的标的')
        current=c.execute('SELECT version FROM watchlist WHERE symbol=?',(s,)).fetchone()
        if current and (version is None or version!=current[0]): raise RuntimeError('自选已被更新，请重新打开编辑')
        ids=set(tag_ids)
        if ids and len(c.execute('SELECT id FROM tags WHERE id IN ('+','.join('?'*len(ids))+')',tuple(ids)).fetchall())!=len(ids): raise ValueError('标签已变更，请刷新')
        if current: c.execute('UPDATE watchlist SET direction=?,note=?,version=version+1,updated_at=? WHERE symbol=?',(direction,note,now(),s))
        else: c.execute('INSERT INTO watchlist(symbol,direction,note,created_at,updated_at) VALUES(?,?,?,?,?)',(s,direction,note,now(),now()))
        c.execute('DELETE FROM watch_tags WHERE symbol=?',(s,))
        c.executemany('INSERT INTO watch_tags(symbol,tag_id) VALUES(?,?)',[(s,i) for i in ids])
        audit(c,'watch_save',s,{'direction':direction,'note':note,'tag_ids':list(ids)})
    return next(x for x in watchlist() if x['symbol']==s)

def remove_watch(s,version):
    with connection() as c:
        r=c.execute('SELECT version FROM watchlist WHERE symbol=?',(s,)).fetchone()
        if r and r[0]!=version: raise RuntimeError('自选已更新，请刷新后移除')
        c.execute('DELETE FROM watchlist WHERE symbol=?',(s,));audit(c,'watch_remove',s,{})

def snapshot(key):
    with connection() as c: r=c.execute('SELECT payload FROM snapshots WHERE key=?',(key,)).fetchone()
    return json.loads(r[0]) if r else None

def put_snapshot(key,data):
    with connection() as c: c.execute('INSERT INTO snapshots VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,fetched_at=excluded.fetched_at',(key,json.dumps(data,ensure_ascii=False,allow_nan=False),now()))

def list_plans():
    with connection() as c: return [dict(r) for r in c.execute('SELECT p.*,i.name FROM plans p JOIN instruments i USING(symbol) ORDER BY p.created_at DESC')]

def create_plan(values):
    with connection() as c:
        if not c.execute('SELECT 1 FROM instruments WHERE symbol=?',(values['symbol'],)).fetchone(): raise ValueError('标的不存在，请先搜索')
        keys=list(values)
        cur=c.execute('INSERT INTO plans('+','.join(keys)+',created_at,updated_at) VALUES('+','.join('?'*(len(keys)+2))+')',list(values.values())+[now(),now()])
        audit(c,'plan_create',cur.lastrowid,values)
        return cur.lastrowid

def close_plan(pid,version,review=''):
    with connection() as c:
        r=c.execute("UPDATE plans SET status='closed',notes=notes||?,version=version+1,updated_at=? WHERE id=? AND version=? AND status='active'",(('\n\n复盘：'+review.strip()) if review.strip() else '',now(),pid,version))
        if not r.rowcount: raise RuntimeError('计划不存在或已更新，请刷新')
        audit(c,'plan_close',pid,{'review':review})

def status():
    with connection() as c:
        return {'database':str(DB),'watchlist_count':c.execute('SELECT COUNT(*) FROM watchlist').fetchone()[0],'plan_count':c.execute('SELECT COUNT(*) FROM plans').fetchone()[0],'snapshots':[dict(r) for r in c.execute('SELECT key,fetched_at FROM snapshots ORDER BY fetched_at DESC LIMIT 30')],'migration':dict(c.execute('SELECT key,value FROM meta').fetchall())}
