#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조건 트리(books/<slug>/tree.json) → 날짜별 판정 (책 무관). 트리의 '뜻'은 여기 한 벌뿐이다.

등급 (COND_DSL.md 1절, 조건 칸 셋):
  filter 거짓 → 🚫 진입 금지 · avoid 참 → ⛔ 보류 · entry 참 → ✅ 매수 후보 · entry 거짓 → ⚪ 관망
수동(manual) 조건은 '확인됨/안 됨' 두 번 평가한다:
  안 돼도 매수(비관) → ✅ · 확인돼야 매수(낙관만) → 🟡 확인 대기 · 데이터 부족으로 못 정함 → ❔ 판정 불가
  비관 = filter·entry 의 수동은 거짓, avoid 의 수동은 참 / 낙관 = 그 반대.
규칙 칸 셋:
  caution  걸린 규칙마다 그날 금액 × scale (null = 줄일 폭 저자 미명시)
  sizing   weight = 총 투자금 대비 비중(%) · tranches = 분할 매수(2차 이후는 포지션 값으로)
  exit     보유분의 매도 — 내 포지션이 있을 때만 평가(position_state)

판정은 봉이 끝난 직후(그날까지의 봉)로 낸다 — cond 연산이 전부 인과적이라 전체 이력을 한 번 계산해
날짜로 꺼내도 미래를 보지 않는다(verify_primitives 가 강제).
"""
import json
import os

from shared.paths import BASE
from shared import cond, md_feed

GRADES = {
    "buy": "✅ 매수 후보",
    "confirm": "🟡 확인 대기",
    "nofilter": "🚫 진입 금지",
    "avoid": "⛔ 보류",
    "wait": "⚪ 관망",
    "unknown": "❔ 판정 불가",
}
OP_WORD = {"all": "모두", "any": "하나 이상", "not": "아님"}


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


def history(trees, start):
    """트리(들)가 쓰는 모든 심볼의 일봉 — 수집 단계(md_feed.histories) 하나로 받는다."""
    syms = set()
    for t in trees if isinstance(trees, list) else [trees]:
        syms |= cond.symbols_of(t)
    return md_feed.histories(syms, start)


class ProductEval:
    """한 상품의 여섯 칸을 전체 달력에 대해 한 번 계산해 둔다."""

    def __init__(self, tree, prod, hist, cal):
        cfg = tree["products"][prod]
        defs = tree.get("defs") or {}
        self.tree, self.prod, self.cfg, self.defs, self.cal, self.hist = tree, prod, cfg, defs, list(cal), hist
        mk = lambda m: cond.Ctx(hist, cal, prod, cfg.get("index"), defs, manual_as=m)
        self.ctx = {True: mk(True), False: mk(False), None: mk(None)}
        s = lambda node, m: cond.series(node, self.ctx[m])
        self.opt = {"filter": s(cfg["filter"], True), "entry": s(cfg["entry"], True), "avoid": s(cfg["avoid"], False)}
        self.pes = {"filter": s(cfg["filter"], False), "entry": s(cfg["entry"], False), "avoid": s(cfg["avoid"], True)}
        self.caution = [(r, s(r["when"], None)) for r in cfg.get("caution") or []]
        w = (cfg.get("sizing") or {}).get("weight")
        self.weight = {m: (s(w, m) if w is not None else None) for m in (None, True, False)}

    # ---------------------------------------------------------------- 등급
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

    # ---------------------------------------------------------------- 금액
    def caution_state(self, i):
        """[{label, ref, note, scale, value, manual}] — value 는 수동 = 모름으로 둔 평가."""
        return [{"label": r["label"], "ref": r.get("ref"), "note": r.get("note"), "scale": r.get("scale"),
                 "value": ser[i], "manual": [n["manual"] for n in cond.manual_leaves(r["when"], self.defs)]}
                for r, ser in self.caution]

    def weight_of(self, i):
        """그날 비중(%) — 수동 때문에 모르면 (None, [가능한 값들]) 로 범위를 함께 돌려준다."""
        if self.weight[None] is None:
            return None, None
        v = self.weight[None][i]
        if v is not None:
            return v, None
        alt = sorted({x for x in (self.weight[True][i], self.weight[False][i]) if x is not None})
        return None, alt or None

    def amount_factor(self, i):
        """(금액 배수, 폭 미명시로 걸린 규칙, 확인이 필요한 규칙) — 걸린 caution 의 scale 곱."""
        f, unspecified, unknown = 1.0, [], []
        for st in self.caution_state(i):
            if st["value"] is True:
                if st["scale"] is None:
                    unspecified.append(st["label"])
                else:
                    f *= st["scale"]
            elif st["value"] is None:
                unknown.append(st["label"])
        return f, unspecified, unknown

    # ---------------------------------------------------------------- 설명
    def explain(self, i):
        """라벨 달린 노드의 그날 값 — 수동은 '모름'(None)으로 둔 평가. {구역: [(label, ref, 값)]}"""
        out = {}
        for sec in cond.SECTIONS:
            out[sec] = [(n.get("label"), n.get("ref"), cond.series(n, self.ctx[None])[i])
                        for n in cond.labeled(self.cfg[sec], self.defs)]
        return out

    def top(self, i):
        """구역마다 맨 위 라벨 노드들의 그날 값(사유 문장용 — 안쪽 노드까지 늘어놓으면
        not 아래의 '거짓 = 정상' 노드가 '미충족'으로 읽힌다). 수동은 모름(None)."""
        out = {}
        for sec in cond.SECTIONS:
            out[sec] = [(n.get("label"), n.get("ref"), cond.series(n, self.ctx[None])[i])
                        for n in _top_labeled(self.cfg[sec], self.defs)]
        return out

    def view(self, node, i):
        """화면용 중첩 설명 — 노드 하나당 항목 하나(_view). 수동은 모름으로 둔 그날 값."""
        return _view(node, self.defs, self.ctx[None], i)

    def manual_items(self):
        out = []
        for z, _l, _r, node in cond.zone_nodes(self.cfg):
            if z == "exit":
                continue
            for n in cond.manual_leaves(node, self.defs):
                out.append((z, n.get("label") or n["manual"], n.get("ref")))
        return out


LOGICAL = ("all", "any", "atleast", "not")


def product_specific(node, defs):
    """$self/$index/pos 를 쓰는 식은 상품마다 값이 달라진다 — 여러 상품이 '같이 보는' 판단이 아니다."""
    for n in cond.labeled_all(node, defs):
        if "px" in n and n.get("sym", "$self") in ("$self", "$index"):
            return True
        if "pos" in n:
            return True
    return False


def _view(node, defs, ctx, i, shared=False):
    """노드 하나 → 화면 항목 하나 {v, op?, n?, kids?, label?, ref?, manual?, note?, hidden?}.

    · 논리 노드(all/any/atleast/not)는 op 와 자식 항목 전부를 담는다 — 화면이 사람이 체크한 수동 조건으로
      같은 3값 논리를 다시 계산할 수 있게(not 아래 수동은 극성이 뒤집힌다 — cond 와 같은 규칙).
    · 그 밖의 노드는 그날 값(v)이 고정된 잎이다. 라벨이 없으면 hidden(화면에 안 보이지만 계산엔 쓴다),
      안쪽에 라벨 달린 노드가 있으면 참고용 kids(op 없음 — 다시 계산하지 않는다)로 붙인다.
    · 라벨 없는 정의 참조는 정의 본문으로, 라벨 달린 정의 참조는 op "ref"(값 = 유일한 자식)로.
    · 상품마다 값이 같은 정의(product_specific 아님) 안의 수동 조건은 shared=True — 화면에서 한 번 체크하면
      그 조건을 쓰는 모든 상품에 같은 답이 들어간다(같은 시장 사실이므로).
    v 는 수동 = 모름(None)으로 둔 그날 값이다."""
    if "def" in node and node["def"] in defs and not node.get("label")             and not [k for k in node if k not in cond.META and k != "def"]:
        body = defs[node["def"]]
        return _view(body, defs, ctx, i, shared or not product_specific(body, defs))
    op = next((k for k in node if k not in cond.META and k not in ("of", "sym", "tf", "else")), None)
    item = {"v": cond.series(node, ctx)[i]}
    for k in ("label", "ref", "note"):
        if node.get(k):
            item[k] = node[k]
    if op == "manual":
        item["manual"] = node["manual"]
        if shared:
            item["shared"] = True
    elif op in LOGICAL:
        kids = node[op] if op in ("all", "any") else (node["of"] if op == "atleast" else [node["not"]])
        kctx = ctx.flipped() if op == "not" else ctx
        item["op"] = op
        if op == "atleast":
            item["n"] = node["atleast"]
        item["kids"] = [_view(k, defs, kctx, i, shared) for k in kids]
    elif op == "def":
        body = defs[node["def"]]
        item["op"] = "ref"
        item["kids"] = [_view(body, defs, ctx, i, shared or not product_specific(body, defs))]
    else:
        inner = [_view(k, defs, ctx, i, shared) for k in _labeled_inside(node, defs)]
        if inner:
            item["kids"] = inner
        if not node.get("label"):
            item["hidden"] = True
    return item


def _labeled_inside(node, defs):
    """잎 노드 안쪽의 가장 바깥 라벨 노드들(참고 표시용)."""
    out = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("label") or "manual" in n:
                out.append(n)
                return
            if "def" in n and n["def"] in defs:
                walk(defs[n["def"]])
                return
            for k, x in n.items():
                if k not in cond.META:
                    walk(x)
        elif isinstance(n, list):
            for x in n:
                walk(x)
    for k, x in node.items():
        if k not in cond.META:
            walk(x)
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


def position_state(tree, prod, hist, cal, entry_date, cost, filled=1):
    """내 포지션(첫 매수일·평균 매입가·산 차수)의 오늘 매도·추가 매수 규칙 상태.
    → {ret, days, exit:[{label, ref, sell, v, view}], next_tranche:{label, ref, frac, v, view}|None}"""
    cfg, defs = tree["products"][prod], tree.get("defs") or {}
    later = [k for k, d in enumerate(cal) if d >= entry_date]
    if not later:
        return {"error": "첫 매수일 %s 이후 시세 없음" % entry_date}
    ctx = cond.Ctx(hist, cal, prod, cfg.get("index"), defs, manual_as=None, pos=(later[0], cost))
    i = len(cal) - 1
    out = {"ret": cond.series({"pos": "ret"}, ctx)[i], "days": cond.series({"pos": "days"}, ctx)[i],
           "exit": [{"label": r["label"], "ref": r.get("ref"), "sell": r["sell"],
                     "v": cond.series(r["when"], ctx)[i], "view": _view(r["when"], defs, ctx, i)}
                    for r in cfg.get("exit") or []]}
    trs = (cfg.get("sizing") or {}).get("tranches") or []
    nt = trs[filled] if 0 < filled < len(trs) else None
    out["next_tranche"] = None if nt is None else {
        "label": nt["label"], "ref": nt.get("ref"), "frac": nt["frac"],
        "v": cond.series(nt["when"], ctx)[i], "view": _view(nt["when"], defs, ctx, i)}
    return out
