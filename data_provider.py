# -*- coding: utf-8 -*-
"""数据层：akshare(新浪美股) 为主，yfinance 兜底，Finnhub 可选实时。

对外主要函数：
    get_daily(symbol, days)        -> DataFrame(open/high/low/close/volume)
    get_index_daily(symbol, days)  -> 同上（指数/ETF）
    get_minute(symbol)             -> 尽力而为的分钟线（可失败）
    get_realtime_quote(symbol)     -> 最新价/涨跌幅（尽力而为）
    get_company_profile(symbol)    -> 基础信息字典（尽力而为）
"""
import datetime as dt
from zoneinfo import ZoneInfo
import os
import threading
import alpaca_data
import demo_market

import pandas as pd

# ---------------- 观察列表与赛道映射 ----------------

WATCHLIST = [
    ("NVDA", "英伟达 · AI算力芯片"),
    ("MU", "美光 · 存储芯片"),
    ("SPIR", "Spire · 卫星(AGI太空)"),
    ("AMD", "AMD · 芯片"),
    ("TSM", "台积电 · 半导体代工"),
    ("SMCI", "超微 · AI算力硬件"),
    ("AVGO", "博通 · 芯片/ASIC"),
    ("VRT", "Vertiv · AI电力/液冷"),
]

SECTOR_MAP = {
    "NVDA": "半导体芯片 / AI算力",
    "MU": "存储芯片 / 半导体",
    "SPIR": "AGI太空 / 卫星",
    "AMD": "半导体芯片",
    "TSM": "半导体代工",
    "SMCI": "AI算力硬件",
    "AVGO": "半导体芯片 / ASIC",
    "VRT": "AI电力 / 液冷",
    "CEG": "核电 / AI电力",
    "FCX": "稀缺资源 / 铜",
    "LUNR": "AGI太空 / 登月",
    "RKLB": "AGI太空 / 火箭",
    "ROK": "机器人",
    "ISRG": "机器人 / 手术",
    "PLTR": "AI软件",
    "CRDO": "AI算力 / 高速互联",
    "ANET": "AI算力 / 网络",
    "MU.PH": "存储芯片（韩·海力士参考）",
}

INDEX_CHOICES = {
    "QQQ": "纳斯达克100 (科技大盘)",
    "SPY": "标普500 (全市场)",
    "DIA": "道琼斯30",
}


# ---------------- 本地 .env 配置（FINNHUB_API_KEY 等） ----------------

def _load_env(path=".env"):
    """极简 .env 解析：把项目目录下的 .env 键值注入环境变量。"""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()


# ---------------- 缓存工具 ----------------

_TTL_CACHE = {}
_CACHE_LOCK = threading.Lock()
_KEY_LOCKS = {}


def _cache_failed(value):
    return value is None or (isinstance(value, pd.DataFrame) and value.empty)


def clear_failed_cache(symbol=None):
    """Manual retry clears failed reads only; successful quotes remain cached."""
    s = _norm_symbol(symbol) if symbol else None
    with _CACHE_LOCK:
        for key, (_, value) in list(_TTL_CACHE.items()):
            if _cache_failed(value) and (s is None or s in key.split(':')):
                _TTL_CACHE.pop(key, None)


def _cached(key, ttl_seconds, producer):
    """Coalesce identical requests; failed reads retry after at most 60 seconds."""
    with _CACHE_LOCK:
        key_lock = _KEY_LOCKS.setdefault(key, threading.Lock())
    with key_lock:
        now = dt.datetime.now()
        with _CACHE_LOCK:
            hit = _TTL_CACHE.get(key)
        if hit:
            ttl = min(ttl_seconds, 60) if _cache_failed(hit[1]) else ttl_seconds
            if (now - hit[0]).total_seconds() < ttl:
                return hit[1]
        try:
            value = producer()
        except Exception:
            value = None
        with _CACHE_LOCK:
            _TTL_CACHE[key] = (dt.datetime.now(), value)
        return value


