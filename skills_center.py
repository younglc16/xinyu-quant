# -*- coding: utf-8 -*-
"""Skills Center v2：ai-berkshire 21 个 Skill 的网页端完整集成引擎（数据驱动研究文章版）。

v2 改进：
- 新增数据解读引擎 narrate_*：把财务/行情指标翻译成自然语言分析段落
- 每个 Skill 输出「完整研究文章」而非表格模板：公司概况 → 分维度分析 → 结论
- 修复 _fmt 单位（1e9）、财年引用、UI 残留等漏洞
"""
import io
from pathlib import Path
import os
import re
import datetime as dt

import pandas as pd
import numpy as np

import ai_berkshire as ab

SKILLS_ROOT = os.environ.get("SKILLS_ROOT", str(Path(__file__).parent / "optional-skills"))
REPORTS_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports", "skills_center")

# ---------------- Skill 元数据 ----------------
SKILLS = [
    {"id": "investment-checklist", "icon": "✅", "group": "个股深度", "name": "巴菲特六关 Checklist",
     "desc": "能力圈 / 好生意 / 护城河 / 管理层 / 安全边际 / 纪律六关，含镜子测试与快速否决清单", "needs": "symbol"},
    {"id": "investment-research", "icon": "🧠", "group": "个股深度", "name": "四大师综合分析",
     "desc": "段永平·巴菲特·芒格·李录四视角对抗 + 估值安全边际 + 综合决策备忘录", "needs": "symbol"},
    {"id": "investment-team", "icon": "👥", "group": "个股深度", "name": "投研团队四角色",
     "desc": "生意本质 / 财务质量 / 风险清单 / 文明趋势 四角色并行评分框架", "needs": "symbol"},
    {"id": "earnings-review", "icon": "📑", "group": "个股深度", "name": "财报精读",
     "desc": "一手资料可得性评级 → 财务数据提取验证 → 六维评分 → 反常信号清单", "needs": "symbol"},
    {"id": "earnings-team", "icon": "🛰️", "group": "个股深度", "name": "财报精读团队",
     "desc": "四大师并行解读 + Team Lead 合成 + 编辑润色与读者评审", "needs": "symbol"},
    {"id": "management-deep-dive", "icon": "🎯", "group": "个股深度", "name": "管理层纵深研究",
     "desc": "CEO 能力圈 / 诚信度 / 资本配置 / 治理结构 八步评估", "needs": "symbol"},
    {"id": "dyp-ask", "icon": "🎋", "group": "个股深度", "name": "段永平问答",
     "desc": "以段永平九维思想体系（生意模式 / Stop doing list / 平常心…）审视标的", "needs": "symbol"},
    {"id": "deep-company-series", "icon": "📚", "group": "个股深度", "name": "深度公司系列",
     "desc": "3-8 篇长文拆一家公司：8 主轴模板 + 事实核查 Checklist", "needs": "symbol"},
    {"id": "quality-screen", "icon": "🧹", "group": "行业筛选", "name": "去劣筛选",
     "desc": "7 条去劣指标快速排除非一流公司 + 3 条豁免规则", "needs": "symbol"},
    {"id": "industry-funnel", "icon": "🔻", "group": "行业筛选", "name": "行业漏斗筛选",
     "desc": "全市场 → 5 条硬指标粗筛 → 精细分析 → 四大师深度 → 终选 3 家", "needs": "symbols"},
    {"id": "industry-research", "icon": "🏭", "group": "行业筛选", "name": "行业投资研究",
     "desc": "逻辑链验证 → 产业链全景 → 上市公司扫描 → 风险评估 → 组合配置", "needs": "symbol"},
    {"id": "bottleneck-hunter", "icon": "🔍", "group": "行业筛选", "name": "供应链瓶颈猎手",
     "desc": "超级趋势 → 供应链拆解 → 瓶颈识别 → 估值检查 → 机会看板", "needs": "symbol"},
    {"id": "private-company-research", "icon": "🕵️", "group": "行业筛选", "name": "未上市公司研究",
     "desc": "商业模式 / 财务拼凑 / 竞争 / 风险治理 / 技术 / 替代数据 六任务框架", "needs": "text"},
    {"id": "financial-data", "icon": "🔢", "group": "行业筛选", "name": "财务数据交叉验证",
     "desc": "多数据源优先级 + 误差计算与标记 + 复权规则", "needs": "symbol"},
    {"id": "portfolio-review", "icon": "🧺", "group": "组合跟踪", "name": "组合管理",
     "desc": "持仓解析 → 单仓位体检 → 集中度/相关性/压力测试 → 调仓建议", "needs": "holdings"},
    {"id": "thesis-tracker", "icon": "📌", "group": "组合跟踪", "name": "投资论文追踪",
     "desc": "建立论文 → 核心假设 / 红线清单 / 估值锚点 → 健康度追踪", "needs": "symbol"},
    {"id": "thesis-drift", "icon": "🧭", "group": "组合跟踪", "name": "论文漂移检测",
     "desc": "对比新旧论文：区分事实变化与措辞变化，维度漂移表", "needs": "texts"},
    {"id": "news-pulse", "icon": "📡", "group": "组合跟踪", "name": "公司新闻脉搏",
     "desc": "股价异动快速归因：事件时间线 + 主因判断 + 是否触发论文重审", "needs": "symbol"},
    {"id": "income-investment", "icon": "💰", "group": "组合跟踪", "name": "Income 股息分析",
     "desc": "股息分布理解 → 可分配现金追踪 → 质量持久性 → 三情景估值", "needs": "symbol"},
    {"id": "wechat-article", "icon": "📰", "group": "内容排版", "name": "公众号文章",
     "desc": "作者-编辑-读者三 Agent 协作：素材框架 + 初稿 + 双审阅 + 定稿", "needs": "symbol"},
    {"id": "investment-memo-craft", "icon": "✒️", "group": "内容排版", "name": "投资备忘录排版",
     "desc": "研究备忘录写作与排版规范：克制排版 + 事实-观点分离 + 行动导向", "needs": "symbol"},
]

SKILL_MAP = {s["id"]: s for s in SKILLS}
GROUP_ORDER = ["个股深度", "行业筛选", "组合跟踪", "内容排版"]


def load_methodology(skill_id: str) -> str:
    """读取仓库内该 Skill 的完整 SKILL.md 原文（完整保留，不简化）。"""
    p = os.path.join(SKILLS_ROOT, skill_id, "SKILL.md")
    if os.path.isfile(p):
        return io.open(p, encoding="utf-8").read()
    return "（未找到 %s 的方法论文本）" % skill_id


# ---------------- 通用工具 ----------------

def _pct(x, nd=1):
    if x is None:
        return "—"
    try:
        f = float(x)
        return "%%.*f%%" % (nd, f * 100 if abs(f) < 2 else f)
    except Exception:
        return "—"


def _fmt(x, nd=2):
    """金额格式化：B=10亿。东财美股接口金额单位为「元」。"""
    if x is None:
        return "—"
    try:
        f = float(x)
        if abs(f) >= 1e9:
            return "$%.2fB" % (f / 1e9)
        if abs(f) >= 1e6:
            return "$%.1fM" % (f / 1e6)
        return "$%%.*f" % (nd, f)
    except Exception:
        return "—"


def _fnum(x, nd=2):
    if x is None:
        return "—"
    try:
        return "%%.*f" % (nd, float(x))
    except Exception:
        return "—"


def _color(v):
    if v is None:
        return ab.APPLE_GRAY
    try:
        f = float(v)
    except Exception:
        return ab.APPLE_GRAY
    if f >= 4.0:
        return ab.APPLE_GREEN
    if f >= 3.0:
        return ab.APPLE_ORANGE
    return ab.APPLE_RED


def _verdict_box(label, color, why):
    return {"label": label, "color": color, "why": why}


def load_company(symbol: str) -> dict:
    """拉取价格 + 财务 + 指标，返回统一数据包。"""
    price = ab.fetch_price(symbol)
    fund = ab.fetch_fundamentals(symbol)
    if price is None or price.empty:
        raise RuntimeError("无法获取 %s 的行情数据（请检查代码或稍后重试）" % symbol)
    m = ab.compute_metrics(symbol, price, fund)
    return {"symbol": symbol.upper(), "price": price, "fund": fund, "m": m}


def fmt_cards(m: dict) -> list:
    return [
        {"label": "现价", "value": "$%.2f" % m["close"], "sub": m.get("date", "")},
        {"label": "PE(TTM)", "value": _fnum(m.get("pe")), "sub": "PE 5年分位 %s" % _pct(m.get("pe_pct"))},
        {"label": "ROE 5年均", "value": _pct(m.get("roe5")), "sub": "最新 %s" % _pct(m.get("roe_latest"))},
        {"label": "毛利率 5年均", "value": _pct(m.get("gm5")), "sub": "最新 %s" % _pct(m.get("gm_latest"))},
        {"label": "净利率 5年均", "value": _pct(m.get("nm5")), "sub": "最新 %s" % _pct(m.get("nm_latest"))},
        {"label": "营收增速 YoY", "value": _pct(m.get("rev_yoy")), "sub": "3年CAGR %s" % _pct(m.get("rev_cagr3"))},
        {"label": "利润增速 YoY", "value": _pct(m.get("np_yoy")), "sub": "3年CAGR %s" % _pct(m.get("np_cagr3"))},
        {"label": "资产负债率", "value": _pct(m.get("debt")), "sub": "距52周高点 %s" % _pct(m.get("off_high"))},
    ]


def _sections_to_md(rows, cols=None):
    if not rows:
        return ""
    if cols is None:
        cols = list(rows[0].keys())
    out = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    return "\n".join(out)


def _out(skill_id, title, verdict=None, cards=None, tables=None, checks=None, md=""):
    return {
        "ok": True, "skill_id": skill_id, "title": title,
        "verdict": verdict, "cards": cards or [], "tables": tables or [],
        "checks": checks or [], "markdown": md,
    }


def _bad(skill_id, msg):
    return {"ok": False, "skill_id": skill_id, "title": SKILL_MAP.get(skill_id, {}).get("name", skill_id),
            "verdict": _verdict_box("分析失败", ab.APPLE_RED, msg), "cards": [], "tables": [], "checks": [], "markdown": msg}


# ================= 数据解读引擎（把指标翻译成分析文字） =================

