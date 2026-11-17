# -*- coding: utf-8 -*-
"""AI Berkshire 价值投资分析引擎（本地化实现）。

复刻 GitHub: xbtlin/ai-berkshire 的核心方法论：
- 巴菲特买入前六关 Checklist（能力圈/好生意/护城河/管理层/安全边际/仓位纪律）
- 四大师视角对抗（段永平·商业模式 / 巴菲特·财务估值 / 芒格·逆向思考 / 李录·长期确定性）
- 快速否决清单 + 镜子测试 + 三情景估值

数据：akshare 东财美股财务指标（年度 ROE/毛利率/净利率/负债/EPS/增速）+
      akshare 新浪美股日线（价格/趋势/估值分位）。
不可量化维度（管理层诚信、能力圈）按技能 B/C 级原则诚实标注"需人工确认"。
"""
from __future__ import annotations

import datetime as dt
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import data_provider as dp

# ---------------- 常量与配色（Apple 风格） ----------------

APPLE_BLUE = "#0071e3"
APPLE_DARK = "#1d1d1f"
APPLE_GRAY = "#86868b"
APPLE_GREEN = "#34c759"
APPLE_RED = "#ff3b30"
APPLE_ORANGE = "#ff9500"
APPLE_BG = "#f5f5f7"

GATES = [
    ("能力圈", "我能理解这门生意吗"),
    ("好生意", "这是一门好生意吗"),
    ("护城河", "护城河够不够深"),
    ("管理层", "管理层值得信任吗"),
    ("安全边际", "价格是否足够便宜"),
]

MASTERS = [
    ("段永平", "商业模式"),
    ("巴菲特", "财务估值"),
    ("芒格", "逆向思考"),
    ("李录", "长期确定性"),
]

# 8 条快速否决清单（来自 investment-checklist skill）
VETO_LIST = [
    "说不清楚这家公司怎么赚钱",
    "连续3年自由现金流为负且看不到改善",
    "管理层有诚信污点",
    "竞争优势正在被不可逆侵蚀",
    "需要靠「下一个接盘者出更高价」来赚钱（博傻）",
    "无法承受这笔投资归零的后果",
    "买入理由主要是「别人都在买」或「最近涨得好」",
    "无法用200字以内写清楚买入理由",
]

NAME_TO_SYMBOL = {
    "特斯拉": "TSLA", "美光": "MU", "英伟达": "NVDA", "苹果": "AAPL", "微软": "MSFT",
    "谷歌": "GOOGL", "亚马逊": "AMZN", "meta": "META", "脸书": "META", "台积电": "TSM",
    "博通": "AVGO", "超微": "SMCI", "amd": "AMD", "拼多多": "PDD", "腾讯": "TCEHY",
    "奈飞": "NFLX", "netflix": "NFLX", "甲骨文": "ORCL", "英特尔": "INTC", "高通": "QCOM",
    "德州仪器": "TXN", "阿斯麦": "ASML", "美光科技": "MU", "英伟达公司": "NVDA",
    "苹果公司": "AAPL", "微软公司": "MSFT", "亚马逊公司": "AMZN",
}

MARKET_NOTE = "美股 + 美股上市中概股（全部放行）；仅排除港股与 A 股市场"


def is_blocked_market(sym: str):
    """市场拦截：仅排除香港 / 中国大陆市场代码，美股（含美股上市中概股 ADR）全部放行。"""
    if not sym:
        return None
    s = sym.strip().upper()
    if s.endswith((".HK", ".SZ", ".SH", ".BJ", ".SS", ".SN")):
        return "港股 / A 股市场（本系统仅做美股，请使用该公司的美股代码或 ADR）"
    if re.fullmatch(r"\d{4,5}", s):
        return "疑似港股代码（如 0700=腾讯港股；美股请用 ADR 代码如 TCEHY）"
    if re.fullmatch(r"\d{6}", s):
        return "疑似 A 股代码（本系统仅做美股）"
    return None


# ---------------- 工具 ----------------

def resolve_symbol(text: str) -> str:
    """把用户输入（中文名 / 英文名 / 代码）解析为美股代码。"""
    if not text:
        return ""
    s = text.strip().upper()
    if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", s):
        return s
    key = text.strip().lower()
    for k, v in NAME_TO_SYMBOL.items():
        if key == k.lower() or key in k.lower():
            return v
    return text.strip().upper()


def _clean_num(x):
    try:
        if x is None:
            return None
        f = float(x)
        if np.isnan(f):
            return None
        return f
    except Exception:
        return None


# ---------------- 数据获取 ----------------

