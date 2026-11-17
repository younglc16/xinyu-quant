# -*- coding: utf-8 -*-
"""FastAPI presentation layer for the XinYu quantitative decision system.

The analytical modules remain the single source of truth.  This file only
normalises their outputs for the React client and serves the production build.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import data_provider as dp
import cedar_strategy as cedar
import ai_berkshire as ab
import band_strategy as band
import industry_rank as industry
import master_insights as masters
import short_system as shortsys
import shortterm as shortterm
import skills_center as skills
import top10_models as top10
from indicators import add_indicators, signal_checks
from scoring import five_dim_score, market_temperature, quality_x_timing, temperature_history


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "frontend" / "dist"

app = FastAPI(
    title="鑫煜量化决策系统 API",
    version="3.3.0",
    description="React UI adapter over the existing investment and risk framework.",
)


def _clean(value: Any) -> Any:
    """Convert pandas/numpy values into strict JSON-compatible primitives."""
    if isinstance(value, pd.DataFrame):
        return [_clean(row) for row in value.reset_index().to_dict(orient="records")]
    if isinstance(value, pd.Series):
        return _clean(value.to_dict())
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_clean(v) for v in value]
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if value is pd.NA:
        return None
    return value


def _name_map() -> dict[str, str]:
    names: dict[str, str] = {}
    for symbol, label in dp.WATCHLIST:
        names[symbol] = label.split("·", 1)[0].strip()
    return names


NAMES = _name_map()


def _name_of(symbol: str) -> str:
    return NAMES.get(symbol, symbol)


def _sector_of(symbol: str) -> str:
    return dp.SECTOR_MAP.get(symbol, "未分类 · 等待研究")


def _chart_rows(frame: pd.DataFrame, limit: int = 140) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, row in frame.tail(limit).iterrows():
        rows.append(
            {
                "time": pd.Timestamp(idx).isoformat(),
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume"),
                "ma5": row.get("MA5"),
                "ma20": row.get("MA20"),
                "ma60": row.get("MA60"),
                "k": row.get("K"),
                "d": row.get("D"),
                "j": row.get("J"),
                "dif": row.get("DIF"),
                "dea": row.get("DEA"),
                "macd": row.get("MACD"),
            }
        )
    return _clean(rows)


def _period_frame(symbol: str, period: str, daily: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    if period == "weekly":
        raw = dp.get_weekly(symbol, 900)
        return add_indicators(raw), dp.source_label("weekly", symbol)
    if period == "monthly":
        raw = dp.get_monthly(symbol, 1800)
        return add_indicators(raw), dp.source_label("monthly", symbol)
    if period == "intraday":
        raw = dp.get_intraday(symbol)
        if raw is not None and len(raw) >= 10:
            return add_indicators(raw), dp.source_label("intraday", symbol)
    return daily, dp.source_label("daily", symbol)


def _signal_rows(signals: dict[str, Any], score: dict[str, Any], risk: dict[str, Any]) -> list[dict[str, str]]:
    ma_pass = signals.get("ma", {}).get("多头排列") == "是"
    volume_text = str(signals.get("volume", {}).get("信号", "等待数据"))
    volume_pass = "确认" in volume_text and "未确认" not in volume_text
    risk_pass = float(risk.get("score", 0)) >= 55
    value_pass = float(score.get("估值", 0)) >= 60
    return [
        {"label": "趋势结构", "detail": str(signals.get("ma", {}).get("信号", "—")), "state": "pass" if ma_pass else "wait"},
        {"label": "量能确认", "detail": volume_text, "state": "pass" if volume_pass else "wait"},
        {"label": "估值代理", "detail": f"估值得分 {score.get('估值', '—')}", "state": "pass" if value_pass else "wait"},
        {"label": "风险隔离", "detail": str(risk.get("level", "—")), "state": "pass" if risk_pass else "fail"},
    ]


def _evidence_chain(score: dict[str, Any], signals: dict[str, Any], risk: dict[str, Any], leader: dict[str, Any]) -> list[dict[str, Any]]:
    items = [
        ("赛道位置", f"赛道评分 {score.get('赛道')} · {_sector_of(str(signals.get('_symbol', '')))}", score.get("赛道", 0)),
        ("趋势结构", str(signals.get("ma", {}).get("信号", "—")), score.get("趋势", 0)),
        ("量价关系", str(signals.get("volume", {}).get("信号", "—")), score.get("成长", 0)),
        ("风险边界", f"{risk.get('level')} · 结构分 {risk.get('score')}", risk.get("score", 0)),
        ("市场角色", str(leader.get("kind", "观察")), score.get("综合", 0)),
    ]
    return [
        {"label": label, "detail": detail, "score": round(float(value or 0)), "state": "pass" if float(value or 0) >= 70 else "wait"}
        for label, detail, value in items
    ]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "ui": "unified-v3", "version": "3.3.0", "logic": "existing-python-modules"}


@app.get("/api/watchlist")
def watchlist() -> dict[str, Any]:
    return {
        "items": [
            {"symbol": symbol, "name": _name_of(symbol), "sector": _sector_of(symbol)}
            for symbol, _ in dp.WATCHLIST
        ],
        "indices": [{"symbol": key, "name": value} for key, value in dp.INDEX_CHOICES.items()],
    }


@app.get("/api/terminal/{symbol}")
def terminal(
    symbol: str,
    period: Literal["intraday", "daily", "weekly", "monthly"] = "daily",
    index: str = Query(default="QQQ", pattern="^(QQQ|SPY|DIA)$"),
    capital: float = Query(default=100000, ge=1000, le=1000000000),
) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    try:
        raw = dp.get_daily(symbol, 320)
        index_raw = dp.get_index_daily(index, 220)
        if raw is None or raw.empty:
            raise ValueError(f"无法获取 {symbol} 日线数据")
        if index_raw is None or index_raw.empty:
            raise ValueError(f"无法获取 {index} 指数数据")

        daily = add_indicators(raw)
        index_daily = add_indicators(index_raw)
        chart_frame, chart_source = _period_frame(symbol, period, daily)
        weekly_raw = dp.get_weekly(symbol, 900)
        weekly = add_indicators(weekly_raw) if weekly_raw is not None and not weekly_raw.empty else None

        signals = signal_checks(daily)
        signals["_symbol"] = symbol
        temperature = market_temperature(index_daily)
        score = five_dim_score(daily, _sector_of(symbol))
        matrix = quality_x_timing(score, signals, temperature)
        risk = cedar.risk_isolation(daily, index_daily, signals)
        macro = cedar.macro_timing(index_daily, f"{index} · {dp.INDEX_CHOICES[index]}")
        redline = cedar.redline_check(daily)
        leader = cedar.leader_rank(daily)
        three_low = cedar.three_low_score(daily)
        five_day = cedar.five_day_signal(daily)
        volume_price = cedar.volume_price_confirm(daily)
        endgame = cedar.endgame(daily, index_daily, weekly)
        position = cedar.position_plan_cedar(temperature["temp"], capital, "普通投资者")

        last = daily.iloc[-1]
        previous = daily.iloc[-2] if len(daily) > 1 else last
        change_pct = (float(last["close"]) / float(previous["close"]) - 1) * 100
        quote = dp.get_realtime_quote(symbol) or {
            "price": float(last["close"]),
            "change_pct": change_pct,
            "source": dp.source_label("daily", symbol),
        }
        history = temperature_history(index_daily).tail(90)
        stop_reference = float(last["close"]) * 0.925
        stage = "识别机会"
        if not redline.get("ok", True) or risk.get("score", 100) < 55:
            stage = "风险观察"
        elif five_day.get("above5") and volume_price.get("q") == "放量":
            stage = "执行或等待"
        elif five_day.get("above5"):
            stage = "验证触发"

        recent = daily.tail(60)
        returns = recent["close"].pct_change().dropna()
        metrics = {
            "close": float(last["close"]),
            "change_pct": change_pct,
            "high_60": float(recent["high"].max()),
            "low_60": float(recent["low"].min()),
            "volume": float(last["volume"]),
            "volatility_annual": float(returns.std() * np.sqrt(252) * 100) if len(returns) else 0,
            "ma5": last.get("MA5"),
            "ma10": last.get("MA10"),
            "ma20": last.get("MA20"),
            "ma60": last.get("MA60"),
            "rsi": last.get("RSI"),
            "j": last.get("J"),
            "vr7": last.get("VR7"),
        }

        return _clean(
            {
                "meta": {
                    "symbol": symbol,
                    "name": _name_of(symbol),
                    "sector": _sector_of(symbol),
                    "as_of": pd.Timestamp(daily.index[-1]).isoformat(),
                    "source": dp.source_label("daily", symbol),
                    "chart_source": chart_source,
                    "index": index,
                    "index_name": dp.INDEX_CHOICES[index],
                },
                "quote": quote,
                "chart": _chart_rows(chart_frame),
                "metrics": metrics,
                "temperature": {
                    **temperature,
                    "history": [{"time": pd.Timestamp(ts).isoformat(), "value": value} for ts, value in history.items()],
                },
                "score": score,
                "matrix": matrix,
                "signals": signals,
                "signal_rows": _signal_rows(signals, score, risk),
                "risk": risk,
                "macro": macro,
                "redline": redline,
                "leader": leader,
                "three_low": three_low,
                "five_day": five_day,
                "volume_price": volume_price,
                "endgame": endgame,
                "position": position,
                "execution": {
                    "stage": stage,
                    "stop_reference": stop_reference,
                    "single_stock_cap_pct": 20,
                    "single_sector_cap_pct": 30,
                    "ladder": [3, 5, 7, 10],
                    "evidence": _evidence_chain(score, signals, risk, leader),
                },
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _recent_rows(frame: pd.DataFrame, limit: int = 15) -> list[dict[str, Any]]:
    columns = ["open", "high", "low", "close", "volume", "MA5", "MA20", "J", "RSI", "DIF", "DEA", "MACD", "Dev5", "VR3"]
    available = [column for column in columns if column in frame.columns]
    rows: list[dict[str, Any]] = []
    for idx, row in frame.tail(limit).sort_index(ascending=False).iterrows():
        item = {"date": pd.Timestamp(idx).strftime("%Y-%m-%d")}
        item.update({column: row[column] for column in available})
        rows.append(item)
    return _clean(rows)


def _signal_table(signals: dict[str, Any]) -> list[dict[str, str]]:
    titles = {
        "macd_kdj": "MACD+KDJ 双指标共振",
        "resonance": "MACD+KDJ 共振信号",
        "kdj": "KDJ 战法",
        "ma5": "五日线纪律",
        "volume": "量能确认",
        "ma": "均线状态",
        "cycle": "分歧周期",
        "range60": "60日区间",
    }
    rows: list[dict[str, str]] = []
    for key, title in titles.items():
        for field, value in signals.get(key, {}).items():
            rows.append({"group": title, "field": str(field), "value": str(value)})
    return rows


@app.get("/api/systems/{symbol}")
def systems(
    symbol: str,
    index: str = Query(default="QQQ", pattern="^(QQQ|SPY|DIA)$"),
    capital: float = Query(default=100000, ge=1000, le=1000000000),
    cost: float = Query(default=0, ge=0, le=1000000000),
    short_event: str = Query(default="无（当前无高概率利空事件）"),
) -> dict[str, Any]:
    """Return every original framework used by the Streamlit application's 12 tabs."""
    symbol = symbol.strip().upper()
    try:
        raw = dp.get_daily(symbol, 420)
        index_raw = dp.get_index_daily(index, 320)
        if raw is None or raw.empty or index_raw is None or index_raw.empty:
            raise ValueError("行情或指数数据不可用")
        daily = add_indicators(raw)
        index_daily = add_indicators(index_raw)
        weekly_raw = dp.get_weekly(symbol, 1000)
        weekly = add_indicators(weekly_raw) if weekly_raw is not None and not weekly_raw.empty else None
        intraday = dp.get_intraday(symbol)
        vix = dp.get_vix(120)

        signal_data = signal_checks(daily)
        temp = market_temperature(index_daily)
        score = five_dim_score(daily, _sector_of(symbol))
        matrix = quality_x_timing(score, signal_data, temp)
        last_price = float(daily.iloc[-1]["close"])

        # Tab 4: 超短线战法
        st_env = shortterm.index_environment(index_daily)
        st_pattern = shortterm.detect_intraday_pattern(intraday)
        st_five = shortterm.five_most_auto(signal_data, daily, _sector_of(symbol))
        st_position = shortterm.position_plan(capital)
        st_exit = shortterm.exit_plan(cost, last_price) if cost > 0 else None

        # Tab 5: 大师智慧
        master_check = masters.master_checklist(signal_data, score, temp, matrix, daily, index_daily)
        inversion, violations = masters.munger_inversion_checks(signal_data, matrix, temp, score)

        # Tab 6: 做空体系
        short_signals = shortsys.short_technical_signals(signal_data, daily, temp)
        short_tech = shortsys.short_technical_score(short_signals)
        event = short_event if short_event in shortsys.EVENT_CHOICES else list(shortsys.EVENT_CHOICES.keys())[0]
        short_macro = shortsys.macro_score(event, temp)
        short_fund = shortsys.fundamental_short_score(score)
        short_score = shortsys.short_composite(short_tech, short_macro, short_fund)
        short_rating = shortsys.short_rating(short_score)

        # Tab 9: 波段战法
        band_env = band.swing_environment(index_daily, vix, f"{index} · {dp.INDEX_CHOICES[index]}")
        band_sector = band.sector_check(_sector_of(symbol), daily, index_daily)
        band_stock = band.stock_position(daily)
        band_pullback = band.ma_pullback_events(daily)
        band_exit = band.band_exit_plan(cost, last_price) if cost > 0 else None
        band_add = band.band_add_3570(cost, last_price) if cost > 0 else None

        # Tab 10: 五步决策漏斗
        step1 = cedar.macro_timing(index_daily, index)
        step2 = cedar.composite_score(score)
        redline = cedar.redline_check(daily)
        leader = cedar.leader_rank(daily)
        step3 = cedar.risk_isolation(daily, index_daily, signal_data)
        tactic_a = cedar.three_low_score(daily)
        tactic_b = cedar.five_day_signal(daily)
        tactic_c = cedar.weekly_13_week(weekly)
        volume_gate = cedar.volume_price_confirm(daily)
        step5 = cedar.endgame(daily, index_daily, weekly)
        tactic_trigger = tactic_a.get("trigger", False) or (tactic_b.get("above5") and tactic_b.get("color") == "#27ae60")
        funnel = cedar.funnel_conclusion({"step1": step1, "step2_red": redline, "step3": step3, "step4": {"触发": tactic_trigger, "结论": tactic_a["结论"]}})

        # Tab 11/12: 仓位与十大思维
        position_levels = {
            ability: cedar.position_plan_cedar(temp["temp"], capital, ability)
            for ability in ["普通投资者", "高手", "顶尖高手"]
        }
        reviews = top10.auto_review(signal_data, score, temp, matrix, daily, index_daily, _sector_of(symbol), cost, violations=violations)

        return _clean({
            "meta": {"symbol": symbol, "name": _name_of(symbol), "sector": _sector_of(symbol), "index": index},
            "signals_data": {"table": _signal_table(signal_data), "recent": _recent_rows(daily)},
            "shortterm": {
                "environment": st_env,
                "pattern": st_pattern,
                "five_most": st_five,
                "position": st_position,
                "exit": st_exit,
                "conclusion": shortterm.overall_conclusion(st_env, st_pattern),
                "pattern_reference": shortterm.PATTERN_REF,
                "exit_cycle": shortterm.EXIT_CYCLE,
                "best_environment": shortterm.BEST_ENV,
                "philosophy": shortterm.PHILOSOPHY,
            },
            "masters": {
                "checklist": master_check,
                "inversion": [{"item": row[0], "current": row[1], "verdict": row[2]} for row in inversion],
                "books": masters.BOOKS,
            },
            "short_system": {
                "score": short_score,
                "rating": short_rating[0],
                "rating_color": short_rating[1],
                "technical_score": short_tech,
                "macro_score": short_macro,
                "fundamental_score": short_fund,
                "technical_signals": short_signals,
                "matrix": shortsys.LONG_SHORT_MATRIX,
                "risk_checks": [{"item": row[0], "rule": row[1], "note": row[2]} for row in shortsys.short_risk_checks(short_signals, daily, score)],
                "events": [{"event": row[0], "logic": row[1], "weight": row[2]} for row in shortsys.MACRO_EVENTS],
                "event_choices": list(shortsys.EVENT_CHOICES.keys()),
                "selected_event": event,
            },
            "ai_berkshire": {
                "market_note": ab.MARKET_NOTE,
                "gates": ab.GATES,
                "masters": ab.MASTERS,
                "veto_list": ab.VETO_LIST,
                "skills": skills.SKILLS,
            },
            "industry": {
                "top3": industry.TOP3_TEXT,
                "matched": industry.match_sector(_sector_of(symbol)),
                "tracks": industry.TRACKS,
                "method": ["时代大趋势", "产业链需求", "核心资源", "锁定赛道龙头"],
            },
            "band": {
                "environment": band_env,
                "sector": band_sector,
                "stock_position": band_stock,
                "pullbacks": band_pullback,
                "exit": band_exit,
                "add": band_add,
                "conclusion": band.swing_conclusion(band_env, band_sector, band_stock, band_pullback),
                "cycles": band.CYCLES,
                "core_four": band.CORE_FOUR,
                "three_resonance": band.THREE_RESONANCE,
                "exit_3221": band.EXIT_3221,
                "add_3570": band.ADD_3570,
                "formation_rule_version": band.RULE_VERSION,
            },
            "funnel": {
                "conclusion": funnel,
                "step1_macro": step1,
                "step2_score": step2,
                "step2_redline": redline,
                "leader": leader,
                "step3_risk": step3,
                "tactic_a": tactic_a,
                "tactic_b": tactic_b,
                "tactic_c": tactic_c,
                "volume_gate": volume_gate,
                "step5_endgame": step5,
            },
            "position": {
                "temperature": temp,
                "levels": position_levels,
                "formations": [
                    {"name": "3-2-2-2", "use": "建仓节奏", "detail": "底仓30% → 量能确认后20%×2 → 留现金10%；亏损不摊平"},
                    {"name": "3221", "use": "分层止盈", "detail": "按市场状态、浮盈区间和已成交档次分批减仓，保护利润优先"},
                    {"name": "3331", "use": "建仓阵型", "detail": "初建30% → 浮盈加30% → 再加30% → 新高补10%"},
                    {"name": "3570", "use": "分层建仓", "detail": "按市场状态选增量路径，浮盈且获新证据后才考虑加仓"},
                ],
                "temperature_tiers": [
                    {"tier": "低温", "position": "6-7成", "mindset": "贪（敢接）"},
                    {"tier": "中温", "position": "5-6成", "mindset": "滑（滚动复利）"},
                    {"tier": "高温", "position": "≤3成或只留底仓", "mindset": "怕（保护利润）"},
                ],
            },
            "models": {"items": top10.MODELS, "reviews": reviews, "summary": top10.summary_stats(reviews), "preflight": top10.PRE_FLIGHT},
        })
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/ai-berkshire/{symbol}")
def ai_berkshire_analysis(symbol: str) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    try:
        if blocked := ab.is_blocked_market(symbol):
            raise HTTPException(status_code=400, detail=f"当前系统不支持 {symbol}：{blocked}")
        return _clean(ab.run_analysis(symbol, _sector_of(symbol), _name_of(symbol)))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# Unified desktop service shares the original analytical modules.
from v3_api import router as unified_router
app.include_router(unified_router)
from research_api import router as research_router
app.include_router(research_router)
from wolf_api import router as wolf_router
app.include_router(wolf_router)

@app.middleware('http')
async def local_write_guard(request, call_next):
    from fastapi.responses import JSONResponse
    from urllib.parse import urlsplit
    origin = request.headers.get('origin')
    if request.url.path.startswith('/api/v3') and request.method in ('POST','PATCH','DELETE','PUT'):
        if origin and (urlsplit(origin).netloc != request.headers.get('host') or urlsplit(origin).scheme not in ('http','https')):
            return JSONResponse({'detail':'仅允许本地应用页面修改数据'}, status_code=403)
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail':'拒绝跨站写入'}, status_code=403)
    response = await call_next(request)
    if request.url.path == '/' or request.url.path.endswith(('.html','.js','.css')):
        response.headers['Cache-Control']='no-cache'
    return response

if DIST.exists():
    assets = DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def react_app(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(404, "接口不存在")
        candidate = DIST / full_path
        if full_path and candidate.is_file() and DIST in candidate.resolve().parents:
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