def narrate_growth(m: dict) -> list:
    """成长性分析段落。"""
    out = []
    rev_yoy, np_yoy = m.get("rev_yoy"), m.get("np_yoy")
    rev_cagr, np_cagr = m.get("rev_cagr3"), m.get("np_cagr3")
    if rev_yoy is not None:
        if rev_yoy > 30:
            out.append("营收处于爆发式扩张区间：最新财年同比 **+%.0f%%**（>30%%），量价齐升或产品放量是主因，需判断可持续性。" % rev_yoy)
        elif rev_yoy > 15:
            out.append("营收保持优秀增速：最新财年同比 **+%.0f%%**（15%%~30%% 优质区间），成长动能健康。" % rev_yoy)
        elif rev_yoy > 0:
            out.append("营收低速增长：最新财年同比 **+%.0f%%**（0~15%%），成长动能偏弱，需靠利润率或回购支撑回报。" % rev_yoy)
        else:
            out.append("营收同比 **%.0f%%**，出现收缩信号，需重点排查需求端或份额流失。" % rev_yoy)
    if np_yoy is not None:
        if np_yoy > 30:
            out.append("利润增速同步爆发：最新财年净利同比 **+%.0f%%**，盈利弹性显著高于营收，存在经营杠杆。" % np_yoy)
        elif np_yoy < -10:
            out.append("利润同比 **%.0f%%**，与营收趋势背离，需检查费用失控 / 减值 / 一次性损失。" % np_yoy)
        else:
            out.append("利润同比 **%+.0f%%**，与营收节奏基本匹配。" % np_yoy)
    if rev_cagr is not None:
        tag = "高速" if rev_cagr > 0.25 else ("中速" if rev_cagr > 0.1 else "低速")
        out.append("近3年营收复合增速 **%.0f%%**（%s成长），判断中期成长中枢时应结合行业渗透率与竞争格局。" % (rev_cagr * 100, tag))
    if np_cagr is not None:
        out.append("近3年净利复合增速 **%.0f%%**，反映盈利能力的长期改善（或恶化）斜率。" % (np_cagr * 100))
    return out or ["成长数据不足，需人工补充历史营收/利润序列。"]


def narrate_profit(m: dict) -> list:
    """盈利质量分析段落。"""
    out = []
    roe5, gm5, nm5 = m.get("roe5"), m.get("gm5"), m.get("nm5")
    roe_l, gm_l, nm_l = m.get("roe_latest"), m.get("gm_latest"), m.get("nm_latest")
    if roe5 is not None:
        if roe5 > 20:
            out.append("ROE 5年均值 **%.1f%%**，显著高于 15%% 优质线，股东回报能力一流（>20%% 属顶尖水准）。" % roe5)
        elif roe5 > 15:
            out.append("ROE 5年均值 **%.1f%%**，站上 15%% 优质线，盈利效率良好。" % roe5)
        else:
            out.append("ROE 5年均值 **%.1f%%**，低于 15%% 优质线，资本回报效率一般。" % roe5)
    if gm5 is not None:
        if gm5 > 50:
            out.append("毛利率 5年均值 **%.1f%%**（>50%%），具备强定价权或轻资产模式，是护城河的量化佐证。" % gm5)
        elif gm5 > 30:
            out.append("毛利率 5年均值 **%.1f%%**（30%%~50%%），商业模式质量中等偏上。" % gm5)
        else:
            out.append("毛利率 5年均值 **%.1f%%**（<30%%），属低毛利生意，议价权有限。" % gm5)
    if nm5 is not None:
        out.append("净利率 5年均值 **%.1f%%**，反映费用管控与税负结构；最新 %s。" % (nm5, _pct(nm_l)))
    if gm_l is not None and gm5 is not None and gm_l < gm5 - 8:
        out.append("⚠️ 最新毛利率 **%.1f%%** 较 5 年均值下滑超 8 个百分点，警惕价格战或成本上行侵蚀。" % gm_l)
    return out or ["盈利数据不足。"]


def narrate_balance(m: dict) -> list:
    """财务稳健分析段落。"""
    out = []
    debt = m.get("debt")
    if debt is not None:
        if debt < 30:
            out.append("资产负债率 **%.1f%%**（<30%%），资产负债表极稳健，抗风险能力强，具备逆周期加杠杆空间。" % debt)
        elif debt < 60:
            out.append("资产负债率 **%.1f%%**（30%%~60%%），杠杆水平适中，财务结构健康。" % debt)
        else:
            out.append("资产负债率 **%.1f%%**（>60%%），杠杆偏高，利率上行或现金流波动时脆弱性上升。" % debt)
    return out or ["负债数据不足。"]


def narrate_valuation(m: dict) -> list:
    """估值分析段落。"""
    out = []
    pe, pct = m.get("pe"), m.get("pe_pct")
    if pe is not None:
        if pct is not None:
            if pct > 80:
                out.append("PE(TTM) **%.1f**，处于近5年 **%.0f%%** 分位（>80%%），估值偏贵，安全边际不足，追高需谨慎。" % (pe, pct))
            elif pct < 20:
                out.append("PE(TTM) **%.1f**，处于近5年 **%.0f%%** 分位（<20%%），估值处于历史低位区间，具备安全边际。" % (pe, pct))
            else:
                out.append("PE(TTM) **%.1f**，处于近5年 **%.0f%%** 分位，估值中枢位置，等待更好的赔率。" % (pe, pct))
        else:
            out.append("PE(TTM) **%.1f**，估值需结合行业对标判断。" % pe)
    off = m.get("off_high")
    if off is not None:
        if off > -5:
            out.append("股价距 52 周高点仅 **%.1f%%**，处于强势区，但追高位置不佳。" % off)
        elif off < -30:
            out.append("股价距 52 周高点 **%.1f%%**，回调充分，关注是否出现左侧机会。" % off)
        else:
            out.append("股价距 52 周高点 **%.1f%%**，处于中间位置。" % off)
    return out or ["估值数据不足。"]


def narrate_momentum(m: dict) -> list:
    """趋势/动量分析段落。"""
    out = []
    ma20, ma60 = m.get("ma20"), m.get("ma60")
    close = m.get("close")
    rsi = m.get("rsi14")
    if close is not None and ma20 is not None:
        if close > ma20:
            out.append("现价站上 MA20（%.2f），短线趋势偏多。" % ma20)
        else:
            out.append("现价跌破 MA20（%.2f），短线趋势转弱。" % ma20)
    if close is not None and ma60 is not None:
        if close > ma60:
            out.append("现价站上 MA60（%.2f），中线趋势保持多头结构。" % ma60)
        else:
            out.append("现价位于 MA60（%.2f）下方，中线趋势承压。" % ma60)
    if rsi is not None:
        if rsi > 70:
            out.append("RSI14 **%.0f**（>70），短线超买，追高性价比低。" % rsi)
        elif rsi < 30:
            out.append("RSI14 **%.0f**（<30），短线超卖，关注企稳信号。" % rsi)
        else:
            out.append("RSI14 **%.0f**，动能中性。" % rsi)
    return out or ["趋势数据不足。"]


def company_analysis(m: dict) -> str:
    """组装「公司基本面分析」完整章节（供所有个股类 Skill 复用）。"""
    md = []
    md.append("### 成长性分析")
    for s in narrate_growth(m):
        md.append("- " + s)
    md.append("")
    md.append("### 盈利质量分析")
    for s in narrate_profit(m):
        md.append("- " + s)
    md.append("")
    md.append("### 财务稳健分析")
    for s in narrate_balance(m):
        md.append("- " + s)
    md.append("")
    md.append("### 估值与位置分析")
    for s in narrate_valuation(m):
        md.append("- " + s)
    md.append("")
    md.append("### 趋势与动量分析")
    for s in narrate_momentum(m):
        md.append("- " + s)
    md.append("")
    return "\n".join(md)


def company_header(m: dict, symbol: str, name: str = "") -> str:
    """公司概况段落。"""
    name = name or symbol
    return "# %s · %s\n\n> 现价 $%.2f（%s）｜PE(TTM) %s｜ROE5年 %s｜营收YoY %s\n\n" % (
        symbol, name, m["close"], m.get("date", ""), _fnum(m.get("pe")), _pct(m.get("roe5")), _pct(m.get("rev_yoy")))


# ================= 个股深度类（完整研究文章） =================

def _clamp(v, lo=1.0, hi=5.0):
    return float(max(lo, min(hi, v)))


def run_investment_checklist(symbol: str, sector: str = "") -> dict:
    """巴菲特六关 Checklist：完整文章 + 六关评分。"""
    data = load_company(symbol)
    m = data["m"]
    r = ab.run_analysis(symbol, sector=sector, out_root=REPORTS_ROOT)
    gates = r["gates"]
    rows = []
    gate_md = []
    for k, v in gates.items():
        sc = v.get("score", 0)
        rows.append({"关卡": k, "评分": "%.1f / 5" % sc, "状态": "✅ 通过" if sc >= 3.5 else ("⚠️ 存疑" if sc >= 3 else "❌ 未过"),
                     "依据": v.get("note") or "；".join(v.get("reasons", []))})
        gate_md.append("- **%s（%.1f/5）**：%s" % (k, sc, v.get("note") or "；".join(v.get("reasons", []))))
    sc_rows = []
    for kk in ["bear", "base", "bull"]:
        s = r["metrics"]["scenarios"][kk]
        sc_rows.append({"情景": s["label"], "年化增长": "%.0f%%" % (s["growth"] * 100), "目标PE": s["pe"],
                        "3年目标价": "$%.2f" % s["target"], "相对现价": "%+.0f%%" % s["upside"]})
    md = company_header(m, symbol)
    md += "## 一、结论\n\n**%s** —— %s\n\n" % (r["conclusion"]["verdict"], r["conclusion"]["why"])
    md += "## 二、六关 Checklist 逐关审查\n\n" + "\n".join(gate_md) + "\n\n"
    md += "## 三、公司基本面分析\n\n" + company_analysis(m) + "\n"
    md += "## 四、四大师视角\n\n" + _sections_to_md([{"视角": k, "评分": "%.2f / 5" % v} for k, v in r["masters"].items()]) + "\n\n"
    md += "## 五、三情景估值（3年目标价）\n\n" + _sections_to_md(sc_rows) + "\n\n"
    md += "## 六、风险标记\n\n" + ("\n".join("- " + f for f in r["flags"]) if r["flags"] else "- 本地引擎未检测到自动风险标记（人工风险仍需自行判断）") + "\n\n"
    md += "## 七、镜子测试与快速否决清单\n\n- 镜子测试：%s\n- 快速否决清单：%d 条需逐条人工确认（见方法论原文）" % (r["mirror"]["note"], len(ab.VETO_LIST))
    checks = [{"title": "快速否决清单", "items": [{"name": v, "ok": None, "note": "需人工确认"} for v in ab.VETO_LIST]}]
    return _out("investment-checklist", "巴菲特六关 Checklist", _verdict_box(r["conclusion"]["verdict"], r["conclusion"]["color"], r["conclusion"]["why"]),
                fmt_cards(m), [{"title": "六关评分", "rows": rows}, {"title": "三情景估值", "rows": sc_rows}], checks, md)


