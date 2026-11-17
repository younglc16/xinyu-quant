# -*- coding: utf-8 -*-
"""做空决策体系（Short System）——与做多系统形成对冲。

核心方法：对立统一——从做多逻辑反向推导做空逻辑。
- 共性：先大势后个股、利用情绪极端、分批纪律、严格止损
- 镜像：KDJ/五日线/分时形态/趋势排列 全部反向
- 矛盾：仓位与风险特征相反（空头理论亏损无限，须更快更小）
- 个性：借券费、逼空、回购、财报暴雷、事件驱动
"""
import datetime as dt

# ---------------- 对立统一对照表 ----------------

LONG_SHORT_MATRIX = [
    {"维度": "大盘前提", "做多": "震荡不创新低", "做空": "转弱破位 / 创新高受阻", "关系": "镜像"},
    {"维度": "KDJ 战法", "做多": "J<0 超卖买入", "做空": "J>100 严重超买→逼空信号", "关系": "镜像"},
    {"维度": "五日线战法", "做多": "站上MA5 + 3/7日放量", "做空": "跌破MA5 7.5% + 放量确认", "关系": "镜像"},
    {"维度": "分时形态", "做多": "V型 / W型 / 三低点", "做空": "M型 / 下跌通道 / 三高点", "关系": "镜像"},
    {"维度": "趋势排列", "做多": "MA5>MA20>MA60", "做空": "MA5<MA20<MA60", "关系": "镜像"},
    {"维度": "情绪利用", "做多": "别人恐惧我贪婪", "做空": "别人贪婪我恐惧", "关系": "共性"},
    {"维度": "分批纪律", "做多": "3221 分批止盈", "做空": "分批建空 + 阶梯回补", "关系": "共性"},
    {"维度": "止损纪律", "做多": "3570/3221成本保护20%，更紧保护沿用", "做空": "突破阻力 5-8% 快止损", "关系": "共性"},
    {"维度": "时间窗口", "做多": "可长持留底仓", "做空": "T+3 / T+5 短周期", "关系": "个性"},
    {"维度": "仓位上限", "做多": "3570按市场状态设上限", "做空": "单标的 ≤ 10-15%", "关系": "个性"},
    {"维度": "风险特征", "做多": "最大亏损 = 本金", "做空": "理论亏损无限 + 借券费 + 逼空", "关系": "矛盾"},
    {"维度": "心理压力", "做多": "怕下跌（恐慌）", "做空": "怕上涨（逼空轧空）", "关系": "矛盾"},
]

# ---------------- 做空技术信号（镜像做多战法） ----------------

def short_technical_signals(signals, d, temp):
    """从日线数据计算做空技术信号。signals 来自 indicators.signal_checks。"""
    last = d.iloc[-1]
    j = signals["kdj"]["J值"]
    out = {}

    # 1) 反向 KDJ 逼空信号
    squeeze = j > 100
    out["kdj_short"] = {
        "J值": j,
        "逼空信号": "释放" if squeeze else "未释放",
        "判定": "J>100 严重超买，顶部逼空区（做空候选，但开空需等回落确认）" if squeeze
                else ("J>80 高位预警，等待滞涨/回落" if j > 80 else "J 未到超买，做空时机未到"),
    }

    # 2) 反向五日线：跌破 7.5%
    dev5 = float(last["Dev5"])
    below = last["close"] < last["MA5"] and dev5 <= -7.5
    out["ma5_short"] = {
        "收盘vs MA5": f"{dev5:+.2f}%",
        "空头确认": "是" if below else "否",
        "判定": "收盘跌破5日线7.5%，空头趋势确认（做空核心信号）" if below
                else ("收盘跌破5日线，短线转弱（空头观察）" if dev5 < 0 else "仍站上5日线，不做空"),
    }

    # 3) 均线空头排列
    ma5v, ma10v, ma20v = float(last["MA5"]), float(last["MA10"]), float(last["MA20"])
    ma60v = float(last["MA60"]) if not float("nan") and last["MA60"] == last["MA60"] else float("nan")
    bear = ma5v < ma20v < ma60v if ma60v == ma60v else ma5v < ma20v
    out["ma_short"] = {
        "排列": "空头排列" if bear else "未空头排列",
        "判定": "MA5<MA20<MA60 空头排列，趋势向下（可持有空单）" if bear else "均线未转空，做空需谨慎",
    }

    # 4) 量价背离（高位放量滞涨 = 出货）
    vr7 = float(last["VR7"]) if last["VR7"] == last["VR7"] else 1.0
    high60 = float(d["high"].iloc[-60:].max())
    near_high = last["close"] >= high60 * 0.95
    stall = near_high and vr7 >= 1.3 and last["close"] <= last["open"]
    out["volume_short"] = {
        "7日量比": round(vr7, 2),
        "高位滞涨": "是（放量滞涨=出货迹象）" if stall else "否",
        "判定": "高位放量滞涨，主力出货嫌疑 → 做空加分" if stall else "量价正常",
    }

    # 5) 60日位置与大盘配合
    pos60 = (last["close"] - d["low"].iloc[-60:].min()) / (high60 - d["low"].iloc[-60:].min()) * 100
    out["position"] = {
        "60日位置": f"{pos60:.1f}%",
        "大盘温度": f"{temp['temp']}°C",
        "判定": "高位（适合找顶部做空候选）" if pos60 >= 70 else ("中位" if pos60 >= 40 else "低位（不做空）"),
    }

    # 6) MACD + KDJ 共振（做空侧，与做多系统镜像）
    #    做空同样要求共振：KDJ 死叉/超买拐头 且 MACD 死叉/上涨减速，才视为强做空点。
    _mk = signals.get("macd_kdj") or {}
    _reso = _mk.get("双指标共振", "无")
    if "做空共振(强)" in _reso:
        _r_txt, _r_score = "强做空：KDJ 死叉 + MACD 死叉（双死叉共振）", 30
    elif "偏空共振" in _reso:
        _r_txt, _r_score = "做空共振：KDJ 死叉/超买拐头 + MACD 上涨减速", 20
    elif "多" in _reso:
        _r_txt, _r_score = "当前为做多共振，不宜逆势做空，等死叉共振", -15
    else:
        _r_txt, _r_score = "无共振，等待 KDJ + MACD 同步死叉", 0
    out["macd_kdj_short"] = {
        "共振状态": _reso,
        "MACD动能": _mk.get("MACD动能", "—"),
        "判定": _r_txt,
        "共振加分": _r_score,
    }
    return out


