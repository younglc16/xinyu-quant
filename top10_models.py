# -*- coding: utf-8 -*-
"""世界公认十大顶级思维模型 —— 与鑫煜系统实时数据联动的决策护航模块。

设计定位：不是"又一张理论卡片"，而是把每个思维模型翻译成
"现在这笔决策该问自己什么 / 系统当前数据在提醒什么"。
"""
import numpy as np


# ---------------------------------------------------------------- 知识库
MODELS = [
    {
        "id": 1, "icon": "⚛️", "zh": "第一性原理", "en": "First Principles",
        "tagline": "回归本质，拆解到最基础的原理，而不是类比",
        "essence": "把问题拆回最基本的、不可再简化的真理，再从零向上推导；拒绝'别人都这么干'的类比式思考。",
        "invest": "把一只股票的故事翻译成三件事：它卖什么？自由现金流能否持续为正？护城河（定价权/唯一性）是否真实？叙事只是表象，单位经济模型才是本质。",
        "question": "如果剥离掉所有题材与故事，这个生意本身的现金流与利润率，还支撑得起当前价格吗？",
    },
    {
        "id": 2, "icon": "🌱", "zh": "复利思维", "en": "Compounding",
        "tagline": "做时间的朋友，抵御短期诱惑",
        "essence": "复利 = 本金 ×（1+收益率）^时间。慢而稳的增长经长期放大后远超暴利，而一次回本无望的亏损会打断整个指数函数。",
        "invest": "让利润奔跑的前提是趋势未破；用 3221 阶梯把浮盈落袋为底仓滚动，用时间而非频率创造收益；拒绝为短期波动频繁换仓。",
        "question": "这笔交易一年后还会是好生意吗？我是在赚时间的钱，还是在赚刺激？",
    },
    {
        "id": 3, "icon": "🪒", "zh": "奥卡姆剃刀", "en": "Occam's Razor",
        "tagline": "如无必要，勿增实体——极简是最高效的",
        "essence": "面对两种解释时选择更简单的那个；增加的假设必须带来新的解释力，否则就是噪音。",
        "invest": "指标越加越多 ≠ 越准。当 MACD、KDJ、均线、量能给出的方向互相打架时，信号本身已是噪音——减少动作，等待共振。",
        "question": "我现在是在执行系统规则，还是在给自己的冲动增加'合理'假设？",
    },
    {
        "id": 4, "icon": "🎯", "zh": "贝叶斯思维", "en": "Bayesian Updating",
        "tagline": "根据新信息不断修正你的根概率",
        "essence": "先有一个基准概率（先验），每当出现新证据，就按证据强度更新它；永远不把任何单一信号当作'确定'。",
        "invest": "先验 = 大盘温度 + 趋势位置（决定市场整体赔率）；新证据 = 放量金叉/死叉、突破/破位等——每次都只做小幅修正，而不是全盘推翻。",
        "question": "这条新消息，把我对上涨的概率从 55% 修正到了多少？幅度合理吗？",
    },
    {
        "id": 5, "icon": "🛡️", "zh": "遍历性", "en": "Ergodicity",
        "tagline": "只要有一次出局，基础概率就毫无意义",
        "essence": "期望值为正但路径上可能归零的策略没有意义——时间平均 ≠ 集合平均。生存是第一约束，任何策略都必须先保证不会出局。",
        "invest": "永不单吊重仓、永不杠杆到爆仓；每次亏小钱（-20% 硬止损），让'活得久'成为复利的前提；保留 30%-50% 现金作为生存缓冲。",
        "question": "如果这笔押注让我出局，后面的所有好机会还跟我有关吗？",
    },
    {
        "id": 6, "icon": "🗿", "zh": "幸存者偏差", "en": "Survivorship Bias",
        "tagline": "不要只看成功者，死人不会说话",
        "essence": "我们只看到活下来的样本，看不见沉默的失败者，于是高估了成功路径的可复制性。",
        "invest": "研究 20 只十倍股之前，先研究 200 只死掉的同赛道股票是怎么死的；别用涨幅榜当样本库，别用最牛案例给平庸标的找理由。",
        "question": "我看到的证据里，有多少是'活下来的'才被展示的？失败样本告诉我的相反结论是什么？",
    },
    {
        "id": 7, "icon": "🔥", "zh": "熵增定律", "en": "Entropy & Discipline",
        "tagline": "系统不主动输入能量，必将走向混乱——自律的物理本质",
        "essence": "封闭系统自发趋向混乱（熵增）。交易系统不加约束就会漂移、过度交易、纪律松垮——自律是持续向系统'输入能量'。",
        "invest": "把买卖规则写成可勾选的清单；信号打架时按规则减仓观望；情绪最强时禁止决策。规则是你对抗熵增的唯一能量来源。",
        "question": "我这一周的交易，是按清单执行的，还是逐步『即兴发挥』的？",
    },
    {
        "id": 8, "icon": "⚡", "zh": "二八法则", "en": "Pareto Principle",
        "tagline": "死磕那 20% 的核心高价值区",
        "essence": "约 80% 的结果来自 20% 的原因。精力与仓位都应集中在少数真正决定结果的核心上。",
        "invest": "主线行业的前三名龙头贡献了大多数利润；把 80% 的研究与仓位留给 20% 的顶级标的，其余只是观察仓。",
        "question": "我重仓的这个标的，属于全市场那 20% 的核心吗？还是我在用 80% 的精力赚 20% 的钱？",
    },
    {
        "id": 9, "icon": "🔁", "zh": "逆向思维", "en": "Inversion",
        "tagline": "反过来想，总是反过来想（查理·芒格的最爱）",
        "essence": "想知道如何成功，先研究如何失败；避开愚蠢比追求聪明更容易——把'怎么亏钱'的清单一条条排除掉。",
        "invest": "先做防亏清单（芒格逆向检查）：逻辑证伪了吗？仓位越界了吗？情绪最强吗？把亏钱路径全部封死，赚钱只是剩下的结果。",
        "question": "如果我想让这笔投资亏钱，我会怎么做？我现在有没有正在做其中任何一条？",
    },
    {
        "id": 10, "icon": "🌊", "zh": "反脆弱", "en": "Antifragile",
        "tagline": "从不确定性和波动中获益，而非仅仅承受它",
        "essence": "脆弱：怕波动；强韧：承受波动；反脆弱：需要波动。杠铃策略——大部分配置在最安全端，小部分押在极高赔率端。",
        "invest": "核心仓（稳健趋势/指数）+ 卫星仓（高赔率弹性），平时留足现金；暴跌与错杀不是风险而是你'从波动获益'的入场券。",
        "question": "市场大跌 20% 时，我是被迫出局，还是拿着现金在别人恐慌时进场？",
    },
]