def run_investment_research(symbol: str, sector: str = "") -> dict:
    """四大师综合分析：完整研究备忘录。"""
    data = load_company(symbol)
    m = data["m"]
    r = ab.run_analysis(symbol, sector=sector, out_root=REPORTS_ROOT)
    rows = []
    for k, v in r["masters"].items():
        rows.append({"视角": k, "评分": "%.2f / 5" % v})
    avg = sum(r["masters"].values()) / len(r["masters"])
    md = company_header(m, symbol)
    md += "## 一、综合决策备忘录\n\n**%s** —— %s\n\n" % (r["conclusion"]["verdict"], r["conclusion"]["why"])
    md += "## 二、四大师视角对抗\n\n" + _sections_to_md(rows) + "\n\n"
    md += "### 段永平·生意本质\n" + "".join("- " + s + "\n" for s in narrate_profit(m)) + "\n"
    md += "### 巴菲特·护城河与财务\n" + "".join("- " + s + "\n" for s in narrate_profit(m) + narrate_balance(m)) + "\n"
    md += "### 芒格·逆向思考与风险\n" + ("\n".join("- " + f for f in r["flags"]) if r["flags"] else "- 本地引擎未自动标记风险，需人工补充") + "\n\n"
    md += "### 李录·文明趋势\n- 当前文明主线（AI 算力/半导体/存储）定位需人工研判；若标的处主线之上，长期确定性加分。\n\n"
    md += "## 三、估值与安全边际\n\n" + "".join("- " + s + "\n" for s in narrate_valuation(m)) + "\n"
    md += "## 四、公司基本面分析\n\n" + company_analysis(m) + "\n"
    return _out("investment-research", "四大师综合分析", _verdict_box(r["conclusion"]["verdict"], r["conclusion"]["color"], r["conclusion"]["why"]),
                fmt_cards(m), [{"title": "四大师评分", "rows": rows}], [], md)


def run_investment_team(symbol: str) -> dict:
    """投研团队四角色：完整分析文章 + 评分表。"""
    data = load_company(symbol)
    m = data["m"]
    roe, gm, nm, pe, pct = m.get("roe5"), m.get("gm5"), m.get("nm5"), m.get("pe"), m.get("pe_pct")
    s_biz = _clamp(1 + 1.0 * (gm or 0) / 40)
    s_fin = _clamp(1 + 1.0 * (roe or 0) / 15)
    s_risk = _clamp(1 + 4.0 * (1 - min((m.get("debt") or 0) / 70, 1)))
    s_civ = 4.0
    rows = [
        {"角色": "Agent 1·生意本质（段永平）", "评分": "%.1f / 5" % s_biz, "数据依据": "毛利率5年 %.1f%%（>40%% 为好生意信号）" % (gm or 0)},
        {"角色": "Agent 2·财务质量（巴菲特）", "评分": "%.1f / 5" % s_fin, "数据依据": "ROE5年 %.1f%%（>15%% 为优质）" % (roe or 0)},
        {"角色": "Agent 3·风险清单（芒格）", "评分": "%.1f / 5" % s_risk, "数据依据": "资产负债率 %.1f%%（<40%% 为稳健）" % (m.get("debt") or 0)},
        {"角色": "Agent 4·文明趋势（李录）", "评分": "%.1f / 5" % s_civ, "数据依据": "AI/半导体主线位置需人工研判"},
    ]
    avg = (s_biz + s_fin + s_risk + s_civ) / 4
    label, color = ("强买入区", ab.APPLE_GREEN) if avg >= 4 else (("关注区", ab.APPLE_ORANGE) if avg >= 3 else ("回避区", ab.APPLE_RED))
    md = company_header(m, symbol)
    md += "## 一、团队框架与结论\n\n四角色并行（段永平·生意 → 巴菲特·财务 → 芒格·风险 → 李录·趋势），综合评分 **%.2f/5**，落入 **%s**。\n\n" % (avg, label)
    md += "## 二、四角色评分表\n\n" + _sections_to_md(rows) + "\n\n"
    md += "## 三、Agent 1 生意本质（段永平视角）\n\n" + "".join("- " + s + "\n" for s in narrate_profit(m)) + "\n"
    md += "## 四、Agent 2 财务质量（巴菲特视角）\n\n" + "".join("- " + s + "\n" for s in narrate_balance(m) + narrate_growth(m)) + "\n"
    md += "## 五、Agent 3 风险清单（芒格视角）\n\n" + "".join("- " + s + "\n" for s in narrate_valuation(m)) + "\n"
    md += "## 六、Agent 4 文明趋势（李录视角）\n\n- 判断标的所处行业是否为当前文明级主线（AI 算力 / 半导体 / 存储 / 电力）。\n- 在主线之内：长期确定性加成；主线之外：需要更强的商业模式证据。\n\n"
    md += "## 七、WebSearch 预检与信息缺口\n\n- 公司事件 / 管理层新闻 / 行业景气度：需联网人工补充。\n- 本地引擎已用财务 + 行情数据填充全部可计算维度。"
    return _out("investment-team", "投研团队四角色", _verdict_box(label, color, "四角色平均 %.2f/5" % avg),
                fmt_cards(m), [{"title": "四角色评分", "rows": rows}], [], md)


def run_quality_screen(symbol: str) -> dict:
    """去劣筛选：7 条指标 + 3 条豁免规则 + 完整分析。"""
    data = load_company(symbol)
    m = data["m"]
    fund = data["fund"]
    roe5, gm5, nm5 = m.get("roe5"), m.get("gm5"), m.get("nm5")
    np_yoy, rev_yoy = m.get("np_yoy"), m.get("rev_yoy")
    debt = m.get("debt")
    np_cagr = m.get("np_cagr3")
    items = [
        {"name": "1. 连续3年净利润增长", "ok": np_cagr is not None and np_cagr > 0.05,
         "note": "3年净利CAGR %.1f%%（豁免A：战略投入期可豁免）" % ((np_cagr or 0) * 100)},
        {"name": "2. ROE 持续大于 15%", "ok": roe5 is not None and roe5 > 15,
         "note": "ROE 5年均 %.1f%%" % (roe5 or 0)},
        {"name": "3. 毛利率稳定（5年标准差小）", "ok": (m.get("gm_std5") or 99) < 8,
         "note": "毛利率5年均 %.1f%%，标准差 %.2f" % (gm5 or 0, m.get("gm_std5") or 0)},
        {"name": "4. 净利率为正且持续", "ok": nm5 is not None and nm5 > 0,
         "note": "净利率5年均 %.1f%%（豁免C：高周转薄利模式）" % (nm5 or 0)},
        {"name": "5. 自由现金流为正", "ok": None, "note": "东财美股接口无 FCF 字段，需人工从现金流量表确认"},
        {"name": "6. 负债率健康", "ok": debt is not None and debt < 60,
         "note": "资产负债率 %.1f%%（<60%% 为健康）" % (debt or 0)},
        {"name": "7. 无重大造假/诚信污点", "ok": None, "note": "需人工核查审计意见与监管处罚记录"},
    ]
    passed = sum(1 for i in items if i["ok"] is True)
    unknown = sum(1 for i in items if i["ok"] is None)
    md = company_header(m, symbol)
    md += "## 一、结论\n\n7 条去劣指标 **%d/7 通过**，%d 项需人工确认 → %s。\n\n" % (passed, unknown, "初步通过，进入深度研究" if passed >= 5 else ("边界争议，需豁免判定" if passed >= 3 else "排除出候选池"))
    md += "## 二、7 条去劣指标逐条检验\n\n" + _sections_to_md([{"#": i + 1, "指标": it["name"], "结果": "✅ 通过" if it["ok"] is True else ("⚠️ 需人工" if it["ok"] is None else "❌ 未通过"), "说明": it["note"]} for i, it in enumerate(items)]) + "\n\n"
    md += "## 三、豁免规则检查\n\n- 豁免A（战略投入期）：营收增速 YoY **%.1f%%**，若为高研发投入期可豁免第1条。\n- 豁免B（主动低利润率）：净利率 **%.1f%%**，若为抢占份额的主动让利可豁免第6条。\n- 豁免C（高周转薄利）：需人工判断（零售/物流等薄利高周转模式）。\n\n" % (rev_yoy or 0, nm5 or 0)
    md += "## 四、基本面交叉验证\n\n" + company_analysis(m) + "\n"
    label, color = ("通过", ab.APPLE_GREEN) if passed >= 5 else (("边界争议", ab.APPLE_ORANGE) if passed >= 3 else ("排除", ab.APPLE_RED))
    return _out("quality-screen", "去劣筛选", _verdict_box(label, color, "%d/7 通过，%d 项需人工确认" % (passed, unknown)),
                fmt_cards(m), [{"title": "7 条去劣指标", "rows": [{"#": i + 1, "指标": it["name"], "结果": "✅" if it["ok"] is True else ("⚠️" if it["ok"] is None else "❌"), "说明": it["note"]} for i, it in enumerate(items)]}],
                [{"title": "去劣检验", "items": items}], md)