def _norm_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    # 去掉 akshare 不认识的尾部（如 .US / .PH）
    if s.endswith(".US"):
        s = s[:-3]
    return s


def _yf_download(*args, retries=1, backoff=1.5, **kwargs):
    """Default to one Yahoo attempt so rate limiting does not trigger a retry burst.

    yfinance 限流时通常返回空 DataFrame 并打印 'Failed download'（不抛异常），
    显式增加 retries 时对空结果退避重试；默认等待下次缓存重试。失败返回 None。
    """
    import time as _t
    import yfinance as yf
    for i in range(retries):
        try:
            df = yf.download(*args, **kwargs)
            if df is not None and not df.empty:
                return df
        except Exception:
            pass
        if i < retries - 1:
            _t.sleep(backoff * (i + 1))
    return None


# ---------------- TradingView 数据源（优先，需代理） ----------------

_SOURCE_MARK = {}
_TV_EXCHANGE_HINT = {
    "TSM": "NYSE", "VRT": "NYSE", "FCX": "NYSE", "SPIR": "NYSE",
    "ANET": "NYSE", "ROK": "NYSE", "SPY": "AMEX", "DIA": "AMEX",
}
_TV_EXCHANGES = ["NASDAQ", "NYSE", "AMEX", "OTC"]


def _tv_proxy():
    """TradingView 代理配置：.env 的 TV_PROXY 优先，其次自动读系统代理；填 none/off 关闭。"""
    raw = os.environ.get("TV_PROXY", "").strip()
    if raw.lower() in ("none", "off", "0", "false"):
        return None
    if raw:
        hp = raw.replace("http://", "").replace("https://", "").split("@")[-1]
    else:
        try:
            import requests as _rq
            prx = _rq.utils.get_environ_proxies("https://data.tradingview.com") or {}
            hp = (prx.get("https") or prx.get("http") or "").replace("http://", "").replace("https://", "").split("@")[-1]
        except Exception:
            hp = ""
    if ":" in hp:
        h, p = hp.rsplit(":", 1)
        if h and p.isdigit():
            return h, int(p)
    return None


def _mark_source(key, source):
    _SOURCE_MARK[key] = source


def source_label(kind, symbol):
    """当前数据源标记。kind: daily / weekly / monthly / intraday / quote。"""
    s = _norm_symbol(symbol)
    return _SOURCE_MARK.get("%s:%s" % (kind, s), "未知")


