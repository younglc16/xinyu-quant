# -*- coding: utf-8 -*-
"""大师智慧（Recommended Reading）——六本经典投资著作的精华提炼与系统化映射。

每本书的观点被转化为：
1. 可执行的检查清单（由行情数据驱动，能算就算，算不了标「人工确认」）
2. 分析指标标签（市场先生情绪 / 达利欧周期 / 林奇公司类型 / 安全边际代理）
3. 决策卡中的「大师原则核对」段落
"""

# ---------------- 书籍精华（展示用） ----------------

BOOKS = [
    {
        "title": "One Up On Wall Street",
        "author": "Peter Lynch 彼得·林奇",
        "core": "从生活细节中挖掘投资机会",
        "essence": [
            "买你了解的东西：用一句话说清这家公司怎么赚钱，说不清就不买。",
            "生活选股：从工作、购物、消费中发现十倍股，领先华尔街一步。",
            "PEG 估值：成长股 PEG<1 才值得买（市盈率/盈利增速）。",
            "六类公司分类：快速增长/稳定增长/缓慢增长/周期/困境反转/隐蔽资产，不同类别不同玩法。",
            "避开热门股与题材炒作：热门股涨得慢、跌得快。",
        ],
        "indicators": ["五维-成长", "五维-估值(PEG代理)", "公司类型分类", "能力圈自检"],
    },
    {
        "title": "The Intelligent Investor",
        "author": "Benjamin Graham 格雷厄姆",
        "core": "价值投资基石，安全边际",
        "essence": [
            "安全边际：只在价格显著低于价值时买入，为错误和意外留出空间。",
            "市场先生：把市场报价当仆人而非向导，情绪极端时反向利用。",
            "投资与投机：投资以深入分析+本金安全+满意回报为前提，否则是投机。",
            "防御型/进攻型：先确认自己是哪种投资者，再定策略与仓位。",
            "分散化与纪律：不押单点，分散降低永久损失风险。",
        ],
        "indicators": ["市场温度(市场先生情绪)", "安全边际代理", "估值分", "分散度检查(单股≤20%)"],
    },
    {
        "title": "Principles",
        "author": "Ray Dalio 瑞·达利欧",
        "core": "宏观周期与债务危机框架",
        "essence": [
            "经济机器：交易、信贷、生产率三要素驱动，债务周期决定大级别涨跌。",
            "短/长债务周期：加杠杆推升繁荣，去杠杆引发衰退；位置决定策略。",
            "全天候思维：不预测，用配置应对所有环境；资产相关性决定组合稳定性。",
            "痛苦+反思=进步：把每次亏损变成系统改进的输入。",
            "五步流程：定目标→找问题→诊断根因→设计方案→执行。",
        ],
        "indicators": ["宏观周期位置(利率/债市)", "市场温度(周期温度)", "组合配置(对冲思维)", "复盘机制(决策卡留档)"],
    },
    {
        "title": "The Most Important Thing",
        "author": "Howard Marks 霍华德·马克斯",
        "core": "投资心理与周期思维",
        "essence": [
            "第二层思维：共识之外再想一层——大家都看好时，好在哪里可能已经兑现？",
            "周期与钟摆：市场在贪婪↔恐惧间摆动，极端位置就是反向机会。",
            "风险不是波动，是永久损失的概率：先问亏多少，再问赚多少。",
            "防御型投资：进攻赚得多，防守活得久；攻守平衡按周期位置切换。",
            "逆向不是单纯反着来，而是判断钟摆位置后站在赔率有利的一侧。",
        ],
        "indicators": ["市场温度(钟摆位置)", "风险分", "攻守档位(只防守/中性/进攻)", "第二层思维三问"],
    },
    {
        "title": "Poor Charlie's Almanack",
        "author": "Charlie Munger 查理·芒格",
        "core": "多元思维模型与 lollapalooza 效应",
        "essence": [
            "多元思维模型：用多个学科模型交叉验证，单一模型容易犯错。",
            "Lollapalooza 效应：多重因素同向共振时威力最大（对应我们的多维共振）。",
            "反过来想：先列「怎么亏钱」清单，再决定怎么做。",
            "能力圈：只在自己懂的领域出手，圈外再好的机会也不碰。",
            "不做傻事清单：避免愚蠢比追求聪明更有效；耐心等待好球。",
        ],
        "indicators": ["六维共振计数", "芒格逆向检查清单", "能力圈自检", "耐心/等待信号(等回调)"],
    },
    {
        "title": "Superinvestors of Graham-and-Doddsville",
        "author": "Warren Buffett 沃伦·巴菲特",
        "core": "价值投资案例集",
        "essence": [
            "价值投资不是运气：格雷厄姆-多德部落的长期超额收益来自方法，不是掷硬币。",
            "核心共识：寻找价格低于价值的机会，坚持原则且互不抄作业。",
            "集中 + 能力圈：少而精，只投能看懂的；分散是无奈而非优势。",
            "长期主义：以企业主视角持有，让复利滚动；波动是入场券不是风险。",
            "赚什么钱要想清楚：价值回归 / 成长兑现 / 情绪修复，三者策略不同。",
        ],
        "indicators": ["安全边际代理", "质量档(选好公司)", "集中度(单股≤20%)", "赚钱来源分类"],
    },
]


