# -*- coding: utf-8 -*-
"""波段战法（Swing Strategy）——波动滚动法 · 新低附近向左看齐。

来源：用户提供的《波段战法文字版本》文档（常士杉直播语音整理）。
逻辑链路：
  大盘温度/位置 -> 三大共振（大盘不创新低 / 板块适宜 / 个股低位）
  -> 个股进场（最近3-5个交易日最低价区间「向左看齐」/ 上升趋势10日线第一次回踩）
  -> 3570按市场状态建仓 -> 3221按成交记录分段兑现 -> 20%成本保护线

美股适配：
  - 无全市场涨跌家数公开数据 -> 市场温度用 VIX + 指数走势替代
  - 只做美股；个股永远追随大盘（纳斯达克科技大盘为主），不参考A股数据
"""
import datetime as dt

import numpy as np
import pandas as pd

from formation_rules import HARD_STOP_PCT, RULE_VERSION, protection_price, rulebook
from indicators import sell_plan_3221


# ---------------- 参考常量 ----------------

CYCLES = [
    {"周期": "超短线波段", "时长": "T+0 ~ T+5（1-5个交易日）", "对应底": "小底", "操作": "抄到小底做3-5天，赚了就跑"},
    {"周期": "超级波段", "时长": "5 ~ 20个交易日", "对应底": "中底", "操作": "低价与最低价之间找最佳进场点（核心战法段）"},
    {"周期": "中期波段", "时长": "10 ~ 40个交易日", "对应底": "中期大底", "操作": "目标30%-40%，需抄到中期大底"},
]

CORE_FOUR = [
    ("大盘", "决定能不能做：大盘见底才有底可抄；半山腰/单边下跌都不做"),
    ("温度", "温度≥65及格、80-90强势、130-150较佳、过冲警惕见顶（美股用VIX+指数走势替代）"),
    ("位置", "从指数最低点到现在的位置：暴跌后的底部区域是最佳位置"),
    ("价格", "临门一脚：最近3-5个交易日最低价区间附近下单（向左看齐，胜率≈85%）"),
]

THREE_RESONANCE = [
    ("大盘", "不创新低（连续3天）、震荡正常、处于上升趋势"),
    ("行业板块", "板块不创新低、温度正常；整体跌幅20%-30%才具备波段选股条件"),
    ("个股", "价格在低位（跌幅40%-60%）、暴跌持续10-20交易日、3-5日最低价区间进场"),
]

VIX_REF = [
    ("<13", "恐慌见底（黄金坑）", "偏积极：底部信号，可关注超跌龙头"),
    ("13-18", "正常偏低", "正常：按常规温度判断"),
    ("18-25", "警惕", "偏谨慎：降低仓位，等企稳"),
    (">25", "恐慌", "观望：不做波段，等VIX回落"),
]

_FORMATION = rulebook()
EXIT_3221 = [
    (mode, f"第{number}项", label)
    for mode, key in (("标准及弱势", "standard"), ("强趋势", "strong"))
    for number, label in enumerate(_FORMATION["exit"][key], 1)
]
ADD_3570 = [
    (path["label"], " → ".join(f"+{pct}%" for pct in path["increments"]), f"累计 {path['cap_pct']}%")
    for path in _FORMATION["entry"]
] + [("A股中性震荡", "+3% → +5% → +7%", "累计 15%")]

HOT_SECTORS = ("芯片", "半导体", "存储", "AI", "算力", "太空", "核电", "电力",
               "机器人", "光模块", "液冷", "铜", "军工", "卫星")


# ---------------- ① 市场温度（美股适配） ----------------

