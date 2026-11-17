"""3570/3221 user-confirmed rulebook and manual planning calculator.

Percentages are percentage points. This module neither verifies market evidence
nor records fills. Use actual confirmed quantities, cost and prior stop as inputs.
"""
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

RULE_VERSION = "3570-3221-user-2026-11-10"
REGIMES = {"strong": "强趋势 · 进攻", "neutral": "中性震荡 · 标准", "defensive": "高风险 · 防御"}
MARKETS = ("us", "hk", "cn", "other")
LIMIT = Decimal("1e15")
HARD_STOP_PCT = 20


def entry_steps(regime, market="us"):
    if regime not in REGIMES or market not in MARKETS:
        raise ValueError("请选择有效的市场状态和市场")
    if regime == "strong":
        return (7, 10)
    if regime == "defensive":
        return (3,)
    return (3, 5, 7) if market == "cn" else (3, 5, 7, 10)


def rulebook():
    return {
        "version": RULE_VERSION,
        "hard_stop_pct": HARD_STOP_PCT,
        "entry": [
            {"regime": k, "label": label, "increments": list(entry_steps(k)),
             "cap_pct": sum(entry_steps(k))}
            for k, label in REGIMES.items()
        ],
        "cn_neutral": {"increments": [3, 5, 7], "cap_pct": 15},
        "exit": {
            "standard": ["10%–15% 首减30%；震荡或弱势可选30%–50%或全退",
                         "15%–30% 首减确认后再减20%",
                         "30%–50% 按上涨分段兑现，每段比例与确认由用户填写",
                         "超过50% 全退，或按计划仅留初始基准股数的10%–30%"],
            "strong": ["盈利达到20%先减30%", "以后相对上次实际减仓价每涨所选10%–15%再减20%",
                       "保留10%–30%底仓的计划到量后停止滚动减仓，跌破盈亏平衡线退出"],
            "basis": "减仓比例采用首次减仓前股数为固定基准；实际股数以成交回执为准",
        },
        "guardrails": ["只在盈利并经新证据确认后加仓；高风险不加仓",
                       "20%按持仓实际成本计算；已设置的更紧保护价不得下调",
                       "止损优先；触发价格与实际成交价格可能不同"],
        "order_enabled": False,
    }


def _num(value, name, minimum=0, strictly=False, whole=False):
    if type(value) not in (int, float, Decimal):
        raise ValueError(name + "必须是数字")
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(name + "无效") from None
    if not d.is_finite() or abs(d) > LIMIT or d < minimum or (strictly and d == minimum):
        raise ValueError(name + "超出有效范围")
    if whole and d != d.to_integral_value():
        raise ValueError(name + "必须是整数")
    return d


def _option(p, key, label):
    return _num(p[key], label, strictly=True) if p.get(key) is not None else None


def protection_price(cost, previous=None):
    cost = _num(cost, "实际成本", strictly=True)
    floor = cost * (1 - Decimal(HARD_STOP_PCT) / 100)
    return max(floor, _num(previous, "原保护价", strictly=True)) if previous is not None else floor