# ---------------- 可计算指标 ----------------

def mr_market_label(temp):
    """格雷厄姆/马克斯：市场先生情绪（钟摆位置）。"""
    t = temp["temp"]
    if t >= 85:
        return "极度贪婪 · 顶部区域（别人贪婪我恐惧）"
    if t >= 70:
        return "贪婪 · 乐观（提防追高）"
    if t >= 45:
        return "中性（按纪律分批）"
    if t >= 30:
        return "恐惧 · 悲观（关注错杀机会）"
    return "极度恐惧 · 底部区域（别人恐惧我贪婪）"


def cycle_position(index_df):
    """达利欧：宏观周期位置（简化版，用指数趋势+温度合成）。"""
    last = index_df.iloc[-1]
    ma20 = last["MA20"] if last["MA20"] == last["MA20"] else last["close"]
    ma60 = last["MA60"] if last["MA60"] == last["MA60"] else ma20
    above60 = last["close"] > ma60
    above20 = last["close"] > ma20
    if above60 and above20:
        stage = "扩张期"
        action = "顺势持有/回调分批"
    elif above60 and not above20:
        stage = "扩张回调"
        action = "观察是否企稳，不急着接"
    elif not above60 and not above20:
        stage = "收缩期"
        action = "防守为主，等底部结构"
    else:
        stage = "底部修复"
        action = "轻仓试探，确认反转再加"
    return {"阶段": stage, "操作": action}


def lynch_company_type(score5, signals):
    """林奇：六类公司分类（简化判定）。"""
    growth, value = score5["成长"], score5["估值"]
    risk, trend = score5["风险"], score5["趋势"]
    dev5 = signals["ma5"]["偏离MA5"]
    dev5_num = float(dev5.replace("%", "").replace("+", ""))
    if growth >= 75 and value >= 60:
        return "快速增长型（高成长+估值合理，林奇首选 PEG<1）"
    if value >= 72 and growth < 60:
        return "稳定增长型（估值低、增长稳，赚价值回归的钱）"
    if risk < 45 and trend >= 60:
        return "周期型（高波动强趋势，需盯周期拐点）"
    if value >= 65 and trend < 40:
        return "困境反转型（被错杀，等基本面/情绪修复）"
    if value < 55 and dev5_num < -3:
        return "缓慢增长/等待型（未到买点，耐心等）"
    return "隐蔽资产型/待确认（需人工判断资产重估空间）"


def margin_of_safety(df):
    """格雷厄姆：安全边际代理（价格在60日区间中的位置，越低越安全）。"""
    low60 = df["low"].iloc[-60:].min()
    high60 = df["high"].iloc[-60:].max()
    last = df["close"].iloc[-1]
    pos = (last - low60) / (high60 - low60) * 100 if high60 > low60 else 50
    if pos <= 30:
        level, note = "高", "价格贴近60日低位区，安全边际大"
    elif pos <= 55:
        level, note = "中", "价格处于区间中下部，有一定安全边际"
    else:
        level, note = "低", "价格已脱离低位区，追高安全边际小"
    return {"pos60": round(float(pos), 1), "level": level, "note": note}


