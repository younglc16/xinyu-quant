# -*- coding: utf-8 -*-
"""五步决策系统（Five-Step Decision System）——五步交易法决策漏斗框架。

五步交易法决策漏斗：
  Step 1 宏观择时（板块指数趋势 -> 做多/空仓方向锚）
  Step 2 微观选股（综合评分矩阵 + 基本面排雷红线一票否决 + 龙头/潜龙定位）
  Step 3 风险隔离（结构性风险评分 + 事件性风险预警 + 30/20 资金防火墙）
  Step 4 战术执行（战法A三低买入 / 战法B五日线 / 战法C 13周时空 + 量能确认闸）
  Step 5 终局思维（板块清仓 -> 个股周线止损 -> 止盈阶梯 -> 落袋复投）

仓位管理：温度定上限(100-温度 + 三档) / 个人能力 / 30-20 分散 / 四套阵型。
三低体系：低位 / 地量 / 低关注 / 基本面未坏。量价确认：放量/地量/缩量 + 量价口诀。
"""
import numpy as np
import pandas as pd


# ---------------- Step 1 · 宏观择时 ----------------

def macro_timing(idx_d, name="QQQ"):
    """第一步 · 宏观择时：板块指数趋势 -> 做多/空仓方向锚。

    工具：60日线 · 均线多头排列(MA5>MA20>MA60) · 价格分位(近1年)。
    只在板块上升趋势/底部启动才做多，否则空仓不做。
    """
    if idx_d is None or len(idx_d) < 70:
        return {"可用": False, "结论": "指数数据不足", "等级": "数据不足", "颜色": "#95a5a6"}
    last = idx_d.iloc[-1]
    close = float(last["close"])
    ma5 = float(last["MA5"]) if last["MA5"] == last["MA5"] else None
    ma20 = float(last["MA20"]) if last["MA20"] == last["MA20"] else None
    ma60 = float(last["MA60"]) if last["MA60"] == last["MA60"] else None
    year_high = float(idx_d["high"].tail(250).max())
    year_low = float(idx_d["low"].tail(250).min())
    pos = (close - year_low) / (year_high - year_low) * 100 if year_high > year_low else 50.0
    ma60_prev = float(idx_d["MA60"].iloc[-6]) if len(idx_d) > 6 and idx_d["MA60"].iloc[-6] == idx_d["MA60"].iloc[-6] else ma60

    above60 = ma60 is not None and close > ma60
    bull = (ma5 is not None and ma20 is not None and ma60 is not None
            and ma5 > ma20 > ma60)
    ma60_up = ma60 is not None and ma60_prev is not None and ma60 > ma60_prev

    if bull and above60:
        level, color = "上升趋势 · 可做多", "#27ae60"
        score, concl = 90, "板块多头排列且站上60日线 → 顺势做多，聚焦主线龙头"
    elif above60 and pos <= 30:
        level, color = "底部启动 · 可做多", "#2ecc71"
        score, concl = 75, "指数自低位企稳站上60日线 → 底部启动，可布局潜龙"
    elif not above60 and ma60_up is False:
        level, color = "下降趋势 · 空仓", "#e74c3c"
        score, concl = 25, "板块跌破60日线且均线向下 → 空仓不做，等企稳"
    elif above60:
        level, color = "震荡 · 谨慎", "#e67e22"
        score, concl = 55, "站上60日线但未多头排列 → 结构性行情，轻仓试错"
    else:
        level, color = "破位 · 空仓", "#e74c3c"
        score, concl = 30, "板块位于60日线下方 → 方向不明，空仓等待"

    return {"可用": True, "等级": level, "颜色": color, "分数": int(score), "结论": concl,
            "pos_year": round(pos, 1), "above60": above60, "bull": bull,
            "ma5": ma5, "ma20": ma20, "ma60": ma60, "name": name,
            "notes": ["%s 现价 %.2f · 近1年分位 %.0f%%" % (name, close, pos),
                      "均线多头(5>20>60)：" + ("✅" if bull else "❌") + " · 站上60日线：" + ("✅" if above60 else "❌"),
                      "60日线方向：" + ("上行" if ma60_up else "下行")]}