def evaluate(payload):
    if not isinstance(payload, dict):
        raise ValueError("计划必须为对象")
    p = payload
    regime, market = p.get("regime", "neutral"), p.get("market", "us")
    if not isinstance(regime, str) or not isinstance(market, str):
        raise ValueError("市场状态和市场必须为文本")
    steps = entry_steps(regime, market)
    price, cost = _option(p, "price", "评估价"), _option(p, "cost", "实际成本")
    equity, previous = _option(p, "equity", "预算净资产"), _option(p, "stop_price", "原保护价")
    shares = int(_num(p.get("shares", 0), "现持有股数", whole=True))
    stage = int(_num(p.get("entry_stage", 0), "已成交买入档数", whole=True))
    exits = int(_num(p.get("exit_count", 0), "已成交减仓次数", whole=True))
    base = int(_num(p.get("exit_base_shares", shares if not exits else 0), "减仓基准股数", whole=True))
    basis_ready = base >= shares and base > 0
    if base and base < shares:
        raise ValueError("减仓基准股数不能小于现持股数")
    last = _option(p, "last_exit_price", "上次减仓成交价")
    strong_step = _option(p, "strong_step_pct", "牛市滚动涨幅")
    stair_pct = _option(p, "stair_pct", "阶梯减仓比例")
    weak_pct = _num(p.get("weak_exit_pct", 30), "首减比例")
    retain = _num(p.get("retain_pct", 20 if regime == "strong" else 0), "底仓比例")
    break_even = _option(p, "break_even", "盈亏平衡价")
    core = p.get("core_only") is True
    if strong_step is not None and not 10 <= strong_step <= 15:
        raise ValueError("牛市滚动涨幅须在10%至15%")
    if stair_pct is not None and stair_pct > 100:
        raise ValueError("阶梯减仓比例不能超过100%")
    if not (30 <= weak_pct <= 50 or weak_pct == 100):
        raise ValueError("首减比例须为30%至50%，或100%全退")
    if not (retain == 0 or 10 <= retain <= 30):
        raise ValueError("底仓比例须为0，或10%至30%")
    if regime == "strong" and not 10 <= retain <= 30:
        raise ValueError("强趋势滚动方案的底仓比例须为10%至30%")
    entry_regime = p.get("entry_regime", regime)
    if not isinstance(entry_regime, str) or entry_regime not in REGIMES:
        raise ValueError("原建仓市场状态无效")
    if stage > len(entry_steps(entry_regime, market)):
        raise ValueError("已成交买入档数超过该建仓路径")
    profit = (price / cost - 1) * 100 if shares and price and cost else None
    stop = protection_price(cost, previous) if shares and cost else previous if shares else None
    out = {
        "rule_version": RULE_VERSION, "status": "observe", "action": "wait",
        "label": "等待核对交易条件", "order_enabled": False, "execution_ready": False,
        "profit_pct": float(profit) if profit is not None else None,
        "protection_price": float(stop) if stop is not None else None,
        "entry_path_pct": list(steps), "cap_pct": sum(steps),
        "next_increment_pct": steps[stage] if stage < len(steps) else None,
        "entry_budget": None, "suggested_reduce_shares": None, "retain_shares": None,
        "exit_base_shares": base if basis_ready else None,
        "exit_count_confirmed": exits,
    }
    def done(action, label, status="candidate", **kw):
        return {**out, "status": status, "action": action, "label": label, **kw}

    if shares and price and stop and price <= stop:
        return done("hard_stop", "已到保护价：退出剩余持仓，优先于加仓和止盈", suggested_reduce_shares=shares)
    core_qty = int((Decimal(base) * retain / 100).to_integral_value(rounding=ROUND_FLOOR))
    if shares and (core or (exits and basis_ready and 0 < shares <= core_qty)):
        # Fee-aware break-even is not inferable from a snapshot. Require explicit input.
        if not price or not break_even:
            return done("wait", "底仓需核对当前价与实际盈亏平衡价", "observe")
        if price < break_even:
            return done("core_exit", "底仓已跌破盈亏平衡线", suggested_reduce_shares=shares)
        return done("hold_core", "仅余底仓；尚未跌破盈亏平衡线", "observe")
    if shares and profit is None:
        return done("wait", "持仓需填写评估价和实际平均成本", "observe")

    def reduce(pct, label, preserve=True):
        if not basis_ready:
            return done("wait", "请补填首次减仓前的股数；不能用剩余仓位重置基数", "observe")
        available = max(0, shares - (core_qty if preserve else 0))
        n = min(available, int((Decimal(base) * pct / 100).to_integral_value(rounding=ROUND_FLOOR)))
        if not n:
            return done("wait", "按所选比例不足一股，或已到预留底仓；请核对股数", "observe")
        return done("reduce", label, suggested_reduce_shares=n, retain_shares=shares - n)

    if shares and regime != "strong":
        if profit > 50:
            if retain and not basis_ready:
                return done("wait", "超过50%：请核对底仓基准，或选择全部退出", "observe")
            n = max(0, shares - core_qty)
            return done("final_exit" if n else "hold_core",
                        ("超过50%：兑现到所选底仓" if core_qty else "超过50%：全部兑现") if n else "已到预留底仓",
                        "candidate" if n else "observe", suggested_reduce_shares=n, retain_shares=shares-n)
        if profit >= 10 and exits == 0:
            if weak_pct == 100:
                return done("final_exit", "弱势/震荡首段：按所选方案全部兑现", suggested_reduce_shares=shares, retain_shares=0)
            return reduce(weak_pct, "10%起进入首段：先执行并确认首次减仓")
        if profit >= 15 and exits == 1:
            return reduce(Decimal(20), "15%起进入第二段：首次减仓已确认，再减20%")
        if profit >= 30 and exits >= 2:
            if not (stair_pct and p.get("stair_confirmed") is True and last and price > last):
                return done("wait", "第三段：需确认新的上涨分段、上次成交价与本次减仓比例", "observe")
            return reduce(stair_pct, "30%–50%：按确认的上涨分段兑现")
    elif shares and regime == "strong":
        if exits == 0 and profit >= 20:
            return reduce(Decimal(30), "强势牛市首段：盈利达到20%，首减30%")
        if exits > 0 and (not last or strong_step is None or not basis_ready):
            return done("wait", "牛市滚动需填写固定基数、上次减仓成交价和10%–15%涨幅", "observe")
        if exits > 0 and price >= last * (1 + strong_step / 100):
            return reduce(Decimal(20), "强势牛市滚动：达到相对上次减仓成交价的上涨门槛，再减20%")

    if shares and (exits or stage == 0 or entry_regime != regime):
        return done("wait", "已有持仓：减仓后不重启建仓，切换状态或缺少成交档数时先复核", "observe")
    if not shares and (stage or exits or core):
        return done("wait", "已无持仓；新一轮请按新的成交档数与基数重新评估", "observe")
    if stage >= len(steps):
        return done("wait", "当前建仓路径已到上限", "observe")
    if not price or p.get("setup_confirmed") is not True:
        return done("wait", "先核对市场状态、有效价格和本档入场证据", "observe")
    if stage > 0 and (profit is None or profit <= 0 or p.get("add_confirmed") is not True or previous is None):
        return done("wait", "只在持仓盈利、新证据确认且原保护价已核实时加仓", "observe")
    budget = None
    if equity is not None:
        nominal = equity * steps[stage] / 100
        headroom = max(Decimal(0), equity * sum(steps) / 100 - price * shares)
        if headroom == 0:
            return done("wait", "现持仓市值已达到该路径上限，暂停加仓", "observe")
        budget = min(nominal, headroom)
        if budget < nominal:
            return done("wait", "该档完整预算会超过路径上限；暂停并复核账户仓位", "observe",
                        entry_budget=float(budget))
    return done("entry", "本档可列为建仓候选，需再过账户风险与成交确认",
                entry_budget=float(budget) if budget is not None else None)
