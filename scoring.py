# -*- coding: utf-8 -*-
"""评分层：市场温度 / 五维评分 / 质量×时机矩阵。

思路（简化可解释版）：
- 市场温度：由指数 RSI、价格相对 MA20 位置、60 日区间位置加权得到 0-100°C。
- 五维评分：赛道(板块溢价) / 成长(动量+量能) / 估值(回调深度代理) / 风险(回撤+波动) / 趋势(均线排列)。
"""
import numpy as np
import pandas as pd

from indicators import add_indicators

# 主线赛道溢价（来自战法赛道框架）
SECTOR_PREMIUM = {
    "半导体芯片": 95, "存储芯片": 95, "AI算力": 92, "AGI太空": 88,
    "AI电力": 85, "核电": 85, "稀缺资源": 80, "机器人": 75,
    "AI软件": 82, "半导体代工": 88, "军工": 70, "金融科技": 65,
}


def _clip(x, lo=0, hi=100):
    return float(max(lo, min(hi, x)))


def market_temperature(index_df, window=90):
    """返回 dict: temp(0-100), label, color, rsi, pos60。"""
    df = index_df.tail(window + 60)
    close = df["close"]
    last = close.iloc[-1]
    r = df["RSI"].iloc[-1] if "RSI" in df.columns else None
    ma20 = df["MA20"].iloc[-1] if "MA20" in df.columns else close.rolling(20).mean().iloc[-1]
    low60 = df["low"].iloc[-60:].min()
    high60 = df["high"].iloc[-60:].max()
    pos60 = (last - low60) / (high60 - low60) * 100 if high60 > low60 else 50
    rsi_c = r if r is not None else 50

    # 温度合成：RSI 权重 0.5，MA20 位置 0.3，60日区间位置 0.2
    ma_score = 50 + (last / ma20 - 1) * 2000
    temp = 0.5 * rsi_c + 0.3 * _clip(ma_score) + 0.2 * pos60
    temp = _clip(temp)

    if temp >= 80:
        label, color = "过热", "crimson"
    elif temp >= 65:
        label, color = "中性偏热", "orange"
    elif temp >= 40:
        label, color = "中性", "gold"
    elif temp >= 25:
        label, color = "中性偏冷", "cornflowerblue"
    else:
        label, color = "冰冷/破位区", "slateblue"

    return {"temp": round(temp, 1), "label": label, "color": color,
            "rsi": round(float(rsi_c), 1), "pos60": round(float(pos60), 1),
            "last": float(last)}


def temperature_history(index_df, window=90):
    """近 N 日温度序列（同一公式逐日计算）。"""
    df = index_df.tail(window + 60).copy()
    out = []
    close = df["close"]
    ma20 = df["MA20"]
    for i in range(60, len(df)):
        seg = df.iloc[i - 59:i + 1]
        low60 = seg["low"].min()
        high60 = seg["high"].max()
        c = close.iloc[i]
        pos60 = (c - low60) / (high60 - low60) * 100 if high60 > low60 else 50
        rsi_c = df["RSI"].iloc[i]
        ma_score = 50 + (c / ma20.iloc[i] - 1) * 2000
        t = 0.5 * rsi_c + 0.3 * _clip(ma_score) + 0.2 * pos60
        out.append((df.index[i], _clip(t)))
    return pd.Series(dict(out), name="temperature")


def five_dim_score(df, sector_key=""):
    """返回 dict：赛道/成长/估值/风险/趋势 各 0-100 + 质量档。"""
    last = df.iloc[-1]
    n = len(df)
    close = df["close"]

    # 赛道：SECTOR_PREMIUM 命中，否则按 60 基线
    sector_score = 60
    for key, val in SECTOR_PREMIUM.items():
        if key in sector_key:
            sector_score = max(sector_score, val)
            break

    # 成长：动量(60日收益 50%) + RSI(25%) + 量能(25%)
    mom60 = (last["close"] / close.iloc[-61] - 1) * 100 if n > 61 else 0
    rsi_c = last["RSI"] if not np.isnan(last["RSI"]) else 50
    vr = last["VR7"] if not np.isnan(last["VR7"]) else 1
    growth = _clip(50 + mom60 * 1.2 + (rsi_c - 50) * 0.6 + (vr - 1) * 40)

    # 估值：以 60 日回撤与低点接近度为代理（真估值需 PE/PS，接入数据后可替换）
    low60 = df["low"].iloc[-60:].min() if n >= 60 else df["low"].min()
    high60 = df["high"].iloc[-60:].max() if n >= 60 else df["high"].max()
    dd = (high60 - last["close"]) / high60 * 100
    value_score = _clip(30 + dd * 2.5 + (1 - (last["close"] - low60) / (high60 - low60)) * 30)

    # 风险：波动率与回撤越大分越低
    ret = close.pct_change().iloc[-60:]
    vol = ret.std() * np.sqrt(252) * 100 if len(ret) >= 20 else 30
    risk_score = _clip(100 - vol * 1.2 - max(0, dd - 10) * 1.5)

    # 趋势：均线多头 60 + 站上60日线 20 + MA20 斜率 20
    ma5, ma20 = last["MA5"], last["MA20"]
    ma60 = last["MA60"] if not np.isnan(last["MA60"]) else ma20
    trend = 0
    trend += 60 if ma5 > ma20 > ma60 else (35 if ma5 > ma20 else 15)
    trend += 20 if last["close"] > ma60 else 5
    slope = (ma20 / df["MA20"].iloc[-6] - 1) * 100 if len(df) > 6 and not np.isnan(df["MA20"].iloc[-6]) else 0
    trend += _clip(20 + slope * 40, 0, 20)
    trend = _clip(trend)

    total = 0.25 * sector_score + 0.25 * growth + 0.15 * value_score + 0.15 * risk_score + 0.2 * trend
    if total >= 85:
        grade = "S · 超级牛股"
    elif total >= 75:
        grade = "A · 优质公司"
    elif total >= 60:
        grade = "B · 一般"
    else:
        grade = "C · 回避"

    return {
        "赛道": round(sector_score), "成长": round(growth), "估值": round(value_score),
        "风险": round(risk_score), "趋势": round(trend),
        "综合": round(total, 1), "质量档": grade,
    }


def quality_x_timing(score5, signals, temp):
    """质量×时机矩阵定位。返回 dict(质量, 时机, 结论, 颜色)。"""
    grade = score5["质量档"]
    if grade.startswith("S"):
        quality = "S/A"
    elif grade.startswith("A"):
        quality = "S/A"
    elif grade.startswith("B"):
        quality = "B"
    else:
        quality = "C"

    j = signals["kdj"]["J值"]
    if j < 0 and temp["temp"] < 40:
        timing = "好时机"
    elif j > 80 or temp["temp"] >= 75:
        timing = "时机差"
    else:
        timing = "中性"

    matrix = {
        ("S/A", "好时机"): ("重点·分批建仓", "green"),
        ("S/A", "中性"): ("关注·小仓试", "limegreen"),
        ("S/A", "时机差"): ("观察·等回调", "orange"),
        ("B", "好时机"): ("波段·轻仓", "teal"),
        ("B", "中性"): ("观察", "dodgerblue"),
        ("B", "时机差"): ("回避", "gray"),
        ("C", "好时机"): ("仅交易·严止损", "peru"),
        ("C", "中性"): ("回避", "gray"),
        ("C", "时机差"): ("回避", "darkgray"),
    }
    conclusion, color = matrix.get((quality, timing), ("观察·等回调", "orange"))
    return {"质量": quality, "时机": timing, "结论": conclusion, "颜色": color}