def band_temperature(idx_d, vix_df=None, index_name="QQQ"):
    """波段战法·市场温度（美股适配：VIX + 指数走势替代涨跌家数）。

    idx_d 需先 add_indicators；vix_df 可为 None（自动降级为纯指数温度）。
    返回 dict: score(0-100), label, color, vix, vix_label, notes。
    """
    if idx_d is None or len(idx_d) < 10:
        return {"score": 0, "label": "数据不足", "color": "#95a5a6", "vix": None,
                "vix_label": "暂无VIX", "notes": ["指数数据不足，无法计算市场温度"]}
    last = idx_d.iloc[-1]
    close = idx_d["close"]
    n = len(close)
    ret1 = (float(close.iloc[-1]) / float(close.iloc[-2]) - 1) * 100 if n >= 2 else 0.0
    ret5 = (float(close.iloc[-1]) / float(close.iloc[-6]) - 1) * 100 if n >= 6 else 0.0
    rsi = float(last["RSI"]) if "RSI" in idx_d.columns and last["RSI"] == last["RSI"] else 50.0
    ma20 = float(last["MA20"]) if "MA20" in idx_d.columns and last["MA20"] == last["MA20"] \
        else float(close.rolling(20).mean().iloc[-1])
    ma20_pos = 50 + (float(last["close"]) / ma20 - 1) * 1500 if ma20 > 0 else 50.0
    ma20_pos = float(max(0.0, min(100.0, ma20_pos)))

    score = 0.4 * rsi + 0.3 * ma20_pos + 0.3 * (50 + ret5 * 5)
    score = float(max(0.0, min(100.0, score)))

    if score >= 85:
        label, color = "冲顶警惕", "#e74c3c"
    elif score >= 75:
        label, color = "较佳", "#27ae60"
    elif score >= 65:
        label, color = "强势", "#2ecc71"
    elif score >= 45:
        label, color = "及格/中性", "#e67e22"
    else:
        label, color = "偏冷/冰点", "#3498db"

    vix, vix_label, vix_color, vix_note = None, "暂无VIX", "#95a5a6", "VIX 数据不可用，温度按指数走势近似"
    if vix_df is not None and len(vix_df) > 0:
        try:
            vix = float(vix_df["close"].iloc[-1])
            if vix < 13:
                vix_label, vix_color, vix_note = "恐慌见底(<13)", "#27ae60", "VIX 恐慌见底 → 底部区域偏积极，可关注超跌龙头"
            elif vix < 18:
                vix_label, vix_color, vix_note = "正常偏低(13-18)", "#2ecc71", "VIX 正常偏低 → 情绪稳定"
            elif vix <= 25:
                vix_label, vix_color, vix_note = "警惕(18-25)", "#e67e22", "VIX 偏高 → 谨慎，降低仓位等企稳"
            else:
                vix_label, vix_color, vix_note = "恐慌(>25)", "#e74c3c", "VIX 恐慌 → 观望，不做波段"
        except Exception:
            pass

    notes = [
        "%s 近1日 %+.2f%% · 近5日 %+.2f%% · RSI %.1f" % (index_name, ret1, ret5, rsi),
        "温度分 %.0f → %s（≥65及格 · 80-90强势 · 130-150较佳为A股口径，美股按0-100折算）" % (score, label),
        "VIX：%s → %s" % (vix_label, vix_note),
    ]
    return {"score": score, "label": label, "color": color,
            "vix": vix, "vix_label": vix_label, "vix_color": vix_color,
            "vix_note": vix_note, "notes": notes}


# ---------------- ② 市场位置 ----------------

