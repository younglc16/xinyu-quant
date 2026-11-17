# -*- coding: utf-8 -*-
"""技术指标与战法信号（对应「美股波段战法系统」skill）。

- KDJ(9,3,3) / RSI(14) / MA5/10/20/60 / 量比
- 战法一：KDJ 超卖(买)/超买(卖)
- 主信号：MACD + KDJ 双指标共振（金叉共振做多 / 死叉共振做空，单指标不算强信号）
- 战法四：五日线纪律（2.5% 牛股带 / 7.5% 止损线 / 3日-7日放量 / 13-27日分歧期）
"""
import numpy as np
import pandas as pd

from formation_rules import RULE_VERSION, rulebook


# ---------------- 基础指标 ----------------

def kdj(df, n=9, m1=3, m2=3):
    low_n = df["low"].rolling(n, min_periods=1).min()
    high_n = df["high"].rolling(n, min_periods=1).max()
    rsv = (df["close"] - low_n) / (high_n - low_n) * 100
    k = rsv.ewm(alpha=1 / m1, adjust=False).mean()
    d = k.ewm(alpha=1 / m2, adjust=False).mean()
    return k, d, 3 * k - 2 * d


def rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = -delta.clip(upper=0).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss
    return 100 - 100 / (1 + rs)




def macd(close, fast=12, slow=26, signal=9):
    """MACD 指标：返回 DIF(快线) / DEA(慢线) / MACD柱(hist)。"""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = (dif - dea) * 2
    return dif, dea, hist

def add_indicators(df):
    """给日线 DataFrame 增加全部指标列，返回新 DataFrame。"""
    out = df.copy()
    out["MA5"] = out["close"].rolling(5).mean()
    out["MA10"] = out["close"].rolling(10).mean()
    out["MA20"] = out["close"].rolling(20).mean()
    out["MA60"] = out["close"].rolling(60).mean()
    k, d, j = kdj(out)
    out["K"] = k
    out["D"] = d
    out["J"] = j
    out["RSI"] = rsi(out["close"])
    dif, dea, hist = macd(out["close"])
    out["DIF"] = dif
    out["DEA"] = dea
    out["MACD"] = hist
    out["Dev5"] = (out["close"] / out["MA5"] - 1) * 100
    vol20 = out["volume"].rolling(20).mean()
    out["VR3"] = out["volume"].rolling(3).mean() / vol20
    out["VR7"] = out["volume"].rolling(7).mean() / vol20
    return out


# ---------------- 战法信号 ----------------