# ---------------- Step 2 · 微观选股 ----------------

def composite_score(score5):
    """第二步 · 综合评分矩阵：五维各 20%，满分 100。"""
    dims = ["赛道", "成长", "估值", "风险", "趋势"]
    total = sum(float(score5.get(d, 0)) for d in dims) / 5.0
    total = round(max(0.0, min(100.0, total)), 1)
    if total >= 85:
        grade, color = "S · 超级", "#27ae60"
    elif total >= 75:
        grade, color = "A · 优秀", "#2ecc71"
    elif total >= 65:
        grade, color = "B · 良好", "#e67e22"
    elif total >= 55:
        grade, color = "C · 一般", "#b7950b"
    else:
        grade, color = "D · 回避", "#e74c3c"
    items = [{"维度": d, "得分": round(float(score5.get(d, 0)), 0), "权重": "20%"} for d in dims]
    return {"total": total, "grade": grade, "color": color, "items": items}


def redline_check(d):
    """第二步 · 基本面排雷：红线一票否决 -> 直接回避级（不进入战术执行）。

    美股可落地代理：退市风险(股价) / 深度破位 / 流动性枯竭 / 单日闪崩。
    """
    if d is None or len(d) < 40:
        return {"ok": True, "redlines": [], "verdict": "数据不足，默认放行"}
    last = d.iloc[-1]
    close = float(last["close"])
    reds = []
    if close < 1.0:
        reds.append("股价 < $1 · 退市风险红线")
    if len(d) >= 250:
        year_low = float(d["low"].tail(250).min())
        if close <= year_low * 1.05 and close < float(d["close"].iloc[-40:].mean()) * 0.5:
            reds.append("深度破位 · 逼近年线新低且远离40日均价")
    vol20 = float(d["volume"].tail(20).mean())
    if vol20 < 100000:
        reds.append("流动性枯竭 · 20日均成交 < 10万股")
    ret1 = (float(last["close"]) / float(d.iloc[-2]["close"]) - 1) * 100 if len(d) > 1 else 0
    if ret1 < -25:
        reds.append("单日闪崩 · 跌幅 %.1f%%" % ret1)
    ok = len(reds) == 0
    return {"ok": ok, "redlines": reds,
            "verdict": "✅ 未触红线，可进入六维/战术执行" if ok else "❌ 触红线 → 一票否决，直接回避级"}


def leader_rank(d):
    """第二步 · 龙头/潜龙定位（可算代理）：龙头=强势+资金虹吸；潜龙=低位+安全边际。"""
    if d is None or len(d) < 60:
        return {"kind": "未知", "color": "#95a5a6", "notes": ["数据不足"]}
    last = d.iloc[-1]
    close = float(last["close"])
    high60 = float(d["high"].tail(60).max())
    low60 = float(d["low"].tail(60).min())
    pos60 = (close - low60) / (high60 - low60) * 100 if high60 > low60 else 50
    ret20 = (close / float(d.iloc[-21]["close"]) - 1) * 100 if len(d) > 21 else 0
    vr = float(last["VR7"]) if last["VR7"] == last["VR7"] else 1.0
    if pos60 >= 80 and ret20 > 0 and vr >= 1.1:
        return {"kind": "龙头 · 进攻主升", "color": "#c0392b", "notes": ["60日分位 %.0f%%（高位强势）" % pos60,
                 "近20日 %+.1f%% · 量比 %.2f → 资金虹吸" % (ret20, vr)]}
    if pos60 <= 35 and ret20 < 5:
        return {"kind": "潜龙 · 补涨弹性", "color": "#27ae60", "notes": ["60日分位 %.0f%%（低位）" % pos60,
                 "近20日 %+.1f%% → 有安全边际，等补涨" % ret20]}
    return {"kind": "中位 · 观察", "color": "#e67e22", "notes": ["60日分位 %.0f%% · 近20日 %+.1f%%" % (pos60, ret20)]}


# ---------------- Step 3 · 风险隔离 ----------------