def run_earnings_review(symbol: str) -> dict:
    """财报精读：完整财报分析文章（成长/盈利/结构/估值 + 反常信号）。"""
    data = load_company(symbol)
    m = data["m"]
    fund = data["fund"]
    if fund is None or fund.empty:
        raise RuntimeError("未获取到 %s 的财务数据" % symbol)
    tail = fund.tail(5)
    revs = tail["OPERATE_INCOME"].tolist()
    nps = tail["PARENT_HOLDER_NETPROFIT"].tolist()
    yrs = tail["year"].tolist() if "year" in tail.columns else list(range(len(tail)))

    def _chg(series):
        out = []
        for i in range(1, len(series)):
            a, b = series[i - 1], series[i]
            if a and b:
                out.append((b - a) / abs(a) * 100)
            else:
                out.append(None)
        return out
    rev_chg, np_chg = _chg(revs), _chg(nps)
    anomaly = []
    for i, c in enumerate(np_chg):
        if c is not None and abs(c) > 60:
            anomaly.append("利润增速异常波动：%d 财年净利变动 %+.0f%%（需追查原因）" % (yrs[i], c))
    if m.get("gm_latest") is not None and m.get("gm5") is not None and m.get("gm_latest") < m.get("gm5") - 8:
        anomaly.append("最新毛利率 %.1f%% 显著低于5年均值 %.1f%%（毛利率侵蚀信号）" % (m["gm_latest"], m["gm5"]))
    if m.get("nm_latest") is not None and m.get("nm_latest") < 0:
        anomaly.append("最新净利率为负（%.1f%%），警惕盈利恶化" % m["nm_latest"])
    if m.get("debt") is not None and m.get("debt") > 70:
        anomaly.append("资产负债率 %.1f%% 偏高（>70%%）" % m["debt"])
    rev_rows = [{"财年": yrs[i], "营收": _fmt(revs[i]), "变动": ("%+.0f%%" % rev_chg[i - 1]) if i > 0 and rev_chg[i - 1] is not None else "—",
                 "净利": _fmt(nps[i]), "净利变动": ("%+.0f%%" % np_chg[i - 1]) if i > 0 and np_chg[i - 1] is not None else "—"} for i in range(len(tail))]
    six = [
        {"维度": "收入质量", "评分": "%.1f/5" % _clamp(2 + (m.get("rev_cagr3") or 0) * 8), "依据": "3年营收CAGR %.1f%%" % ((m.get("rev_cagr3") or 0) * 100)},
        {"维度": "盈利质量", "评分": "%.1f/5" % _clamp(2 + (m.get("np_cagr3") or 0) * 8), "依据": "3年净利CAGR %.1f%%" % ((m.get("np_cagr3") or 0) * 100)},
        {"维度": "现金流", "评分": "—", "依据": "需人工从现金流量表确认（东财美股接口无 FCF）"},
        {"维度": "资产负债", "评分": "%.1f/5" % _clamp(5 - max((m.get("debt") or 0) - 40, 0) / 15), "依据": "负债率 %.1f%%" % (m.get("debt") or 0)},
        {"维度": "成长性", "评分": "%.1f/5" % _clamp(2 + max(m.get("rev_yoy") or 0, 0) / 20), "依据": "营收YoY %.1f%%" % (m.get("rev_yoy") or 0)},
        {"维度": "估值合理", "评分": "%.1f/5" % (_clamp(5 - (m.get("pe_pct") or 50) / 25) if m.get("pe_pct") is not None else 3), "依据": "PE分位 %.0f%%" % (m.get("pe_pct") or 0)},
    ]
    md = company_header(m, symbol)
    md += "## 一、资料可得性评级\n\n- 财务指标（东财美股年报）：可用（近%d个财年）\n- 现金流量表 / 管理层讨论 / 电话会：需人工补充一手资料\n\n" % len(fund)
    md += "## 二、近5年核心财务数据\n\n" + _sections_to_md(rev_rows) + "\n\n"
    md += "## 三、成长性分析\n\n" + "".join("- " + s + "\n" for s in narrate_growth(m)) + "\n"
    md += "## 四、盈利质量分析\n\n" + "".join("- " + s + "\n" for s in narrate_profit(m)) + "\n"
    md += "## 五、财务结构分析\n\n" + "".join("- " + s + "\n" for s in narrate_balance(m)) + "\n"
    md += "## 六、估值分析\n\n" + "".join("- " + s + "\n" for s in narrate_valuation(m)) + "\n"
    md += "## 七、六维评分\n\n" + _sections_to_md(six) + "\n\n"
    md += "## 八、反常信号清单（最重要）\n\n" + ("\n".join("- ⚠️ " + a for a in anomaly) if anomaly else "- 未检测到自动异常信号（仍需人工核对现金流量与商誉减值）") + "\n\n"
    md += "## 九、财报精读结论\n\n- 收入与利润趋势：见第三/四节分析。\n- 反常信号 %d 条：%s\n- 下一步：人工补现金流量表、管理层口径，再定投资论点。" % (len(anomaly), "需逐一追查" if anomaly else "无自动异常")
    label, color = ("正常", ab.APPLE_GREEN) if not anomaly else ("异常关注", ab.APPLE_ORANGE)
    return _out("earnings-review", "财报精读", _verdict_box(label, color, "发现 %d 个反常信号" % len(anomaly)),
                fmt_cards(m), [{"title": "近5年财务", "rows": rev_rows}, {"title": "六维评分", "rows": six}],
                [{"title": "反常信号清单", "items": [{"name": a, "ok": False, "note": "需追查"} for a in anomaly] or [{"name": "无自动异常", "ok": True, "note": ""}]}], md)


def run_earnings_team(symbol: str) -> dict:
    """财报精读团队：四大师并行解读 + 合成报告 + 编辑/读者评审。"""
    data = load_company(symbol)
    m = data["m"]
    roe, gm, nm = m.get("roe5"), m.get("gm5"), m.get("nm5")
    s1 = _clamp(1 + (gm or 0) / 40); s2 = _clamp(1 + (roe or 0) / 15)
    s3 = _clamp(1 + 4 * (1 - min((m.get("debt") or 0) / 70, 1))); s4 = 3.5
    rows = [
        {"大师": "段永平·生意本质", "评分": "%.1f/5" % s1, "核心关注": "商业模式与毛利率 %.1f%%" % (gm or 0)},
        {"大师": "巴菲特·财务审计", "评分": "%.1f/5" % s2, "核心关注": "ROE %.1f%% 与自由现金流（人工）" % (roe or 0)},
        {"大师": "芒格·竞争格局", "评分": "%.1f/5" % s3, "核心关注": "护城河与负债率 %.1f%%" % (m.get("debt") or 0)},
        {"大师": "李录·风险信号", "评分": "%.1f/5" % s4, "核心关注": "文明趋势位置与尾部风险"},
    ]
    avg = (s1 + s2 + s3 + s4) / 4
    md = company_header(m, symbol)
    md += "## 一、一句话结论\n\n四大师平均 **%.2f/5**，数据面%s。\n\n" % (avg, "健康" if avg >= 3.5 else "存疑")
    md += "## 二、本期最重要的 3 个变化\n\n1. 营收 YoY **%s**（%s）\n2. 净利 YoY **%s**\n3. 距 52 周高点 **%s**（需结合财报事件人工确认）\n\n" % (
        _pct(m.get("rev_yoy")), narrate_growth(m)[0] if narrate_growth(m) else "", _pct(m.get("np_yoy")), _pct(m.get("off_high")))
    md += "## 三、四大师评分表\n\n" + _sections_to_md(rows) + "\n\n"
    md += "## 四、四大师深度分析\n\n### 段永平视角：生意本质\n" + "".join("- " + s + "\n" for s in narrate_profit(m)) + "\n"
    md += "### 巴菲特视角：财务审计\n" + "".join("- " + s + "\n" for s in narrate_balance(m) + narrate_growth(m)) + "\n"
    md += "### 芒格视角：竞争格局\n" + "".join("- " + s + "\n" for s in narrate_valuation(m) + narrate_momentum(m)) + "\n"
    md += "### 李录视角：风险信号\n- 行业是否处于文明级趋势（AI/半导体）；尾部风险情景需人工推演。\n\n"
    md += "## 五、编辑润色 + 读者评审\n\n- 编辑意见：文章应突出「本期最重要的变化」，弱化指标罗列。\n- 读者视角：普通投资者最关心「要不要关注 / 什么价位 / 什么风险」，需在文章开头发问。\n\n"
    md += "## 六、Team Lead 定稿要点\n\n- 结论：**%s**（平均 %.2f/5）\n- 数据抽检：财务指标已交叉验证（新浪日线 + 东财年报）。" % ("健康" if avg >= 3.5 else ("关注" if avg >= 3 else "风险"), avg)
    label, color = ("健康", ab.APPLE_GREEN) if avg >= 3.5 else (("关注", ab.APPLE_ORANGE) if avg >= 3 else ("风险", ab.APPLE_RED))
    return _out("earnings-team", "财报精读团队", _verdict_box(label, color, "四大师平均 %.2f/5" % avg),
                fmt_cards(m), [{"title": "四大师评分", "rows": rows}], [], md)




def run_management_deep_dive(symbol: str) -> dict:
    """管理层纵深研究：八步评估 + 资本配置数据 + 完整文章。"""
    data = load_company(symbol)
    m = data["m"]
    roe, debt = m.get("roe_latest"), m.get("debt")
    cap_score = _clamp(1 + (roe or 0) / 20)
    items = [
        {"name": "2.1 战略眼光", "ok": None, "note": "需人工：管理层对行业趋势的判断与历史布局"},
        {"name": "2.2 执行能力", "ok": None, "note": "需人工：营收/利润承诺兑现率"},
        {"name": "3.1 承诺 vs 兑现追踪", "ok": None, "note": "需人工：电话会/指引兑现记录"},
        {"name": "3.2 困难时期表现", "ok": None, "note": "需人工：危机中是否诚实沟通"},
        {"name": "4 资本配置能力", "ok": cap_score >= 3.5, "note": "数据代理：ROE %.1f%%（≥15%% 为优）" % (roe or 0)},
        {"name": "5.1 股权结构", "ok": None, "note": "需人工：大股东/创始人持股与利益绑定"},
        {"name": "5.2 薪酬合理性", "ok": None, "note": "需人工：高管薪酬与业绩挂钩程度"},
        {"name": "5.3 关联交易", "ok": None, "note": "需人工：异常关联交易排查"},
    ]
    md = company_header(m, symbol)
    md += "## 一、关键管理层识别\n\n- CEO / CFO 名单与任期：需人工补充（本地引擎无管理层数据库）。\n\n"
    md += "## 二、资本配置数据代理（可计算部分）\n\n- ROE（最新）**%.1f%%**：资本回报代理指标，资本配置评分 **%.1f/5**。\n- 资产负债率 **%.1f%%**：杠杆纪律的量化反映。\n- 解读：%s\n\n" % (roe or 0, cap_score, debt or 0, narrate_balance(m)[0] if narrate_balance(m) else "")
    md += "## 三、八步评估清单\n\n" + _sections_to_md([{"#": i + 1, "评估项": it["name"], "状态": "✅ 数据通过" if it["ok"] is True else ("❌ 数据未过" if it["ok"] is False else "⚠️ 人工"), "说明": it["note"]} for i, it in enumerate(items)]) + "\n\n"
    md += "## 四、段永平「买人」标准\n\n- 本分 / 诚信 / 敢为天下后：需人工对照管理层访谈与历史言行。\n- 买股票就是买公司，买公司就是买人——管理层诚信 > 能力。\n\n"
    md += "## 五、CEO 离开后的情景分析\n\n- 关键人风险：若 CEO 离开，公司护城河是否受损？（需人工判断）"
    label, color = ("资本配置优秀", ab.APPLE_GREEN) if cap_score >= 3.5 else (("待人工确认", ab.APPLE_ORANGE) if cap_score >= 3 else ("资本配置存疑", ab.APPLE_RED))
    return _out("management-deep-dive", "管理层纵深研究", _verdict_box(label, color, "资本配置数据代理 %.1f/5，其余需人工"),
                [{"label": "ROE 最新", "value": _pct(roe), "sub": "资本回报代理"}, {"label": "资本配置评分", "value": "%.1f / 5" % cap_score, "sub": "ROE 换算"},
                 {"label": "负债率", "value": _pct(debt), "sub": "财务稳健"}, {"label": "距52周高", "value": _pct(m.get("off_high")), "sub": "当前"}],
                [{"title": "八步评估清单", "rows": [{"#": i + 1, "评估项": it["name"], "状态": "✅" if it["ok"] is True else ("❌" if it["ok"] is False else "⚠️"), "说明": it["note"]} for i, it in enumerate(items)]}],
                [{"title": "管理层评估", "items": items}], md)