def market_position(idx_d, window=90):
    """市场位置：距近 window 日最低点涨幅 + 连续不创新低/新高天数。

    底部企稳：连续3天不创新低；见顶警惕：连续3天创新高。
    """
    if idx_d is None or len(idx_d) < 25:
        return {"可用": False, "zone": "数据不足", "color": "#95a5a6", "rise_from_low": 0.0,
                "pos90": 50.0, "streak_no_low": 0, "streak_no_high": 0,
                "bottom_ok": False, "top_warn": False}
    close = idx_d["close"]
    low_w = float(idx_d["low"].tail(window).min())
    high_w = float(idx_d["high"].tail(window).max())
    last_c = float(close.iloc[-1])
    rise = (last_c / low_w - 1) * 100 if low_w > 0 else 0.0
    pos90 = (last_c - low_w) / (high_w - low_w) * 100 if high_w > low_w else 50.0

    rolling_low = close.rolling(20).min().shift(1)
    rolling_high = close.rolling(20).max().shift(1)
    streak_no_low = 0
    for i in range(len(close) - 1, -1, -1):
        rl = rolling_low.iloc[i]
        if not np.isnan(rl) and float(close.iloc[i]) > rl:
            streak_no_low += 1
        else:
            break
    streak_no_high = 0
    for i in range(len(close) - 1, -1, -1):
        rh = rolling_high.iloc[i]
        if not np.isnan(rh) and float(close.iloc[i]) < rh:
            streak_no_high += 1
        else:
            break

    if rise <= 12 or pos90 <= 15:
        zone, color = "底部区域", "#27ae60"
    elif pos90 >= 85 or rise >= 60:
        zone, color = "高位区", "#e74c3c"
    else:
        zone, color = "半山腰", "#e67e22"

    return {"可用": True, "zone": zone, "color": color,
            "rise_from_low": round(rise, 2), "pos90": round(pos90, 1),
            "low_ref": low_w, "last": last_c,
            "streak_no_low": streak_no_low, "streak_no_high": streak_no_high,
            "bottom_ok": streak_no_low >= 3, "top_warn": streak_no_high >= 3}


# ---------------- ③ 大盘环境（三大共振第①条） ----------------

def swing_environment(idx_d, vix_df=None, index_name="QQQ"):
    """波段战法·大盘环境：不创新低 + 不会暴跌 + 上升趋势（三大共振第①条）。"""
    if idx_d is None or len(idx_d) < 30:
        return {"可用": False, "score": 0, "level": "数据不足", "color": "#95a5a6",
                "结论": "指数数据不足，无法判断大盘环境", "conds": {}, "notes": [], "cond_count": 0}
    temp = band_temperature(idx_d, vix_df, index_name)
    pos = market_position(idx_d)
    last = idx_d.iloc[-1]
    close = idx_d["close"]
    ma20 = float(last["MA20"]) if "MA20" in idx_d.columns and last["MA20"] == last["MA20"] \
        else float(close.rolling(20).mean().iloc[-1])
    ma20_prev = float(idx_d["MA20"].iloc[-6]) if len(idx_d) > 6 and "MA20" in idx_d.columns \
        and idx_d["MA20"].iloc[-6] == idx_d["MA20"].iloc[-6] else ma20
    above_ma20 = float(last["close"]) > ma20
    ma20_up = ma20 > ma20_prev

    ret10 = close.pct_change().tail(10).dropna()
    worst = float(ret10.min()) * 100 if len(ret10) else 0.0

    conds = {
        "大盘不创新低（连续3天）": pos["bottom_ok"],
        "大盘不会暴跌（近10日最差单日>-4%）": worst > -4.0,
        "大盘上升趋势（站上MA20且MA20向上）": above_ma20 and ma20_up,
    }
    cond_count = sum(1 for v in conds.values() if v)

    score = 40 + cond_count * 15 + (temp["score"] - 65) * 0.4
    if pos["zone"] == "底部区域":
        score += 8
    elif pos["zone"] == "高位区":
        score -= 12
    score = int(max(0, min(100, score)))

    if score >= 75 and cond_count >= 2:
        level, color, concl = "共振可做", "#27ae60", "大盘三大条件基本满足 → 可进入选股/择时环节"
    elif score >= 55 and cond_count >= 1:
        level, color, concl = "部分共振", "#e67e22", "大盘条件部分满足 → 小仓试，严选超跌低位股"
    else:
        level, color, concl = "回避", "#e74c3c", "大盘不满足波段前提（半山腰/单边下跌）→ 空仓等底"

    notes = [
        "温度 %.0f（%s）· VIX %s" % (temp["score"], temp["label"], temp["vix_label"]),
        "位置 %s（距90日低点 %+.1f%%，连续 %d 天不创新低）" % (pos["zone"], pos["rise_from_low"], pos["streak_no_low"]),
        "近10日最差单日 %+.2f%% · 站上MA20：%s · MA20方向：%s" % (worst, "是" if above_ma20 else "否", "上" if ma20_up else "下"),
    ]
    return {"可用": True, "score": score, "level": level, "color": color, "结论": concl,
            "conds": conds, "notes": notes, "cond_count": cond_count,
            "temp": temp, "pos": pos}