def risk_isolation(d, idx_d, signals):
    """第三步 · 风险隔离：结构性风险评分 + 事件性预警 + 30/20 防火墙。"""
    warnings = []
    if d is None or len(d) < 30:
        return {"score": 50, "level": "数据不足", "color": "#95a5a6", "warnings": [], "firewall": True}
    last = d.iloc[-1]
    close = float(last["close"])
    ma5 = float(last["MA5"]) if last["MA5"] == last["MA5"] else None
    ma20 = float(last["MA20"]) if last["MA20"] == last["MA20"] else None
    # 结构性评分：波动 + 回撤 + 破位
    ret = d["close"].pct_change().iloc[-60:]
    vol = float(ret.std() * np.sqrt(252) * 100) if len(ret) > 20 else 30.0
    high60 = float(d["high"].tail(60).max())
    dd = (high60 - close) / high60 * 100 if high60 > 0 else 0
    score = 100 - vol * 1.2 - max(0, dd - 10) * 1.2
    score = int(max(0, min(100, score)))
    # 事件性预警
    if ma5 is not None and close < ma5:
        warnings.append("🔴 跌破5日线（短线破位）")
    if idx_d is not None and len(idx_d) > 20:
        idm = float(idx_d["MA60"].iloc[-1]) if "MA60" in idx_d.columns and idx_d["MA60"].iloc[-1] == idx_d["MA60"].iloc[-1] else None
        if idm is not None and float(idx_d["close"].iloc[-1]) < idm:
            warnings.append("🟠 大盘跌破60日线（宏观风险）")
    try:
        if signals and signals.get("kdj", {}).get("J值", 0) > 100:
            warnings.append("🟠 KDJ 严重超买（短线过热）")
    except Exception:
        pass
    if dd > 25:
        warnings.append("🟠 距60日高点回撤 %.0f%%（深度回撤）" % dd)
    if not warnings:
        warnings.append("✅ 无事件性预警")
    firewall = "单行业 ≤30% · 单股 ≤20% · 总仓位动态上限"
    if score >= 75:
        level, color = "低风险", "#27ae60"
    elif score >= 55:
        level, color = "中风险", "#e67e22"
    else:
        level, color = "高风险", "#e74c3c"
    return {"score": score, "level": level, "color": color, "warnings": warnings,
            "firewall": firewall, "vol": round(vol, 1), "dd": round(dd, 1)}


# ---------------- Step 4 · 战术执行 ----------------

def three_low_score(d):
    """战法A · 三低买入法：低位 + 地量 + 低关注 + 右侧确认。

    三低管「在哪等」，右侧确认(站上5日线) + 排雷管「何时扣扳机」。
    """
    if d is None or len(d) < 60:
        return {"score": 0, "candidate": False, "trigger": False, "items": [], "结论": "数据不足"}
    last = d.iloc[-1]
    close = float(last["close"])
    year_high = float(d["high"].tail(250).max()) if len(d) >= 60 else float(d["high"].max())
    year_low = float(d["low"].tail(250).min()) if len(d) >= 60 else float(d["low"].min())
    pos_year = (close - year_low) / (year_high - year_low) * 100 if year_high > year_low else 50.0
    dd = (year_high - close) / year_high * 100 if year_high > 0 else 0
    vr5 = float(last["VR3"]) if last["VR3"] == last["VR3"] else 1.0
    vol20 = float(d["volume"].tail(20).mean())
    ma5 = float(last["MA5"]) if last["MA5"] == last["MA5"] else None

    items = [
        ("低位", "近1年分位 %.0f%% · 距高点回撤 %.0f%%" % (pos_year, dd), pos_year <= 30 and dd >= 25),
        ("地量", "3日量比 %.2f（<0.6 为地量）" % vr5, vr5 < 0.6),
        ("低关注", "20日均量 %.0f 万股（冷门/无人问津）" % (vol20 / 10000), vol20 < 5000000),
        ("右侧确认", "收盘站上5日线 %.2f" % (ma5 or 0), ma5 is not None and close > ma5),
    ]
    hits = sum(1 for _, _, ok in items if ok)
    candidate = hits >= 2 and pos_year <= 30 and dd >= 25
    trigger = candidate and (ma5 is not None and close > ma5)
    if trigger:
        concl = "✅ 三低候选 + 右侧确认 → 可试仓（破支撑止损≤5%）"
        color = "#27ae60"
    elif candidate:
        concl = "🟡 三低候选，但右侧未确认 → 在低价区带等站上5日线"
        color = "#e67e22"
    else:
        concl = "⏸ 非三低候选（高位/放量/关注度高）→ 换战法B/战法C"
        color = "#95a5a6"
    return {"score": hits, "candidate": candidate, "trigger": trigger, "items": items,
            "结论": concl, "color": color, "buy_ref": round(float(year_low), 2)}


