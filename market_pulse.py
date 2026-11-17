"""Compact QQQ temperature and Cboe VIX daily snapshot for the main workbench."""
from __future__ import annotations

import csv
import io
import math
import threading
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import requests

import data_provider as dp
import demo_market
from indicators import add_indicators
from scoring import market_temperature
import v3_store as store
from market_clock import freshness,completed


NY = ZoneInfo("America/New_York")
VIX_CSV = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
_LOCK = threading.Lock()
_TTL = 10 * 60
_RETRY_TTL = 60
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='market-pulse')
_ITEMS = {}
_LOG = logging.getLogger(__name__)


def _fresh(day, today):
    return freshness(day)['fresh']


def _qqq(today, now):
    raw = dp.get_index_daily("QQQ", 220)
    if raw is None or len(raw) < 65:
        raise ValueError("QQQ 日线不足")
    raw = raw[~raw.index.duplicated(keep="last")].sort_index().copy()
    raw.index = pd.to_datetime(raw.index)
    raw, _ = completed(raw, now)
    if len(raw) < 65:
        raise ValueError("QQQ 已完成日线不足")
    frame = add_indicators(raw)
    temp = market_temperature(frame)
    value = float(temp["temp"])
    if not math.isfinite(value):
        raise ValueError("QQQ 温度无法计算")
    last, previous = frame.iloc[-1], frame.iloc[-2]
    day = frame.index[-1].date()
    return {
        "symbol": "QQQ",
        "temperature": value,
        "label": temp["label"],
        "rsi": temp["rsi"],
        "position_60": temp["pos60"],
        "close": round(float(last["close"]), 2),
        "change_pct": round((float(last["close"]) / float(previous["close"]) - 1) * 100, 2),
        "ma20": round(float(last["MA20"]), 2),
        "history": [{"date": pd.Timestamp(t).date().isoformat(), "value": round(float(r["close"]), 2)} for t, r in frame.tail(30).iterrows()],
        "as_of": day.isoformat(),
        "fresh": _fresh(day, today),
        "source": dp.source_label("daily", "QQQ"),
        "method": "原系统市场温度：RSI 50% + 相对MA20位置 30% + 近60日区间位置 20%",
    }


def _vix(today):
    if demo_market.enabled():
        frame = demo_market.daily('VIX', 30)
        rows = [(index.date(), float(value)) for index, value in frame.close.items()]
    else:
        response = requests.get(VIX_CSV, timeout=12)
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.text.lstrip("\ufeff")))
        if not reader.fieldnames or not {"DATE", "CLOSE"}.issubset(reader.fieldnames):
            raise ValueError("VIX 数据格式已变化")
        rows = []
        for row in reader:
            try:
                day = datetime.strptime(row["DATE"], "%m/%d/%Y").date()
                value = float(row["CLOSE"])
            except (ValueError, TypeError, KeyError):
                continue
            if math.isfinite(value) and value > 0 and day <= today:
                rows.append((day, value))
        rows.sort(key=lambda x: x[0])
    if len(rows) < 30:
        raise ValueError("VIX 日线不足")
    day, value = rows[-1]
    previous = rows[-2][1]
    return {
        "symbol": "VIX",
        "value": round(value, 2),
        "change": round(value - previous, 2),
        "change_pct": round((value / previous - 1) * 100, 2),
        "as_of": day.isoformat(),
        "fresh": _fresh(day, today),
        "source": demo_market.SOURCE if demo_market.enabled() else "Cboe 官方历史日线",
        "source_url": None if demo_market.enabled() else "https://www.cboe.com/tradable_products/vix/vix_historical_data",
        "history": [{"date": d.isoformat(), "value": round(v, 2)} for d, v in rows[-30:]],
    }


def _refresh(name):
    now = datetime.now(NY)
    checked = datetime.now(timezone.utc).isoformat()
    try:
        data = _qqq(now.date(), now) if name == 'qqq' else _vix(now.date())
        data = {**data, 'fetched_at': datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        # Log the exception class only: URLs and credentials can occur in exception text.
        _LOG.warning('Market pulse %s failed (%s)', name, type(exc).__name__)
        error = ('QQQ 行情源请求失败，稍后自动重试' if name == 'qqq'
                 else 'VIX 官方数据请求失败，稍后自动重试')
        with _LOCK:
            _ITEMS[name].update(state='error', updated=time.monotonic(),
                                checked_at=checked, error=error)
        return
    try:
        store.put_snapshot('market-pulse:' + name, data)
    except Exception as exc:
        _LOG.warning('Market pulse cache save failed (%s)', type(exc).__name__)
    with _LOCK:
        _ITEMS[name].update(state='ready', data=data, updated=time.monotonic(),
                            checked_at=checked, error=None)


def current(force=False):
    """Return immediately; QQQ and VIX load independently in the background."""
    today = datetime.now(NY).date()
    result = {'checked_at': datetime.now(timezone.utc).isoformat(),
              'qqq': None, 'vix': None, 'errors': [], 'states': {}}
    with _LOCK:
        for name in ('qqq', 'vix'):
            if name not in _ITEMS:
                try:
                    data = store.snapshot('market-pulse:' + name)
                except Exception:
                    data = None
                _ITEMS[name] = {'data': data, 'state': 'idle', 'updated': 0,
                                'error': None, 'checked_at': None}
            item = _ITEMS[name]
            ttl = _RETRY_TTL if item['state'] == 'error' else _TTL
            if item['state'] != 'loading' and (force or item['state'] == 'idle'
                                               or time.monotonic() - item['updated'] >= ttl):
                if force and name == 'qqq':
                    dp.clear_failed_cache('QQQ')
                item.update(state='loading', error=None)
                _POOL.submit(_refresh, name)
            result['states'][name] = item['state']
            if item['data']:
                data = dict(item['data'])
                # Recompute freshness after restart and while reusing an old snapshot.
                try:
                    data['fresh'] = _fresh(datetime.fromisoformat(data['as_of']).date(), today)
                except (ValueError, TypeError, KeyError):
                    data['fresh'] = False
                data['from_cache'] = item['state'] != 'ready'
                data['refresh_failed'] = item['state'] == 'error'
                result[name] = data
            if item['error']:
                result['errors'].append(item['error'])
        result['loading'] = any(v == 'loading' for v in result['states'].values())
    return result
