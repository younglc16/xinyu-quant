# -*- coding: utf-8 -*-
"""超短线战法（Ultra-Short-Term Strategy）——看大盘做超短，只做最强票。

流程：大盘分析 -> 确定形态(V/W/M) -> 选品种 -> 定仓位 -> 执行 -> 止盈/止损
来源：用户提供的《超短线战法核心逻辑分析》报告（直播语音转写整理）。
"""
import datetime as dt

import pandas as pd


# ---------------- 形态参考表 / 周期 / 环境 / 金句 ----------------

PATTERN_REF = [
    {"形态": "V型反转", "星级": "★★★★★", "胜率": "85%+", "操作": "首选·最高赔率", "判断": "开盘后快速下探+拐头，形成V字"},
    {"形态": "W型双底", "星级": "★★★★", "胜率": "较高", "操作": "第二选择", "判断": "出现两个低点形成W底"},
    {"形态": "M型/单边下跌", "星级": "★", "胜率": "低", "操作": "当天放弃", "判断": "前半小时形成M头或持续创新低"},
]

EXIT_CYCLE = [
    {"周期": "T+0", "定义": "当日超短", "规则": "当天买当天卖，3%-10% 止盈"},
    {"周期": "T+1", "定义": "隔日", "规则": "次日平开/低开走强则持有，需收盘 > 买入价 2% 以上"},
    {"周期": "T+3", "定义": "时间节点", "规则": "必须看到利润兑现"},
    {"周期": "T+5", "定义": "最终期限", "规则": "强制卖出"},
]

BEST_ENV = [
    "指数连续下跌后出现暴跌 → 最佳超短机会",
    "标的需要：抗跌 + 重要均线支撑 + 强于大盘",
    "星期一是最好的狙击时机",
    "A股主板胜率赔率最高（美股对应：纳斯达克科技龙头最强票）",
]

PHILOSOPHY = [
    "不经历三次大熊大牛，不可能悟道",
    "看大事、赚大钱",
    "任何超短都不能变成长期套牢",
    "超短不是赌博，看大盘决定胜率赔率",
    "把学会的转十倍回去",
]

FIVE_MOST = [
    ("最强行业赛道", "只选最热行业：半导体/存储/AI算力/AGI太空/核电/机器人（AI 时代大事主线）"),
    ("最热门题材", "当前时代大事：AI 人工智能 / AIGC 产业链"),
    ("最强主力资金介入", "热门股（MU、LUNR、NVDA 等），量比放大 = 资金介入"),
    ("市场最牛龙头股", "行业第一名、第二名、第三名（龙头赛道里的龙头股）"),
    ("前一天明显放量", "前一日显著放量（量比/成交额放大）"),
]


# ---------------- 第一步：大盘分析（核心中的核心） ----------------

