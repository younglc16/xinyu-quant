"""Daily and weekly chart events for the supplied KDJ/MACD strategy v1.0."""
from __future__ import annotations

from math import isfinite

import pandas as pd

from indicators import add_indicators
from market_clock import calendar, weekly_freshness
from trade_engine import prepare

VERSION = 'kdj-macd-resonance-v1.0'
MIN_BARS = 60
GAP_BARS = 3
# Each group is AND; alternatives within a group are OR. Order is priority.
RULES = {
    'long': (
        ('R-L1', 'strong', '双金叉', (('kdj_gold',), ('macd_gold',))),
        ('R-L2', 'medium', 'KDJ金叉 · MACD负柱收窄', (('kdj_gold',), ('decel_up',))),
        ('R-L3', 'medium', 'J值超卖拐头', (('turn_up',), ('decel_up', 'macd_gold'))),
    ),
    'short': (
        ('R-S1', 'strong', '双死叉', (('kdj_dead',), ('macd_dead',))),
        ('R-S2', 'medium', 'KDJ死叉 · MACD正柱收窄', (('kdj_dead',), ('decel_dn',))),
        ('R-S3', 'medium', 'J值超买拐头', (('turn_dn',), ('decel_dn', 'macd_dead'))),
    ),
}
EVENT_LABELS = {
    'kdj_gold': 'KDJ金叉', 'kdj_dead': 'KDJ死叉', 'macd_gold': 'MACD金叉',
    'macd_dead': 'MACD死叉', 'decel_up': 'MACD负柱收窄', 'decel_dn': 'MACD正柱收窄',
    'turn_up': 'J值超卖拐头', 'turn_dn': 'J值超买拐头',
}
CROSS_EVENTS = {
    'kdj_gold': ('kdj', 'gold'), 'kdj_dead': ('kdj', 'dead'),
    'macd_gold': ('macd', 'gold'), 'macd_dead': ('macd', 'dead'),
}


def _event_columns(bars):
    """Use the same unrounded K/D and DIF/DEA as the chart."""
    kdj_delta = bars['K'] - bars['D']
    macd_delta = bars['DIF'] - bars['DEA']
    histogram = bars['MACD']
    j = bars['J']
    spread = bars['high'].rolling(9, min_periods=1).max() - bars['low'].rolling(9, min_periods=1).min()
    # Pandas EWM carries forward across a NaN RSV. Do not treat that value as a new KDJ reading.
    kdj_valid = spread.gt(0) & spread.shift(1).gt(0)
    return {
        'kdj_gold': kdj_valid & kdj_delta.shift(1).le(0) & kdj_delta.gt(0),
        'kdj_dead': kdj_valid & kdj_delta.shift(1).ge(0) & kdj_delta.lt(0),
        'macd_gold': macd_delta.shift(1).le(0) & macd_delta.gt(0),
        'macd_dead': macd_delta.shift(1).ge(0) & macd_delta.lt(0),
        'decel_up': histogram.lt(0) & histogram.gt(histogram.shift(1)),
        'decel_dn': histogram.gt(0) & histogram.lt(histogram.shift(1)),
        'turn_up': kdj_valid & j.shift(1).le(20) & j.gt(j.shift(1)),
        'turn_dn': kdj_valid & j.shift(1).ge(80) & j.lt(j.shift(1)),
    }


def _zone(side, d):
    if side == 'long':
        return 'low' if d <= 20 else 'mid' if d <= 50 else 'high'
    return 'high' if d >= 80 else 'mid' if d >= 50 else 'low'


def _number(value):
    return float(value) if isfinite(value) else None


