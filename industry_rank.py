# -*- coding: utf-8 -*-
"""产业主线赛道 · 六维赛道参考池（高→低排行模板）。

来源：投资认知训练合集「行业赛道排行模板」。
选赛道方法论：自上而下 —— 时代大趋势 → 产业链需求(能源/电力) → 核心资源(铜) → 锁定赛道龙头。
"""
import html

# 赛道排行（rank 越高越靠前，badge 为梯队）
TRACKS = [
    {"rank": 1, "name": "AI 算力链", "tag": "绝对核心", "badge": "三大最确定",
     "kws": ["算力 / IDC", "光模块 / CPO", "液冷 / PCB", "铜缆 / 存储芯片"],
     "note": "AI 时代最强主线，算力即国力"},
    {"rank": 2, "name": "半导体 · 芯片", "tag": "", "badge": "三大最确定",
     "kws": ["国产替代 / 进口替代"], "note": ""},
    {"rank": 3, "name": "核电 · 核能 · 电力 · 电网", "tag": "", "badge": "最强赛道",
     "kws": ["小型反应堆 SMR", "AI 电力需求"], "note": ""},
    {"rank": 4, "name": "稀缺资源 · 铜为首", "tag": "", "badge": "三大最确定",
     "kws": ["铜（AI / 电缆需求）", "稀土", "小金属 / 战略金属"], "note": ""},
    {"rank": 5, "name": "军工 · 太空 · 航天 · 卫星 · 无人机", "tag": "", "badge": "最强赛道",
     "kws": ["太空军工", "卫星互联网 / 太空数据 / 太空能源 / 太空制造 / 月球经济"], "note": ""},
    {"rank": 6, "name": "机器人 · 人形机器人", "tag": "", "badge": "最强赛道",
     "kws": ["具身智能", "机器人神经系统"], "note": ""},
    {"rank": 7, "name": "金融科技", "tag": "", "badge": "延伸赛道",
     "kws": ["互联网券商 / 全球线上经纪", "RWA 资产代币化", "区块链 / 合规牌照"], "note": ""},
]

TOP3_TEXT = "三大最确定：① 进口替代（半导体）　② 稀缺资源（铜为首）　③ AGI 算力基建"


def match_sector(sector):
    """返回当前标的赛道命中的排行索引列表（子串匹配）。"""
    if not sector:
        return []
    s = sector.lower()
    hits = []
    for i, t in enumerate(TRACKS):
        blob = (t["name"] + " " + " ".join(t["kws"])).lower()
        # 赛道名或关键词出现在标的赛道中，或标的赛道出现在关键词中
        if any(kw in s for kw in (t["name"] + " " + " ".join(t["kws"])).split()) or s in blob or any(k.lower() in s for k in t["kws"]):
            hits.append(i)
    return hits


def _badge_color(badge):
    return {
        "三大最确定": "#c9a227",
        "绝对核心": "#c0392b",
        "最强赛道": "#e67e22",
        "延伸赛道": "#7f8c8d",
    }.get(badge, "#7f8c8d")


