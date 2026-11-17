"""Unvalidated swing research template; completed bars only, no execution adapter."""
from __future__ import annotations
import math
from datetime import datetime
import trade_engine as engine
import swing_confluence
from indicators import add_indicators

VERSION = 'swing-confluence-plan-v1'
SOURCE_IDS = ['aqr', 'man', 'ibkr', 'quantconnect']

def decision(raw, source, values=None, now=None):
    if isinstance(now, str):
        now = datetime.fromisoformat(now.replace("Z", "+00:00"))
    base = engine.decision(raw, source, values, now)
    out = {**base, 'version': VERSION, 'template': '多空波段共振',
           'validation': '研究假设，尚未验证收益；55/20回测不适用于此模板',
           'source_ids': SOURCE_IDS, 'sides': {}, 'signals': [],
           'horizon': {'review_session': 3, 'time_exit_session': 5,
                       'note': '候选纪律：实际成交日为T，T+3复查；T+5未兑现则退出候选。尚未回测，无成交时不启动倒计时。'}}
    if not base.get('available'):
        return out
    clean, _ = engine.prepare(raw, now)
    evidence = swing_confluence.evaluate(add_indicators(clean), now)
    out['confluence'] = evidence
    latest = evidence.get('latest', {})
    close, atr = base['close'], base['atr']
    ratio, ma20 = latest.get('volume_ratio'), latest.get('ma20')
    signal = evidence.get('latest_signal')
    for side, sign in [('long', 1), ('short', -1)]:
        directional = latest.get('kdj_side') == latest.get('macd_side') == ('up' if sign == 1 else 'down')
        trend = ma20 is not None and (close - ma20) * sign > 0
        vol = ratio is not None and math.isfinite(ratio) and ratio >= 1
        crossover = bool(signal and signal['direction'] == side)
        stop = close - sign * 2 * atr
        sensible = close > 0 and stop > 0
        eligible = bool(base['current_eligible'] and evidence.get('available') and not evidence.get('stale') and sensible)
        triggered = bool(eligible and crossover and trend and vol)
        status = ('技术触发 · 待执行核验' if triggered else
                  '条件冲突 · 暂缓该方向' if not trend or not directional else '观察中 · 等待同日共振与量能')
        if not eligible:
            status = '数据或风险价格待核验 · 暂停当前提示'
        out['sides'][side] = {
            'direction': side, 'triggered': triggered, 'stage': 'triggered' if triggered else 'observe',
            'status': status, 'entry': close, 'stop': stop if sensible else None,
            'target2r': close + sign * 4 * atr if close + sign * 4 * atr > 0 else None,
            'target3r': close + sign * 6 * atr if close + sign * 6 * atr > 0 else None,
            'sizing': engine.size(close, atr, base['parameters']) if eligible else None,
            'entry_note': '最新完成收盘为情景基准；技术触发后仍须核验，实际下一开盘按成交价重算',
            'checks': [
                {'label': '同日双金叉' if sign == 1 else '同日双死叉', 'passed': crossover},
                {'label': '收盘高于MA20' if sign == 1 else '收盘低于MA20', 'passed': trend},
                {'label': '量比≥1（此前20日）', 'passed': vol}],
            'execution_checks': base['sides'][side]['execution_checks'] + ['行业、估值和催化剂需独立研究'],
            'executable': False,
        }
    return out