def fetch_fundamentals(symbol: str) -> pd.DataFrame | None:
    """东财美股年度财务指标（2005 至今）。返回按财年升序的 DataFrame。"""
    import akshare as ak
    df = ak.stock_financial_us_analysis_indicator_em(symbol=symbol.upper())
    if df is None or df.empty:
        return None
    keep = ["REPORT_DATE", "OPERATE_INCOME", "OPERATE_INCOME_YOY", "PARENT_HOLDER_NETPROFIT",
            "BASIC_EPS", "GROSS_PROFIT_RATIO", "NET_PROFIT_RATIO", "ROE_AVG", "ROA", "PARENT_HOLDER_NETPROFIT_YOY",
            "DEBT_ASSET_RATIO", "CURRENT_RATIO"]
    cols = [c for c in keep if c in df.columns]
    out = df[cols].copy()
    out["REPORT_DATE"] = pd.to_datetime(out["REPORT_DATE"])
    out["year"] = out["REPORT_DATE"].dt.year
    for c in cols:
        if c != "REPORT_DATE":
            out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["year"]).sort_values("year").drop_duplicates("year", keep="last")
    return out.reset_index(drop=True)


def fetch_price(symbol: str, days: int = 1500) -> pd.DataFrame | None:
    """日线（前复权），用于趋势与估值分位。"""
    return dp.get_daily(symbol, days=days)


# ---------------- 指标计算 ----------------

def _ttm_eps(fund: pd.DataFrame) -> float | None:
    """最近年度 EPS（东财美股为日历年/财年 EPS）。"""
    if fund is None or fund.empty:
        return None
    eps = _clean_num(fund["BASIC_EPS"].iloc[-1])
    return eps if eps and eps > 0 else None


def compute_metrics(symbol: str, price: pd.DataFrame, fund: pd.DataFrame) -> dict:
    """汇总可量化指标。"""
    import indicators as ind
    d = ind.add_indicators(price)
    last = d.iloc[-1]
    close = float(last["close"])
    eps = _ttm_eps(fund)

    roe_series = fund["ROE_AVG"].dropna().tail(5)
    gm_series = fund["GROSS_PROFIT_RATIO"].dropna().tail(5)
    nm_series = fund["NET_PROFIT_RATIO"].dropna().tail(5)
    debt = _clean_num(fund["DEBT_ASSET_RATIO"].iloc[-1]) if fund is not None and len(fund) else None

    metrics = {
        "symbol": symbol.upper(),
        "close": close,
        "date": d.index[-1].strftime("%Y-%m-%d"),
        "ma20": float(last["MA20"]) if last["MA20"] == last["MA20"] else None,
        "ma60": float(last["MA60"]) if last["MA60"] == last["MA60"] else None,
        "rsi14": float(last["RSI"]) if last["RSI"] == last["RSI"] else None,
        "eps": eps,
        "pe": (close / eps) if eps else None,
        "roe5": float(roe_series.mean()) if len(roe_series) else None,
        "gm5": float(gm_series.mean()) if len(gm_series) else None,
        "nm5": float(nm_series.mean()) if len(nm_series) else None,
        "debt": debt,
        "roe_latest": _clean_num(fund["ROE_AVG"].iloc[-1]) if fund is not None and len(fund) else None,
        "gm_latest": _clean_num(fund["GROSS_PROFIT_RATIO"].iloc[-1]) if fund is not None and len(fund) else None,
        "nm_latest": _clean_num(fund["NET_PROFIT_RATIO"].iloc[-1]) if fund is not None and len(fund) else None,
        "rev_latest": _clean_num(fund["OPERATE_INCOME"].iloc[-1]) if fund is not None and len(fund) else None,
        "rev_yoy": _clean_num(fund["OPERATE_INCOME_YOY"].iloc[-1]) if fund is not None and len(fund) else None,
        "np_yoy": _clean_num(fund["PARENT_HOLDER_NETPROFIT_YOY"].iloc[-1]) if fund is not None and len(fund) else None,
    }

    # 近3年营收/利润 CAGR（有 4 个财年数据即可算）
    if fund is not None and len(fund) >= 4:
        rev = fund["OPERATE_INCOME"].dropna()
        np_ = fund["PARENT_HOLDER_NETPROFIT"].dropna()
        if len(rev) >= 4 and rev.iloc[-1] > 0 and rev.iloc[-4] > 0:
            metrics["rev_cagr3"] = (rev.iloc[-1] / rev.iloc[-4]) ** (1 / 3) - 1
        if len(np_) >= 4 and np_.iloc[-1] > 0 and np_.iloc[-4] > 0:
            metrics["np_cagr3"] = (np_.iloc[-1] / np_.iloc[-4]) ** (1 / 3) - 1

    # 5年毛利率/ROE 稳定性
    if len(gm_series) >= 4:
        metrics["gm_std5"] = float(gm_series.std())
    if len(roe_series) >= 4:
        metrics["roe_std5"] = float(roe_series.std())

    # PE 历史分位（近5年每日 close / 对应财年 EPS）
    if eps:
        pe_hist = []
        pe_dates = []
        fund_map = {}
        if fund is not None and len(fund):
            for _, r in fund.iterrows():
                fund_map[r["year"]] = _clean_num(r["BASIC_EPS"])
        for ts, row in d.iterrows():
            yr = ts.year
            e = fund_map.get(yr)
            if not e:
                # 用最近一个不晚于该年的财年 EPS
                cand = [v for k, v in sorted(fund_map.items()) if k <= yr]
                e = cand[-1] if cand else None
            if e and e > 0:
                pe_hist.append(float(row["close"]) / e)
                pe_dates.append(ts)
        if len(pe_hist) >= 60:
            pe_now = close / eps
            pct = (np.array(pe_hist) <= pe_now).mean() * 100
            metrics["pe_pct"] = float(pct)
            metrics["pe_hist_min"] = float(np.min(pe_hist))
            metrics["pe_hist_max"] = float(np.max(pe_hist))

    # 52周高低 / 距高点
    win = d["close"].tail(252)
    metrics["high52"] = float(win.max())
    metrics["low52"] = float(win.min())
    metrics["off_high"] = (close / win.max() - 1) * 100 if win.max() > 0 else 0.0

    return metrics