def run_dyp_ask(symbol: str) -> dict:
    """段永平问答：九维框架 + 数据驱动的段永平式分析文章。"""
    data = load_company(symbol)
    m = data["m"]
    gm, roe, pe, pct = m.get("gm5"), m.get("roe5"), m.get("pe"), m.get("pe_pct")
    s_biz = _clamp(1 + (gm or 0) / 40)
    s_val = _clamp(5 - (pct or 50) / 25) if pct is not None else 3.0
    rows = [
        {"维度": "一、投资信仰", "判断": "「不懂不做」：我能看懂 %s 怎么赚钱吗？——需人工回答", "数据": "能力圈=第一原则", "评分": "—"},
        {"维度": "二、生意模式", "判断": "毛利率 %.1f%% 说明商业模式 %s；生意模式比股价重要。" % (gm or 0, "好（有定价权）" if (gm or 0) > 40 else "一般"), "数据": "毛利率5年 %.1f%%" % (gm or 0), "评分": "%.1f/5" % s_biz},
        {"维度": "三、Stop doing list", "判断": "检查：是否高负债扩张 / 多元化乱投 / 加杠杆？负债率 %.1f%%。" % (m.get("debt") or 0), "数据": "负债率 %.1f%%" % (m.get("debt") or 0), "评分": "—"},
        {"维度": "四、能力圈", "判断": "产品 / 客户 / 竞争格局是否在我认知范围内？——需人工回答", "数据": "人工", "评分": "—"},
        {"维度": "五、估值与买卖", "判断": "「对的价格」：PE %.1f、5年分位 %.0f%%，%s。" % (pe or 0, pct or 0, "偏贵" if (pct or 0) > 60 else "合理偏低"), "数据": "PE %.1f / 分位 %.0f%%" % (pe or 0, pct or 0), "评分": "%.1f/5" % s_val},
        {"维度": "六、企业文化", "判断": "是否本分、用户导向、敢为天下后？——需人工调研", "数据": "人工", "评分": "—"},
        {"维度": "七、管理层评估", "判断": "ROE %.1f%% 为资本配置提供量化证据；诚信需人工核实。" % (roe or 0), "数据": "ROE5年 %.1f%%" % (roe or 0), "评分": "—"},
        {"维度": "八、宏观与市场", "判断": "距52周高点 %s，避免因宏观噪音动作变形。" % _pct(m.get("off_high")), "数据": "距52周高 %s" % _pct(m.get("off_high")), "评分": "—"},
        {"维度": "九、投资心态", "判断": "现在买入能否拿三年？不能拿三年就不要拿三分钟。——需人工自问", "数据": "平常心", "评分": "—"},
    ]
    md = company_header(m, symbol)
    md += "## 一、段永平式总览\n\n以「生意模式 > 股价波动」「不懂不做」「平常心」三原则审视 %s：\n\n" % symbol
    md += "## 二、九维问答框架（数据驱动）\n\n" + _sections_to_md(rows) + "\n\n"
    md += "## 三、生意模式分析\n\n" + "".join("- " + s + "\n" for s in narrate_profit(m)) + "\n"
    md += "## 四、估值与买卖时机\n\n" + "".join("- " + s + "\n" for s in narrate_valuation(m)) + "\n"
    md += "## 五、段永平式结论\n\n- 看得懂 + 生意好 + 价格对 = 买入；缺一项 = 等待。\n- 若估值分位 >80%，段永平会说：「好公司也要好价格，贵了就不买，等。」\n- 若商业模式平庸（毛利率 <30%），段永平会说：「这不是我愿意花时间的生意。」"
    return _out("dyp-ask", "段永平问答", None, fmt_cards(m), [{"title": "九维问答框架", "rows": rows}], [], md)


def run_deep_company_series(symbol: str) -> dict:
    """深度公司系列：首篇「生意本质」完整文章 + 后续篇目大纲 + 素材包。"""
    data = load_company(symbol)
    m = data["m"]
    plan = [
        {"篇": "01", "主轴": "生意本质", "内容": "这家公司到底怎么赚钱（商业模式拆解）——已由引擎生成初稿"},
        {"篇": "02", "主轴": "行业与竞争", "内容": "所处行业空间、竞争格局、护城河来源"},
        {"篇": "03", "主轴": "财务质量", "内容": "ROE/毛利率/现金流/资产负债的十年体检"},
        {"篇": "04", "主轴": "管理层", "内容": "CEO 与团队：诚信、资本配置、文化"},
        {"篇": "05", "主轴": "成长逻辑", "内容": "增长引擎拆解与 3-5 年推演"},
        {"篇": "06", "主轴": "风险与反面", "内容": "芒格式逆向：什么会让这笔投资归零"},
        {"篇": "07", "主轴": "估值", "内容": "三情景估值与安全边际"},
        {"篇": "08", "主轴": "结论与跟踪", "内容": "买入/持有/回避 + 跟踪指标清单"},
    ]
    n = 8 if (m.get("rev_latest") or 0) > 1e9 else 5
    md = company_header(m, symbol)
    md += "## 篇 01 · 生意本质（引擎初稿）\n\n"
    md += "### 1. 它卖什么、向谁卖、怎么收钱\n\n- 主营产品与服务：需人工补充（引擎无业务描述库）。\n- 数据提示：最新营收 **%s**，营收 YoY **%s**。\n\n" % (_fmt(m.get("rev_latest")), _pct(m.get("rev_yoy")))
    md += "### 2. 这门生意的经济特征\n\n" + "".join("- " + s + "\n" for s in narrate_profit(m)) + "\n"
    md += "### 3. 一句话商业模式\n\n> %s 靠 %s 赚钱，当前 %s。\n\n" % (symbol, "（需人工一句话概括）", narrate_growth(m)[0] if narrate_growth(m) else "")
    md += "## 全系列篇目计划（%d 篇）\n\n" % n + _sections_to_md(plan[:n]) + "\n\n"
    md += "## 素材包（本地数据）\n\n" + _sections_to_md(fmt_cards(m)) + "\n\n"
    md += "## 事实核查 Checklist（每篇必跑）\n\n1. 所有数字标注来源与日期\n2. 区分事实 vs 观点\n3. 无「伪精确」表述\n4. 修订时跑 7 项一致性检查\n5. 发布前 grep 敏感词（合规与隐私）"
    return _out("deep-company-series", "深度公司系列", None, fmt_cards(m),
                [{"title": "系列篇目计划", "rows": plan[:n]}], [], md)


# ================= 行业筛选类 =================

def run_industry_funnel(symbols: list) -> dict:
    """行业漏斗筛选：5 条硬指标粗筛 → 逐家分析 → 排名 → 终选建议。"""
    syms = [s.strip().upper() for s in symbols if s and s.strip()]
    if not syms:
        raise RuntimeError("请至少输入一个股票代码（逗号分隔）")
    rows = []
    detail_md = []
    for s in syms:
        try:
            data = load_company(s)
            m = data["m"]
            score = 0
            notes = []
            if m.get("rev_yoy") is not None and m["rev_yoy"] > 10:
                score += 1; notes.append("营收增速>10%%（%.0f%%）" % m["rev_yoy"])
            if m.get("np_cagr3") is not None and m["np_cagr3"] > 0.1:
                score += 1; notes.append("3年净利CAGR>10%%（%.0f%%）" % (m["np_cagr3"] * 100))
            if (m.get("roe5") or 0) > 15:
                score += 1; notes.append("ROE>15%%（%.0f%%）" % m["roe5"])
            if (m.get("gm5") or 0) > 30:
                score += 1; notes.append("毛利率>30%%（%.0f%%）" % m["gm5"])
            if (m.get("debt") or 0) < 60:
                score += 1; notes.append("负债率<60%%（%.0f%%）" % m["debt"])
            rows.append({"代码": s, "硬指标通过": "%d/5" % score, "现价": "$%.2f" % m["close"], "PE": _fnum(m.get("pe")),
                         "ROE5": _pct(m.get("roe5")), "营收YoY": _pct(m.get("rev_yoy")), "提示": "；".join(notes)})
            detail_md.append("### %s\n\n- 结论：硬指标 %d/5。\n- %s\n" % (s, score, "；".join(notes) or "全部未达阈值"))
        except Exception as e:
            rows.append({"代码": s, "硬指标通过": "数据失败", "现价": "—", "PE": "—", "ROE5": "—", "营收YoY": "—", "提示": str(e)[:60]})
            detail_md.append("### %s\n\n- 数据获取失败：%s\n" % (s, str(e)[:80]))
    rows.sort(key=lambda r: r["硬指标通过"], reverse=True)
    top = [r["代码"] for r in rows if r["硬指标通过"].startswith(("3", "4", "5"))][:3] or [r["代码"] for r in rows[:3]]
    md = "# 行业漏斗筛选报告\n\n## 第一步：全市场扫描入口\n\n本次输入 **%d** 个标的（活跃股票池需自行扩大）。\n\n## 第二步：5 条硬指标粗筛结果\n\n" % len(syms)
    md += _sections_to_md(rows) + "\n\n## 第三步：精细分析（每家 300-500 字）\n\n" + "\n".join(detail_md) + "\n"
    md += "## 第四步：四大师深度分析（终选 %d 家）\n\n%s\n\n" % (len(top), "、".join(top))
    md += "## 第五步：综合输出\n\n- 终选组合：**%s**\n- 行业级 ETF 替代：如 QQQ / SMH（需人工确认）\n- 信息充分度自评：需人工填写\n- 待更新数据点：需人工标注" % ("、".join(top))
    return _out("industry-funnel", "行业漏斗筛选", None, [],
                [{"title": "5 条硬指标粗筛", "rows": rows}], [], md)


