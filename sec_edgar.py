"""Small, cached adapter for the SEC's public EDGAR company facts API.

This is fundamental filing data, not price data and not a trading signal.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from threading import Lock
from typing import Any

import requests
import demo_market

_BASE = "https://data.sec.gov"
_TICKERS = "https://www.sec.gov/files/company_tickers.json"
_LOCK = Lock()
_CACHE: dict[str, tuple[datetime, Any]] = {}
_TTL = timedelta(hours=12)
_USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "XinyuQuant desktop research contact: local@example.invalid",
)


class EdgarUnavailable(RuntimeError):
    pass


def _cached(key: str, loader):
    now = datetime.now(timezone.utc)
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < _TTL:
            return hit[1]
    value = loader()
    with _LOCK:
        _CACHE[key] = (now, value)
    return value


def _get(url: str) -> dict[str, Any]:
    if demo_market.enabled():
        raise EdgarUnavailable('演示模式下 SEC 基本面不联网')
    try:
        response = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT, "Accept-Encoding": "gzip, deflate"},
            timeout=12,
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise EdgarUnavailable("SEC EDGAR 数据暂不可用，请稍后刷新") from exc


def _cik_for(symbol: str) -> int:
    symbol = symbol.strip().upper()

    def load():
        listing = _get(_TICKERS)
        for item in listing.values():
            if item.get("ticker", "").upper() == symbol:
                return int(item["cik_str"])
        raise ValueError("SEC 未找到此代码对应的美国申报主体")

    return _cached(f"ticker:{symbol}", load)


def _latest_fact(facts: dict[str, Any], tags: tuple[str, ...], units: tuple[str, ...]) -> dict[str, Any] | None:
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    candidates: list[dict[str, Any]] = []
    for tag in tags:
        metric = us_gaap.get(tag, {})
        for unit in units:
            candidates.extend(metric.get("units", {}).get(unit, []))
    candidates = [x for x in candidates if x.get("val") is not None and x.get("form") in {"10-K", "10-Q"}]
    if not candidates:
        return None
    # A current 10-Q can include a comparative prior-year value. Prefer the
    # most recent reporting period before the filing date to avoid surfacing it.
    candidates.sort(key=lambda x: (x.get("end", ""), x.get("filed", ""), x.get("fy", 0)), reverse=True)
    return candidates[0]


def _metric(facts: dict[str, Any], label: str, tags: tuple[str, ...], units: tuple[str, ...] = ("USD",)) -> dict[str, Any]:
    value = _latest_fact(facts, tags, units)
    if not value:
        return {"label": label, "value": None, "unit": units[0], "period": None, "filed": None, "form": None}
    return {
        "label": label,
        "value": value["val"],
        "unit": value.get("unit", units[0]),
        "period": value.get("end"),
        "filed": value.get("filed"),
        "form": value.get("form"),
    }


def company_fundamentals(symbol: str) -> dict[str, Any]:
    """Return latest reported company facts and their filing provenance."""
    symbol = symbol.strip().upper()
    cik = _cik_for(symbol)
    facts = _cached(f"facts:{cik}", lambda: _get(f"{_BASE}/api/xbrl/companyfacts/CIK{cik:010d}.json"))
    metrics = [
        _metric(facts, "营收", ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet")),
        _metric(facts, "净利润", ("NetIncomeLoss",)),
        _metric(facts, "经营现金流", ("NetCashProvidedByUsedInOperatingActivities",)),
        _metric(facts, "资产总额", ("Assets",)),
        _metric(facts, "现金及等价物", ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents")),
        _metric(facts, "稀释每股收益", ("EarningsPerShareDiluted",), ("USD/shares",)),
    ]
    return {
        "symbol": symbol,
        "company": facts.get("entityName"),
        "cik": f"{cik:010d}",
        "source": "SEC EDGAR Company Facts",
        "source_url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "notice": "SEC 申报财报数据，不是实时行情；指标按公司最近提交的10-K或10-Q披露期显示。",
    }