# ---------------- 六关评分 ----------------

def _clamp(v, lo=1.0, hi=5.0):
    return float(max(lo, min(hi, v)))


def score_gates(m: dict, sector: str = "") -> dict:
    """六关评分（第6关为纪律清单，不评分）。返回 {gate: {score, reason, note}}。"""
    g = {}

    # 第一关：能力圈 —— 系统只做"业务清晰度"提示，最终需人工确认
    clear_words = ["半导体", "芯片", "存储", "软件", "银行", "保险", "零售", "饮料",
                   "酒", "汽车", "制药", "医药", "电信", "能源", "地产", "航空", "电商"]
    clear = sum(1 for w in clear_words if w in sector)
    if clear >= 1:
        cap = 4.0
        cap_note = "行业语义较清晰（" + sector + "），10年确定性仍请自行判断"
    else:
        cap = 3.0
        cap_note = "行业=" + (sector or "未知") + "，请用一句话回答：它靠什么赚钱？"
    g["能力圈"] = {"score": cap, "note": cap_note}

    # 第二关：好生意
    s = 1.0
    reasons = []
    roe, gm, nm, debt = m.get("roe5"), m.get("gm5"), m.get("nm5"), m.get("debt")
    if roe is not None:
        if roe >= 20: s += 1.6; reasons.append("ROE5年均值 %.1f%%（≥20 卓越）" % roe)
        elif roe >= 15: s += 1.2; reasons.append("ROE5年均值 %.1f%%（≥15 优秀）" % roe)
        elif roe >= 10: s += 0.8; reasons.append("ROE5年均值 %.1f%%（≥10 合格）" % roe)
        else: reasons.append("ROE5年均值 %.1f%%（<10 偏弱）" % roe)
    if gm is not None:
        if gm >= 40: s += 1.2; reasons.append("毛利率5年均值 %.1f%%（≥40 有定价权）" % gm)
        elif gm >= 25: s += 0.7; reasons.append("毛利率5年均值 %.1f%%（≥25）" % gm)
        else: reasons.append("毛利率5年均值 %.1f%%（<25 偏弱）" % gm)
    if nm is not None:
        if nm >= 15: s += 0.7; reasons.append("净利率5年均值 %.1f%%" % nm)
        elif nm >= 5: s += 0.3
        else: reasons.append("净利率5年均值 %.1f%%（<5）" % nm)
    if debt is not None and debt <= 40:
        s += 0.5; reasons.append("资产负债率 %.1f%%（低杠杆）" % debt)
    g["好生意"] = {"score": _clamp(s), "reasons": reasons}

    # 第三关：护城河（代理指标）
    s = 1.0
    reasons = []
    if gm is not None:
        if gm >= 50: s += 1.8; reasons.append("毛利率5年均值 %.1f%%（强定价权信号）" % gm)
        elif gm >= 35: s += 1.2; reasons.append("毛利率5年均值 %.1f%%" % gm)
        else: reasons.append("毛利率5年均值 %.1f%%" % gm)
    if roe is not None and roe >= 20:
        s += 1.2; reasons.append("ROE %.1f%%（资本回报优秀=护城河在起作用）" % roe)
    if m.get("gm_std5") is not None and m["gm_std5"] <= 6:
        s += 0.8; reasons.append("毛利率5年波动仅 %.1fpp（定价权稳定）" % m["gm_std5"])
    if m.get("rev_cagr3") is not None and m["rev_cagr3"] > 0:
        s += 0.5; reasons.append("近3年营收CAGR %+.1f%%（份额/需求在扩张）" % (m["rev_cagr3"] * 100))
    g["护城河"] = {"score": _clamp(s), "reasons": reasons}

    # 第四关：管理层 —— 数据不足，诚实标注
    g["管理层"] = {"score": 3.0, "note": "本地引擎无法核验管理层诚信/资本配置 → 需人工确认（信息等级C级）"}

    # 第五关：安全边际
    s = 1.0
    reasons = []
    pe, pct = m.get("pe"), m.get("pe_pct")
    if pe is not None:
        if pe <= 15: s += 1.2; reasons.append("PE %.1f（≤15 便宜）" % pe)
        elif pe <= 25: s += 1.0; reasons.append("PE %.1f（15-25 合理）" % pe)
        elif pe <= 40: s += 0.6; reasons.append("PE %.1f（25-40 偏贵）" % pe)
        else: reasons.append("PE %.1f（>40 贵）" % pe)
    if pct is not None:
        if pct <= 30: s += 1.4; reasons.append("PE处于近5年 %.0f%% 分位（低）" % pct)
        elif pct <= 60: s += 1.0; reasons.append("PE处于近5年 %.0f%% 分位（中）" % pct)
        elif pct <= 85: s += 0.5; reasons.append("PE处于近5年 %.0f%% 分位（偏高）" % pct)
        else: reasons.append("PE处于近5年 %.0f%% 分位（极高）" % pct)
    sc = m.get("scenarios")
    if sc:
        up = sc["base"]["upside"]
        if up >= 30: s += 1.2; reasons.append("中性情景3年潜在空间 %+.0f%%" % up)
        elif up >= 0: s += 0.6; reasons.append("中性情景3年潜在空间 %+.0f%%" % up)
        else: reasons.append("中性情景3年潜在空间 %+.0f%%（现价偏高）" % up)
    g["安全边际"] = {"score": _clamp(s), "reasons": reasons}

    return g