def _tv_ws_hist(full_symbol, interval, n_bars):
    """TradingView WebSocket 历史K线（非官方协议，失败返回 None）。"""
    import json
    import random
    import re
    import string
    import time as _time

    import websocket
    proxy = _tv_proxy()
    kw = {}
    if proxy:
        kw.update(http_proxy_host=proxy[0], http_proxy_port=proxy[1])
    try:
        ws = websocket.create_connection(
            "wss://data.tradingview.com/socket.io/websocket",
            timeout=15,
            header=["Origin: https://data.tradingview.com", "User-Agent: Mozilla/5.0"],
            **kw)
    except Exception:
        return None

    def _send(func, args):
        payload = json.dumps({"m": func, "p": args}, separators=(",", ":"))
        ws.send("~m~%d~m~%s" % (len(payload), payload))

    chart = "cs_" + "".join(random.choice(string.ascii_lowercase) for _ in range(12))
    try:
        _send("set_auth_token", ["unauthorized_user_token"])
        _send("chart_create_session", [chart, ""])
        _send("resolve_symbol", [chart, "symbol_1",
              '={"symbol":"%s","adjustment":"splits","session":"regular"}' % full_symbol])
        _send("create_series", [chart, "s1", "s1", "symbol_1", interval, n_bars])
        _send("switch_timezone", [chart, "exchange"])
    except Exception:
        try:
            ws.close()
        except Exception:
            pass
        return None

    raw = ""
    ws.settimeout(15)
    deadline = _time.time() + 15
    while _time.time() < deadline:
        try:
            raw += ws.recv()
        except Exception:
            break
        if '"s":[' in raw:
            # 快速收几帧，确保大数据分片收全后再结束
            ws.settimeout(1.0)
            for _ in range(6):
                try:
                    raw += ws.recv()
                except Exception:
                    break
            break
        if "critical_error" in raw or "protocol_error" in raw:
            break
    try:
        ws.close()
    except Exception:
        pass

    m = re.search(r'"s":\[(.+?)\}\]', raw)
    if not m:
        return None
    rows = []
    for p in re.split(r',\{"', m.group(1)):
        f = re.split(r"\[|:|,|\]", p)
        try:
            ts = dt.datetime.fromtimestamp(float(f[4]), ZoneInfo("America/New_York")).replace(tzinfo=None)
            o, h, l = float(f[5]), float(f[6]), float(f[7])
            c = float(f[8])
            # 兼容 5 值K线（无 volume，如 VIX/部分指数）：f[9] 非数字（'}')时 volume 置 0
            vol = 0.0
            if len(f) > 9 and f[9]:
                try:
                    vol = float(f[9])
                except (TypeError, ValueError):
                    vol = 0.0
            rows.append([ts, o, h, l, c, vol])
        except Exception:
            continue
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df["datetime"])
    df = df[["open", "high", "low", "close", "volume"]]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def _tv_get_hist(symbol, interval, n_bars):
    """按交易所顺序尝试 TradingView 历史；日/周/月线 index 归一化为日期。"""
    hint = _TV_EXCHANGE_HINT.get(symbol)
    exchanges = ([hint] if hint else []) + [e for e in _TV_EXCHANGES if e != hint]
    for ex in exchanges:
        df = _tv_ws_hist("%s:%s" % (ex, symbol), interval, n_bars)
        if df is not None and len(df) >= 5:
            if interval in ("1D", "1W", "1M"):
                df = df.copy()
                df.index = pd.to_datetime(df.index.date)
                df = df[~df.index.duplicated(keep="last")].sort_index()
            return df
    return None


def _tv_scanner_one(ticker):
    """TradingView 扫描器单标的快照。失败返回 None。"""
    import requests as _rq
    payload = {
        "symbols": {"tickers": [ticker]},
        "columns": ["name", "close", "change", "change_abs", "volume", "Recommend.All"],
    }
    for _ in range(2):
        try:
            r = _rq.post("https://scanner.tradingview.com/america/scan", json=payload, timeout=8,
                         headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json",
                                  "Origin": "https://www.tradingview.com",
                                  "Referer": "https://www.tradingview.com/"})
            if r.ok:
                data = (r.json().get("data") or [])
                if data:
                    d = data[0].get("d") or []
                    if len(d) >= 3:
                        return {"price": float(d[1]), "change_pct": float(d[2]),
                                "volume": float(d[4]) if len(d) > 4 and d[4] is not None else None,
                                "source": "TradingView"}
            return None
        except Exception:
            continue
    return None


def _tv_scanner_quote(symbol):
    """TradingView 实时快照（自动尝试多个交易所）。失败返回 None。"""
    hint = _TV_EXCHANGE_HINT.get(symbol)
    exchanges = ([hint] if hint else []) + [e for e in _TV_EXCHANGES if e != hint]
    for ex in exchanges:
        q = _tv_scanner_one("%s:%s" % (ex, symbol))
        if q:
            return q
    return None


# ---------------- 日线数据 ----------------

