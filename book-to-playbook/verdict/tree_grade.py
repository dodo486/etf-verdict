#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조건 트리(books/<slug>/tree.json) → 날짜별 등급 (책 무관).

등급 (COND_DSL.md 1절):
  filter 거짓 → 🚫 진입 금지 · avoid 참 → ⛔ 보류 · entry 참 → ✅ 매수 후보 · entry 거짓 → ⚪ 관망
수동(manual) 조건은 '확인됨/안 됨' 두 번 평가한다:
  안 돼도 매수(비관) → ✅ · 확인돼야 매수(낙관만) → 🟡 확인 대기 · 데이터 부족으로 못 정함 → ❔ 판정 불가
  비관 = filter·entry 의 수동은 거짓, avoid 의 수동은 참 / 낙관 = 그 반대.

판정은 종가 직후(그날까지의 일봉)로 낸다 — cond 연산이 전부 인과적이라 전체 이력을 한 번 계산해
날짜로 꺼내도 미래를 보지 않는다(verify_primitives 가 강제).
"""
import json
import os

from shared.paths import BASE
from verdict import cond

GRADES = {
    "buy": "✅ 매수 후보",
    "confirm": "🟡 확인 대기",
    "nofilter": "🚫 진입 금지",
    "avoid": "⛔ 보류",
    "wait": "⚪ 관망",
    "unknown": "❔ 판정 불가",
}


def tree_path(slug, name="tree.json"):
    return os.path.join(BASE, "books", slug, name)


def load_tree(slug, name="tree.json"):
    """트리 파일을 읽고 문법 검사까지 한다. 없으면 None, 문법 오류면 CondError."""
    p = tree_path(slug, name)
    if not os.path.exists(p):
        return None
    t = json.load(open(p, encoding="utf-8"))
    cond.validate_tree(t)
    return t


class ProductEval:
    """한 상품의 세 구역을 전체 달력에 대해 한 번 계산해 둔다."""

    def __init__(self, tree, prod, hist, cal):
        cfg = tree["products"][prod]
        defs = tree.get("defs") or {}
        self.tree, self.prod, self.cfg, self.defs, self.cal = tree, prod, cfg, defs, list(cal)
        mk = lambda m: cond.Ctx(hist, cal, prod, cfg.get("index"), defs, manual_as=m)
        self.ctx = {True: mk(True), False: mk(False), None: mk(None)}
        s = lambda sec, m: cond.series(cfg[sec], self.ctx[m])
        self.opt = {"filter": s("filter", True), "entry": s("entry", True), "avoid": s("avoid", False)}
        self.pes = {"filter": s("filter", False), "entry": s("entry", False), "avoid": s("avoid", True)}

    def grade_key(self, i):
        fo, eo, ao = self.opt["filter"][i], self.opt["entry"][i], self.opt["avoid"][i]
        fp, ep, ap = self.pes["filter"][i], self.pes["entry"][i], self.pes["avoid"][i]
        if fp is True and ap is False and ep is True:
            return "buy"
        if fo is True and ao is False and eo is True:
            return "confirm"
        if fo is False:
            return "nofilter"
        if ao is True:
            return "avoid"
        if fo is True and ao is False and eo is False:
            return "wait"
        return "unknown"

    def explain(self, i):
        """라벨 달린 노드의 그날 값 — 수동은 '모름'(None)으로 둔 평가. {구역: [(label, ref, 값)]}"""
        out = {}
        for sec in cond.SECTIONS:
            rows = []
            for n in cond.labeled(self.cfg[sec], self.defs):
                v = cond.series(n, self.ctx[None])[i]
                rows.append((n.get("label"), n.get("ref"), v))
            out[sec] = rows
        return out

    def top(self, i):
        """구역마다 맨 위 라벨 노드들의 그날 값(사유 문장용 — 안쪽 노드까지 늘어놓으면
        not 아래의 '거짓 = 정상' 노드가 '미충족'으로 읽힌다). 수동은 모름(None)."""
        out = {}
        for sec in cond.SECTIONS:
            out[sec] = [(n.get("label"), n.get("ref"), cond.series(n, self.ctx[None])[i])
                        for n in _top_labeled(self.cfg[sec], self.defs)]
        return out

    def manual_items(self):
        out = []
        for sec in cond.SECTIONS:
            for n in cond.manual_leaves(self.cfg[sec], self.defs):
                out.append((sec, n.get("label") or n["manual"], n.get("ref")))
        return out


def _top_labeled(node, defs):
    """라벨 달린 가장 바깥 노드들. all/any/atleast 는 펼치고, not 아래는 들어가지 않는다."""
    if not isinstance(node, dict):
        return []
    if node.get("label"):
        return [node]
    if "def" in node and node["def"] in defs:
        return _top_labeled(defs[node["def"]], defs)
    kids = node.get("all") or node.get("any") or (node.get("of") if "atleast" in node else None) or []
    out = []
    for k in kids:
        out.extend(_top_labeled(k, defs))
    return out


def reason_of(key, ex, manual):
    """등급 사유 한 줄 — 무엇이 걸렸는지 라벨로."""
    def labels(sec, val):
        return [l for l, _, v in ex.get(sec, []) if l and v is val]
    if key == "nofilter":
        bad = labels("filter", False)
        return "필터 미충족: " + (" · ".join(bad[:3]) if bad else "전제 조건 거짓")
    if key == "avoid":
        hit = labels("avoid", True)
        return "회피 신호: " + (" · ".join(hit[:3]) if hit else "회피 조건 참")
    if key == "wait":
        return "진입 조건 미충족 — 매수 자리 아님"
    if key == "confirm":
        items = [l for s, l, _ in manual if s in ("filter", "entry")] + \
                ["(회피 아님) " + l for s, l, _ in manual if s == "avoid"]
        return "수동·장중 확인 시 매수: " + " · ".join(items[:4])
    if key == "buy":
        ok = labels("entry", True)
        return "필터 통과 · 회피 없음 · 진입: " + (" · ".join(ok[:3]) if ok else "조건 충족")
    return "데이터 부족으로 판정 불가"


def symbols(tree):
    return cond.symbols_of(tree)