def index_environment(idx_df):
    """超短线第一步：大盘环境评估。

    超短线只看大盘：做哪个市场就看哪个指数（美股看纳斯达克）。
    最佳环境 = 连续下跌后暴跌企稳 + 周一 + 站上重要均线。
    idx_df 需先 add_indicators。
    """
    if idx_df is None or len(idx_df) < 8:
        return {"可用": False, "分数": 0, "等级": "数据不足", "颜色": "#95a5a6",
                "结论": "指数数据不足，无法判断大盘环境", "notes": [],
                "ret_1d": 0.0, "ret_5d": 0.0, "ret_10d": 0.0, "streak_down": 0,
                "max_dd": 0.0, "is_monday": False}
    closes = idx_df["close"]
    n = len(closes)
    last = idx_df.iloc[-1]
    ret_1d = float((closes.iloc[-1] / closes.iloc[-2] - 1) * 100) if n >= 2 else 0.0
    ret_5d = float((closes.iloc[-1] / closes.iloc[-6] - 1) * 100) if n >= 6 else 0.0
    ret_10d = float((closes.iloc[-1] / closes.iloc[-11] - 1) * 100) if n >= 11 else 0.0

    streak_down = 0
    for i in range(n - 1, 0, -1):
        if closes.iloc[i] < closes.iloc[i - 1]:
            streak_down += 1
        else:
            break

    win = closes.iloc[-20:]
    peak = win.cummax()
    max_dd = float((win / peak - 1).min() * 100)

    ma5v = float(last["MA5"]) if "MA5" in idx_df.columns and last["MA5"] == last["MA5"] else None
    ma20v = float(last["MA20"]) if "MA20" in idx_df.columns and last["MA20"] == last["MA20"] else None
    above_ma5 = (float(last["close"]) > ma5v) if ma5v is not None else None
    above_ma20 = (float(last["close"]) > ma20v) if ma20v is not None else None
    is_monday = idx_df.index[-1].weekday() == 0

    score = 50
    notes = []
    if streak_down >= 3:
        score += 20
        notes.append("指数已连续下跌 %d 天（暴跌后企稳 = 最佳超短机会）" % streak_down)
    if max_dd <= -8:
        score += 15
        notes.append("近20日最大回撤 %.1f%%（超跌区）" % max_dd)
    if ret_1d > 0:
        score += 10
        notes.append("今日收阳 %+.2f%%（企稳信号）" % ret_1d)
    elif ret_1d > -0.5:
        score += 5
        notes.append("今日跌幅收窄 %+.2f%%" % ret_1d)
    if above_ma20 is True:
        score += 10
        notes.append("站上20日线（趋势偏强）")
    if is_monday:
        score += 5
        notes.append("今天是周一（最佳狙击时机）")
    if ret_5d > 8:
        score -= 15
        notes.append("近5日已涨 %+.1f%%（高位追涨风险，回避）" % ret_5d)
    if above_ma5 is False and ret_1d < -1:
        score -= 10
        notes.append("跌破5日线且走弱")

    score = int(max(0, min(100, score)))
    if score >= 75:
        level, color, concl = "极佳", "#27ae60", "大盘切准→个股必跟，可执行超短"
    elif score >= 60:
        level, color, concl = "良好", "#2ecc71", "可小仓试，严选 V/W 强形态"
    elif score >= 45:
        level, color, concl = "一般", "#e67e22", "观望为主，只做最强 V 型"
    else:
        level, color, concl = "回避", "#e74c3c", "大盘切不准 = 盲人摸象，当天放弃操作"

    return {"可用": True, "分数": score, "等级": level, "颜色": color, "结论": concl,
            "notes": notes, "ret_1d": ret_1d, "ret_5d": ret_5d, "ret_10d": ret_10d,
            "streak_down": streak_down, "max_dd": max_dd,
            "above_ma5": above_ma5, "above_ma20": above_ma20, "is_monday": is_monday}


# ---------------- 第二步：分时形态（V / W / M） ----------------

def _early_window(df, max_bars=20, max_minutes=60):
    """取开盘后前 max_bars 根（且不超过 max_minutes）作为形态判断窗口。"""
    d = df.iloc[:max_bars]
    if isinstance(d.index, pd.DatetimeIndex) and len(d) > 0:
        t0 = d.index[0]
        d = d[d.index <= t0 + pd.Timedelta(minutes=max_minutes)]
    return d


