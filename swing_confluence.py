"""Completed-daily-bar KDJ/MACD crossover evidence for the V3 swing desk."""
from __future__ import annotations

from datetime import datetime
from math import isfinite
from zoneinfo import ZoneInfo

import pandas as pd
from market_clock import completed,freshness

NY = ZoneInfo('America/New_York')
VERSION = 'swing-kdj-macd-volume-v1'


def _number(value):
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (TypeError, ValueError):
        return None


def evaluate(daily: pd.DataFrame, now: datetime | None = None) -> dict:
    """Signals use the same completed bar; volume baseline excludes that bar."""
    now = now.astimezone(NY) if now is not None else datetime.now(NY)
    bars = daily.sort_index().copy()
    # The data provider may publish a partial current-day candle during the session.
    bars, _ = completed(bars, now)
    if len(bars) < 60:
        return {'rule_version': VERSION, 'available': False, 'reason': '已收盘日线不足60根，暂不生成共振信号', 'signals': []}

    signals = []
    for i in range(60, len(bars)):
        previous, current = bars.iloc[i-1], bars.iloc[i]
        keys = ('K', 'D', 'DIF', 'DEA', 'volume', 'close')
        if any(_number(previous[k]) is None or _number(current[k]) is None for k in keys):
            continue
        gold_kdj = previous['K'] <= previous['D'] and current['K'] > current['D']
        gold_macd = previous['DIF'] <= previous['DEA'] and current['DIF'] > current['DEA']
        death_kdj = previous['K'] >= previous['D'] and current['K'] < current['D']
        death_macd = previous['DIF'] >= previous['DEA'] and current['DIF'] < current['DEA']
        if not (gold_kdj and gold_macd or death_kdj and death_macd):
            continue
        baseline = _number(bars['volume'].iloc[i-20:i].mean())
        ratio = float(current['volume'] / baseline) if baseline and baseline > 0 else None
        direction = 'long' if gold_kdj and gold_macd else 'short'
        signals.append({
            'time': pd.Timestamp(bars.index[i]).date().isoformat(),
            'direction': direction,
            'close': float(current['close']),
            'volume_ratio': ratio,
            'volume_confirmed': ratio is not None and ratio >= 1.0,
        })

    latest = bars.iloc[-1]
    last_date = pd.Timestamp(bars.index[-1]).date()
    baseline = _number(bars['volume'].iloc[-21:-1].mean())
    ratio = _number(latest['volume'] / baseline) if baseline and baseline > 0 else None
    low60 = _number(bars['low'].iloc[-60:].min())
    high60 = _number(bars['high'].iloc[-60:].max())
    close = _number(latest['close'])
    position = (close - low60) / (high60 - low60) * 100 if close is not None and low60 is not None and high60 is not None and high60 > low60 else None
    k, d, j = (_number(latest[x]) for x in ('K', 'D', 'J'))
    dif, dea, hist = (_number(latest[x]) for x in ('DIF', 'DEA', 'MACD'))
    kdj_side = 'up' if k is not None and d is not None and k > d else 'down' if k is not None and d is not None and k < d else 'flat'
    macd_side = 'up' if dif is not None and dea is not None and dif > dea else 'down' if dif is not None and dea is not None and dif < dea else 'flat'
    recent = signals[-1] if signals and signals[-1]['time'] == last_date.isoformat() else None
    stale = not freshness(last_date,now)['fresh']
    if stale:
        state = 'stale'
        recent = None
    elif recent:
        state = 'long' if recent['direction'] == 'long' else 'short'
    elif kdj_side == macd_side == 'up':
        state = 'up'
    elif kdj_side == macd_side == 'down':
        state = 'down'
    else:
        state = 'mixed'
    return {
        'rule_version': VERSION, 'available': True, 'as_of': last_date.isoformat(),
        'stale': stale, 'state': state, 'latest_signal': recent,
        'last_historical_signal': signals[-1] if signals else None,
        'signals': signals[-180:],
        'latest': {
            'k': k, 'd': d, 'j': j, 'dif': dif, 'dea': dea, 'histogram': hist,
            'kdj_side': kdj_side, 'macd_side': macd_side,
            'close': close, 'ma20': _number(latest['MA20']),
            'position_60': position, 'volume_ratio': ratio,
        },
    }
