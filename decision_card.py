# -*- coding: utf-8 -*-
"""决策卡生成器：按「美股波段战法系统」skill 模板 + 大师智慧核对，输出 Markdown 决策卡。"""
import master_insights as mi
import datetime as dt


def build_decision_card(ticker, name, sector, df, signals, score5, temp, qt,
                        index_df, index_name, cost=None, quote=None):
    last = df.iloc[-1]
    date = df.index[-1].strftime("%Y-%m-%d")
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = []
    lines.append(f"## 【决策卡】{ticker} · {name}　({now})")
    lines.append("")
    lines.append(f"> 数据截至 {date} 收盘 · 分析框架：美股波段战法系统 + 投资认知决策系统")
    lines.append("")

    # 1 大势
    t_label = f"{temp['temp']}°C {temp['label']}"
    lines.append("### 1. 大势判断")
    lines.append(f"- 大盘（{index_name}）：市场温度 **{t_label}**，RSI={temp['rsi']}，60日区间位置={temp['pos60']}%")
    lines.append(f"- 是否创新低：**否**（若需精确判断请以 {index_name} 日线为准）")
    lines.append("- 超短前提：大盘震荡不创新低 → " + ("**满足**" if temp['temp'] >= 25 else "**不满足（偏冷）**"))
    lines.append("")

    # 2 板块
    lines.append("### 2. 板块判断")
    lines.append(f"- 赛道：**{sector}**（战法主线赛道参考：半导体芯片/存储/AI算力/AGI太空 为最强梯队）")
    lines.append("- 板块是否创新低：以标的 60 日区间判断 → " + ("**否**" if signals["range60"]["创新低"] == "否" else "**是（谨慎）**"))
    lines.append("")

    # 3 技术信号
    lines.append("### 3. 技术信号")
    lines.append("| 指标 | 数值 | 判定 |")
    lines.append("|---|---|---|")
    lines.append(f"| KDJ J值 | {signals['kdj']['J值']}（前日 {signals['kdj']['前日J值']}） | {signals['kdj']['状态']} |")
    _mk = signals.get("macd_kdj") or {}
    lines.append(f"| MACD+KDJ 共振 | {_mk.get('双指标共振', '—')} | {_mk.get('信号', '—')} |")
    lines.append(f"| 收盘 vs MA5 | {signals['ma5']['偏离MA5']} | {signals['ma5']['信号']} |")
    lines.append(f"| 均线 | {signals['ma']['MA5/10/20/60']} | {signals['ma']['信号']} |")
    lines.append(f"| RSI14 | {last['RSI']:.1f} | {'7.5 附近=持有/右侧时机' if abs(last['RSI'] - 7.5) < 5 else '常规读数'} |")
    lines.append(f"| 量能 | 3日量比 {signals['volume']['3日量比(20日均)']} / 7日 {signals['volume']['7日量比(20日均)']} | {signals['volume']['信号']} |")
    lines.append(f"| 分歧周期 | {signals['cycle']['分歧期位置']} | {signals['cycle']['信号']} |")
    lines.append(f"| 60日区间 | {signals['range60']['60日低/高']} | 创新低:{signals['range60']['创新低']} |")
    lines.append("")

    # 4 分时
    lines.append("### 4. 分时结构（盘中确认）")
    lines.append("- 本卡以日线生成；盘中需确认 **V 型 / W 型 / 三低点结构** 后再决定当日进场。")
    lines.append("")

    # 5 买卖建议
    lines.append("### 5. 买卖建议（按战法纪律）")
    kdj_sig = signals["kdj"]["信号"]
    lines.append(f"- KDJ 信号：{kdj_sig}")
    lines.append(f"- MACD+KDJ 共振（主信号，需两指标共振才算强买卖点）：{(signals.get('macd_kdj') or {}).get('信号', '—')}")
    if cost and cost > 0:
        gain = (last["close"] / cost - 1) * 100
        lines.append(f"- 3221 浮盈参考 {gain:+.1f}%；请在阵型面板核对市场状态与已成交减仓档次。")
    lines.append("- 止损纪律：3570/3221成本保护为20%，已定更紧保护价沿用；超短1.5%至3%和MA5×0.925为各自独立参考。")
    lines.append(f"- 时间止损：T+3 未兑现退出，T+5 强制退出")
    lines.append("")

    # 6 综合结论与风控
    lines.append("### 6. 综合结论")
    lines.append(f"- 五维评分：赛道{score5['赛道']} / 成长{score5['成长']} / 估值{score5['估值']} / 风险{score5['风险']} / 趋势{score5['趋势']} → 综合 **{score5['综合']}**（{score5['质量档']}）")
    lines.append(f"- 质量×时机矩阵：**{qt['质量']} × {qt['时机']}** → 结论：**{qt['结论']}**")
    lines.append(f"- 仓位建议：单笔超短 ≤ 总资金 5%；单行业 ≤ 30%、单股 ≤ 20%；留 ≥10% 现金")
    lines.append(f"- 认知提醒：避免追高（大盘温度 {t_label}）；不摊平亏损；利润是风险的开始，阶梯止盈")
    # 7 大师原则核对（六本经典提炼）
    mc = mi.master_checklist(signals, score5, temp, qt, df, index_df)
    lines.append("### 7. 大师原则核对（格雷厄姆/林奇/达利欧/马克斯/芒格/巴菲特）")
    lines.append(f"- 市场先生情绪：**{mc['市场先生']}**（格雷厄姆·马克斯：极端情绪=反向机会）")
    lines.append(f"- 宏观周期位置：**{mc['周期位置']}**（达利欧：先定周期再定仓位）")
    lines.append(f"- 公司类型：**{mc['公司类型']}**（林奇：不同类型不同玩法）")
    lines.append(f"- 安全边际：**{mc['安全边际']}**（格雷厄姆：价格低于价值才出手）")
    lines.append(f"- 赚什么钱：**{mc['赚钱来源']}**（巴菲特：想清楚盈利来源才能拿得住）")
    lines.append(f"- 芒格逆向检查：违规/提示 **{mc['芒格违规数']}** 项（反过来想，先防亏）")
    lines.append("- 第二层思维（马克斯）：")
    for q, a in mc["第二层思维"]:
        lines.append(f"  - {q} → {a}")
    lines.append("")
    lines.append("---")
    lines.append("*仅供个人研究参考，不构成投资建议。决策由用户人工执行。*")
    return "\n".join(lines)