def detect_intraday_pattern(df):
    """分时形态识别（启发式）：V型 / W型 / M型 / 单边下跌 / 震荡。

    判定优先级：单边下跌 → M型 → V型 → W型 → 震荡。
    返回 dict 或 None（数据不足）。
    """
    if df is None or len(df) < 8:
        return None
    d = df.dropna(subset=["open", "high", "low", "close"])
    if len(d) < 8:
        return None
    try:
        d = _early_window(d)
        if len(d) < 8:
            d = df.dropna(subset=["open", "high", "low", "close"]).iloc[:20]
    except Exception:
        d = df.dropna(subset=["open", "high", "low", "close"]).iloc[:20]
    if len(d) < 8:
        return None

    c = d["close"].astype(float)
    l = d["low"].astype(float)
    h = d["high"].astype(float)
    n = len(d)
    open_px = float(c.iloc[0])
    close_px = float(c.iloc[-1])
    low_px = float(l.min())
    low_pos = int(l.values.argmin())
    high_px = float(h.max())

    lows = [(i, float(l.iloc[i])) for i in range(1, n - 1)
            if l.iloc[i] <= l.iloc[i - 1] and l.iloc[i] <= l.iloc[i + 1]]
    highs = [(i, float(h.iloc[i])) for i in range(1, n - 1)
             if h.iloc[i] >= h.iloc[i - 1] and h.iloc[i] >= h.iloc[i + 1]]

    drawdown = (open_px - low_px) / open_px * 100 if open_px else 0.0
    rebound = (close_px - low_px) / low_px * 100 if low_px else 0.0
    if isinstance(d.index, pd.DatetimeIndex):
        dur = (d.index[-1] - d.index[0]).total_seconds() / 60
        window = "开盘后前 %d 根K线（约 %.0f 分钟）" % (n, dur)
    else:
        window = "开盘后前 %d 根K线" % n
    params = ("开盘 %.2f → 最低 %.2f（下探 %.2f%%）→ 现价 %.2f（自低点回升 %+.2f%%）"
              % (open_px, low_px, drawdown, close_px, rebound))

    def pack(name, star, winrate, op, color):
        return {"形态": name, "星级": star, "胜率": winrate, "操作": op, "颜色": color,
                "params": params, "window": window}

    # 1) 单边下跌：收盘弱 + 低点在尾部 + 几乎无回升
    if close_px < open_px and low_pos >= n * 0.6 and rebound < 0.5:
        return pack("单边下跌", "★", "低", "当天放弃操作", "#e74c3c")
    # 2) M型：双顶回落，收盘明显弱于高点
    if len(highs) >= 2 and close_px < open_px and (high_px - close_px) / high_px * 100 >= 0.3:
        return pack("M型", "★", "低", "当天放弃操作", "#e74c3c")
    # 3) V型：低点在前40%时段 + 明显回升 + 无邻近双底
    twin_low = False
    if len(lows) >= 2:
        twin_low = abs(lows[0][1] - lows[-1][1]) / max(lows[0][1], 1e-9) < 0.005
    if low_pos <= n * 0.5 and rebound >= 0.3 and not twin_low:
        return pack("V型反转", "★★★★★", "85%+", "首选·可进场", "#27ae60")
    # 4) W型：两个接近低点 + 收盘站上双底
    if len(lows) >= 2:
        l1, l2 = lows[0][1], lows[-1][1]
        gap = abs(l2 - l1) / max(l1, 1e-9)
        if gap < 0.008 and close_px > min(l1, l2) * 1.002:
            return pack("W型双底", "★★★★", "较高", "第二选择·可进场", "#2ecc71")
    return pack("震荡/无法判断", "★★", "不确定", "等 V/W 确认再进", "#95a5a6")


# ---------------- 第三步：选品种（五个最原则） ----------------

def five_most_auto(signals, df, sector):
    """五个最原则：自动可判断部分 + 人工确认。df 需先 add_indicators。"""
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    vr3 = float(signals["volume"]["3日量比(20日均)"])
    vr7 = float(signals["volume"]["7日量比(20日均)"])
    vol_y = float(prev["volume"])
    vol_ref = float(df["volume"].iloc[-7:-1].mean()) if len(df) >= 8 else vol_y
    prev_big = vol_y >= vol_ref * 1.3 if vol_ref > 0 else False
    ret5 = (float(last["close"]) / float(df.iloc[-6]["close"]) - 1) * 100 if len(df) > 6 else 0.0
    strong5 = ret5 >= 3
    hot = any(k in str(sector) for k in ("芯片", "半导体", "存储", "AI", "算力", "太空", "核电", "机器人"))
    high60 = float(df["high"].iloc[-60:].max()) if len(df) >= 60 else float(df["high"].max())
    near_high = float(last["close"]) >= high60 * 0.95

    items = [
        {"检查项": "最强行业赛道", "自动判定": str(sector), "结果": "✅ 热门赛道" if hot else "⚠ 需人工确认", "自动": hot},
        {"检查项": "最热门题材", "自动判定": "AI / AIGC 产业链（时代大事）", "结果": "需人工确认题材热度", "自动": None},
        {"检查项": "最强主力资金介入", "自动判定": "3日量比 %.2f / 7日 %.2f" % (vr3, vr7),
         "结果": "✅ 放量介入" if vr3 >= 1.5 else "⚠ 量能一般", "自动": vr3 >= 1.5},
        {"检查项": "市场最牛龙头股",
         "自动判定": "60日新高 %.2f，现价距新高 %.1f%%" % (high60, (1 - float(last["close"]) / high60) * 100),
         "结果": "✅ 接近新高·强势" if near_high else "⚠ 需人工确认龙头地位", "自动": near_high},
        {"检查项": "前一天明显放量", "自动判定": "昨日量/前6日均量 %.2f" % (vol_y / vol_ref if vol_ref > 0 else 1.0),
         "结果": "✅ 放量" if prev_big else "⚠ 未明显放量", "自动": prev_big},
    ]
    return {"items": items, "strong5": strong5, "ret5": ret5}