# ---------------- ④ 行业板块检查 ----------------

def sector_check(sector, d=None, idx_d=None):
    """板块检查（三大共振第②条）：主线热门赛道 + 不创新低（近似）。

    板块指数数据未接入 → 用「赛道是否主线热门 + 个股相对大盘强弱」近似。
    """
    hot = any(k in str(sector) for k in HOT_SECTORS)
    notes = []
    rel_ok = None
    if d is not None and idx_d is not None and len(d) > 21 and len(idx_d) > 21:
        stock_ret20 = (float(d["close"].iloc[-1]) / float(d["close"].iloc[-22]) - 1) * 100
        idx_ret20 = (float(idx_d["close"].iloc[-1]) / float(idx_d["close"].iloc[-22]) - 1) * 100
        rel_ok = stock_ret20 >= idx_ret20 - 3
        notes.append("近20日个股 %+.1f%% vs 大盘 %+.1f%% → %s"
                     % (stock_ret20, idx_ret20, "抗跌/强于大盘（板块温度较好）" if rel_ok else "弱于大盘，板块温度存疑"))
    ok = hot and (rel_ok is not False)
    label = "主线热门赛道" if hot else "非主线赛道（需人工确认板块温度）"
    if not ok and hot:
        label = "热门赛道但个股弱于大盘（需确认板块是否不创新低）"
    return {"hot": hot, "rel_ok": rel_ok, "ok": ok, "label": label, "notes": notes}


# ---------------- ⑤ 个股位置（向左看齐） ----------------

def stock_position(d, lookback=5):
    """个股位置（三大共振第③条）：3-5日最低价区间「向左看齐」+ 超跌 + 企稳。

    核心：最近3-5个交易日找到最低价，在最低价附近（3%以内）下单，胜率≈85%。
    """
    if d is None or len(d) < 25:
        return {"可用": False, "level": "数据不足", "level_color": "#95a5a6", "buy_ok": False,
                "stable": False, "dist_to_low": 99.0, "drawdown": 0.0,
                "decline_days": 0, "streak_no_low": 0, "zone_min": 0.0, "zone_max": 0.0,
                "buy_ref": 0.0, "limit_price": 0.0}
    last = d.iloc[-1]
    close = d["close"]
    low3 = float(d["low"].tail(3).min())
    low5 = float(d["low"].tail(5).min())
    zone_min = low5
    zone_max = float(d["low"].tail(3).max())
    last_c = float(last["close"])
    dist = (last_c / zone_min - 1) * 100 if zone_min > 0 else 0.0

    high120 = float(d["high"].tail(120).max()) if len(d) >= 60 else float(d["high"].max())
    dd = (high120 - last_c) / high120 * 100 if high120 > 0 else 0.0

    hi_pos = d["high"].tail(120).idxmax() if len(d) >= 60 else d["high"].idxmax()
    try:
        hi_loc = d.index.get_loc(hi_pos)
        decline_days = len(d) - 1 - hi_loc
    except Exception:
        decline_days = 0

    rolling_low = close.rolling(20).min().shift(1)
    streak_no_low = 0
    for i in range(len(close) - 1, -1, -1):
        rl = rolling_low.iloc[i]
        if not np.isnan(rl) and float(close.iloc[i]) > rl:
            streak_no_low += 1
        else:
            break

    if dd >= 40:
        level, level_color = "超跌（40%+）· 波段选股区", "#27ae60"
    elif dd >= 20:
        level, level_color = "温和回撤（20%-40%）", "#e67e22"
    else:
        level, level_color = "未深跌（<20%）· 追高风险", "#e74c3c"

    buy_ok = dist <= 3.0
    stable = streak_no_low >= 3
    return {"可用": True, "level": level, "level_color": level_color,
            "zone_min": zone_min, "zone_max": zone_max, "low3": low3, "low5": low5,
            "dist_to_low": round(dist, 2), "drawdown": round(dd, 1),
            "decline_days": decline_days, "streak_no_low": streak_no_low,
            "buy_ok": buy_ok, "stable": stable,
            "buy_ref": zone_min, "limit_price": round(zone_min * 1.03, 2),
            "last": last_c}