def five_day_signal(d):
    """战法B · 五日线战法：放量站上5日线 + 3日放量 + 7日1.45倍巨量。"""
    if d is None or len(d) < 30:
        return {"结论": "数据不足", "color": "#95a5a6"}
    last = d.iloc[-1]
    close = float(last["close"])
    ma5 = float(last["MA5"]) if last["MA5"] == last["MA5"] else None
    above5 = ma5 is not None and close > ma5
    vr3 = float(last["VR3"]) if last["VR3"] == last["VR3"] else 1.0
    vr7 = float(last["VR7"]) if last["VR7"] == last["VR7"] else 1.0
    big7 = vr7 >= 1.45
    dev5 = (close / ma5 - 1) * 100 if ma5 else 0
    notes = ["收盘 vs 5日线：%+.2f%%（牛股带≤2.5%% · 纪律线-7.5%%）" % dev5,
             "3日量比 %.2f · 7日量比 %.2f（≥1.45 = 巨量）" % (vr3, vr7)]
    if above5 and big7:
        concl, color = "✅ 放量站上5日线 + 7日巨量 → 进场信号（分歧明显需人工确认）", "#27ae60"
    elif above5 and vr3 >= 1.5:
        concl, color = "🟢 站上5日线 + 3日放量 → 可短线跟进", "#2ecc71"
    elif dev5 < -7.5:
        concl, color = "🔴 跌破5日线7.5% → 减50%（回撤15-20%清仓）", "#e74c3c"
    elif not above5:
        concl, color = "⏸ 未站上5日线 → 等待", "#95a5a6"
    else:
        concl, color = "🟡 站上5日线但量能不足 → 持有观察", "#e67e22"
    return {"结论": concl, "color": color, "notes": notes, "above5": above5}


def weekly_13_week(weekly):
    """战法C · 13周时空战法：洗盘8-13周 · 第13周放量企稳=买点 · 守30周生命线。"""
    if weekly is None or len(weekly) < 16:
        return {"结论": "数据不足（需≥16根周线）", "color": "#95a5a6"}
    w = weekly.copy()
    w = w[~w.index.duplicated(keep="last")].sort_index()
    close = w["close"]
    n = len(w)
    # 洗盘：近13周最高点 vs 之前，回撤幅度
    seg = w.tail(13)
    seg_high = float(seg["high"].max())
    prev_high = float(w["high"].iloc[-14:-1].max()) if n >= 14 else seg_high
    pullback = (prev_high - float(close.iloc[-1])) / prev_high * 100 if prev_high > 0 else 0
    # 第13周放量企稳：最近一周收阳 + 量放大
    if n >= 3:
        last_w = w.iloc[-1]
        prev_w = w.iloc[-2]
        vol_ratio = float(last_w["volume"]) / float(prev_w["volume"]) if prev_w["volume"] > 0 else 1.0
        up = float(last_w["close"]) > float(last_w["open"])
    else:
        vol_ratio, up = 1.0, False
    # 30周生命线
    w["MA30"] = close.rolling(30).mean()
    ma30 = float(w["MA30"].iloc[-1]) if len(w) >= 30 and w["MA30"].iloc[-1] == w["MA30"].iloc[-1] else None
    above30 = ma30 is not None and float(close.iloc[-1]) > ma30

    notes = ["近13周回撤 %.0f%%（洗盘8-13周）" % pullback,
             "本周%s · 量比 %.2f（放量企稳=买点，无量=诱多）" % ("收阳" if up else "收阴", vol_ratio),
             "30周生命线 %.2f：%s" % (ma30 or 0, "守" if above30 else "破")]
    if pullback >= 12 and up and vol_ratio >= 1.2 and above30:
        concl, color = "✅ 洗盘后第13周放量企稳 → 周线中继买点", "#27ae60"
    elif pullback >= 12 and above30:
        concl, color = "🟡 洗盘中（%d周内），等放量企稳" % min(13, n), "#e67e22"
    elif not above30:
        concl, color = "🔴 跌破30周生命线 → 放弃", "#e74c3c"
    else:
        concl, color = "⏸ 未形成洗盘结构 → 等回调", "#95a5a6"
    return {"结论": concl, "color": color, "notes": notes}