def get_daily(symbol: str, days: int = 250):
    """获取美股日线（前复权）。TradingView -> akshare 新浪 -> yfinance 兜底。"""
    if demo_market.enabled():
        _mark_source(f"daily:{_norm_symbol(symbol)}", demo_market.SOURCE)
        return demo_market.daily(_norm_symbol(symbol), days)
    s = _norm_symbol(symbol)
    key = "daily:%s" % s

    def from_akshare():
        import akshare as ak
        df = ak.stock_us_daily(symbol=s, adjust="qfq")
        if df is None or df.empty:
            return None
        df = df.rename(columns=str.lower)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df = df[["open", "high", "low", "close", "volume"]].astype(float)
        return df.tail(days)

    def from_yfinance():
        df = _yf_download({"BRK.B":"BRK-B","BF.B":"BF-B"}.get(s,s), period=f"{max(days, 60)}d", interval="1d",
                          progress=False, auto_adjust=True, threads=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[["Open", "High", "Low", "Close", "Volume"]]
        df.columns = ["open", "high", "low", "close", "volume"]
        df.index = pd.to_datetime(df.index)
        return df.tail(days)

    # A configured consolidated feed is authoritative for this request. Failure
    # must not silently switch volume / corporate-action methodology.
    if alpaca_data.configured():
        df = _cached(f"daily_alpaca:{s}:{days}", 300, lambda: alpaca_data.daily(s, days))
        _mark_source(key, "Alpaca SIP / split")
        if df is not None: df.attrs["data_source"] = "Alpaca SIP / split"
        return df
    df = _cached(f"daily_tv:{s}:{days}", 300, lambda: _tv_get_hist(s, "1D", max(days, 60)))
    if df is not None and len(df):
        _mark_source(key, "TradingView")
        df.attrs["data_source"] = "TradingView"
        return df.tail(days)
    df = _cached(f"daily:{s}:{days}", 300, from_akshare)
    if df is not None and len(df):
        _mark_source(key, "akshare(新浪)")
        df.attrs["data_source"] = "akshare(新浪)"
        return df
    df = _cached(f"daily_yf:{s}:{days}", 600, from_yfinance)
    if df is not None and len(df):
        _mark_source(key, "Yahoo Finance")
        df.attrs["data_source"] = "Yahoo Finance"
        return df
    _mark_source(key, "无可用数据源")
    return None


def get_index_daily(symbol: str, days: int = 120):
    """指数/ETF 日线，同 get_daily。"""
    return get_daily(symbol, days=days)


# ---------------- 周期重采样：周线 / 月线 ----------------

def _resample(df, rule):
    """OHLC 重采样：open=首、high=max、low=min、close=末、volume=sum。"""
    df = df[~df.index.duplicated(keep="last")].sort_index()
    out = pd.DataFrame({
        "open": df["open"].resample(rule).first(),
        "high": df["high"].resample(rule).max(),
        "low": df["low"].resample(rule).min(),
        "close": df["close"].resample(rule).last(),
        "volume": df["volume"].resample(rule).sum(),
    }).dropna()
    return out


def get_weekly(symbol: str, days: int = 700):
    """周线。TradingView(1W) 优先，失败用日线重采样（每周五收盘为周期末）。"""
    if demo_market.enabled():
        _mark_source(f"weekly:{_norm_symbol(symbol)}", demo_market.SOURCE)
        return _resample(demo_market.daily(_norm_symbol(symbol), days), "W-FRI")
    s = _norm_symbol(symbol)
    key = "weekly:%s" % s
    df = _cached(f"weekly_tv:{s}", 300, lambda: _tv_get_hist(s, "1W", 300))
    if df is not None and len(df):
        _mark_source(key, "TradingView")
        return df
    daily = get_daily(symbol, days=days)
    if daily is None or daily.empty:
        _mark_source(key, "无可用数据源")
        return None
    _mark_source(key, _SOURCE_MARK.get("daily:%s" % s, "日线重采样"))
    try:
        return _resample(daily, "W-FRI")
    except Exception:
        return _resample(daily, "W")


def get_monthly(symbol: str, days: int = 1300):
    """月线。TradingView(1M) 优先，失败用日线重采样（自然月末为周期末）。"""
    if demo_market.enabled():
        _mark_source(f"monthly:{_norm_symbol(symbol)}", demo_market.SOURCE)
        return _resample(demo_market.daily(_norm_symbol(symbol), days), "ME")
    s = _norm_symbol(symbol)
    key = "monthly:%s" % s
    df = _cached(f"monthly_tv:{s}", 300, lambda: _tv_get_hist(s, "1M", 300))
    if df is not None and len(df):
        _mark_source(key, "TradingView")
        return df
    daily = get_daily(symbol, days=days)
    if daily is None or daily.empty:
        _mark_source(key, "无可用数据源")
        return None
    _mark_source(key, _SOURCE_MARK.get("daily:%s" % s, "日线重采样"))
    try:
        return _resample(daily, "ME")
    except Exception:
        return _resample(daily, "M")


# ---------------- 分钟线 / 实时 ----------------

def get_minute(symbol: str):
    """分钟线（尽力而为）。yfinance 1m -> akshare 东财。失败返回 None。"""
    if demo_market.enabled():
        return None
    s = _norm_symbol(symbol)

    def from_yf():
        df = _yf_download({"BRK.B":"BRK-B","BF.B":"BF-B"}.get(s,s), period="1d", interval="1m", progress=False,
                          auto_adjust=True, threads=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[["Open", "High", "Low", "Close", "Volume"]]
        df.columns = ["open", "high", "low", "close", "volume"]
        df.index = pd.to_datetime(df.index)
        return df

    return _cached(f"min:{s}", 120, from_yf)


def get_intraday(symbol: str, market_codes=("105", "106", "107")):
    """美股分时（1分钟K线）。优先级：TradingView -> Finnhub(需Key) -> 东财 -> yfinance。
    全部失败返回 None。"""
    if demo_market.enabled():
        return None
    s = _norm_symbol(symbol)
    _df_tv = _cached(f"intraday_tv:{s}", 120, lambda: _tv_get_hist(s, "1", 400))
    if _df_tv is not None and len(_df_tv) >= 10:
        _mark_source("intraday:%s" % s, "TradingView")
        return _df_tv

    def from_finnhub():
        key = os.environ.get("FINNHUB_API_KEY", "").strip()
        if not key:
            return None
        import requests
        to_ts = int(dt.datetime.now().timestamp())
        from_ts = to_ts - 2 * 86400
        r = requests.get("https://finnhub.io/api/v1/stock/candle",
                         params={"symbol": s, "resolution": "1",
                                 "from": from_ts, "to": to_ts, "token": key},
                         timeout=10)
        if not r.ok:
            return None
        j = r.json()
        if j.get("s") != "ok" or not j.get("t"):
            return None
        out = pd.DataFrame({
            "time": pd.to_datetime(j["t"], unit="s", utc=True).tz_convert("America/New_York").tz_localize(None),
            "open": j["o"], "high": j["h"], "low": j["l"],
            "close": j["c"], "volume": j["v"],
        }).set_index("time").sort_index()
        return out

    def from_akshare():
        import akshare as ak
        end = dt.datetime.now() + dt.timedelta(days=1)
        start = end - dt.timedelta(days=3)
        for code in market_codes:
            try:
                df = ak.stock_us_hist_min_em(
                    symbol=f"{code}.{s}",
                    start_date=start.strftime("%Y-%m-%d 09:30:00"),
                    end_date=end.strftime("%Y-%m-%d 23:59:00"))
                if df is None or df.empty:
                    continue
                df = df.rename(columns={"时间": "time", "开盘": "open", "最高": "high",
                                        "最低": "low", "收盘": "close", "成交量": "volume"})
                df = df[["time", "open", "high", "low", "close", "volume"]]
                df["time"] = pd.to_datetime(df["time"])
                df = df.set_index("time").sort_index()
                df = df.apply(pd.to_numeric, errors="coerce").dropna()
                return df
            except Exception:
                continue
        return None

    df = _cached(f"intraday_fh:{s}", 120, from_finnhub)
    if df is not None and not df.empty:
        _mark_source("intraday:%s" % s, "Finnhub 1分钟")
    if df is None or df.empty:
        df = _cached(f"intraday:{s}", 120, from_akshare)
        if df is not None and not df.empty:
            _mark_source("intraday:%s" % s, "东方财富 分钟数据（时区待核验）")
    if df is None or df.empty:
        # 兜底：yfinance 5 分钟线（可能被限流）
        def from_yf():
            d = _yf_download(s, period="1d", interval="5m", progress=False,
                             threads=False, auto_adjust=True)
            if d is None or d.empty:
                return None
            if isinstance(d.columns, pd.MultiIndex):
                d.columns = d.columns.get_level_values(0)
            d = d[["Open", "High", "Low", "Close", "Volume"]]
            d.columns = ["open", "high", "low", "close", "volume"]
            d.index = pd.to_datetime(d.index)
            return d
        df = _cached(f"intraday_yf:{s}", 300, from_yf)
        if df is not None and not df.empty:
            df = df.copy()
            if df.index.tz is not None:
                df.index = df.index.tz_convert("America/New_York").tz_localize(None)
            _mark_source("intraday:%s" % s, "Yahoo 5分钟")
    return df


def get_realtime_quote(symbol: str):
    """最新报价（尽力而为）：TradingView > Finnhub Key > yfinance 1m 最后一根。"""
    if demo_market.enabled():
        return None
    s = _norm_symbol(symbol)
    _q_tv = _cached(f"quote_tv:{s}", 60, lambda: _tv_scanner_quote(s))
    if _q_tv:
        _mark_source("quote:%s" % s, "TradingView")
        return _q_tv
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if key:
        try:
            import requests
            r = requests.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": s, "token": key}, timeout=10)
            if r.ok:
                j = r.json()
                if j.get("c"):
                    return {"price": j["c"], "change_pct": j.get("dp"),
                            "open": j.get("o"), "high": j.get("h"),
                            "low": j.get("l"), "source": "Finnhub"}
        except Exception:
            pass
    m = _cached(f"min:{s}", 120, lambda: get_minute(s))
    if m is not None and not m.empty:
        last = m.iloc[-1]
        prev = m.iloc[-2] if len(m) > 1 else last
        chg = (last["close"] / prev["close"] - 1) * 100 if prev["close"] else None
        return {"price": last["close"], "change_pct": chg,
                "open": last["open"], "high": last["high"], "low": last["low"],
                "source": "yfinance-1m"}
    return None


def get_company_profile(symbol: str):
    """公司基础信息（尽力而为，失败返回 None）。"""
    if demo_market.enabled():
        return None
    s = _norm_symbol(symbol)

    def from_yf():
        import yfinance as yf
        t = yf.Ticker(s)
        fi = t.fast_info
        out = {"name": str(getattr(fi, "last_price", "") and t.info.get("shortName", s))}
        try:
            out["shortName"] = t.info.get("shortName", s)
        except Exception:
            out["shortName"] = s
        out["pe"] = getattr(fi, "last_price", None)
        return out

    return _cached(f"profile:{s}", 3600, from_yf)
def get_vix(days: int = 90):
    """CBOE VIX 波动率恐慌指数（尽力而为，失败返回 None）。

    用于波段战法市场温度判断（无涨跌家数公开数据时的替代指标）。
    数据源：TradingView(CBOE:VIX) 优先（不依赖代理之外的第三方限流），
    yfinance ^VIX 兜底（可能被限流，自动降级为 None）。
    """
    if demo_market.enabled():
        return demo_market.daily("VIX", days)
    key = "vix:%s" % days

    def from_tv():
        df = _tv_ws_hist("CBOE:VIX", "1D", max(days, 60))
        if df is None or len(df) == 0:
            return None
        df = df.copy()
        df.index = pd.to_datetime(df.index.date)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df.tail(days)

    def from_yf():
        df = _yf_download("^VIX", period="%dd" % max(days, 60), interval="1d",
                          progress=False, auto_adjust=True, threads=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[["Open", "High", "Low", "Close"]]
        df.columns = ["open", "high", "low", "close"]
        df.index = pd.to_datetime(df.index)
        return df.tail(days)

    df = _cached(f"vix_tv:{days}", 300, from_tv)
    if df is not None and len(df):
        _mark_source(key, "TradingView")
        return df
    df = _cached(f"vix:{days}", 600, from_yf)
    if df is not None and len(df):
        _mark_source(key, "Yahoo Finance")
        return df
    return None