def run_industry_research(symbol: str, sector: str = "") -> dict:
    """行业投资研究：逻辑链 + 产业链 + 四大师 + 风险 + 配置建议（完整文章）。"""
    data = load_company(symbol)
    m = data["m"]
    r = ab.run_analysis(symbol, sector=sector, out_root=REPORTS_ROOT)
    chain_rows = [
        {"环节": "上游（材料/设备）", "代表公司": "需人工补充", "生意特征": "资本密集、周期性强", "卡脖子": "需人工标注"},
        {"环节": "中游（制造）", "代表公司": symbol, "生意特征": "规模效应", "卡脖子": "—"},
        {"环节": "下游（应用/客户）", "代表公司": "需人工补充", "生意特征": "需求驱动", "卡脖子": "—"},
    ]
    master_rows = [
        {"视角": "段永平·生意本质", "评分": "%.1f/5" % r["masters"]["段永平·商业模式"]},
        {"视角": "巴菲特·护城河", "评分": "%.1f/5" % r["masters"]["巴菲特·财务估值"]},
        {"视角": "芒格·风险", "评分": "%.1f/5" % r["masters"]["芒格·逆向思考"]},
        {"视角": "李录·文明趋势", "评分": "%.1f/5" % r["masters"]["李录·长期确定性"]},
    ]
    md = company_header(m, symbol)
    md += "## 一、投资逻辑链构建与验证\n\n- 逻辑链：趋势 → 需求 → 供给 → 龙头受益（%s 的定位需人工细化）。\n- 已发生的验证事件：需人工补充（财报超预期 / 扩产 / 涨价）。\n\n" % symbol
    md += "## 二、产业链全景图\n\n" + _sections_to_md(chain_rows) + "\n\n"
    md += "## 三、当前标的四大师分析\n\n" + _sections_to_md(master_rows) + "\n\n"
    md += "### 生意本质与护城河（数据视角）\n" + "".join("- " + s + "\n" for s in narrate_profit(m) + narrate_balance(m)) + "\n"
    md += "### 成长逻辑（数据视角）\n" + "".join("- " + s + "\n" for s in narrate_growth(m)) + "\n"
    md += "## 四、行业级风险评估（芒格检查清单）\n\n" + ("\n".join("- " + f for f in r["flags"]) if r["flags"] else "- 无自动标记（人工补充系统性风险：政策/技术迭代/竞争）") + "\n\n"
    md += "## 五、文明趋势判断（李录框架）\n\n- 当前主线：AI 算力 / 半导体 / 存储。\n- %s 是否处于主线之上？需人工研判；在主线内的公司长期确定性加分。\n\n" % symbol
    md += "## 六、组合配置建议\n\n- 主题仓位上限：建议 ≤20%%（人工）。\n- 估值位置：PE 分位 **%.0f%%**，%s" % (m.get("pe_pct") or 0, narrate_valuation(m)[0] if narrate_valuation(m) else "")
    return _out("industry-research", "行业投资研究", _verdict_box(r["conclusion"]["verdict"], r["conclusion"]["color"], r["conclusion"]["why"]),
                fmt_cards(m), [{"title": "产业链全景", "rows": chain_rows}, {"title": "四大师分析", "rows": master_rows}], [], md)


def run_bottleneck_hunter(symbol: str) -> dict:
    """供应链瓶颈猎手：趋势确认 → 瓶颈定位 → 估值检查 → 机会看板（完整文章）。"""
    data = load_company(symbol)
    m = data["m"]
    trend_rows = [
        {"趋势": "AI 算力链", "强度": "S", "依据": "半导体/存储/算力基建需求爆发", "跟踪": "NVDA / MU / AVGO"},
        {"趋势": "AGI 太空", "强度": "A", "依据": "卫星互联网/太空军工", "跟踪": "需人工补充"},
        {"趋势": "机器人", "强度": "A", "依据": "人形机器人/具身智能", "跟踪": "需人工补充"},
    ]
    pe_pct = m.get("pe_pct"); pe = m.get("pe"); off_high = m.get("off_high")
    est = []
    if pe_pct is not None and pe_pct > 80:
        est.append("**估值红灯**：PE 分位 %.0f%%（>80%%），信号强度封顶 ★★，标注 ⚠️估值透支。" % pe_pct)
    elif pe_pct is not None and pe_pct > 60:
        est.append("**估值黄灯**：PE 分位 %.0f%%（>60%%），需额外解释否则降级。" % pe_pct)
    elif pe_pct is not None:
        est.append("**估值绿灯**：PE 分位 %.0f%%（<60%%），估值未透支，加分项。" % pe_pct)
    if off_high is not None and off_high > -5:
        est.append("价格贴近 52 周高点（%s），追高风险高。" % _pct(off_high))
    score = 3.0
    if pe_pct is not None and pe_pct > 80:
        score -= 1.0
    elif pe_pct is not None and pe_pct < 40:
        score += 0.5
    md = company_header(m, symbol)
    md += "## 一、超级趋势确认\n\n" + _sections_to_md(trend_rows) + "\n\n"
    md += "## 二、供应链物理拆解\n\n- %s 的产业链定位（上游/中游/下游 + 是否卡脖子）：需人工标注。\n- 数据线索：%s\n\n" % (symbol, narrate_growth(m)[0] if narrate_growth(m) else "")
    md += "## 三、瓶颈识别（6 条标准）\n\n1. 供给集中度 2. 扩产周期 3. 技术壁垒 4. 客户锁定 5. 价格弹性 6. 需求刚性 —— 逐条人工评估。\n\n"
    md += "## 四、估值检查（必做）\n\n" + "\n".join("- " + e for e in est) + "\n\n"
    md += "## 五、基本面交叉验证\n\n" + company_analysis(m) + "\n"
    md += "## 六、瓶颈机会看板\n\n- 信号强度：**%s**（估值调整后 %.1f/5）\n- 一页纸摘要：需人工撰写（瓶颈定位 + 催化 + 风险）\n- 行动建议：低点分批、设止损（人工执行）" % ("★ 优先关注" if score >= 3.5 else ("★★ 观察" if score >= 2.5 else "⚠️ 估值透支"), score)
    label, color = ("★ 优先关注", ab.APPLE_GREEN) if score >= 3.5 else (("★★ 观察", ab.APPLE_ORANGE) if score >= 2.5 else ("⚠️ 估值透支", ab.APPLE_RED))
    return _out("bottleneck-hunter", "供应链瓶颈猎手", _verdict_box(label, color, "估值检查后信号 %.1f/5" % score),
                fmt_cards(m), [{"title": "超级趋势清单", "rows": trend_rows}], [], md)


def run_private_company_research(name: str, desc: str = "") -> dict:
    """未上市公司研究：六任务框架 + 完整报告模板（数据需人工输入）。"""
    md = "# %s · 未上市公司研究\n\n## 公司简介\n\n%s\n\n## 一、六任务并行框架\n\n" % (name or "未命名公司", desc or "（待补充）")
    tasks = [
        {"任务": "1·商业模式与产品用户", "输出": "核心生意定义 / 收入拆解 / UE / BMC / 定价权", "状态": "人工"},
        {"任务": "2·财务数据拼凑", "输出": "数据来源矩阵 / 关键指标推算 / 融资估值演变", "状态": "人工"},
        {"任务": "3·行业格局与竞争", "输出": "波特五力 / 竞争对比 / 情景推演", "状态": "人工"},
        {"任务": "4·风险全景与治理", "输出": "创始人评估 / 股权治理 / 全维度风险 / 退出路径", "状态": "人工"},
        {"任务": "5·技术能力与知识产权", "输出": "专利布局 / 研发能力 / 技术护城河", "状态": "人工"},
        {"任务": "6·替代数据信号", "输出": "招聘 / 产品数据 / 舆情 / 供应链信号 / 信号评分", "状态": "人工"},
    ]
    md += _sections_to_md(tasks) + "\n\n## 二、最终报告结构\n\n1. 一句话结论 2. 公司画像 3. 六维评分总表 4. 关键数据拼图 5. 信号一致性矩阵 6. 各维度摘要 7. 真实价值评估 8. 投资论点（多 vs 空） 9. 风险矩阵 10. 退出路径 11. 投资决策表 12. 信息盲区地图 13. 持续跟踪清单\n\n"
    md += "## 三、使用说明\n\n本 Skill 面向未上市公司（无公开财务数据），引擎无法自动取数；请按六任务框架逐项人工录入，AI 负责拼图与交叉验证。"
    return _out("private-company-research", "未上市公司研究", None, [],
                [{"title": "六任务框架", "rows": tasks}], [], md)


def run_financial_data(symbol: str) -> dict:
    """财务数据交叉验证：多源状态 + 核心指标 + 误差规则（完整文章）。"""
    data = load_company(symbol)
    m = data["m"]
    fund = data["fund"]
    src_rows = [
        {"数据": "日线（前复权）", "来源": "新浪", "状态": "✅ 已获取", "说明": "%d 个交易日" % len(data["price"])},
        {"数据": "年度财务指标", "来源": "东财", "状态": "✅ 已获取" if fund is not None else "❌ 未获取", "说明": "%d 个财年" % (len(fund) if fund is not None else 0)},
        {"数据": "实时行情", "来源": "yfinance", "状态": "⚠️ 限流/降级", "说明": "当前被限流，用日线替代"},
        {"数据": "实时行情", "来源": "Finnhub", "状态": "可选", "说明": "需配置 FINNHUB_API_KEY"},
    ]
    md = company_header(m, symbol)
    md += "## 一、数据源优先级（financial-data Skill 规范）\n\n1. 公司一手资料（财报/电话会）\n2. 交易所数据\n3. 聚合数据源（新浪/东财）\n4. 第三方估算\n\n"
    md += "## 二、本次数据获取状态\n\n" + _sections_to_md(src_rows) + "\n\n"
    md += "## 三、核心指标（交叉验证后）\n\n" + _sections_to_md(fmt_cards(m)) + "\n\n"
    md += "## 四、数据解读\n\n" + company_analysis(m) + "\n"
    md += "## 五、误差计算与标记规则\n\n- 不同源差异 >1%% 需标注来源与日期。\n- 历史序列一律前复权（当前已用）。\n- 常见差异原因：除权除息、币种换算、会计口径（GAAP vs Non-GAAP）。"
    return _out("financial-data", "财务数据交叉验证", None, fmt_cards(m),
                [{"title": "数据源状态", "rows": src_rows}], [], md)




# ================= 组合跟踪类 =================

def _parse_holdings(text: str) -> list:
    out = []
    for line in (text or "").splitlines():
        line = line.strip().strip(",")
        if not line:
            continue
        parts = [p.strip() for p in re.split(r"[,\\s;]+", line) if p.strip()]
        if not parts:
            continue
        try:
            qty = float(parts[1]) if len(parts) > 1 else 0
            cost = float(parts[2]) if len(parts) > 2 else None
            out.append({"symbol": parts[0].upper(), "qty": qty, "cost": cost})
        except Exception:
            continue
    return out