def signal_checks(df):
    """按「美股波段战法系统」输出信号字典。df 需先 add_indicators。"""
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    n = len(df)
    checks = {}

    # 1) KDJ 战法
    j_now, j_prev = last["J"], prev["J"]
    checks["kdj"] = {
        "J值": round(float(j_now), 1),
        "前日J值": round(float(j_prev), 1),
        "状态": "超卖(买点区)" if j_now < 0 else ("超买(卖点区)" if j_now > 100 else ("偏超买" if j_now > 80 else "中性")),
        "信号": ("J<-0 超卖 → 战法一买点区" if j_now < 0
                 else ("J>100 超买 → 战法一卖点区" if j_now > 100
                       else ("J>80 偏超买 → 减仓观察" if j_now > 80 else "J 中性，等待极端值"))),
    }


    # 1.5) MACD + KDJ 双指标共振（做多/做空最新状态）
    #     单独的 KDJ 金叉/死叉不足以构成强买卖点，必须与 MACD 共振确认。
    try:
        _res = find_macd_kdj_resonance(df)
        _longs = [x for x in _res if x[1] == "long"]
        _shorts = [x for x in _res if x[1] == "short"]
        _lg = _longs[-1] if _longs else None
        _ld = _shorts[-1] if _shorts else None
        if _lg and (not _ld or _lg[0] > _ld[0]):
            _cur = "做多共振 · %s（%s）" % (_lg[4], _lg[5])
        elif _ld:
            _cur = "做空共振 · %s（%s）" % (_ld[4], _ld[5])
        else:
            _cur = "无共振信号 · 观望"
        checks["resonance"] = {
            "最近做多共振": ("%s · %s" % (_lg[0].strftime("%Y-%m-%d"), _lg[4])) if _lg else "无",
            "最近做空共振": ("%s · %s" % (_ld[0].strftime("%Y-%m-%d"), _ld[4])) if _ld else "无",
            "当前状态": _cur,
        }
    except Exception:
        checks["resonance"] = {"当前状态": "数据不足"}

    # 2) 五日线纪律
    dev5 = float(last["Dev5"])
    ma5 = float(last["MA5"])
    above_ma5 = bool(last["close"] > ma5)
    checks["ma5"] = {
        "收盘价": round(float(last["close"]), 2),
        "MA5": round(ma5, 2),
        "偏离MA5": f"{dev5:+.2f}%",
        "站上5日线": "是" if above_ma5 else "否",
        "信号": ("站上5日线，偏离 %.2f%%（牛股带≤2.5%% | 纪律线7.5%%）" % dev5 if above_ma5
                 else "跌破5日线，短线走弱"),
    }

    # 3) 放量要求（战法：3日内 / 7日内放巨量）
    vr3 = float(last["VR3"]) if not np.isnan(last["VR3"]) else 1.0
    vr7 = float(last["VR7"]) if not np.isnan(last["VR7"]) else 1.0
    big3 = vr3 >= 1.5
    big7 = vr7 >= 1.3
    checks["volume"] = {
        "3日量比(20日均)": round(vr3, 2),
        "7日量比(20日均)": round(vr7, 2),
        "3日内放巨量": "是" if big3 else "否",
        "7日内放巨量": "是" if big7 else "否",
        "信号": "量能确认" if (big3 and big7) else ("量能部分确认" if (big3 or big7) else "量能未确认(反弹需谨慎)"),
    }

    # 4) 均线状态
    ma5v, ma10v, ma20v = float(last["MA5"]), float(last["MA10"]), float(last["MA20"])
    ma60v = float(last["MA60"]) if not np.isnan(last["MA60"]) else float("nan")
    bull = ma5v > ma20v > ma60v if not np.isnan(ma60v) else ma5v > ma20v
    checks["ma"] = {
        "MA5/10/20/60": f"{ma5v:.2f} / {ma10v:.2f} / {ma20v:.2f} / {ma60v:.2f}" if not np.isnan(ma60v) else f"{ma5v:.2f} / {ma10v:.2f} / {ma20v:.2f} / -",
        "多头排列": "是" if bull else "否",
        "信号": "均线多头排列(MA5>MA20>MA60)" if bull else "未形成多头排列",
    }

    # 5) 分歧周期（13-27 日）与近期极值
    seg = df.iloc[-27:]
    low27, high27 = float(seg["low"].min()), float(seg["high"].max())
    low_idx = seg["low"].idxmin()
    days_since_low = len(df.loc[low_idx:])
    checks["cycle"] = {
        "近27日低点": round(low27, 2),
        "近27日高点": round(high27, 2),
        "分歧期位置": f"自低点 {low_idx:%m-%d} 以来第 {days_since_low} 个交易日" + ("（13-27日分歧期参考）" if days_since_low <= 27 else "（已过27日分歧期）"),
        "信号": f"近27日区间 {low27:.2f}~{high27:.2f}，低点 {low_idx:%m-%d}",
    }

    # 6) 60日新高/新低
    low60 = float(df["low"].iloc[-60:].min()) if n >= 60 else float(df["low"].min())
    high60 = float(df["high"].iloc[-60:].max()) if n >= 60 else float(df["high"].max())
    checks["range60"] = {
        "60日低/高": f"{low60:.2f} / {high60:.2f}",
        "创新低": "是" if last["low"] <= low60 else "否",
        "创新高": "是" if last["high"] >= high60 else "否",
    }


    # 7) MACD + KDJ 双指标共振战法（金叉/死叉/零轴/减速/拐头）
    #    分工：MACD 看趋势——下跌减速（绿柱缩短）买、上涨减速（红柱缩短）卖；
    #          KDJ 看转折——超买(J>80)拐头卖、超卖(J<20)拐头买。
    #    只有两指标共振的点位才算强买卖点，用来过滤假突破/假反弹。
    try:
        dif0, dea0 = float(last["DIF"]), float(last["DEA"])
        dif1, dea1 = float(prev["DIF"]), float(prev["DEA"])
        h0, h1 = float(last["MACD"]), float(prev["MACD"])
        macd_cross_up = (dif1 <= dea1) and (dif0 > dea0)      # DIF 上穿 DEA -> 金叉
        macd_cross_dn = (dif1 >= dea1) and (dif0 < dea0)      # DIF 下穿 DEA -> 死叉
        macd_decel_up = (h0 < 0) and (h0 > h1)                # 绿柱缩短：下跌减速，接近金叉
        macd_decel_dn = (h0 > 0) and (h0 < h1)                # 红柱缩短：上涨减速，接近死叉
        k0, d0, j0 = float(last["K"]), float(last["D"]), float(last["J"])
        k1, d1, j1 = float(prev["K"]), float(prev["D"]), float(prev["J"])
        kdj_cross_up = (k1 <= d1) and (k0 > d0)
        kdj_cross_dn = (k1 >= d1) and (k0 < d0)
        kdj_turn_up = (j1 <= 20) and (j0 > j1)                # J 自超卖区拐头向上
        kdj_turn_dn = (j1 >= 80) and (j0 < j1)                # J 自超买区拐头向下
        above_zero = dif0 > 0
        below_zero = dif0 < 0

        strong_long = kdj_cross_up and macd_cross_up           # 双金叉同日：强做多
        strong_short = kdj_cross_dn and macd_cross_dn          # 双死叉同日：强做空
        long_reso = strong_long or (kdj_cross_up and macd_decel_up) or (kdj_turn_up and (macd_decel_up or macd_cross_up))
        short_reso = strong_short or (kdj_cross_dn and macd_decel_dn) or (kdj_turn_dn and (macd_decel_dn or macd_cross_dn))

        if strong_long:
            action = "共振金叉（KDJ+MACD 双金叉）→ 强做多买点"
        elif long_reso:
            action = "共振偏多（KDJ 金叉/超卖拐头 + MACD 下跌减速）→ 做多买点"
        elif strong_short:
            action = "共振死叉（KDJ+MACD 双死叉）→ 强做空卖点"
        elif short_reso:
            action = "共振偏空（KDJ 死叉/超买拐头 + MACD 上涨减速）→ 做空卖点"
        elif macd_cross_dn:
            action = "仅 MACD 死叉，KDJ 未共振 → 减仓观察，勿单独做空"
        elif macd_cross_up:
            action = "仅 MACD 金叉，KDJ 未共振 → 观察，等共振确认"
        else:
            action = "无共振信号，等待 KDJ 与 MACD 同步"
        checks["macd_kdj"] = {
            "DIF": round(dif0, 3),
            "DEA": round(dea0, 3),
            "MACD柱": round(h0, 3),
            "MACD位置": "零轴上方" if above_zero else ("零轴下方" if below_zero else "零轴附近"),
            "MACD动能": "下跌减速(绿柱缩短)" if macd_decel_up else ("上涨减速(红柱缩短)" if macd_decel_dn else "动能延续"),
            "MACD金叉": "是" if macd_cross_up else "否",
            "MACD死叉": "是" if macd_cross_dn else "否",
            "KDJ金叉": "是" if kdj_cross_up else "否",
            "KDJ死叉": "是" if kdj_cross_dn else "否",
            "KDJ拐头": "超卖区拐头向上" if kdj_turn_up else ("超买区拐头向下" if kdj_turn_dn else "无"),
            "双指标共振": ("做多共振(强)" if strong_long else
                       ("做空共振(强)" if strong_short else
                        ("偏多共振" if long_reso else ("偏空共振" if short_reso else "无")))),
            "信号": action,
        }
    except Exception:
        checks["macd_kdj"] = {"信号": "MACD 数据不足"}

    return checks