def _scan(bars, after):
    """Scan once across the whole series. Only serialize dates on the chart."""
    signals, crosses = [], []
    latest_by_side = {}
    last_match = {}
    columns = _event_columns(bars)
    for i, values in enumerate(zip(*columns.values())):
        events = {key for key, on in zip(columns, values) if on}
        if not events:
            continue
        date = bars.index[i].date().isoformat()
        on_chart = i >= MIN_BARS - 1 and bars.index[i] >= after
        if on_chart:
            for key, (indicator, kind) in CROSS_EVENTS.items():
                if key in events:
                    crosses.append(dict(time=date, indicator=indicator, cross=kind, label=EVENT_LABELS[key]))
        for side, rules in RULES.items():
            for rule_id, strength, label, groups in rules:
                if not all(events.intersection(group) for group in groups):
                    continue
                previous = last_match.get(side, -GAP_BARS)
                last_match[side] = i
                if i - previous >= GAP_BARS and i >= MIN_BARS - 1:
                    row = bars.iloc[i]
                    evidence = [EVENT_LABELS[event] for group in groups for event in group if event in events]
                    vr3, vr7 = _number(row.VR3), _number(row.VR7)
                    point = {
                        'time': date, 'direction': side, 'strength': strength, 'rule_id': rule_id,
                        'label': label, 'events': evidence, 'zone': _zone(side, row.D),
                        'd': float(row.D), 'j': float(row.J), 'close': float(row.close),
                        'vr3': vr3, 'vr7': vr7,
                        'volume_confirmed': None if vr3 is None or vr7 is None else vr3 >= 1.5 and vr7 >= 1.3,
                    }
                    latest_by_side[side] = point
                    if on_chart:
                        signals.append(point)
                break
    return signals, crosses, latest_by_side


def evaluate(raw, source, adjustment, now=None):
    daily, quality = prepare(raw, now)
    return _evaluate(add_indicators(daily), quality, source, adjustment, 'daily')


def evaluate_weekly(raw, source, adjustment, now=None):
    daily, daily_quality = prepare(raw, now)
    quality = weekly_freshness(None, now)
    weekly = daily.iloc[:0].copy()
    missing_weeks = 0
    if not daily.empty:
        first = daily.index[0].to_period('W-FRI')
        last_session = pd.Timestamp(quality['expected_session'])
        if daily.index[0] <= last_session:
            sessions = calendar().sessions_in_range(first.start_time, last_session)
            session_weeks = sessions.to_period('W-FRI')
            expected = pd.Series(sessions, index=session_weeks)
            daily = daily.loc[daily.index.intersection(sessions)]
            grouped = daily.groupby(daily.index.to_period('W-FRI'))
            counts = grouped.size()
            complete = counts[counts == expected.groupby(level=0).size().reindex(counts.index)].index
            weekly = grouped.agg({
                'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum',
            }).loc[complete]
            if len(complete):
                required = pd.period_range(complete[0], complete[-1], freq='W-FRI')
                missing_weeks = len(required.difference(complete))
            weekly.index = pd.DatetimeIndex(expected.groupby(level=0).last().reindex(complete))
    as_of = weekly.index[-1].date().isoformat() if len(weekly) else None
    quality.update(
        rows=len(weekly), as_of=as_of, fresh=as_of == quality['expected_session'],
        invalid_rows=daily_quality['invalid_rows'], duplicate_rows=daily_quality['duplicate_rows'],
        unexpected_sessions=daily_quality.get('unexpected_sessions', 0), missing_weeks=missing_weeks,
    )
    chart = add_indicators(weekly)
    return chart, _evaluate(chart, quality, source, adjustment, 'weekly')


def _evaluate(bars, quality, source, adjustment, period):
    unit = '周线' if period == 'weekly' else '日线'
    result = {
        'version': VERSION, 'period': period, 'source': source, 'adjustment': adjustment, 'quality': quality,
        'available': False, 'signals': [], 'crosses': [], 'latest_signals': [],
        'last_long': None, 'last_short': None,
    }
    quality['valid'] = False
    if len(bars) < MIN_BARS:
        return {**result, 'reason': f'有效已收盘{unit}不足{MIN_BARS}根'}
    if quality['invalid_rows'] or quality['duplicate_rows'] or quality.get('unexpected_sessions'):
        return {**result, 'reason': f'{unit}来源有异常、重复或非交易日记录，共振暂不标注'}
    if quality.get('missing_sessions') or quality.get('missing_weeks'):
        return {**result, 'reason': f'{unit}序列缺失，共振暂不标注'}
    quality['valid'] = True
    signals, crosses, history = _scan(bars, bars.index[max(0, len(bars) - 180)])
    result.update(
        available=True, as_of=quality['as_of'], signals=signals, crosses=crosses,
        latest_signals=[p for p in signals if quality['fresh'] and p['time'] == quality['as_of']],
        last_long=history.get('long'), last_short=history.get('short'),
    )
    return result