def volume_price_confirm(d):
    """量能确认闸：放量/地量/缩量 + 量价口诀（贯穿三战法）。"""
    if d is None or len(d) < 30:
        return {"结论": "数据不足", "color": "#95a5a6"}
    last = d.iloc[-1]
    close = float(last["close"])
    vol = float(last["volume"])
    vol20 = float(d["volume"].tail(20).mean())
    vr = vol / vol20 if vol20 > 0 else 1.0
    ret1 = (close / float(d.iloc[-2]["close"]) - 1) * 100 if len(d) > 1 else 0
    # 5日量均线
    vol5 = float(d["volume"].tail(5).mean())
    vol_keep = vol5 / vol20 if vol20 > 0 else 1.0

    if vr >= 1.3:
        q = "放量"
        if ret1 < 0.5:
            concl, color = "🔴 放量不涨 = 出货（危险）", "#e74c3c"
        else:
            concl, color = "🟢 放量上涨 = 资金进场", "#27ae60"
    elif vr < 0.6:
        q = "地量"
        if ret1 > -0.5:
            concl, color = "🟢 缩量不跌 = 机会（地量见地价）", "#2ecc71"
        else:
            concl, color = "🟡 地量阴跌 = 无人接盘，观察", "#e67e22"
    else:
        q = "常态"
        concl, color = "⏸ 量能常态（量比 %.2f）" % vr, "#95a5a6"

    keep_ok = 0.55 <= vol_keep <= 0.70
    return {"结论": concl, "color": color, "量比": round(vr, 2), "5日量维持": round(vol_keep, 2),
            "量能持续合格": keep_ok, "q": q,
            "notes": ["当日量比 %.2f（≥1.3放量 · <0.6地量）" % vr,
                      "5日量能维持 %.0f%%（加仓需维持55-70%%）" % (vol_keep * 100),
                      "量价口诀：放量不涨=出货（危险）· 缩量不跌=机会"]}


# ---------------- Step 5 · 终局思维 ----------------

def endgame(d, idx_d, weekly):
    """第五步 · 终局思维：板块清仓 -> 个股周线止损 -> 止盈/移动止盈。"""
    out = {}
    # ① 板块顶信号：跌破60日线连3日收不回 + 均线空头 -> 无条件清仓
    sector_top = False
    if idx_d is not None and len(idx_d) > 70:
        idc = idx_d["close"]
        ma60 = idx_d["MA60"] if "MA60" in idx_d.columns else idc.rolling(60).mean()
        below = (idc < ma60).tail(3)
        ma5 = idx_d["MA5"].iloc[-1] if "MA5" in idx_d.columns else np.nan
        ma20 = idx_d["MA20"].iloc[-1] if "MA20" in idx_d.columns else np.nan
        ma60v = ma60.iloc[-1]
        bear = ma5 < ma20 < ma60v
        sector_top = bool(below.sum() >= 3 and bear)
    out["板块顶"] = ("🔴 板块跌破60日线连3日+空头 → 无条件清仓" if sector_top
                    else "🟢 板块未破位（可继续持有）")

    # ② 个股周线：跌破27周止损 / 守30周生命线 / 站上47周转强
    wstat = "数据不足"
    if weekly is not None and len(weekly) >= 28:
        wc = weekly["close"]
        ma27 = wc.rolling(27).mean().iloc[-1]
        ma30 = wc.rolling(30).mean().iloc[-1]
        ma47 = wc.rolling(47).mean().iloc[-1]
        c = float(wc.iloc[-1])
        if c < ma27:
            wstat = "🔴 跌破27周 → 止损"
        elif c < ma30:
            wstat = "🟠 破30周生命线 → 警惕/减仓"
        elif c > ma47:
            wstat = "🟢 站上47周 → 趋势转强"
        else:
            wstat = "🟡 30周上方 · 47周下方 → 中性持有"
    out["周线"] = wstat

    # ③ 动态移动止盈规则（盈≥10%保本，每涨5%抬3%）——规则说明由 UI 展示
    out["移动止盈"] = "底仓盈 ≥10% → 止盈位设成本上方5%（保本）；之后每涨5%抬高3%；跌破即离场锁利"
    return out