def find_macd_kdj_resonance(df):
    """返回 MACD + KDJ 双指标共振买卖点（强信号）。

    设计逻辑：MACD 看价格趋势（下跌减速买、上涨减速卖），KDJ 看价格转折
    （超买拐头卖、超卖拐头买）。只有两指标共振，才视为强做多/做空点，
    以此过滤单指标产生的假突破与假反弹。

    做多共振（long）：
      - 强：KDJ 金叉 + MACD 金叉（同日双金叉）
      - 中：KDJ 金叉 + MACD 下跌减速（绿柱缩短，接近金叉）
      - 中：J 自超卖区(<20)拐头 + MACD 下跌减速/金叉
    做空共振（short）：
      - 强：KDJ 死叉 + MACD 死叉（同日双死叉）
      - 中：KDJ 死叉 + MACD 上涨减速（红柱缩短，接近死叉）
      - 中：J 自超买区(>80)拐头 + MACD 上涨减速/死叉

    同方向 3 个交易日内重复共振只保留第一次，减少震荡噪音。
    返回 [(date, kind, zone, strength, label, detail), ...]，
    kind∈{long, short}，zone∈{low, mid, high}，strength∈{强, 中}。
    """
    pts = []
    if len(df) < 2:
        return pts
    k, d, j = df["K"], df["D"], df["J"]
    dif, dea, hist = df["DIF"], df["DEA"], df["MACD"]
    last_idx = {"long": -99, "short": -99}
    for i in range(1, len(df)):
        k0, d0, j0 = float(k.iloc[i]), float(d.iloc[i]), float(j.iloc[i])
        k1, d1, j1 = float(k.iloc[i - 1]), float(d.iloc[i - 1]), float(j.iloc[i - 1])
        dif0, dea0, h0 = float(dif.iloc[i]), float(dea.iloc[i]), float(hist.iloc[i])
        dif1, dea1, h1 = float(dif.iloc[i - 1]), float(dea.iloc[i - 1]), float(hist.iloc[i - 1])

        kdj_gold = (k1 <= d1) and (k0 > d0)
        kdj_dead = (k1 >= d1) and (k0 < d0)
        macd_gold = (dif1 <= dea1) and (dif0 > dea0)
        macd_dead = (dif1 >= dea1) and (dif0 < dea0)
        macd_decel_up = (h0 < 0) and (h0 > h1)      # 绿柱缩短：下跌减速
        macd_decel_dn = (h0 > 0) and (h0 < h1)      # 红柱缩短：上涨减速
        kdj_turn_up = (j1 <= 20) and (j0 > j1)      # 超卖区拐头向上
        kdj_turn_dn = (j1 >= 80) and (j0 < j1)      # 超买区拐头向下

        long_sig = None
        if kdj_gold and macd_gold:
            long_sig = ("强", "共振金叉 · 强做多", "KDJ金叉 + MACD金叉（双金叉同日）")
        elif kdj_gold and macd_decel_up:
            long_sig = ("中", "KDJ金叉 + MACD下跌减速 · 做多", "KDJ金叉，MACD绿柱缩短（接近金叉）")
        elif kdj_turn_up and (macd_decel_up or macd_gold):
            long_sig = ("中", "KDJ超卖拐头 + MACD减速 · 做多", "J自<20拐头 + MACD下跌减速")

        short_sig = None
        if kdj_dead and macd_dead:
            short_sig = ("强", "共振死叉 · 强做空", "KDJ死叉 + MACD死叉（双死叉同日）")
        elif kdj_dead and macd_decel_dn:
            short_sig = ("中", "KDJ死叉 + MACD上涨减速 · 做空", "KDJ死叉，MACD红柱缩短（接近死叉）")
        elif kdj_turn_dn and (macd_decel_dn or macd_dead):
            short_sig = ("中", "KDJ超买拐头 + MACD减速 · 做空", "J自>80拐头 + MACD上涨减速")

        if long_sig and i - last_idx["long"] >= 3:
            last_idx["long"] = i
            zone = "low" if d0 <= 20 else ("mid" if d0 <= 50 else "high")
            pts.append((df.index[i], "long", zone, long_sig[0], long_sig[1], long_sig[2]))
        elif long_sig:
            last_idx["long"] = i

        if short_sig and i - last_idx["short"] >= 3:
            last_idx["short"] = i
            zone = "high" if d0 >= 80 else ("mid" if d0 >= 50 else "low")
            pts.append((df.index[i], "short", zone, short_sig[0], short_sig[1], short_sig[2]))
        elif short_sig:
            last_idx["short"] = i
    return pts

def sell_plan_3221(cost, price):
    """Compatibility adapter for price-only callers; do not mark fills as done."""
    if not cost or cost <= 0:
        return None
    exit_rules = rulebook()["exit"]
    return {
        "gain_pct": round((price / cost - 1) * 100, 2),
        "done": [],
        "pending": list(zip((10, 15, 30, 50), (30, 20, None, None), exit_rules["standard"])),
        "keep": "底仓按持有周期与计划选择，详见3221。",
        "rule": "仅有成本和价格时，阶段与减仓数量待确认。",
        "rule_version": RULE_VERSION,
    }