def render_html(sector=None):
    """生成产业赛道排行面板 HTML（白金色主题）。"""
    hits = match_sector(sector) if sector else []
    items = []
    for t in TRACKS:
        active = (t["rank"] - 1) in hits
        tag_html = ('<span class="irt-tag">%s</span>' % html.escape(t["tag"])) if t.get("tag") else ""
        note_html = ('<div class="irt-note">%s</div>' % html.escape(t["note"])) if t.get("note") else ""
        kws = " · ".join(t["kws"])
        badge_c = _badge_color(t["badge"])
        items.append(
            '<div class="irt-item%s">'
            '  <div class="irt-rank">%d</div>'
            '  <div class="irt-body">'
            '    <div class="irt-name">%s %s</div>'
            '    <div class="irt-kws">%s</div>%s'
            '  </div>'
            '  <div class="irt-badge" style="border-color:%s;color:%s;background:%s22">%s</div>'
            '</div>' % (
                " irt-active" if active else "",
                t["rank"],
                html.escape(t["name"]),
                tag_html,
                html.escape(kws),
                note_html,
                badge_c, badge_c, badge_c, html.escape(t["badge"]),
            ))
    sector_line = ""
    if sector:
        if hits:
            names = "、".join(TRACKS[i]["name"] for i in hits)
            sector_line = ('<div class="irt-current">当前标的赛道：<b>%s</b> → 命中参考池：<span style="color:#c0392b;font-weight:700">%s</span></div>' % (html.escape(sector), html.escape(names)))
        else:
            sector_line = ('<div class="irt-current">当前标的赛道：<b>%s</b> → 未直接命中参考池（属新兴/细分方向，按梯队精神自行定位）</div>' % html.escape(sector))
    return """
<div class="irt-panel">
  <div class="irt-head">
    <div class="irt-title">产业主线赛道 · 六维赛道参考池</div>
    <div class="irt-sub">先选对产业主线，再在主线里挑个股，才有戴维斯双击空间（高 → 低）</div>
  </div>
  <div class="irt-method"><b>选赛道（自上而下）：</b>时代大趋势 → 产业链需求（能源/电力） → 核心资源（铜） → 锁定赛道龙头</div>
  <div class="irt-top3">%s</div>
  %s
  <div class="irt-list">%s</div>
  <div class="irt-disc">⚠️ 参考池随产业周期与时代大事动态变化，非静态名单；仅供赛道定位参考，不构成投资建议。</div>
</div>
""" % (TOP3_TEXT, sector_line, "\n".join(items))


STYLE = """
<style>
.irt-panel { font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; }
.irt-head { background: linear-gradient(120deg, #fff8e6, #fdf0d5); border: 1px solid rgba(201,162,39,0.35); border-radius: 14px; padding: 16px 20px; margin-bottom: 12px; }
.irt-title { font-size: 22px; font-weight: 800; color: #5c2e2e; }
.irt-sub { font-size: 13px; color: #8a6d3b; margin-top: 4px; }
.irt-method { background: #fff; border: 1px solid rgba(201,162,39,0.25); border-radius: 10px; padding: 10px 14px; margin-bottom: 8px; color: #5c2e2e; font-size: 14px; }
.irt-top3 { background: linear-gradient(90deg, #fdf0d5, #fff); border: 1px solid rgba(192,57,43,0.3); border-left: 5px solid #c0392b; border-radius: 10px; padding: 10px 14px; margin-bottom: 14px; color: #8b1a1a; font-weight: 600; font-size: 14px; }
.irt-current { background: #fff8e6; border: 1px dashed rgba(201,162,39,0.5); border-radius: 10px; padding: 10px 14px; margin-bottom: 12px; font-size: 14px; color: #5c2e2e; }
.irt-list { display: flex; flex-direction: column; gap: 10px; }
.irt-item { display: flex; align-items: center; gap: 14px; background: #fff; border: 1px solid rgba(201,162,39,0.22); border-radius: 12px; padding: 12px 16px; box-shadow: 0 1px 4px rgba(201,162,39,0.08); }
.irt-item.irt-active { border: 2px solid #c9a227; box-shadow: 0 2px 12px rgba(201,162,39,0.25); background: linear-gradient(90deg, #fffdf5, #fff7e6); }
.irt-rank { min-width: 34px; height: 34px; border-radius: 50%; background: linear-gradient(135deg, #c9a227, #e6b94e); color: #fff; font-weight: 800; font-size: 16px; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 6px rgba(201,162,39,0.35); }
.irt-item:nth-child(n+4) .irt-rank { background: linear-gradient(135deg, #c0392b, #e0654f); }
.irt-body { flex: 1; }
.irt-name { font-size: 16px; font-weight: 700; color: #5c2e2e; }
.irt-tag { display: inline-block; background: #c0392b; color: #fff; font-size: 11px; font-weight: 700; border-radius: 8px; padding: 1px 8px; margin-left: 8px; vertical-align: 2px; }
.irt-kws { font-size: 13px; color: #7a5c38; margin-top: 3px; }
.irt-note { font-size: 12px; color: #b9a06a; margin-top: 2px; font-style: italic; }
.irt-badge { border: 1px solid; border-radius: 999px; padding: 4px 12px; font-size: 12px; font-weight: 700; white-space: nowrap; }
.irt-disc { margin-top: 14px; font-size: 12px; color: #a08555; }
</style>
"""