# ---------------- ⑥ 10日线第一次回踩 ----------------

def ma_pullback_events(d, ma="MA10", recent=80):
    """上升趋势中回踩均线事件（默认10日线）。

    文档规则：上升趋势第一次回踩=进场信号；第二、三次回踩危险；
    连续3天收在均线下方=趋势转震荡，切换「震荡不创新低+最低价」打法。
    """
    if d is None or len(d) < 30 or ma not in d.columns:
        return {"events": [], "latest": None, "type": "none", "count": 0,
                "note": "数据不足，无法检测均线回踩", "ma": ma}
    seg = d.tail(recent).copy()
    events = []
    for i in range(1, len(seg) - 1):
        day = seg.iloc[i]
        prev = seg.iloc[i - 1]
        nxt = seg.iloc[i + 1]
        ma_v = float(day[ma])
        if np.isnan(ma_v):
            continue
        prev_ma = float(prev[ma])
        if np.isnan(prev_ma):
            continue
        above_before = float(prev["close"]) > prev_ma
        touch = float(day["low"]) <= ma_v and float(day["close"]) >= ma_v
        bounce = float(nxt["close"]) > ma_v
        up = False
        if "MA20" in seg.columns:
            m20 = float(day["MA20"])
            if not np.isnan(m20):
                up = float(day["close"]) > m20
        else:
            up = float(day["close"]) > ma_v
        if above_before and touch and bounce and up:
            events.append(seg.index[i])

    if not events:
        return {"events": [], "latest": None, "type": "none", "count": 0,
                "note": "近期无%s回踩事件（上升趋势中第一次回踩才是进场点）" % ma, "ma": ma}

    latest = events[-1]
    recent_hit = (len(seg) - 1 - seg.index.get_loc(latest)) <= 10
    recent_events = [e for e in events if len(seg) - 1 - seg.index.get_loc(e) <= 40]
    count = len(recent_events)
    if count >= 2:
        typ, note = "repeat", "近期第 %d 次回踩%s → 第二/三次回踩危险，只做第一次" % (count, ma)
    elif recent_hit:
        typ, note = "first", "上升趋势中第一次回踩%s（%s）→ 进场信号" % (ma, latest.strftime("%Y-%m-%d"))
    else:
        typ, note = "none", "最近一次回踩在 %s，已较远，等新回踩" % latest.strftime("%Y-%m-%d")
    return {"events": events, "latest": latest, "type": typ, "count": count, "note": note, "ma": ma}


# ---------------- ⑦ 仓位 / 出场 / 加仓 ----------------

def band_exit_plan(cost, price):
    """Compatibility adapter. A price snapshot cannot establish actual reductions."""
    plan = sell_plan_3221(cost, price)
    if plan is None:
        return None
    stop = float(protection_price(float(cost)))
    return {
        "chg": plan["gain_pct"], "done": [],
        "pending": [(threshold, label) for threshold, _, label in plan["pending"]],
        "keep": plan["keep"], "sl_hard": round(stop, 2),
        "dist_hard": round((price / stop - 1) * 100, 2),
        "rule": plan["rule"], "rule_version": RULE_VERSION,
    }


def band_add_3570(cost, price):
    """Show the documented paths while leaving all execution stages unconfirmed."""
    if not cost or cost <= 0:
        return None
    return {
        "chg": round((price / cost - 1) * 100, 2),
        "steps": [(label, f"{path} · {cap}", False) for label, path, cap in ADD_3570],
        "confirm": False, "rule_version": RULE_VERSION,
        "rule": "浮盈且获得新的趋势证据后才可加仓；市场状态和已成交档次须人工确认。",
    }


# ---------------- ⑧ 综合结论 ----------------