def three_scenarios(m: dict) -> dict:
    """三情景估值：乐观/中性/悲观 3年目标价。"""
    eps = m.get("eps")
    if not eps:
        return {}
    g_base = 0.12
    cagr_vals = []
    if m.get("np_cagr3") is not None:
        cagr_vals.append(m["np_cagr3"])
    if m.get("rev_cagr3") is not None:
        cagr_vals.append(m["rev_cagr3"])
    if cagr_vals:
        g_base = float(np.mean(cagr_vals))
    if m.get("rev_yoy") is not None:
        g_base = 0.5 * g_base + 0.5 * min(max(m["rev_yoy"] / 100, -0.5), 0.6) * 0.8
    g_base = min(max(g_base, 0.03), 0.30)

    scenarios = {
        "bull": {"growth": g_base * 1.6, "pe": 32, "label": "乐观"},
        "base": {"growth": g_base, "pe": 22, "label": "中性"},
        "bear": {"growth": max(0.0, g_base * 0.25), "pe": 14, "label": "悲观"},
    }
    out = {}
    for key, sc in scenarios.items():
        eps3 = eps * (1 + sc["growth"]) ** 3
        target = eps3 * sc["pe"]
        out[key] = {
            "label": sc["label"],
            "growth": sc["growth"],
            "pe": sc["pe"],
            "target": target,
            "upside": (target / m["close"] - 1) * 100,
        }
    m["scenarios"] = out
    return out


# ---------------- 四大师视角 ----------------

def score_masters(m: dict, gates: dict) -> dict:
    """四大师视角评分（1-5）。"""
    def star(gate):
        return gates.get(gate, {}).get("score", 3.0)

    business = (star("好生意") * 0.6 + star("护城河") * 0.4)
    value = (star("好生意") * 0.4 + star("安全边际") * 0.4 + _roe_score(m) * 0.2)
    certainty = (_roe_score(m) * 0.4 + _stability_score(m) * 0.3 + _debt_score(m) * 0.3)
    risk = 5.0 - _risk_penalty(m)
    return {
        "段永平·商业模式": round(_clamp(business), 2),
        "巴菲特·财务估值": round(_clamp(value), 2),
        "芒格·逆向思考": round(_clamp(risk), 2),
        "李录·长期确定性": round(_clamp(certainty), 2),
    }


