# -*- coding: utf-8 -*-
"""自选股本地持久化（单用户本地应用，JSON 文件即可，无需数据库服务）。

结构：{"groups": {"赛道名": ["代码", ...]}, "selected": "代码"}
赛道名以 industry_rank.TRACKS 为基准；代码统一大写去空格。
"""
import json
import os

import industry_rank as ir

_DIR = os.path.dirname(os.path.abspath(__file__))
_PATH = os.path.join(_DIR, "watchlist.json")


def _track_names():
    return [t["name"] for t in ir.TRACKS]


def _norm(code):
    return str(code or "").strip().upper()


def _empty():
    return {"groups": {name: [] for name in _track_names()}, "selected": ""}


def load():
    """读取自选股；缺失的赛道自动补空组，旧赛道保留。"""
    data = _empty()
    try:
        if os.path.exists(_PATH):
            with open(_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            groups = raw.get("groups", {}) if isinstance(raw, dict) else {}
            for name in _track_names():
                if name not in groups:
                    groups[name] = []
            data["groups"] = {
                k: [_norm(x) for x in v if _norm(x)]
                for k, v in groups.items() if k in _track_names()
            }
            data["selected"] = _norm(raw.get("selected", ""))
    except Exception:
        data = _empty()
    return data


def save(data):
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add(data, group, code):
    code = _norm(code)
    if not code:
        return data
    if group not in data["groups"]:
        data["groups"][group] = []
    if code not in data["groups"][group]:
        data["groups"][group].append(code)
    save(data)
    return data


def remove(data, group, code):
    code = _norm(code)
    if group in data["groups"] and code in data["groups"][group]:
        data["groups"][group].remove(code)
    if data.get("selected") == code:
        data["selected"] = ""
    save(data)
    return data


def remove_anywhere(data, code):
    code = _norm(code)
    for g in list(data["groups"]):
        if code in data["groups"][g]:
            data["groups"][g].remove(code)
    if data.get("selected") == code:
        data["selected"] = ""
    save(data)
    return data


def all_codes(data):
    seen, out = set(), []
    for g in data["groups"]:
        for c in data["groups"][g]:
            if c not in seen:
                seen.add(c)
                out.append(c)
    return out