def swing_conclusion(env, sector_ok, sp, pb):
    """大盘 × 板块 × 个股位置 × 均线回踩 → 波段操作结论。"""
    if not env.get("可用"):
        return "⚠ 数据不足：指数数据不可用，无法判断波段环境"
    if env["level"] == "回避":
        return "❌ 大盘回避（半山腰/单边下跌/条件不足）→ 空仓等待，不抄底"
    if not sector_ok.get("ok", False):
        return "⚠ 行业板块未确认（需主线热门赛道 + 不创新低）→ 只做最熟悉的热门赛道龙头"
    if not sp.get("可用"):
        return "⚠ 个股数据不足，等待"
    if sp["level"].startswith("未深跌"):
        return "⚠ 个股未深跌（追高风险）→ 等回调至低位再考虑"
    if sp["buy_ok"] and sp["stable"]:
        return "✅ 三重共振：大盘 + 板块 + 个股低位企稳 → 新低附近向左看齐，可分批进场"
    if sp["buy_ok"]:
        return "🟢 个股已到3-5日最低价区间（向左看齐）→ 大盘/板块配合即可进"
    if pb and pb["type"] == "first":
        return "🟢 上升趋势中第一次回踩%s → 进场信号（第二/三次回踩危险）" % pb["ma"]
    if pb and pb["type"] == "repeat":
        return "⚠ 近期第 %d 次回踩%s → 危险，不追，等新低企稳" % (pb["count"], pb["ma"])
    return "⏳ 条件未齐：等个股回到3-5日最低价区间附近再进"


# ---------------- 决策卡 ----------------

def build_band_card(ticker, name, env, sector_ok, sp, pb, ex, add, index_name, price):
    lines = []
    lines.append("## 【波段战法决策卡】%s · %s（%s）" % (ticker, name, dt.datetime.now().strftime("%Y-%m-%d %H:%M")))
    lines.append("")
    lines.append("> 大盘（%s）：**%s %d/100** —— %s" % (index_name, env["level"], env["score"], env["结论"]))
    if env.get("temp"):
        lines.append("> 温度：**%s**（VIX：%s）" % (env["temp"]["label"], env["temp"]["vix_label"]))
    if env.get("pos"):
        lines.append("> 位置：**%s**（连续%d天不创新低）" % (env["pos"]["zone"], env["pos"]["streak_no_low"]))
    lines.append("> 板块：**%s**" % sector_ok["label"])
    if sp.get("可用"):
        lines.append("> 个股：**%s** · 距5日最低 %.2f%%（买点参考 $%.2f，±3%%区间 $%.2f）"
                     % (sp["level"], sp["dist_to_low"], sp["buy_ref"], sp["limit_price"]))
        lines.append("> 跌幅：**%.1f%%** · 下跌持续 %d 个交易日 · 连续%d天不创新低"
                     % (sp["drawdown"], sp["decline_days"], sp["streak_no_low"]))
    if pb and pb["type"] != "none":
        lines.append("> 均线回踩：**%s**" % pb["note"])
    lines.append("")
    lines.append("### 操作清单（按纪律执行）")
    lines.append("- 顺序：先看大盘（决定能不能做）→ 再看板块（不创新低）→ 最后看个股（3-5日最低价区间）")
    lines.append("- 进场：最近3-5个交易日最低价附近下单（向左看齐，胜率≈85%）；有底仓才能T+0降低成本")
    if ex:
        lines.append(f"- 当前浮盈 {ex['chg']:+.2f}%。3221需依据市场状态与已成交的减仓档次，价格无法确认已卖出。")
        lines.append(f"- {HARD_STOP_PCT}%成本保护参考 **${ex['sl_hard']:.2f}**；原保护价更紧时沿用原价。")
    if add:
        lines.append("- 3570路径按市场状态选择。盈利且有新证据才考虑下一档，高风险仅试仓。")
    lines.append("- 请在「3570 / 3221」填写实际成本、股数和成交进度，再核对下一步。")
    lines.append("")
    lines.append("---")
    lines.append("*波段战法来源于直播课程笔记整理，仅供个人研究参考，不构成投资建议；决策由用户人工执行。*")
    return "\n".join(lines)