# ---------------- 仓位管理 ----------------

def position_plan_cedar(temp_score, capital=100000, ability="普通投资者"):
    """仓位管理：温度定上限 + 个人能力 + 30/20 + 现金。
    temp_score: 市场温度 0-100（来自 scoring.market_temperature）。
    """
    if not capital or capital <= 0:
        return None
    # A. 温度定上限：三档（低温6-7成 · 中温5-6成 · 高温≤3成）
    if temp_score >= 80:
        temp_cap, temp_label, temp_color = 0.30, "高温 ≤3成（怕）", "#e74c3c"
    elif temp_score >= 65:
        temp_cap, temp_label, temp_color = 0.55, "中温 5-6成（滑）", "#e67e22"
    elif temp_score >= 40:
        temp_cap, temp_label, temp_color = 0.65, "低温 6-7成（贪）", "#27ae60"
    else:
        temp_cap, temp_label, temp_color = 0.30, "冰点观察（<4成）", "#95a5a6"
    # B. 个人能力
    ability_map = {"普通投资者": (0.25, 0.35), "高手": (0.40, 0.50), "顶尖高手": (0.50, 0.55)}
    ab_lo, ab_hi = ability_map.get(ability, (0.25, 0.35))
    cap = min(temp_cap, ab_hi)
    # C. 30/20
    single_stock = capital * 0.20
    single_sector = capital * 0.30
    cash = capital * 0.10
    return {"temp_cap": temp_cap, "temp_label": temp_label, "temp_color": temp_color,
            "ability": ability, "ab_range": "%d%%-%d%%" % (int(ab_lo * 100), int(ab_hi * 100)),
            "total_cap": cap, "total_amount": capital * cap,
            "single_stock": single_stock, "single_sector": single_sector, "cash": cash,
            "rule": "单行业≤30% · 单股≤20%（龙头≤25%） · 现金≥10% · 多赛道合计≤90% · 三不原则：不满仓/不加杠杆/不单挑一只票"}


# ---------------- 综合漏斗结论 ----------------

def funnel_conclusion(steps):
    """五步漏斗汇总：任一硬性否决（排雷/破位）优先，其次看各步得分。"""
    if not steps.get("step1") or not steps["step1"].get("可用"):
        return "⚠ 数据不足，无法执行五步漏斗"
    s1 = steps["step1"]
    if s1["等级"].startswith("下降") or s1["等级"].startswith("破位"):
        return "❌ Step1 宏观否决：板块下降趋势 → 空仓不做（方向锚优先）"
    if steps["step2_red"] is not None and not steps["step2_red"]["ok"]:
        return "❌ Step2 排雷否决：触红线一票否决 → 回避级"
    if steps["step3"]["score"] < 55:
        return "⚠ Step3 风险过高 → 仅轻仓或等待风险释放"
    t4 = steps["step4"]
    if t4["触发"]:
        return "✅ 五步通过：" + t4["结论"]
    return "🟡 漏斗未全绿：" + t4["结论"]