def short_technical_score(sig_short):
    """做空技术分 0-100。"""
    score = 0
    if sig_short["kdj_short"]["逼空信号"] == "释放":
        score += 25
    elif sig_short["kdj_short"]["J值"] > 80:
        score += 15
    if sig_short["ma5_short"]["空头确认"] == "是":
        score += 30
    elif "跌破5日线" in sig_short["ma5_short"]["判定"]:
        score += 15
    if sig_short["ma_short"]["排列"] == "空头排列":
        score += 20
    if sig_short["volume_short"]["高位滞涨"].startswith("是"):
        score += 15
    if float(sig_short["position"]["60日位置"].replace("%", "")) >= 70:
        score += 10
    score += int(sig_short.get("macd_kdj_short", {}).get("共振加分", 0))
    return max(0, min(100, score))


# ---------------- 宏观 / 事件驱动 ----------------

MACRO_EVENTS = [
    ("美联储加息 / 缩表", "利率上行压制高估值成长股，科技/长久期资产承压", 20),
    ("地缘冲突 / 战争", "风险偏好收缩，避险情绪推跌风险资产", 15),
    ("政策利空（如关税/监管）", "特朗普关税等政策冲击特定行业（如中国链、新能源）", 15),
    ("财报暴雷季", "预期过高 + 估值泡沫 + 环比走弱 → 业绩不及预期即暴跌", 20),
    ("黑天鹅事件", "不可预知但高影响：闪崩、系统性流动性危机", 10),
    ("行业渗透率见顶", "赛道逻辑破坏（如 AI 资本开支下修）→ 龙头估值重定价", 20),
]

EVENT_CHOICES = {
    "无（当前无高概率利空事件）": 0,
    "弱（有苗头，未定价）": 30,
    "中（事件临近/已发酵，市场部分定价）": 60,
    "强（事件已落地或高概率发生）": 90,
}


def macro_score(event_choice="无（当前无高概率利空事件）", temp=None):
    """宏观/事件分：事件强度 70% + 大盘温度极端 30%。"""
    ev = EVENT_CHOICES.get(event_choice, 0)
    temp_part = 0
    if temp:
        t = temp["temp"]
        if t >= 85:
            temp_part = 100   # 大盘过热，转弱风险高
        elif t <= 25:
            temp_part = 70    # 大盘破位下跌中
        elif t >= 70:
            temp_part = 40
    return round(0.7 * ev + 0.3 * temp_part)


# ---------------- 基本面做空分（镜像估值分） ----------------

def fundamental_short_score(score5):
    """估值越高（估值分越低）+ 质量越差 → 越适合做空。"""
    value = score5["估值"]          # 越高=越便宜
    trend = score5["趋势"]
    growth = score5["成长"]
    s = 0
    s += (100 - value) * 0.5        # 贵 → 做空加分
    s += (100 - trend) * 0.3        # 趋势弱 → 加分
    s += max(0, 50 - growth) * 0.2  # 成长乏力 → 加分
    return round(min(100, s))


# ---------------- 综合评分与评级 ----------------

def short_composite(tech_score, macro, fund):
    return round(0.4 * tech_score + 0.3 * macro + 0.3 * fund)