# ---------------- 第四步：仓位管理 ----------------

def position_plan(capital):
    """单笔超短 ≤ 总资金 5%（硬上限）；示例按 3% 保守执行。"""
    if not capital or capital <= 0:
        return None
    return {"cap5": capital * 0.05, "cap3": capital * 0.03,
            "rule": "单笔 ≤ 5%，超短途中不加仓"}


# ---------------- 第五步：止盈 / 止损 ----------------

def exit_plan(cost, price):
    """超短线止盈阶梯 + 止损线。cost = 成本价，price = 现价。"""
    if not cost or cost <= 0:
        return None
    chg = (price / cost - 1) * 100
    tp = [(3, "卖出一半（50%）"), (5, "再卖一半（50%）"), (7, "再卖一半（50%）"), (10, "全部卖出")]
    sl_hard = cost * 0.985
    sl_max = cost * 0.97
    return {"chg": chg, "tp": tp, "sl_hard": sl_hard, "sl_max": sl_max,
            "dist_hard": (price / sl_hard - 1) * 100}


# ---------------- 综合结论 ----------------

def overall_conclusion(env, pattern):
    """大盘环境 × 分时形态 的最终操作结论。"""
    if not env.get("可用"):
        return "⚠ 数据不足：指数或分时数据不可用，无法执行超短判断"
    if env["等级"] == "回避":
        return "❌ 大盘回避（切不准 = 盲人摸象）→ 当天放弃操作，等指数企稳"
    if pattern is None:
        return "ℹ 大盘环境可用，但分时数据暂缺 → 形态未确认，谨慎为主"
    p = pattern["形态"]
    if p in ("V型反转", "W型双底") and env["等级"] in ("极佳", "良好"):
        return "✅ 大盘 + 形态双确认 → 可执行超短（严按止盈止损，绝不变套牢）"
    if p in ("V型反转", "W型双底"):
        return "⚠ 形态合格但大盘一般 → 小仓试或等下午二次确认"
    return "❌ 形态（%s）不符合超短进场 → 当天放弃" % p


# ---------------- 超短线决策卡 ----------------

def build_shortterm_card(ticker, name, env, pattern, five, pos, ex, index_name, price):
    lines = []
    lines.append("## 【超短线决策卡】%s · %s（%s）" % (ticker, name, dt.datetime.now().strftime("%Y-%m-%d %H:%M")))
    lines.append("")
    lines.append("> 大盘（%s）：**%s %d/100** —— %s" % (index_name, env["等级"], env["分数"], env["结论"]))
    if pattern:
        lines.append("> 分时形态：**%s %s**（%s，%s）" % (pattern["形态"], pattern["星级"], pattern["胜率"], pattern["操作"]))
    else:
        lines.append("> 分时形态：数据不足（需盘中 1 分钟数据）")
    lines.append("")
    lines.append("### 操作清单（按纪律执行）")
    lines.append("- 看大盘做超短：大盘切准 → 只做 V/W 强形态 → 选最强 30 只中的龙头")
    lines.append("- 五个最：最强赛道 / 最热题材 / 最强资金 / 最牛龙头 / 前日放量")
    if pos:
        lines.append("- 仓位：单笔 ≤ 总资金 5%%（硬上限，约 $%.0f），途中不加仓" % pos["cap5"])
    if ex:
        lines.append("- 止盈：3%% 卖半 → 5%% 卖半 → 7%% 卖半 → 10%% 清仓（当前浮盈 %+.2f%%）" % ex["chg"])
        lines.append("- 止损：%.2f（-1.5%% 强制）/ %.2f（-3%% 极限）；T+3 未兑现退出、T+5 强制退出" % (ex["sl_hard"], ex["sl_max"]))
    lines.append("- 铁律：任何超短都不能变成长期套牢")
    lines.append("")
    lines.append("---")
    lines.append("*超短战法仅供个人研究参考，不构成投资建议；决策由用户人工执行。*")
    return "\n".join(lines)