MODELS_BY_ID = {m["id"]: m for m in MODELS}


# 主线赛道关键词（与产业赛道排行口径一致，供“二八法则”联动）
_MAIN_LINE_KEYWORDS = ["AI", "算力", "芯片", "半导体", "存储", "核电", "电力", "能源",
                       "铜", "资源", "太空", "卫星", "军工", "机器人", "金融科技", "网络安全",
                       "云计算", "数据中心", "软件"]


def _num(row, col):
    try:
        v = float(row[col])
        return v if np.isfinite(v) else None
    except Exception:
        return None


def _pct_str(x, nd=1):
    return "--" if x is None else f"{x * 100:+.{nd}f}%"


def _ret_series(df):
    return df["close"].pct_change().dropna()


# ---------------------------------------------------------------- 自动检查
def auto_review(signals, score5, temp, qt, d, idx_d=None, sector="", cost_input=0.0,
                violations=None):
    """把 10 个思维模型映射到当前系统数据，返回每条的自动检查结论。

    state: 0=绿灯(纪律通过/信号一致) 1=黄灯(提示/需人工) 2=红灯(警惕/越界)
    """
    last = d.iloc[-1]
    close = _num(last, "close") or 0.0
    n = len(d)
    cl = d["close"]
    dev5 = _num(last, "Dev5")
    ma5 = _num(last, "MA5")
    ma20 = _num(last, "MA20")
    ma60 = _num(last, "MA60")
    j = _num(last, "J")
    rsi = _num(last, "RSI")
    vr3 = _num(last, "VR3")
    vr7 = _num(last, "VR7")

    high60 = float(d["high"].iloc[-60:].max()) if n >= 60 else float(d["high"].max())
    low60 = float(d["low"].iloc[-60:].min()) if n >= 60 else float(d["low"].min())
    span = (high60 - low60) or 1e-9
    pos60 = (close - low60) / span * 100          # 60日区间位置 0-100
    dd60 = (high60 - close) / high60 * 100 if high60 else 0   # 距60日高点回撤 %
    ret = _ret_series(d)
    vol20 = float(ret.iloc[-20:].std() * np.sqrt(252) * 100) if len(ret) >= 20 else 30.0
    ret3 = float((close / cl.iloc[-4] - 1) * 100) if n >= 5 else 0.0

    # ---- 信号方向统计（奥卡姆/熵增用）----
    bull_flags, bear_flags, notes = [], [], []
    _mk = signals.get("macd_kdj") or {}
    _reso = _mk.get("双指标共振", "")
    if "多" in _reso:
        bull_flags.append("MACD+KDJ做多共振")
    elif "空" in _reso:
        bear_flags.append("MACD+KDJ做空共振")
    if _mk.get("MACD金叉") == "是":
        bull_flags.append("MACD金叉")
    if _mk.get("MACD死叉") == "是":
        bear_flags.append("MACD死叉")
    if _mk.get("KDJ金叉") == "是":
        bull_flags.append("KDJ金叉")
    if _mk.get("KDJ死叉") == "是":
        bear_flags.append("KDJ死叉")
    if (signals.get("volume") or {}).get("3日内放巨量") == "是":
        bull_flags.append("3日放量")
    if ma20 and close > ma20:
        bull_flags.append("站上MA20")
    else:
        bear_flags.append("跌破MA20")
    if (signals.get("ma") or {}).get("多头排列") == "是":
        bull_flags.append("均线多头")
    else:
        bear_flags.append("均线未多头")

    temp_val = float(temp.get("temp", 50) or 50)
    temp_label = temp.get("label", "中温")
    grow = int(score5.get("成长", 50))
    val_score = int(score5.get("估值", 50))
    risk_score = int(score5.get("风险", 50))
    trend = int(score5.get("趋势", 50))
    sector_ok = any(k in (sector or "") for k in _MAIN_LINE_KEYWORDS)
    if violations is None:
        violations = int(qt.get("芒格违规数", 0) or 0) if isinstance(qt, dict) else 0
    else:
        violations = int(violations or 0)

    results = []

    # 1 第一性原理：叙事 vs 现金流锚
    if val_score >= 70 and grow >= 65:
        state, st_txt = 0, "估值与成长双高，价格仍贴基本面锚"
    elif val_score < 45 and pos60 > 85:
        state, st_txt = 2, "高位 + 估值分低 → 叙事溢价显著"
    else:
        state, st_txt = 1, "需人工回归现金流/护城河"
    results.append({
        "id": 1, "state": state, "state_text": st_txt,
        "evidence": [f"60日位置 {pos60:.0f}% · 距60日高点 {dd60:.1f}%",
                     f"五维·估值 {val_score} / 成长 {grow}",
                     "自问：剥离题材后，自由现金流与利润率还撑得起这个价格吗？"],
    })

    # 2 复利思维：让利润奔跑 vs 纪律线
    _ok_run = (dev5 is not None and dev5 < 7.5) and (ma20 and close > ma20)
    if _ok_run:
        state, st_txt = 0, "趋势未破，符合'让利润奔跑'"
    elif dev5 is not None and dev5 > 7.5:
        state, st_txt = 2, f"收盘价已偏离5日线 {dev5:+.1f}% 超纪律线7.5%"
    else:
        state, st_txt = 1, "短线走弱，先守住利润再谈复利"
    results.append({
        "id": 2, "state": state, "state_text": st_txt,
        "evidence": [f"偏离MA5 {_pct_str(dev5 / 100 if dev5 else None)}",
                     f"{'站上' if (ma20 and close > ma20) else '跌破'}MA20 · 近3日 {ret3:+.1f}%",
                     "提示：只要不破五日线纪律(7.5%)，波动是复利的一部分"],
    })

    # 3 奥卡姆剃刀：信号一致性
    both = len(bull_flags) and len(bear_flags)
    if not both:
        state, st_txt = 0, "当前信号方向一致，动作少而清晰"
    elif len(bull_flags) >= 2 and len(bear_flags) >= 2:
        state, st_txt = 2, "多空信号严重打架 → 最该做的是观望"
    else:
        state, st_txt = 1, "存在反向噪音，减少动作等待共振"
    results.append({
        "id": 3, "state": state, "state_text": st_txt,
        "evidence": [f"同向信号 {len(bull_flags)} 项：{'、'.join(bull_flags) or '无'}",
                     f"反向信号 {len(bear_flags)} 项：{'、'.join(bear_flags) or '无'}",
                     "结论：信号越多越该等共振，指标堆叠不等于确定性"],
    })

    # 4 贝叶斯思维：先验温度 × 新证据
    _hot = temp_val >= 70
    _cold = temp_val <= 30
    _reso_dir = _mk.get("双指标共振", "")
    _up_new = ("多" in _reso_dir) or (_mk.get("MACD金叉") == "是") or (_mk.get("KDJ金叉") == "是") or ret3 > 0
    _dn_new = ("空" in _reso_dir) or (_mk.get("MACD死叉") == "是") or (_mk.get("KDJ死叉") == "是") or ret3 < 0
    if (_hot and _dn_new) or (_cold and _up_new):
        state, st_txt = 1, "温度与新证据相反 → 概率应下调"
    elif (_hot and _up_new) or (_cold and _dn_new):
        state, st_txt = 0, "温度与新证据同向，方向概率增强"
    else:
        state, st_txt = 1, "证据偏中性，先验为主"
    prob_dir = ("偏多" if (_hot and _up_new) or (_cold and _dn_new) or (not _hot and not _cold and ret3 > 0)
                else ("偏空" if ret3 < 0 or _dn_new else "中性"))
    results.append({
        "id": 4, "state": state, "state_text": st_txt,
        "evidence": [f"先验：市场温度 {temp_val:.0f}°C（{temp_label}）· 60日位置 {pos60:.0f}%",
                     f"新证据：近3日 {ret3:+.1f}% · KDJ/MACD 状态（金叉/死叉/放量见上）",
                     f"修正方向：{prob_dir} —— 每次只小幅修正，不因单一消息全盘推翻"],
    })

    # 5 遍历性：先保证不出局
    _vol_high = vol20 > 55
    _dev_break = dev5 is not None and abs(dev5) > 7.5
    _j_extreme = (j is not None) and (j > 100 or j < -10)
    if _dev_break and _vol_high:
        state, st_txt = 2, "波动剧烈 + 已破纪律线 → 先活下来"
    elif _vol_high or _j_extreme:
        state, st_txt = 1, "波动偏高，务必控制单票仓位"
    else:
        state, st_txt = 0, "未出现出局级风险信号"
    results.append({
        "id": 5, "state": state, "state_text": st_txt,
        "evidence": [f"年化波动约 {vol20:.0f}% · KDJ J值 {j if j is not None else '--'}",
                     "出局红线：单票 ≤20% + 硬止损 -20% + 现金缓冲 30-50%",
                     "自问：最坏情形下我会被清出局吗？"],
    })

    # 6 幸存者偏差：别只给成功找理由
    if risk_score >= 70:
        state, st_txt = 0, "风险分健康，继续双向求证"
    elif risk_score >= 50:
        state, st_txt = 1, "注意：你的样本里有没有'活下来的'偏差"
    else:
        state, st_txt = 2, "风险分低 → 停止用上涨逻辑说服自己"
    results.append({
        "id": 6, "state": state, "state_text": st_txt,
        "evidence": [f"五维·风险 {risk_score} · 距60日高点回撤 {dd60:.1f}%",
                     f"当前 60日位置 {pos60:.0f}%（越高越要研究它过去怎么跌的）",
                     "自问：同赛道死掉的标的长什么样？我现在持有的是'最好的那个'吗？"],
    })

    # 7 熵增定律：纪律对抗混乱
    _mess = len(bull_flags) + len(bear_flags)
    _extreme_now = _hot or _cold or (j is not None and (j > 100 or j < -10))
    if _mess >= 4 and _extreme_now:
        state, st_txt = 2, "环境极端 + 信号杂多 → 纪律最容易失守"
    elif _mess >= 4 or _extreme_now:
        state, st_txt = 1, "系统接近'混乱临界'，按清单执行"
    else:
        state, st_txt = 0, "系统有序，维持清单式执行"
    results.append({
        "id": 7, "state": state, "state_text": st_txt,
        "evidence": [f"温度 {temp_val:.0f}°C（{'高/极端' if _hot else '低/冰点' if _cold else '中温'}）",
                     "动作清单：买卖必须过 5 道闸（趋势/仓位/止损/止盈/情绪）",
                     "熵增提醒：不做记录、不按清单 = 系统正在自发走向混乱"],
    })

    # 8 二八法则：只重仓那 20% 核心
    if sector_ok and trend >= 65:
        state, st_txt = 0, f"当前赛道属主线（20%）且趋势分 {trend}"
    elif sector_ok:
        state, st_txt = 1, "赛道属主线，但个股强度待确认"
    else:
        state, st_txt = 2, f"当前赛道「{sector or '未识别'}」不在主线清单"
    results.append({
        "id": 8, "state": state, "state_text": st_txt,
        "evidence": [f"赛道：{sector or '—'} · {'命中主线关键词' if sector_ok else '未命中主线关键词'}",
                     "执行口径：主线行业里挑 第1/2/3 名龙头重仓，其余只做观察仓",
                     "自问：这笔钱是放在 20% 的核心上，还是在 80% 的边缘里？"],
    })

    # 9 逆向思维：先防亏（芒格清单联动）
    if violations == 0:
        state, st_txt = 0, "逆向防亏清单无违规"
    elif violations <= 2:
        state, st_txt = 1, f"芒格检查提示 {violations} 项 → 逐条排除后再行动"
    else:
        state, st_txt = 2, f"逆向清单亮起 {violations} 项 → 停止动作"
    results.append({
        "id": 9, "state": state, "state_text": st_txt,
        "evidence": [f"芒格逆向检查：{violations} 项违规/提示（详见「大师智慧」Tab）",
                     "反过来问：想让它亏钱，我现在最该做什么？",
                     "处理：先封死亏钱路径，再谈赚钱空间"],
    })

    # 10 反脆弱：从波动中获益（杠铃）
    if temp_val >= 70:
        state, st_txt = 1, "高温 → 保留现金等待别人恐慌"
    elif pos60 < 40 and trend >= 60:
        state, st_txt = 0, "低位 + 趋势尚可 → 波动是低吸机会"
    elif dd60 > 20:
        state, st_txt = 1, "深度回撤中 → 分批而非一次下注"
    else:
        state, st_txt = 0, "结构健康，杠铃两端都能接住波动"
    results.append({
        "id": 10, "state": state, "state_text": st_txt,
        "evidence": [f"距60日高点回撤 {dd60:.1f}% · 温度 {temp_val:.0f}°C",
                     "杠铃结构：核心仓(稳健) + 卫星仓(高赔率) + 现金缓冲(选择权)",
                     "自问：暴跌 20% 时我是被迫出局，还是拿着现金进场？"],
    })

    return results


def summary_stats(results):
    green = sum(1 for r in results if r["state"] == 0)
    yellow = sum(1 for r in results if r["state"] == 1)
    red = sum(1 for r in results if r["state"] == 2)
    return {"绿灯": green, "黄灯": yellow, "红灯": red}


# ---------------------------------------------------------------- 决策前 10 问
PRE_FLIGHT = [
    ("第一性原理", "我是否把故事剥离到了现金流与护城河本身？"),
    ("复利思维", "这笔交易是否会打断我已有的复利进程？"),
    ("奥卡姆剃刀", "我的每一个动作，是否都能被系统规则解释？"),
    ("贝叶斯思维", "我的概率更新幅度，是否与证据强度匹配？"),
    ("遍历性", "最坏情形下我会出局吗？仓位与止损是否已设好？"),
    ("幸存者偏差", "我是否忽略了失败样本给出的相反结论？"),
    ("熵增定律", "我是按清单执行，还是在即兴发挥？"),
    ("二八法则", "重仓标的真的属于最核心的 20% 吗？"),
    ("逆向思维", "想让它亏钱的话，我现在正做的是不是其中一步？"),
    ("反脆弱", "波动来临时，我是受害者还是受益者？"),
]