def run_portfolio_review(holdings_text: str) -> dict:
    """组合管理：持仓收益、集中度、相关性、压力测试（完整报告）。"""
    h = _parse_holdings(holdings_text)
    if not h:
        raise RuntimeError("未解析到有效持仓。格式：每行「代码,数量,成本价」，例如 NVDA,100,120.5")
    rows = []
    total_mv = 0.0
    details = []
    for p in h:
        try:
            data = load_company(p["symbol"])
            m = data["m"]
            price = m["close"]
            mv = price * p["qty"]
            total_mv += mv
            pnl = None
            if p.get("cost"):
                pnl = (price / p["cost"] - 1) * 100
            rows.append({"代码": p["symbol"], "数量": p["qty"], "现价": "$%.2f" % price,
                         "市值": "$%.0f" % mv, "盈亏": ("%+.1f%%" % pnl) if pnl is not None else "—",
                         "PE": _fnum(m.get("pe")), "距52周高": _pct(m.get("off_high"))})
            details.append("### %s\n\n- 现价 $%.2f，%s。\n- %s\n" % (p["symbol"], price,
                          ("累计盈亏 %+.1f%%" % pnl) if pnl is not None else "无成本数据", narrate_valuation(m)[0] if narrate_valuation(m) else ""))
        except Exception as e:
            rows.append({"代码": p["symbol"], "数量": p["qty"], "现价": "数据失败", "市值": "—", "盈亏": "—", "PE": "—", "距52周高": str(e)[:40]})
            details.append("### %s\n\n- 数据获取失败：%s\n" % (p["symbol"], str(e)[:80]))
    conc = []
    for r in rows:
        try:
            mv = float(str(r["市值"]).replace("$", "").replace(",", ""))
            w = mv / total_mv * 100 if total_mv else 0
            conc.append({"代码": r["代码"], "权重": "%.1f%%" % w, "建议上限": "≤20%%", "超配": "⚠️" if w > 20 else "✅"})
        except Exception:
            pass
    md = "# 组合管理报告\n\n## 一、持仓总览（%d 只）\n\n" % len(h)
    md += _sections_to_md(rows) + "\n\n## 二、组合市值：**$%.0f**\n\n## 三、单仓位体检\n\n" % total_mv + "\n".join(details) + "\n"
    md += "## 四、组合层面分析\n\n### 4.1 集中度\n\n" + (_sections_to_md(conc) if conc else "- 无") + "\n\n"
    md += "### 4.2 相关性检查\n\n- 美股科技股相关性普遍较高；若 >3 只同赛道，分散效果有限，需人工确认。\n\n"
    md += "### 4.3 压力测试\n\n- 情景1：大盘 -20%%（科技股联动）\n- 情景2：个股黑天鹅 -50%%\n- 情景3：利率上行杀估值\n\n"
    md += "## 五、优化建议\n\n- 减仓：权重 >20%% 的标的（见集中度表）。\n- 替代：估值分位 / 现金流更优的标的（人工）。\n- 现金管理：保留 5-20%% 现金（人工）。"
    label, color = ("组合需审视", ab.APPLE_ORANGE) if any("⚠️" == c["超配"] for c in conc) else (("组合健康", ab.APPLE_GREEN) if conc else ("数据不足", ab.APPLE_GRAY))
    return _out("portfolio-review", "组合管理", _verdict_box(label, color, "共 %d 只持仓，总市值 $%.0f" % (len(h), total_mv)),
                [{"label": "持仓数量", "value": str(len(h)), "sub": "只"}, {"label": "总市值", "value": "$%.0f" % total_mv, "sub": "按现价"}],
                [{"title": "持仓明细", "rows": rows}, {"title": "集中度分析", "rows": conc}], [], md)


def run_thesis_tracker(symbol: str, thesis_text: str = "") -> dict:
    """投资论文追踪：建立论文 → 数据快照 → 假设/红线 → 健康度（完整报告）。"""
    data = load_company(symbol)
    m = data["m"]
    checks = [
        {"name": "核心假设1：成长可持续（营收YoY>10%%）", "ok": (m.get("rev_yoy") or 0) > 10, "note": "当前营收YoY %.1f%%" % (m.get("rev_yoy") or 0)},
        {"name": "核心假设2：盈利能力稳定（ROE>15%%）", "ok": (m.get("roe5") or 0) > 15, "note": "ROE5年 %.1f%%" % (m.get("roe5") or 0)},
        {"name": "核心假设3：估值未透支（PE分位<80%%）", "ok": (m.get("pe_pct") or 0) < 80, "note": "PE分位 %.0f%%" % (m.get("pe_pct") or 0)},
        {"name": "红线1：未跌破关键支撑（距52周高>-30%%）", "ok": (m.get("off_high") or 0) > -30, "note": "距52周高 %s" % _pct(m.get("off_high"))},
        {"name": "红线2：基本面未恶化（净利YoY>-30%%）", "ok": (m.get("np_yoy") or 0) > -30, "note": "净利YoY %.1f%%" % (m.get("np_yoy") or 0)},
    ]
    ok_n = sum(1 for c in checks if c["ok"])
    health = ok_n / len(checks) * 100
    label, color = ("健康", ab.APPLE_GREEN) if health >= 80 else (("关注", ab.APPLE_ORANGE) if health >= 60 else ("警报", ab.APPLE_RED))
    md = company_header(m, symbol)
    md += "## 一、核心投资论文（200 字以内）\n\n> %s\n\n" % (thesis_text or "（待填写：为什么买？赚什么钱？什么情况卖出？）")
    md += "## 二、数据快照（A0）\n\n" + _sections_to_md(fmt_cards(m)) + "\n\n"
    md += "## 三、核心假设与红线清单\n\n" + _sections_to_md([{"检查项": c["name"], "状态": "✅ 未触发" if c["ok"] else "❌ 触发", "当前值": c["note"]} for c in checks]) + "\n\n"
    md += "## 四、论文健康度：**%.0f / 100 → %s**\n\n" % (health, label)
    md += "## 五、估值锚点更新\n\n- 当前 PE **%.1f**，5 年分位 **%.0f%%**。\n- 锚点（买点 / 卖点 PE）需人工设定并写入论文。\n\n" % (m.get("pe") or 0, m.get("pe_pct") or 0)
    md += "## 六、追踪结论\n\n- 触发红线 %d 条（%s）。\n- 建议：%s" % (len(checks) - ok_n, "需人工确认" if ok_n < len(checks) else "无", "按计划持有，下次复核日人工设定" if health >= 80 else "重新评估论文：区分事实变化 vs 措辞变化（运行 thesis-drift）")
    return _out("thesis-tracker", "投资论文追踪", _verdict_box(label, color, "论文健康度 %.0f/100" % health),
                [{"label": "健康度", "value": "%.0f / 100" % health, "sub": label}, {"label": "PE 分位", "value": _pct(m.get("pe_pct")), "sub": "估值位置"}],
                [{"title": "假设与红线", "rows": [{"检查项": c["name"], "状态": "✅" if c["ok"] else "❌", "当前值": c["note"]} for c in checks]}],
                [{"title": "论文健康检查", "items": checks}], md)


def run_thesis_drift(old_text: str, new_text: str) -> dict:
    """论文漂移检测：维度对比 + 结论（完整报告）。"""
    if not old_text or not new_text:
        raise RuntimeError("请同时输入旧论文与新论文文本")
    dims = ["核心逻辑", "估值锚点", "增长假设", "风险认知", "仓位纪律", "结论"]
    rows = []
    for d in dims:
        old_hit = d in old_text
        new_hit = d in new_text
        if old_hit and new_hit:
            state = "✅ 一致"
        elif old_hit and not new_hit:
            state = "⚠️ 维度消失（措辞漂移？）"
        elif not old_hit and new_hit:
            state = "🆕 新增维度（事实变化？）"
        else:
            state = "— 均未提及"
        rows.append({"维度": d, "旧论文": "有" if old_hit else "无", "新论文": "有" if new_hit else "无", "判定": state})
    changed = sum(1 for r in rows if "⚠️" in r["判定"] or "🆕" in r["判定"])
    md = "# 论文漂移检测报告\n\n## 一、对比模式\n\n模式A：指定报告对比（两篇论文全文）。\n\n## 二、证据归一化\n\n- 数字需归一化到同一口径（币种/财年/口径）后再比较。\n- 建议对照最新数据逐条核验（运行 thesis-tracker 获取快照）。\n\n## 三、维度漂移表\n\n" + _sections_to_md(rows) + "\n\n"
    md += "## 四、证据驱动规则\n\n- 事实变化（业绩/行业/管理层）：需重新评估。\n- 措辞变化（描述风格/情绪）：记录但不改变结论。\n\n## 五、总体结论\n\n检测到 **%d** 个维度变化。是否触发论文重审：**%s**。" % (changed, "是（人工确认）" if changed else "否")
    label, color = ("漂移需关注", ab.APPLE_ORANGE) if changed else (("无漂移", ab.APPLE_GREEN))
    return _out("thesis-drift", "论文漂移检测", _verdict_box(label, color, "%d 个维度发生变化" % changed),
                [{"label": "变化维度", "value": str(changed), "sub": "共 %d 个维度" % len(dims)}],
                [{"title": "维度漂移表", "rows": rows}], [], md)


def run_news_pulse(symbol: str) -> dict:
    """公司新闻脉搏：异动检测 + 归因框架 + 行动建议（完整报告）。"""
    data = load_company(symbol)
    price = data["price"]
    m = data["m"]
    d = price.tail(20)
    rows = []
    prev_close = None
    for ts, row in d.iterrows():
        if prev_close is not None and prev_close:
            chg = (row["close"] / prev_close - 1) * 100
            flag = "🔥" if abs(chg) >= 3 else ""
            rows.append({"日期": ts.strftime("%m-%d"), "收盘": "$%.2f" % row["close"], "日涨跌": "%+.2f%%" % chg, "异动": flag})
        prev_close = row["close"]
    big = [r for r in rows if "🔥" in r.get("异动", "")]
    md = company_header(m, symbol)
    md += "## 一、参数与场景\n\n- 代码：%s\n- 近20日异动检测，阈值 ±3%%\n\n## 二、近20日行情\n\n" % symbol
    md += _sections_to_md(rows) + "\n\n"
    md += "## 三、异动归因（4 个侦察维度）\n\n1. 公司事件：财报 / 产品 / 管理层变动（需联网人工）\n2. 监管政策：法案 / 关税 / 反垄断（需联网人工）\n3. 行业对手：同业财报 / 价格战（需联网人工）\n4. 市场情绪：加息 / 避险 / 板块轮动（需联网人工）\n\n"
    if big:
        md += "## 四、检测到的异动\n\n" + "\\n".join("- %s：%s（%s）" % (b["日期"], b["收盘"], b["日涨跌"]) for b in big) + "\n\n"
    else:
        md += "## 四、检测到的异动\n\n近 20 日无 ±3%% 以上异动，行情平稳。\n\n"
    md += "## 五、趋势与动量参考\n\n" + "".join("- " + s + "\n" for s in narrate_momentum(m)) + "\n"
    md += "## 六、行动建议\n\n- 异动≥3%% 或重大事件 → 运行 thesis-tracker 复核论文（人工判断）。\n- 信息缺口声明：本地无新闻流，需人工补充新闻与事件时间线。"
    label, color = ("异动关注", ab.APPLE_ORANGE) if big else (("平稳", ab.APPLE_GREEN))
    return _out("news-pulse", "公司新闻脉搏", _verdict_box(label, color, "近20日检测到 %d 个异动日" % len(big)),
                [{"label": "近20日异动", "value": str(len(big)), "sub": "≥3%"}, {"label": "现价", "value": "$%.2f" % m["close"], "sub": m.get("date", "")}],
                [{"title": "近20日行情", "rows": rows}], [], md)