def short_rating(score):
    if score >= 75:
        return ("强做空信号（破位+逼空/事件共振）", "crimson")
    if score >= 60:
        return ("标准做空（趋势+催化确认）", "#c0392b")
    if score >= 45:
        return ("观察（等待做空触发点）", "#b8860b")
    return ("不做空（条件不满足）", "#95a5a6")


# ---------------- 做空风控 ----------------

def short_risk_checks(sig_short, d, score5):
    """做空特有风控检查。"""
    last = d.iloc[-1]
    high60 = float(d["high"].iloc[-60:].max())
    pos60 = (last["close"] - d["low"].iloc[-60:].min()) / (high60 - d["low"].iloc[-60:].min()) * 100
    j = sig_short["kdj_short"]["J值"]
    checks = [
        ("逼空风险", "高（价格贴近60日高点 + J>100，一旦利空证伪会轧空）" if (pos60 >= 75 and j > 100) else "中" if j > 80 else "低", "核心风险：做空比例高+好消息→轧空"),
        ("借券费率", "数据暂缺 → 人工确认（>10% 年化谨慎，>50% 放弃）", "人工确认"),
        ("回购风险", "公司回购会推升股价，做空前查回购计划", "人工确认"),
        ("财报窗口", "财报/重大事件前不裸空（波动无法控制）", "纪律提示"),
        ("仓位上限", "单标的 ≤ 10-15%，组合净空敞口可控", "纪律提示"),
        ("止损纪律", "突破入场价 5-8% 无条件止损（空头亏损理论无限）", "纪律提示"),
        ("时间止损", "T+3 无利润回补，T+5 强制回补（空头有时间成本）", "纪律提示"),
        ("熔断/停牌", "极端行情可能暂停交易，空单无法平仓", "风险提示"),
    ]
    return checks


# ---------------- 做空决策卡 ----------------

def build_short_card(ticker, name, sector, d, sig_short, tech_score, macro, fund, comp, rating,
                     idx_name, temp, event_choice, quote=None):
    last = d.iloc[-1]
    date = d.index[-1].strftime("%Y-%m-%d")
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    lines.append(f"## 【做空决策卡】{ticker} · {name}　({now})")
    lines.append("")
    lines.append(f"> 数据截至 {date} 收盘 · 做空体系（与做多系统对冲）· 参考为主，人工执行")
    lines.append("")
    lines.append("### 1. 大势与板块")
    lines.append(f"- 大盘（{idx_name}）：温度 {temp['temp']}°C（{temp['label']}）→ 做空前提：{'满足（转弱/过热待回落）' if temp['temp'] >= 70 or temp['temp'] <= 30 else '一般（中性，做空需更强个股信号）'}")
    lines.append(f"- 赛道：{sector}（做空偏好：高估值泡沫、破位、逻辑破坏）")
    lines.append("")
    lines.append("### 2. 技术信号（镜像做多战法）")
    lines.append(f"- 反向 KDJ：J={sig_short['kdj_short']['J值']} → {sig_short['kdj_short']['判定']}")
    lines.append(f"- MACD+KDJ 共振：{sig_short['macd_kdj_short']['判定']}（{sig_short['macd_kdj_short']['MACD动能']}）")
    lines.append(f"- 反向五日线：{sig_short['ma5_short']['收盘vs MA5']} → {sig_short['ma5_short']['判定']}")
    lines.append(f"- 均线：{sig_short['ma_short']['判定']}")
    lines.append(f"- 量价：{sig_short['volume_short']['判定']}")
    lines.append(f"- 位置：{sig_short['position']['判定']}")
    lines.append("")
    lines.append("### 3. 宏观 / 事件驱动")
    lines.append(f"- 当前事件选择：{event_choice}（宏观分 {macro}/100）")
    lines.append(f"- 大盘温度贡献：{temp['temp']}°C")
    lines.append("")
    lines.append("### 4. 综合评分")
    lines.append(f"- 技术 {tech_score}（40%）+ 宏观 {macro}（30%）+ 基本面 {fund}（30%）= **{comp}**")
    lines.append(f"- 评级：**{rating[0]}**")
    lines.append("")
    lines.append("### 5. 操作建议（按战法纪律）")
    lines.append("- **进场**：等待「反向 KDJ 高位回落拐头 / 跌破 5 日线 / 放量滞涨」确认后分批开空，不抢最高点")
    lines.append("- **回补**：跌 20% 分批回补（独立做空纪律）；放巨量收复 5 日线 → 立即回补")
    lines.append("- **止损**：突破入场价 5-8% 无条件止损；财报/事件前不裸空")
    lines.append("- **时间止损**：T+3 无利润回补，T+5 强制回补")
    lines.append("")
    lines.append("### 6. 做空风控")
    lines.append("- 仓位：单标的 ≤ 10-15%，组合净空敞口可控")
    lines.append("- 逼空/借券/回购/熔断：见风控清单，逐项人工确认")
    lines.append("")
    lines.append("---")
    lines.append("*仅供个人研究参考，不构成投资建议。做空风险高于做多，决策由用户人工执行。*")
    return "\n".join(lines)
