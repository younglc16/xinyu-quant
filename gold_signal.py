"""Daily gold macro watch based on published Federal Reserve series.

This is a dated research prompt, not a gold price forecast or an order signal.
"""
from __future__ import annotations

import csv
import io
import math
import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests


SERIES = {
    "dollar": {
        "id": "DTWEXBGS",
        "name": "名义广义美元指数",
        "unit": "指数",
        "note": "美联储贸易加权广义美元指数；与 ICE DXY 不同",
    },
    "yield10": {
        "id": "DGS10",
        "name": "美国10年期国债收益率",
        "unit": "%",
        "note": "恒定期限收益率；不是国债价格",
    },
}
NY = ZoneInfo("America/New_York")
_LOCK = threading.Lock()
_CACHE: tuple[float, dict] | None = None
_TTL = 15 * 60


class GoldDataUnavailable(Exception):
    pass


def _load_series(series_id: str, today: date) -> dict[date, float]:
    response = requests.get(
        "https://fred.stlouisfed.org/graph/fredgraph.csv",
        params={"id": series_id, "cosd": (today - timedelta(days=100)).isoformat()},
        headers={"User-Agent": "curl/8.7.1"},
        timeout=12,
    )
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.text.lstrip("\ufeff")))
    if not reader.fieldnames or series_id not in reader.fieldnames or "observation_date" not in reader.fieldnames:
        raise GoldDataUnavailable("FRED 返回的数据格式已变化")
    result = {}
    for row in reader:
        try:
            value = float(row[series_id])
            day = date.fromisoformat(row["observation_date"])
        except (ValueError, TypeError, KeyError):
            continue
        if math.isfinite(value) and value > 0 and day <= today:
            result[day] = value
    if len(result) < 10:
        raise GoldDataUnavailable("FRED 有效日线不足")
    return result


def _evaluate_one(key: str, dates: list[date], values: list[float]) -> dict:
    if len(values) < 10:
        raise GoldDataUnavailable("共同交易日不足")
    ma5 = [None] * 4 + [sum(values[i - 4:i + 1]) / 5 for i in range(4, len(values))]
    below = [values[i] < ma5[i] if ma5[i] is not None else False for i in range(len(values))]
    # Day one is a close through MA5; day two must remain below and decline.
    first_break = values[-3] > values[-4] and values[-3] >= ma5[-3] and below[-2]
    confirmed = first_break and below[-1] and values[-1] < values[-2]
    one_day = below[-1] and not below[-2] and values[-2] >= ma5[-2]
    history = [
        {"date": dates[i].isoformat(), "value": round(values[i], 4), "ma5": round(ma5[i], 4)}
        for i in range(max(4, len(values) - 30), len(values))
    ]
    return {
        "series_id": SERIES[key]["id"],
        "name": SERIES[key]["name"],
        "unit": SERIES[key]["unit"],
        "note": SERIES[key]["note"],
        "source_url": f'https://fred.stlouisfed.org/series/{SERIES[key]["id"]}',
        "as_of": dates[-1].isoformat(),
        "value": round(values[-1], 4),
        "ma5": round(ma5[-1], 4),
        "previous": round(values[-2], 4),
        "below_ma5": below[-1],
        "falling": values[-1] < values[-2],
        "one_day_break": one_day,
        "confirmed_break": confirmed,
        "history": history,
    }


def evaluate(dollar: dict[date, float], yield10: dict[date, float], today: date | None = None) -> dict:
    today = today or datetime.now(NY).date()
    dates = sorted(set(dollar) & set(yield10))
    if len(dates) < 10:
        raise GoldDataUnavailable("两项数据的共同交易日不足")
    # A release delay is visible and never silently treated as a current signal.
    latest = dates[-1]
    lag = (today - latest).days
    stale = lag > 5 or lag < 0
    series = {
        "dollar": _evaluate_one("dollar", dates, [dollar[d] for d in dates]),
        "yield10": _evaluate_one("yield10", dates, [yield10[d] for d in dates]),
    }
    both = all(item["confirmed_break"] for item in series.values())
    if stale:
        state, title = "stale", "数据已过期，暂停判断"
    elif both:
        state, title = "candidate", "双指标确认：黄金加仓观察"
    elif all(item["below_ma5"] for item in series.values()):
        state, title = "watch", "两项均在5日线下，等待同步确认"
    else:
        state, title = "wait", "条件未齐，继续观察"
    return {
        "state": state,
        "title": title,
        "signal_date": latest.isoformat(),
        "checked_at": datetime.now(NY).isoformat(timespec="seconds"),
        "lag_days": lag,
        "source": "FRED / 美国联邦储备系统",
        "rule_version": "gold-macro-v1",
        "definition": "两项指标在同一数据日对齐；跌破前一日仍上涨且不低于各自MA5，随后连续两个已公布交易日收于MA5下方，第二日继续下降。MA5包含当日收盘。",
        "meaning": "仅提示宏观条件；黄金价格、仓位、风险和实际入场仍需独立核验。",
        "auto_orders": False,
        "series": series,
    }


def current(force: bool = False) -> dict:
    global _CACHE
    with _LOCK:
        if _CACHE and not force and time.monotonic() - _CACHE[0] < _TTL:
            return _CACHE[1]
    today = datetime.now(NY).date()
    try:
        dollar = _load_series(SERIES["dollar"]["id"], today)
        yield10 = _load_series(SERIES["yield10"]["id"], today)
        result = evaluate(dollar, yield10, today)
    except (requests.RequestException, GoldDataUnavailable) as exc:
        raise GoldDataUnavailable("FRED 日线暂不可用，请稍后重试") from exc
    with _LOCK:
        _CACHE = (time.monotonic(), result)
    return result