def _roe_score(m):
    roe = m.get("roe5")
    if roe is None:
        return 3.0
    if roe >= 20: return 5.0
    if roe >= 15: return 4.0
    if roe >= 10: return 3.0
    return 2.0


def _debt_score(m):
    d = m.get("debt")
    if d is None:
        return 3.0
    if d <= 30: return 5.0
    if d <= 50: return 4.0
    if d <= 70: return 3.0
    return 2.0


def _stability_score(m):
    s = 3.0
    if m.get("roe_std5") is not None and m["roe_std5"] <= 12:
        s += 1.0
    if m.get("gm_std5") is not None and m["gm_std5"] <= 6:
        s += 0.5
    if m.get("rev_cagr3") is not None and m["rev_cagr3"] > 0:
        s += 0.5
    return s


def _risk_penalty(m):
    p = 0.0
    if m.get("pe_pct") is not None and m["pe_pct"] > 85:
        p += 1.5
    if m.get("rsi14") is not None and m["rsi14"] > 75:
        p += 1.0
    if m.get("off_high") is not None and m["off_high"] > -5:
        p += 1.0
    if m.get("debt") is not None and m["debt"] > 60:
        p += 1.0
    if m.get("scenarios") and m["scenarios"]["bear"]["upside"] < -30:
        p += 0.5
    return p


# ---------------- 风险 / 否决 / 镜子测试 ----------------

def risk_flags(m: dict, gates: dict) -> list:
    """自动可检测的风险标记。"""
    flags = []
    if gates.get("护城河", {}).get("score", 3) <= 2:
        flags.append("竞争优势疑似被侵蚀（护城河评分≤2）")
    if m.get("pe_pct") is not None and m["pe_pct"] > 85:
        flags.append("估值处于近5年极高分位（%.0f%%）" % m["pe_pct"])
    if m.get("rsi14") is not None and m["rsi14"] > 75:
        flags.append("RSI %.0f 超买，追高风险（「别人都在买」信号）" % m["rsi14"])
    if m.get("off_high") is not None and m["off_high"] > -3:
        flags.append("股价距52周高点不足3%%，警惕高位")
    if m.get("debt") is not None and m["debt"] > 60:
        flags.append("资产负债率 %.0f%% 偏高" % m["debt"])
    if m.get("scenarios") and m["scenarios"]["bear"]["upside"] < -30:
        flags.append("悲观情景下行超30%，需评估「无法承受归零」")
    if gates.get("好生意", {}).get("score", 3) <= 2:
        flags.append("生意质量差（好生意评分≤2）")
    return flags


def mirror_test(m: dict, gates: dict, sector: str) -> dict:
    """镜子测试：5句话说不完整 = 不买。"""
    gm = gates.get("好生意", {})
    moat = gates.get("护城河", {})
    ms = gates.get("安全边际", {})
    lines = [
        "1. 这门生意的本质是「%s」，请确认：能否一句话讲清它怎么赚钱" % (sector or "未知"),
        "2. 它的护城河信号是：%s" % ("；".join(moat.get("reasons", ["需人工确认"]))[:120] or "需人工确认"),
        "3. 管理层：本地数据无法核验 → 需人工确认是否值得信赖",
        "4. 当前价格对应近5年PE %.0f%% 分位，安全边际评分 %.1f/5" % (m.get("pe_pct", 0), ms.get("score", 3)),
        "5. 即使我错了，悲观情景3年约 %+.0f%% 下行，风险%s" % (
            m.get("scenarios", {}).get("bear", {}).get("upside", 0),
            "可控" if m.get("scenarios", {}).get("bear", {}).get("upside", -99) > -40 else "偏大需谨慎"),
    ]
    complete = "无法确认" not in "".join(lines) and "人工确认" not in "".join(lines)
    return {"lines": lines, "passed": complete, "note": "5句话说不完整 = 不买；第3句需人工确认后补全"}