def munger_inversion_checks(signals, qt, temp, score5):
    """芒格：反过来想——「怎么亏钱」检查清单。返回 (清单, 违规数)。"""
    checks = []
    j = signals["kdj"]["J值"]
    dev5 = signals["ma5"]["偏离MA5"]
    checks.append(("高位追涨", f"J={j}，{signals['ma5']['信号']}", "禁止" if (j > 80 or "+" in dev5 and float(dev5.replace('%','').replace('+','')) > 5) else "通过"))
    checks.append(("重仓单押", "单行业≤30%、单股≤20%", "纪律提示"))
    checks.append(("使用杠杆", "杜绝杠杆，锚定稳健", "纪律提示"))
    checks.append(("逆势硬扛", f"市场温度 {temp['temp']}°C", "通过" if temp["temp"] >= 25 else "注意：大盘偏冷"))
    checks.append(("忽视止损", "五日线7.5% / 超短1.5%-3% / 波段15-20%", "纪律提示"))
    checks.append(("能力圈外", "能用一句话说清商业模式吗？", "人工确认"))
    checks.append(("情绪化交易", f"矩阵结论：{qt['结论']}", "通过" if "回避" not in qt["结论"] else "提示：当前结论=回避"))
    checks.append(("忽略赔率", "风险收益比目标 1:2 ~ 1:3", "纪律提示"))
    violations = sum(1 for _, _, st in checks if st.startswith("禁止") or st.startswith("注意") or st.startswith("提示"))
    return checks, violations


def second_level_questions(temp, signals, score5):
    """马克斯：第二层思维三问。"""
    t = temp["temp"]
    consensus = "市场乐观（温度偏高，追涨者多）" if t >= 65 else ("市场悲观（温度偏低，恐慌者多）" if t < 40 else "市场中性")
    return [
        ("第一层：共识是什么？", consensus + f"，J值={signals['kdj']['J值']}"),
        ("第二层：共识哪里可能错了？",
         f"量能{'已确认' if signals['volume']['3日内放巨量'] == '是' else '未确认'}；"
         f"估值分={score5['估值']}（{'偏低→错杀可能' if score5['估值'] >= 70 else '中性' if score5['估值'] >= 55 else '偏高→追高危险'}）；"
         f"趋势分={score5['趋势']}"),
        ("反证：什么情况下我的判断会错？", "收盘跌破5日线7.5%纪律线 / 大盘创新低 / 逻辑变化（财报/订单/行业）→ 立即离场"),
    ]


def money_made_classification(score5, df):
    """巴菲特：这笔投资赚的是什么钱？"""
    value = score5["估值"]
    growth = score5["成长"]
    ms = margin_of_safety(df)
    kinds = []
    if value >= 70:
        kinds.append("价值回归（低估修复）")
    if growth >= 75:
        kinds.append("成长兑现（业绩增长）")
    if ms["pos60"] <= 30 and value >= 55:
        kinds.append("情绪修复（恐慌错杀反弹）")
    if not kinds:
        kinds.append("趋势/动量（需严格止损）")
    return " + ".join(kinds)


def master_checklist(signals, score5, temp, qt, df, index_df):
    """汇总：大师原则核对（供决策卡使用）。"""
    ms = margin_of_safety(df)
    cycle = cycle_position(index_df)
    inv_checks, violations = munger_inversion_checks(signals, qt, temp, score5)
    return {
        "市场先生": mr_market_label(temp),
        "周期位置": f"{cycle['阶段']}（{cycle['操作']}）",
        "公司类型": lynch_company_type(score5, signals),
        "安全边际": f"{ms['level']}（60日区间位置 {ms['pos60']}%）",
        "赚钱来源": money_made_classification(score5, df),
        "芒格违规数": violations,
        "第二层思维": second_level_questions(temp, signals, score5),
    }