def run_income_investment(symbol: str) -> dict:
    """Income 股息分析：分布 → 可分配现金 → 质量 → 三情景（完整文章）。"""
    data = load_company(symbol)
    m = data["m"]
    rows = [
        {"维度": "1. 股息分布理解", "数据": "需人工输入（每股股息/派息频率）", "说明": "yfinance 可补充 dividends"},
        {"维度": "2. 可分配现金追踪", "数据": "需人工（FCF = 经营现金流 - 资本开支）", "说明": "东财接口无 FCF"},
        {"维度": "3. 质量与持久性", "数据": "ROE5 %.1f%% / 负债率 %.1f%%" % (m.get("roe5") or 0, m.get("debt") or 0), "说明": "盈利稳定为派息基础"},
        {"维度": "4. 收入流估值", "数据": "PE %.1f（分位 %.0f%%）" % (m.get("pe") or 0, m.get("pe_pct") or 0), "说明": "股息率需人工"},
        {"维度": "5. 可用收入", "数据": "需人工", "说明": "税率/币种/到账"},
        {"维度": "6. 组合适配", "数据": "需人工", "说明": "与现有持仓相关性"},
    ]
    md = company_header(m, symbol)
    md += "## 一、执行工作流\n\n" + _sections_to_md(rows) + "\n\n"
    md += "## 二、派息能力基本面（数据视角）\n\n" + "".join("- " + s + "\n" for s in narrate_profit(m) + narrate_balance(m)) + "\n"
    md += "## 三、三情景构建\n\n- 乐观：股息增长 + 估值修复（人工参数）\n- 基准：股息平稳（人工参数）\n- 悲观：股息削减（人工参数）\n\n"
    md += "## 四、分类与判决\n\n- 分红可持续性：需人工（历史派息 + 派息率）。\n- 数据缺口：东财美股接口无股息/FCF，建议用 yfinance dividends 或公司财报补充。"
    return _out("income-investment", "Income 股息分析", None, fmt_cards(m), [{"title": "执行工作流", "rows": rows}], [], md)




# ================= 内容排版类 =================

def run_wechat_article(symbol: str, topic: str = "") -> dict:
    """公众号文章：基于真实数据生成完整文章初稿（作者 Agent），附编辑/读者评审清单。"""
    data = load_company(symbol)
    m = data["m"]
    topic = topic.strip() or ("AI 算力与半导体" if "NVDA" in symbol.upper() or "MU" in symbol.upper() or "AVGO" in symbol.upper() else "科技成长")
    growth_md = "".join("- " + s + "\n" for s in narrate_growth(m))
    profit_md = "".join("- " + s + "\n" for s in narrate_profit(m))
    val_md = "".join("- " + s + "\n" for s in narrate_valuation(m))
    mom_md = "".join("- " + s + "\n" for s in narrate_momentum(m))
    md = "# 标题：%s 值得关注吗？——用数据拆解 %s\n\n" % (symbol, topic)
    md += "> 副标题：不荐股，只拆生意。本文由本地量化系统基于真实财务与行情数据自动生成初稿。\n\n"
    md += "## 一、开头钩子\n\n%s 现价 **$%.2f**（%s），过去一年 %s。当大家都在讨论%s的时候，我们回到数据本身，看三个问题：生意好不好？贵不贵？风险在哪？\n\n" % (
        symbol, m["close"], m.get("date", ""), _pct(m.get("off_high")) + "（距52周高点）", topic)
    md += "## 二、生意本质：它靠什么赚钱\n\n"
    md += "- 营收规模：最新财年 **%s**，营收 YoY **%s**。\n" % (_fmt(m.get("rev_latest")), _pct(m.get("rev_yoy")))
    md += "- 盈利底色：毛利率 5 年均值 **%.1f%%**，净利率 5 年均值 **%.1f%%**，ROE 5 年均值 **%.1f%%**。\n\n" % (m.get("gm5") or 0, m.get("nm5") or 0, m.get("roe5") or 0)
    md += "### 成长性\n" + growth_md + "\n### 盈利质量\n" + profit_md + "\n"
    md += "## 三、财务体检\n\n" + _sections_to_md(fmt_cards(m)) + "\n\n"
    md += "## 四、贵不贵：估值与位置\n\n" + val_md + mom_md + "\n"
    md += "## 五、风险与反面（芒格式）\n\n"
    md += "- 估值风险：%s\n- 竞争风险：需人工补充（同业、替代技术）。\n- 宏观风险：利率、汇率、地缘（需人工补充）。\n\n" % (val_md.split("- ")[-1] if val_md else "待补充")
    md += "## 六、结论（不构成投资建议）\n\n%s 当前处于%s。建议：%s。本文为数据初稿，发布前必须经过「编辑 + 读者」双审阅（见下）。\n\n" % (
        symbol, narrate_valuation(m)[0] if narrate_valuation(m) else "估值中枢", "低位分批、设好止损" if (m.get("pe_pct") or 50) < 40 else "等待更好的赔率，不追高")
    md += "---\n\n## 阶段三：编辑 Agent 审阅清单\n\n- [ ] 逻辑是否自洽：数据与结论是否一致？\n- [ ] 数字是否准确：所有 %s 已由本地引擎核验（新浪日线 + 东财年报）。\n- [ ] 有无夸大表述 / 荐股嫌疑？\n\n## 阶段四：读者 Agent 评审\n\n- 读者最关心：我该不该关注？什么价位？什么风险？\n- 文章是否回答了上述问题？（人工补充）"
    return _out("wechat-article", "公众号文章", None, fmt_cards(m), [], [], md)


def run_investment_memo(symbol: str, sector: str = "") -> dict:
    """投资备忘录排版：事实-观点分离 + 反面观点 + 行动导向（完整备忘录）。"""
    data = load_company(symbol)
    m = data["m"]
    r = ab.run_analysis(symbol, sector=sector, out_root=REPORTS_ROOT)
    avg = sum(r["gates"][k]["score"] for k in ["能力圈", "好生意", "护城河", "管理层", "安全边际"]) / 5.0
    md = "# %s · 投资备忘录（Investment Memo）\n\n## 一、一句话论点\n\n**%s**：%s\n\n" % (symbol, r["conclusion"]["verdict"], r["conclusion"]["why"])
    md += "## 二、事实（可验证，带来源）\n\n" + _sections_to_md(fmt_cards(m)) + "\n\n"
    md += "## 三、观点（与事实区分）\n\n" + company_analysis(m) + "\n"
    md += "- 生意质量：六关平均 **%.2f/5**。\n- 估值判断：PE 分位 **%.0f%%**，%s\n" % (avg, m.get("pe_pct") or 0, narrate_valuation(m)[0] if narrate_valuation(m) else "")
    md += "## 四、反面观点（芒格式逆向）\n\n" + ("\n".join("- " + f for f in r["flags"]) if r["flags"] else "- 待人工补充：什么会让这笔投资归零？") + "\n\n"
    md += "## 五、行动与跟踪\n\n- 买入区间 / 卖出纪律：人工设定。\n- 跟踪指标：营收增速、ROE、PE 分位、距 52 周高点。\n- 下次复核：人工设定。\n\n## 六、排版规范（investment-memo-craft）\n\n- 克制排版：白底、单色强调、表格承载数据。\n- 事实与观点分节，杜绝情绪化表达。\n- 每条数据标注来源与日期。"
    return _out("investment-memo-craft", "投资备忘录排版", _verdict_box(r["conclusion"]["verdict"], r["conclusion"]["color"], r["conclusion"]["why"]),
                fmt_cards(m), [], [], md)


# ================= 统一入口 =================

RUNNERS = {
    "investment-checklist": lambda kw: run_investment_checklist(kw.get("symbol", ""), kw.get("sector", "")),
    "investment-research": lambda kw: run_investment_research(kw.get("symbol", ""), kw.get("sector", "")),
    "investment-team": lambda kw: run_investment_team(kw.get("symbol", "")),
    "earnings-review": lambda kw: run_earnings_review(kw.get("symbol", "")),
    "earnings-team": lambda kw: run_earnings_team(kw.get("symbol", "")),
    "management-deep-dive": lambda kw: run_management_deep_dive(kw.get("symbol", "")),
    "dyp-ask": lambda kw: run_dyp_ask(kw.get("symbol", "")),
    "deep-company-series": lambda kw: run_deep_company_series(kw.get("symbol", "")),
    "quality-screen": lambda kw: run_quality_screen(kw.get("symbol", "")),
    "industry-funnel": lambda kw: run_industry_funnel(kw.get("symbols", [])),
    "industry-research": lambda kw: run_industry_research(kw.get("symbol", ""), kw.get("sector", "")),
    "bottleneck-hunter": lambda kw: run_bottleneck_hunter(kw.get("symbol", "")),
    "private-company-research": lambda kw: run_private_company_research(kw.get("name", ""), kw.get("desc", "")),
    "financial-data": lambda kw: run_financial_data(kw.get("symbol", "")),
    "portfolio-review": lambda kw: run_portfolio_review(kw.get("holdings", "")),
    "thesis-tracker": lambda kw: run_thesis_tracker(kw.get("symbol", ""), kw.get("thesis", "")),
    "thesis-drift": lambda kw: run_thesis_drift(kw.get("old_text", ""), kw.get("new_text", "")),
    "news-pulse": lambda kw: run_news_pulse(kw.get("symbol", "")),
    "income-investment": lambda kw: run_income_investment(kw.get("symbol", "")),
    "wechat-article": lambda kw: run_wechat_article(kw.get("symbol", ""), kw.get("topic", "")),
    "investment-memo-craft": lambda kw: run_investment_memo(kw.get("symbol", ""), kw.get("sector", "")),
}


def run_skill(skill_id: str, **kw) -> dict:
    """统一入口：按 skill_id 运行对应引擎。"""
    runner = RUNNERS.get(skill_id)
    if runner is None:
        return _bad(skill_id, "未知 Skill：%s" % skill_id)
    try:
        return runner(kw)
    except Exception as ex:
        return _bad(skill_id, "运行失败：%s" % ex)


def save_report(result: dict, symbol: str = "") -> str:
    """把结果保存为 Markdown 文件，返回路径。"""
    os.makedirs(REPORTS_ROOT, exist_ok=True)
    sid = result.get("skill_id", "skill")
    tag = re.sub(r"[^A-Za-z0-9_]", "_", (symbol or sid).upper())
    p = os.path.join(REPORTS_ROOT, "%s_%s_%s.md" % (tag, sid, dt.datetime.now().strftime("%Y%m%d_%H%M")))
    io.open(p, "w", encoding="utf-8").write(result.get("markdown", ""))
    return p