def final_conclusion(gates: dict, flags: list, mirror: dict) -> dict:
    """最终结论：通过 / 不通过 / 灰色地带。

    快速否决清单是个人判断（能否承受归零/说不清生意等），本地引擎只做证据提示，
    不代替用户自动否决；硬性不通过仅限可量化的客观红线。
    """
    avg = np.mean([gates[k]["score"] for k in ["能力圈", "好生意", "护城河", "管理层", "安全边际"]])
    bs = gates.get("好生意", {}).get("score", 3)
    moat = gates.get("护城河", {}).get("score", 3)
    ms = gates.get("安全边际", {}).get("score", 3)
    if bs <= 2:
        return {"verdict": "不通过", "color": APPLE_RED, "why": "好生意评分 %.1f/5，生意质量不达标" % bs}
    if moat <= 2:
        return {"verdict": "不通过", "color": APPLE_RED, "why": "护城河评分 %.1f/5，竞争优势疑似被侵蚀" % moat}
    if ms <= 2:
        return {"verdict": "不通过", "color": APPLE_RED, "why": "安全边际不足（评分 %.1f/5），好公司买贵了也会亏钱" % ms}
    if not mirror["passed"]:
        return {"verdict": "灰色地带", "color": APPLE_ORANGE,
                "why": "镜子测试未补全（管理层/能力圈需人工确认），暂不构成买入依据"}
    if avg >= 3.5:
        return {"verdict": "通过", "color": APPLE_GREEN,
                "why": "六关平均 %.2f/5，可进入深度研究阶段（仍需人工确认管理层）" % avg}
    return {"verdict": "灰色地带", "color": APPLE_ORANGE,
            "why": "六关平均 %.2f/5，存在关键争议点，需自行判断" % avg}


# ---------------- Apple 风格图表 ----------------

def _apple_rc():
    plt.rcParams.update({
        "font.sans-serif": ["Microsoft YaHei", "PingFang SC", "Arial", "Helvetica", "sans-serif"],
        "axes.unicode_minus": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#e8e8ed",
        "axes.labelcolor": APPLE_DARK,
        "xtick.color": APPLE_GRAY,
        "ytick.color": APPLE_GRAY,
        "text.color": APPLE_DARK,
        "axes.titlecolor": APPLE_DARK,
        "font.size": 12,
    })


def _save(fig, path, tight=True):
    if tight:
        try:
            fig.tight_layout()
        except Exception:
            pass
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _style_ax(ax):
    for sp in ["top", "right"]:
        ax.spines[sp].set_visible(False)
    for sp in ["left", "bottom"]:
        ax.spines[sp].set_color("#d2d2d7")
    ax.grid(axis="y", color="#f0f0f2", linewidth=0.9)
    ax.set_axisbelow(True)


def chart_price(m: dict, price: pd.DataFrame, out_path: str) -> str:
    _apple_rc()
    d = price.copy()
    fig, (ax, axv) = plt.subplots(2, 1, figsize=(11, 5.6), sharex=True,
                                  gridspec_kw={"height_ratios": [3.2, 1]})
    ax.plot(d.index, d["close"], color=APPLE_BLUE, lw=1.8, label="收盘价")
    if "MA20" in d.columns:
        ax.plot(d.index, d["MA20"], color="#ff9500", lw=1.1, label="MA20")
    if "MA60" in d.columns:
        ax.plot(d.index, d["MA60"], color="#86868b", lw=1.1, label="MA60")
    if m.get("high52"):
        ax.axhline(m["high52"], color=APPLE_GREEN, lw=0.9, ls="--", alpha=0.55)
        ax.text(d.index[-1], m["high52"], "  52周高", color=APPLE_GREEN, fontsize=10, va="bottom")
    if m.get("low52"):
        ax.axhline(m["low52"], color=APPLE_RED, lw=0.9, ls="--", alpha=0.55)
        ax.text(d.index[-1], m["low52"], "  52周低", color=APPLE_RED, fontsize=10, va="top")
    ax.set_title("%s · 日线趋势（%s）" % (m["symbol"], m["date"]), loc="left", fontsize=17, fontweight="bold")
    ax.legend(loc="upper left", frameon=False, fontsize=10)
    _style_ax(ax)
    vol_colors = [APPLE_GREEN if c >= o else APPLE_RED for c, o in zip(d["close"], d["open"])]
    axv.bar(d.index, d["volume"], color=vol_colors, alpha=0.65, width=0.7)
    _style_ax(axv)
    axv.set_ylabel("成交量", fontsize=10)
    axv.yaxis.set_major_formatter(lambda x, p: "%.0f亿" % (x / 1e8) if x >= 1e8 else "%.0fM" % (x / 1e6))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    return _save(fig, out_path)


def chart_financials(m: dict, fund: pd.DataFrame, out_path: str) -> str:
    _apple_rc()
    f = fund.tail(10)
    fig, ax = plt.subplots(figsize=(11, 4.6))
    years = f["year"].astype(str)
    ax.plot(years, f["ROE_AVG"], marker="o", ms=4, color=APPLE_BLUE, lw=1.8, label="ROE")
    ax.plot(years, f["GROSS_PROFIT_RATIO"], marker="o", ms=4, color=APPLE_GREEN, lw=1.8, label="毛利率")
    ax.plot(years, f["NET_PROFIT_RATIO"], marker="o", ms=4, color=APPLE_ORANGE, lw=1.8, label="净利率")
    ax.set_title("%s · 财务质量（近10个财年 %%）" % m["symbol"], loc="left", fontsize=17, fontweight="bold")
    ax.legend(loc="upper left", frameon=False, fontsize=10)
    _style_ax(ax)
    for lab in ax.get_xticklabels():
        lab.set_rotation(45)
        lab.set_ha("right")
    return _save(fig, out_path)


