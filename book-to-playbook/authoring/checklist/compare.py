#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""심판의 비교 도구 + a·b '같은 뜻' 잣대 (구간②, 책 무관). 트리를 만들거나 고치지 않는다(판단은 심판이 원문으로).

  · 잣대 — logic_key·rule_keys·pair_rules·factorable: 이름·출처(META)를 뗀 정규화 식으로 '같은 뜻'을 가린다.
           채점기(verify_tree.py)도 이 한 벌로 채점한다 — 심판이 본 비교 = 채점 기준(두 벌이면 갈라진다).
  · 실제 시세 비교 — history·evaluate·window·compare: 두 트리를 판정과 같은 판단자(signals/judge.Judge)로 날마다 평가.
  · 덤프 — dump_disagreements: 규칙 짝(common·only_a·only_b)·조건 짝·식 모양 차이·판정이 갈린 날 N개씩을
           books/<slug>/logs/disagree.json 으로.

사용: python -m authoring.checklist.compare <slug> [N=6] [--years 3]
"""
import json
import sys
from datetime import datetime, timedelta

from shared import paths  # noqa: F401  (UTF-8 출력)
from shared.paths import book_log, write_text
from dsl.tradeTool import Cond
from signals.judge import Judge

COMPARED = Cond.GATES + ("weight",)                   # 날마다 비교하는 것(등급 동사 둘 + 비중 — 분할·판다는 거래로)
SHAPES = COMPARED + (Cond.SELL,)                       # 모양(식)을 비교하는 것


# ------------------------------------------------------------------ 실제 시세 평가
def history(books, years):
    return Judge.shared_prices([b for b in books if b], int(365 * years))


def _day_values(judge, i):
    """그날 값 — 등급 동사는 수동 = 모름 평가, 비중은 (값, 범위)."""
    out = {do: judge.gate_value(do, i) for do in Cond.GATES}
    w, alt = judge.weight_at(i)
    out["weight"] = (None if w is None else round(w, 6), tuple(alt or ()))
    out["grade"] = judge.grade(i)
    return out


def evaluate(book, prod, prices, days=None):
    """상품 하나를 그 책 판단자로 달력 전체 평가 → ({항목: 날짜별 값}, ProductJudge). days 생략 = 그 상품 봉 날짜."""
    judge = book.product(prod, prices, days=days)
    vals = [_day_values(judge, i) for i in range(len(judge.days))]
    return {k: [d[k] for d in vals] for k in COMPARED + ("grade",)}, judge


def window(cal, years):
    start = (datetime.now() - timedelta(days=int(365 * years))).strftime("%Y%m%d")
    return [i for i, d in enumerate(cal) if d >= start]


def compare(ta, tb, hist, years):
    """두 트리를 상품·등급 동사(+비중)별로 날마다 비교 → {prod: {do: {agree, n, days:[date...]}}}."""
    res = {}
    for p in ta.products():
        if not tb.has(p):
            res[p] = {"missing_in_b": True}
            continue
        ea, ja = evaluate(ta, p, hist)
        cal = ja.days
        eb, _ = evaluate(tb, p, hist, cal)
        idx = window(cal, years)
        res[p] = {}
        for sec in COMPARED + ("grade",):
            diff = [i for i in idx if ea[sec][i] != eb[sec][i]]
            res[p][sec] = {"n": len(idx), "agree": 1 - len(diff) / max(1, len(idx)),
                           "days": [cal[i] for i in diff], "_ia": ea, "_ib": eb, "_cal": cal}
    for p in tb.products():
        if not ta.has(p):
            res[p] = {"missing_in_a": True}
    return res


# ------------------------------------------------------------------ 트리 비교 도구(검사용)
def _strip_meta(node):
    """META(label·ref·id·note)를 모든 깊이에서 떼낸 '순수 로직'만 남긴다 — 되접기 신원 비교용."""
    if isinstance(node, dict):
        return {k: _strip_meta(v) for k, v in node.items() if k not in Cond.META}
    if isinstance(node, list):
        return [_strip_meta(x) for x in node]
    return node


_FLIP = {"lt": "gt", "le": "ge"}


def _canon(node):
    """모양만 다르고 뜻이 같은 식을 같은 글자로 — 시세 기본값(tf 1d) 생략, a<b → b>a, a≤b → b≥a, all/any/atleast 안의 순서 정렬
    (3값 논리에서 순서는 결과에 영향이 없다). META 는 이미 뗀 식을 받는다. 그 밖의 목록(판다·분할 규칙 등)은
    순서를 그대로 둔다."""
    if isinstance(node, list):
        return [_canon(x) for x in node]
    if not isinstance(node, dict):
        return node
    out = {k: _canon(v) for k, v in node.items()}
    if "px" in out:                                  # 시세 노드의 기본값은 적든 안 적든 같은 뜻 — 생략형으로 통일
        if out.get("tf") == "1d":
            del out["tf"]
    for op, to in _FLIP.items():
        if op in out and isinstance(out[op], list) and len(out[op]) == 2 and len(out) == 1:
            out = {to: [out[op][1], out[op][0]]}
    srt = lambda xs: sorted(xs, key=lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True))
    for op in ("all", "any"):
        if isinstance(out.get(op), list):
            out[op] = srt(out[op])
    if "atleast" in out and isinstance(out.get("of"), list):
        out["of"] = srt(out["of"])
    return out


def logic_key(node):
    """같은 식인지 가리는 지문 — META(이름·출처)를 뗀 뒤 정규화(_canon)한 식.
    문장·이름과 무관하게 식이 같으면 같은 조건이다("?" 수동 식도 식 그대로 비교된다)."""
    return json.dumps(_canon(_strip_meta(node)), ensure_ascii=False, sort_keys=True)


_RULE_OPS = ("all", "any", "atleast", "not", "manual")


def _cond_op(node):
    """노드의 연산 키 하나(META·보조키 제외). 조건 노드가 아니면(연산 0개·2개 이상) None.
    갈래 래퍼({when, do, qty})나 리스트·원시값을 조건으로 오인하지 않게 cond 의 판정을 그대로 쓴다."""
    if not isinstance(node, dict):
        return None
    try:
        return Cond._op_of(node)
    except Cond.CondError:
        return None


def factorable(node):
    """공통 def 로 뽑거나 되접을 '규칙 덩어리'인가 — 유효한 조건 노드이면서, 규칙 연산(all/any/atleast/
    not/manual)이거나 '이름표 달린 비교'(VIX 10% 같은 gt/ge/lt/le). 원시값·arith·case·qty 구조
    ·갈래 래퍼는 제외한다(래퍼는 _cond_op 가 None, 나머지는 op 가 집합 밖이라 자동 제외)."""
    op = _cond_op(node)
    if op is None:
        return False
    if op in _RULE_OPS:
        return True
    return op in Cond.CMP and bool(node.get("label"))


# ------------------------------------------------------------------ 규칙 단위 이중 추출 · 같은 뜻 정리
def rule_keys(tree, expand=True):
    """{라벨: 규칙 뜻 지문}."""
    return {l: logic_key(tree.body(l, expand)) for l in tree.labels()}


def pair_rules(ta, tb):
    """a·b 규칙 짝 — 뜻(펼친 식)이 같으면 common, 아니면 only_a·only_b (심판의 비교 도구 · 채점 공용)."""
    ka, kb = rule_keys(ta), rule_keys(tb)
    rb = {}
    for l, k in kb.items():
        rb.setdefault(k, []).append(l)
    common = [{"a": l, "b": rb[k][0]} for l, k in ka.items() if k in rb]
    return {"common": common, "only_a": [l for l, k in ka.items() if k not in rb],
            "only_b": [l for l, k in kb.items() if k not in set(ka.values())]}


# ------------------------------------------------------------------ 심판의 비교 도구(덤프 — 판단은 안 함)
def _zone_explain(judge, sec, i):
    if sec in Cond.GATES:
        return judge.explain(i)[sec]
    w, alt = judge.weight_at(i)
    return {"weight": w, "weight_range": alt, "tranches": _tranche_rows(judge.tranches())}


def _tranche_rows(tranches):
    """분할 차수의 덤프·비교용 모양 [{label, ref, frac, when}]."""
    return [{"label": t.label, "ref": t.ref, "frac": t.qty.x, "when": t.when} for t in tranches]


def _zone_node(tree, prod, sec):
    """등급 동사 하나의 식(any 묶음) — 안 산다·산다만(그 밖은 None)."""
    return tree.gate(prod, sec) if sec in Cond.GATES else None


def _section_key(tree, prod, sec):
    """등급 동사 하나의 식 지문(정규화) — 동작 비교로 안 보이는 차이(수동·"?" 식)까지 드러낸다."""
    return logic_key(_zone_node(tree, prod, sec))


def _conditions(tree, prod):
    """상품의 이름 달린 조건들 {지문: {"label", "zones", "expr"}} — 동사 어디든(분할·비중·판다 갈래 안 포함).
    같은 식이 여러 동사에 쓰이면 한 항목에 동사를 모은다."""
    out = {}
    for z, _l, _r, node in tree.expressions(prod):
        def walk(n):
            if isinstance(n, dict):
                if n.get("label") and factorable(n):
                    k = logic_key(n)
                    it = out.setdefault(k, {"label": n["label"], "zones": [], "expr": json.loads(k)})
                    if z not in it["zones"]:
                        it["zones"].append(z)
                for v in n.values():
                    walk(v)
            elif isinstance(n, list):
                for v in n:
                    walk(v)
        walk(node)
    return out


def pair_conditions(ta, tb, prod, hist, years):
    """조건 짝짓기 표 — 같은 식(정규화 지문)이면 공통, 아니면 a에만·b에만. a에만·b에만 있는 자동 조건끼리는
    실제 시세 3년치에서 판정이 한 번도 안 갈린 짝을 '동작 같음' 후보로 붙인다(식은 달라도 같은 뜻일 수 있다 —
    판단은 심판이 원문으로). 수동("?" 식·문장)은 기계가 값을 모르니 동작 근거가 없다."""
    ca, cb = _conditions(ta, prod), _conditions(tb, prod)
    common = [{"a": ca[k]["label"], "b": cb[k]["label"], "zones": sorted(set(ca[k]["zones"]) | set(cb[k]["zones"]))}
              for k in ca if k in cb]
    only_a = {k: v for k, v in ca.items() if k not in cb}
    only_b = {k: v for k, v in cb.items() if k not in ca}
    pa = ta.product(prod, hist)
    cal = pa.days
    pb = tb.product(prod, hist, days=cal)
    idx = window(cal, years)

    def ser(judge, v):
        if Cond.is_manual(v["expr"]):
            return None
        try:
            s = judge.evaluate(v["expr"])
        except Exception:  # noqa: BLE001
            return None
        return [s[i] for i in idx]
    sa = {k: ser(pa, v) for k, v in only_a.items()}
    sb = {k: ser(pb, v) for k, v in only_b.items()}

    def side(items, mine, theirs, other):
        rows = []
        for k, v in items.items():
            same = [other[j]["label"] for j in theirs if mine[k] is not None and theirs[j] is not None
                    and mine[k] == theirs[j] and any(x is not None for x in mine[k])]
            rows.append({"label": v["label"], "zones": v["zones"], "expr": v["expr"],
                         "manual": Cond.is_manual(v["expr"]), "same_behavior_as": same})
        return rows
    return {"common": common, "only_a": side(only_a, sa, sb, only_b), "only_b": side(only_b, sb, sa, only_a)}


_GROUPS = ("all", "any", "atleast", "not")


def _ckey(node):
    """이미 펼친(def 없음) 노드의 정규화 지문."""
    return json.dumps(_canon(_strip_meta(node)), ensure_ascii=False, sort_keys=True)


def _kids_of(node):
    """묶음(all/any/atleast/not)의 자식 목록 — 묶음이 아니면 None."""
    if not isinstance(node, dict):
        return None
    op = _cond_op(node)
    if op in ("all", "any"):
        return node[op]
    if op == "atleast":
        return node["of"]
    if op == "not":
        return [node["not"]]
    return None


def _group_sig(node):
    """묶음의 종류 — all/any/not, atleast 는 n 까지(같은 종류끼리만 안을 맞춰 본다)."""
    op = _cond_op(node)
    return "atleast %s" % node.get("atleast") if op == "atleast" else op


def _descendant_keys(node, acc=None):
    acc = set() if acc is None else acc
    if isinstance(node, dict):
        acc.add(_ckey(node))
        for k, v in node.items():
            if k not in Cond.META:
                _descendant_keys(v, acc)
    elif isinstance(node, list):
        for v in node:
            _descendant_keys(v, acc)
    return acc


def _shape(node):
    """티커(sym)를 뺀 식 모양 — 짝 찾기 전용(a 는 지수, b 는 상품 자신을 본 같은 갈래도 짝으로 맞춰 차이를 보이게)."""
    if isinstance(node, dict):
        return {k: _shape(v) for k, v in node.items() if k not in Cond.META and k != "sym"}
    if isinstance(node, list):
        return [_shape(x) for x in node]
    return node


def _pair_score(x, y):
    """짝 후보 점수 — 비교할 짝을 찾는 용도일 뿐(같다는 판정은 식으로만). 같은 이름, 심볼을 뺀 모양이 같음,
    같은 묶음 종류이면서 안쪽 (모양) 식이 겹치는 정도. 근거가 없으면 0(짝 안 지음 → 한쪽에만)."""
    sc = 0.0
    if isinstance(x, dict) and isinstance(y, dict):
        if x.get("label") and x.get("label") == y.get("label"):
            sc += 2.0
        if _ckey(_shape(x)) == _ckey(_shape(y)):
            sc += 3.0
        kx, ky = _kids_of(x), _kids_of(y)
        if kx is not None and ky is not None and _group_sig(x) == _group_sig(y):
            dx = _descendant_keys(_shape(x)) - {_ckey(_shape(x))}
            dy = _descendant_keys(_shape(y)) - {_ckey(_shape(y))}
            if dx | dy:
                sc += len(dx & dy) / len(dx | dy) * 2.0
    return sc


def _align(xs, ys, walk):
    """두 자식 목록을 맞춘다 — ① 식이 같은 것 ② 남은 것끼리 짝 후보 점수가 가장 높은 것 ③ 나머지는 한쪽에만."""
    pairs, used = {}, set()
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            if j not in used and _ckey(x) == _ckey(y):
                pairs[i] = j
                used.add(j)
                break
    cand = sorted(((_pair_score(x, ys[j]), i, j) for i, x in enumerate(xs) if i not in pairs
                   for j in range(len(ys)) if j not in used), reverse=True)
    for sc, i, j in cand:
        if sc > 0 and i not in pairs and j not in used:
            pairs[i] = j
            used.add(j)
    out = [walk(x, ys[pairs[i]]) if i in pairs else walk(x, None) for i, x in enumerate(xs)]
    out.extend(walk(None, y) for j, y in enumerate(ys) if j not in used)
    return out


def _lab(n):
    if isinstance(n, dict):
        return n.get("label") or (n.get("manual") if isinstance(n.get("manual"), str) else None)
    return None


def _one_side(x, y):
    n = x if y is None else y
    return {"status": "only_a" if y is None else "only_b", "label": _lab(n), "expr": _strip_meta(n)}


def tree_diff(x, y):
    """펼친 두 식을 트리 모양 그대로 나란히 맞춘다 — {status: same|diff|only_a|only_b, label_a, label_b, group?,
    a?, b?, kids?}. 같은지는 정규화한 식으로만 판정하고, 묶음(all/any/atleast/not)은 종류가 같으면 안쪽 자식끼리
    다시 맞춘다(뼈대가 같고 잎 하나만 다르면 그 잎만 '다름'으로 드러난다)."""
    if x is None or y is None:
        return _one_side(x, y)
    r = {"label_a": _lab(x), "label_b": _lab(y)}
    if _ckey(x) == _ckey(y):
        r["status"] = "same"
        return r
    kx, ky = _kids_of(x), _kids_of(y)
    if kx is not None and ky is not None and _group_sig(x) == _group_sig(y):
        r.update(status="diff", group=_group_sig(x), kids=_align(kx, ky, tree_diff))
        return r
    r.update(status="diff", a=_strip_meta(x), b=_strip_meta(y))
    return r


def _rules_diff(ra, rb):
    """규칙 목록(판다·분할)을 규칙 단위로 맞춘다 — 규칙의 when 은 tree_diff 로 더 내려간다."""
    def walk(x, y):
        if x is None or y is None:
            return _one_side(x, y)
        r = {"label_a": _lab(x), "label_b": _lab(y)}
        if _ckey(x) == _ckey(y):
            r["status"] = "same"
            return r
        r["status"] = "diff"
        if isinstance(x.get("when"), dict) and isinstance(y.get("when"), dict):
            r["when"] = tree_diff(x["when"], y["when"])
        others = [k for k in set(x) | set(y) if k not in Cond.META and k != "when" and _ckey(x.get(k)) != _ckey(y.get(k))]
        if others:
            r["fields"] = {k: {"a": _strip_meta(x.get(k)), "b": _strip_meta(y.get(k))} for k in others}
        return r
    return _align(ra or [], rb or [], walk)


def zone_diff(ta, tb, prod, zone):
    """상품 한 칸의 a·b 트리 모양 비교."""
    xa, xb = _zone_node(ta, prod, zone), _zone_node(tb, prod, zone)
    if zone in Cond.GATES:
        return tree_diff(xa, xb)
    if zone == Cond.SELL:
        return {"status": "same" if _ckey(xa) == _ckey(xb) else "diff", "rules": _rules_diff(xa, xb)}
    out = {"status": "same" if _ckey(xa) == _ckey(xb) else "diff"}            # weight(비중·분할)
    wa, wb = ta.weight(prod).qty.x, tb.weight(prod).qty.x
    if _ckey(wa) != _ckey(wb):
        out["weight"] = tree_diff(wa, wb) if isinstance(wa, dict) and isinstance(wb, dict) else {"a": wa, "b": wb}
    ra, rb = _tranche_rows(ta.tranches(prod)), _tranche_rows(tb.tranches(prod))
    if _ckey(ra) != _ckey(rb):
        out["tranches"] = _rules_diff(ra, rb)
    return out


def render_diff(node, indent=0, out=None, head=""):
    """tree_diff 결과 → 사람이 읽는 트리 줄(= 같음 · ≠ 다름 · +a/+b 한쪽에만). 같은 가지는 펼치지 않는다."""
    out = [] if out is None else out
    pad = "  " * indent
    mark = {"same": "=", "diff": "≠", "only_a": "+a", "only_b": "+b"}[node["status"]]
    if node["status"] in ("only_a", "only_b"):
        out.append("%s%s %s%s" % (pad, mark, head, node.get("label") or json.dumps(node["expr"], ensure_ascii=False)[:90]))
        return out
    la, lb = node.get("label_a"), node.get("label_b")
    name = la if (la == lb or not lb) else ("%s  /  b: %s" % (la, lb) if la else "b: %s" % lb)
    grp = (" [%s]" % node["group"]) if node.get("group") else ""
    out.append("%s%s %s%s%s" % (pad, mark, head, name or "(이름 없음)", grp))
    if node["status"] == "diff" and "kids" not in node and "a" in node:
        out.append("%s    a: %s" % (pad, json.dumps(node["a"], ensure_ascii=False)[:110]))
        out.append("%s    b: %s" % (pad, json.dumps(node["b"], ensure_ascii=False)[:110]))
    for k in node.get("kids") or []:
        render_diff(k, indent + 1, out)
    if node.get("when"):
        render_diff(node["when"], indent + 1, out, head="when: ")
    for f, ab in (node.get("fields") or {}).items():
        out.append("%s    %s — a: %s · b: %s" % (pad, f, json.dumps(ab["a"], ensure_ascii=False)[:50],
                                                  json.dumps(ab["b"], ensure_ascii=False)[:50]))
    return out


def render_zone(zd):
    """zone_diff 결과 한 칸 → 줄 목록."""
    if "rules" in zd:
        out = []
        for r in zd["rules"]:
            render_diff(r, 0, out)
        return out
    if "weight" in zd or "tranches" in zd:
        out = []
        if isinstance(zd.get("weight"), dict) and "status" in zd["weight"]:
            render_diff(zd["weight"], 0, out, head="비중: ")
        elif "weight" in zd:
            out.append("≠ 비중 — a: %s · b: %s" % (json.dumps(zd["weight"]["a"], ensure_ascii=False)[:60],
                                                 json.dumps(zd["weight"]["b"], ensure_ascii=False)[:60]))
        for r in zd.get("tranches") or []:
            render_diff(r, 0, out, head="분할: ")
        return out or ["= 같음"]
    return render_diff(zd)


def dump_disagreements(slug, per, years):
    ta, tb = Judge.read(slug, "a"), Judge.read(slug, "b")
    ta.validate()
    tb.validate()
    hist = history([ta, tb], years)
    cmp_ = compare(ta, tb, hist, years)
    out = {}
    for p, secs in cmp_.items():
        for sec, r in secs.items():
            if not isinstance(r, dict) or sec == "grade":
                continue
            sdiff = _section_key(ta, p, sec) != _section_key(tb, p, sec)
            if not (r["days"] or sdiff):
                continue
            cal = r["_cal"]
            step = max(1, len(r["days"]) // per)
            picks = r["days"][::step][:per]
            pa = ta.product(p, hist, days=cal)
            pb = tb.product(p, hist, days=cal)
            cases = []
            for d in picks:
                i = cal.index(d)
                prices = {}
                for s in sorted(ta.symbols([p]) | tb.symbols([p])):
                    prices[s] = Judge.recent(hist, s, d, 25)
                cases.append({"date": d, "a": r["_ia"][sec][i], "b": r["_ib"][sec][i],
                              "a_explain": _zone_explain(pa, sec, i), "b_explain": _zone_explain(pb, sec, i),
                              "prices_last25[date,o,h,l,c,v]": prices})
            entry = {"agree": r["agree"], "diff_days": len(r["days"]), "expr_differs": sdiff,
                     "a_tree": _zone_node(ta, p, sec), "b_tree": _zone_node(tb, p, sec), "cases": cases}
            out["%s.%s" % (p, sec)] = entry
    path = book_log(slug, "disagree.json")
    pairing = {p: pair_conditions(ta, tb, p, hist, years) for p in ta.products() if tb.has(p)}
    shape = {p: {z: zone_diff(ta, tb, p, z) for z in SHAPES} for p in ta.products() if tb.has(p)}
    rules = pair_rules(ta, tb)
    write_text(path, json.dumps({"rules": rules, "tree_diff": shape, "pairing": pairing,
                                 "sections": out}, ensure_ascii=False, indent=1, default=str))
    print("  규칙 짝: 같은 뜻 %d · a에만 %d · b에만 %d" % (len(rules["common"]), len(rules["only_a"]), len(rules["only_b"])))
    for p, t in pairing.items():
        print("  %s 조건 짝: 공통 %d · a에만 %d · b에만 %d" % (p, len(t["common"]), len(t["only_a"]), len(t["only_b"])))
    print("갈린 동사 %d개 → %s" % (len(out), path))


def main():
    argv = sys.argv[1:]
    years = float(argv[argv.index("--years") + 1]) if "--years" in argv else 3
    pos = [a for i, a in enumerate(argv) if not a.startswith("-") and not (i and argv[i - 1] == "--years")]
    if not pos:
        print(__doc__)
        return 2
    dump_disagreements(pos[0], int(pos[1]) if len(pos) > 1 else 6, years)
    return 0


if __name__ == "__main__":
    sys.exit(main())