def chart_gates(m: dict, gates: dict, out_path: str) -> str:
    _apple_rc()
    names = [g[0] for g in GATES]
    scores = [gates[k]["score"] for k in names]
    colors = []
    for s in scores:
        if s >= 4: colors.append(APPLE_GREEN)
        elif s >= 3: colors.append(APPLE_BLUE)
        elif s >= 2: colors.append(APPLE_ORANGE)
        else: colors.append(APPLE_RED)
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    y = np.arange(len(names))[::-1]
    ax.barh(y, scores, color=colors, height=0.55, alpha=0.92)
    for yi, s in zip(y, scores):
        ax.text(s + 0.06, yi, "%s / 5" % s, va="center", fontsize=11, color=APPLE_DARK)
    ax.set_yticks(y, names, fontsize=12)
    ax.set_xlim(0, 5.6)
    ax.set_title("%s · 买入前六关评分" % m["symbol"], loc="left", fontsize=17, fontweight="bold")
    ax.text(0, -0.85, "第6关·仓位纪律：FOMO 检查 / 停牌5年可否接受 / 200字买入理由（人工确认）",
            fontsize=10, color=APPLE_GRAY)
    _style_ax(ax)
    return _save(fig, out_path)


def chart_masters(m: dict, masters: dict, out_path: str) -> str:
    _apple_rc()
    names = list(masters.keys())
    scores = list(masters.values())
    colors = [APPLE_BLUE, APPLE_GREEN, APPLE_ORANGE, "#af52de"]
    fig, ax = plt.subplots(figsize=(8.6, 4.2))
    y = np.arange(len(names))[::-1]
    ax.barh(y, scores, color=colors, height=0.55, alpha=0.92)
    for yi, s in zip(y, scores):
        ax.text(s + 0.06, yi, "%.1f / 5" % s, va="center", fontsize=11)
    ax.set_yticks(y, names, fontsize=12)
    ax.set_xlim(0, 5.6)
    ax.set_title("%s · 四大师视角对抗" % m["symbol"], loc="left", fontsize=17, fontweight="bold")
    _style_ax(ax)
    return _save(fig, out_path)


def chart_scenarios(m: dict, out_path: str) -> str:
    _apple_rc()
    sc = m.get("scenarios")
    if not sc:
        return ""
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    keys = ["bear", "base", "bull"]
    labels = [sc[k]["label"] for k in keys]
    targets = [sc[k]["target"] for k in keys]
    ups = [sc[k]["upside"] for k in keys]
    colors = [APPLE_RED, APPLE_BLUE, APPLE_GREEN]
    x = np.arange(3)
    bars = ax.bar(x, targets, color=colors, width=0.5, alpha=0.92)
    ax.axhline(m["close"], color=APPLE_DARK, lw=1.4, ls="--")
    ax.text(2.45, m["close"], "  现价 %.2f" % m["close"], va="center", fontsize=10, color=APPLE_DARK)
    for xi, t, u in zip(x, targets, ups):
        ax.text(xi, t, "%.0f\n(%+d%%)" % (t, u), ha="center", va="bottom", fontsize=11, fontweight="bold")
    ax.set_xticks(x, ["悲观\nPE %d" % sc["bear"]["pe"], "中性\nPE %d" % sc["base"]["pe"], "乐观\nPE %d" % sc["bull"]["pe"]], fontsize=11)
    ax.set_title("%s · 三情景 3 年目标价" % m["symbol"], loc="left", fontsize=17, fontweight="bold")
    _style_ax(ax)
    return _save(fig, out_path)


# ---------------- 主入口 ----------------

def run_analysis(symbol: str, sector: str = "", name: str = "", out_root: str = "reports/ai_berkshire") -> dict:
    """执行完整分析，导出图表，返回结果字典。"""
    symbol = symbol.upper()
    price = fetch_price(symbol, days=1500)
    if price is None or price.empty:
        return {"ok": False, "error": "无法获取 %s 的日线数据（数据源限制）" % symbol}
    fund = None
    try:
        fund = fetch_fundamentals(symbol)
    except Exception as e:
        fund = None
    m = compute_metrics(symbol, price, fund)
    three_scenarios(m)
    gates = score_gates(m, sector)
    masters = score_masters(m, gates)
    flags = risk_flags(m, gates)
    mirror = mirror_test(m, gates, sector)
    conclusion = final_conclusion(gates, flags, mirror)

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(out_root, "%s_%s" % (symbol, ts))
    os.makedirs(out_dir, exist_ok=True)

    charts = {}
    try:
        charts["price"] = chart_price(m, price, os.path.join(out_dir, "01_price.png"))
    except Exception:
        charts["price"] = ""
    if fund is not None and len(fund):
        try:
            charts["financials"] = chart_financials(m, fund, os.path.join(out_dir, "02_financials.png"))
        except Exception:
            charts["financials"] = ""
    try:
        charts["gates"] = chart_gates(m, gates, os.path.join(out_dir, "03_gates.png"))
    except Exception:
        charts["gates"] = ""
    try:
        charts["masters"] = chart_masters(m, masters, os.path.join(out_dir, "04_masters.png"))
    except Exception:
        charts["masters"] = ""
    try:
        charts["scenarios"] = chart_scenarios(m, os.path.join(out_dir, "05_scenarios.png"))
    except Exception:
        charts["scenarios"] = ""

    return {
        "ok": True,
        "symbol": symbol,
        "name": name or symbol,
        "sector": sector,
        "metrics": m,
        "gates": gates,
        "masters": masters,
        "flags": flags,
        "mirror": mirror,
        "conclusion": conclusion,
        "fund_rows": fund.tail(6) if fund is not None else None,
        "charts": charts,
        "out_dir": out_dir,
        "time": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

# ---------------- 报告导出 ----------------

def export_md(r: dict, path: str) -> str:
    """把分析结果导出为 Markdown 报告（与 ai-berkshire 的 .md 报告风格一致）。"""
    m = r.get("metrics", {})
    lines = []
    lines.append("# %s · AI 巴菲特价值投资体检" % r.get("symbol", ""))
    lines.append("")
    lines.append("> 生成时间：%s ｜ 数据源：akshare 东财财务指标 + 新浪日线 ｜ 方法论：ai-berkshire（巴菲特六关 + 四大师视角）" % r.get("time", ""))
    lines.append("")
    lines.append("## 结论：%s" % r["conclusion"]["verdict"])
    lines.append("")
    lines.append(r["conclusion"]["why"])
    lines.append("")
    lines.append("## 核心指标")
    lines.append("| 指标 | 数值 |")
    lines.append("|---|---|")
    lines.append("| 现价 | %.2f（%s） |" % (m.get("close", 0), m.get("date", "")))
    lines.append("| PE（最近财年EPS） | %s |" % ("%.1f" % m["pe"] if m.get("pe") else "N/A"))
    lines.append("| PE 近5年分位 | %s |" % ("%.0f%%" % m["pe_pct"] if m.get("pe_pct") is not None else "N/A"))
    lines.append("| ROE 5年均值 | %s |" % ("%.1f%%" % m["roe5"] if m.get("roe5") is not None else "N/A"))
    lines.append("| 毛利率 5年均值 | %s |" % ("%.1f%%" % m["gm5"] if m.get("gm5") is not None else "N/A"))
    lines.append("| 净利率 5年均值 | %s |" % ("%.1f%%" % m["nm5"] if m.get("nm5") is not None else "N/A"))
    lines.append("")
    lines.append("## 六关评分")
    for k, v in r.get("gates", {}).items():
        note = v.get("note") or "；".join(v.get("reasons", []))[:100]
        lines.append("- **%s**：%.1f/5 ｜ %s" % (k, v.get("score", 0), note))
    lines.append("")
    lines.append("## 四大师视角")
    for k, v in r.get("masters", {}).items():
        lines.append("- **%s**：%.2f/5" % (k, v))
    lines.append("")
    sc = m.get("scenarios") or {}
    if sc:
        lines.append("## 三情景估值（3年目标价）")
        lines.append("| 情景 | 年化增长 | 目标PE | 目标价 | 空间 |")
        lines.append("|---|---|---|---|---|")
        for k in ["bear", "base", "bull"]:
            s = sc[k]
            lines.append("| %s | %.0f%% | %d | %.2f | %+.0f%% |" % (s["label"], s["growth"] * 100, s["pe"], s["target"], s["upside"]))
        lines.append("")
    lines.append("## 镜子测试")
    for line in r.get("mirror", {}).get("lines", []):
        lines.append("- " + line)
    lines.append("")
    if r.get("flags"):
        lines.append("## 风险提示")
        for f in r["flags"]:
            lines.append("- " + f)
        lines.append("")
    lines.append("---")
    lines.append("*本报告由本地引擎生成，仅供个人研究参考，不构成投资建议；管理层/能力圈等维度需人工确认。*")
    text = "\n".join(lines)
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(text)
    return path