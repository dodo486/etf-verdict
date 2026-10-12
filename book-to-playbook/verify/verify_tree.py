#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조건 트리(체크리스트) 검사 — 규칙이 원문 뜻대로 '동작'하나 (책 무관). 트리를 만들거나 고치지 않는다.

  최종 트리(tree.json)는 심판(서브에이전트)만 쓴다 — 추출자 a·b 의 후보를 원문과 대조해 융합한다. 이 파일은
  심판이 쓰는 비교 도구(갈린 날 덤프)와, 심판이 쓴 트리의 채점만 있다(코드가 최종 트리에 끼어들지 않는다).

왜 있나
  옛 검증층(창작·커버리지·규칙↔명세·의미검사·자동가능)은 원문과 규칙의 **글자**(숫자·단어·어휘)를
  대조했다. 그래서 '2'라는 글자만 있으면 2거래일 유지가 1일로 판정돼도 통과했고, 사전에 없는
  새 조건(RSI·볼린저…)은 '찾은 게 없으니 누락도 없음'으로 통과했다. 이 검사는 규칙을 실제 시세와
  원문 사례에 돌려 본다 — 조건 종류를 몰라도 같은 절차가 돈다. 트리의 뜻은 dsl/(cond·grade)
  한 벌이라 여기서 본 동작이 곧 구간③ 판정 엔진의 동작이다. 트리 읽기도 판정 엔진과 같은 출입구(TreeGateway).

무엇을 하나 (books/<slug>/ 아래) — 정지·경고의 뜻과 고칠 곳은 authoring/checklist/JUDGE.md 5절
  1. 최종 트리(tree.json, 심판이 씀) — 라이브 책은 반드시 있어야 하고, 문법 검사를 통과해야 한다.
     v3 형식 밖의 키(옛 review·오타)·동사에 안 맞는 qty 는 문법 오류로 정지(출입구 validate).
  2. 이중 추출 일치 — 서로 독립인 두 추출(tree_candidates/a.json·b.json)과 최종 트리를 **규칙 단위**로 맞춘다(규칙의 뜻 =
     이름·출처·메모를 뗀 펼친 식). a·b 가 같은 식으로 합의하지 않은 최종 규칙(한쪽에서 고름·심판이 새로 씀)은 그 규칙의
     `why` 가 있어야 한다(미심판 불일치). 등급 동사(안 산다·산다)·비중은 실제 시세 수년치로 날마다 비교해 일치율을 보인다(참고).
  3. 같은 뜻 정리 — 같은 식 두 벌(규칙 둘이 같은 뜻 · 같은 측정을 참조 없이 두 번) · 이름↔식 1:1(같은 이름 다른 식 ·
     같은 식 다른 이름) · skip 사유 머리(데이터 없음:·연산 없음:) · 종목·이름 심볼에 "?" 남음 → 정지.
  4. 원문 사례 재현 — 원문만 보고 따로 쓴 시나리오(scenarios.json)를 합성 시세로 돌려 그날 결과(안 산다·산다·관망·판다,
     비중 % 포함)가 기대값과 맞는지. 틀리면 정지(사례가 원문을 잘못 읽었으면 심판이 보고 — 사례 작성자가 다시 쓴다).
  5. 발화 통계 — 최종 트리의 라벨 노드를 실제 시세에서 날마다 평가해: 한 번도 안 뜸 · 거의 매일 ·
     항상 판정 불가 · 두 조건이 완전히 같음 · 산다가 뜨면 늘 안 산다도 뜸 · 산다 도달 불가.
     (경고. 단 '완전히 같은 조건'은 같은 조건 두 벌일 수 있어 정지 — 동사가 다르거나 두 규칙 다 why 가 있으면 둔다.)
  6. 비중 합 — 상품 비중(산다 qty cash)의 합이 어느 날이든 100% 를 넘으면 정지.
  7. 수동 사유 분류 — manual 사유를 '저자 미명시 / 데이터 없음 / 연산 없음' 으로 세어 보고한다.
     사유 머리가 없으면 경고(어디로 보내야 할지 모르는 수동은 조용한 누락이 된다).

책 계약(--contract) — 시세 없이 바로 갈리는 산출물 계약만(라이브 책마다, 실패 → 정지):
  · books/<slug>/source_index.json — 원문이 소절 단위로 잘려 있다(소절 키 = 체크리스트 ref)
  · books/<slug>/tree.json — 체크리스트가 문법을 통과한다(v3 규칙·동사 셋)
  · 트리의 ref 가 전부 실제 소절 키다(없는 소절을 근거로 삼지 않는다)
  (책 페이지 구획·UI 사본은 화면층 verify.verify_view --pages 가 본다)

종료코드: 0 통과 · 1 정지(트리 없음/문법/미심판 불일치/같은 뜻 두 벌/사례 실패/비중 초과 …) · 2 경고만. --contract 는 0 · 1.
사용:
  python -m verify.verify_tree [slug ...] [--years 3]
  python -m verify.verify_tree --contract [slug ...]   책 계약만(빠름 — entry.run 이 항상 돌린다)
  python -m verify.verify_tree <slug> --dump N     심판의 비교 도구 — 규칙 짝(common·only_a·only_b)과 판정이 갈린 날 N개씩을
                                                   books/<slug>/logs/disagree.json 으로(판단은 안 함)
"""
import json
import os
import sys
from collections import namedtuple
from datetime import datetime, timedelta

from shared import paths  # noqa: F401  (UTF-8 출력)
from shared.paths import book_file, book_log, live_slugs, source_index_json, write_text
from dsl.tradeTool import Cond, Grade
from market import md_feed
from dsl.tree_gateway import TreeGateway
from signals.judge import Holding

Candle = namedtuple("Candle", "date open high low close volume")
COMPARED = Cond.GATES + ("weight",)                   # 날마다 비교하는 것(등급 동사 둘 + 비중 — 분할·판다는 거래로)
SHAPES = COMPARED + (Cond.SELL,)                       # 모양(식)을 비교하는 것
MANUAL_HEADS = ("저자 미명시", "데이터 없음", "연산 없음")
SKIP_HEADS = ("데이터 없음", "연산 없음")                 # skip 은 식으로 못 쓰는 잔여만(JUDGE 5절 · 충실성)
WAIT = "관망"                                           # 사례의 그날 결과 넷 = 동사 둘(안 산다·산다) + 관망 + 판다


def _load(slug, name):
    """산출물 JSON(원문 사례 scenarios.json 등 — 트리 아님) — 없으면 None."""
    p = book_file(slug, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def _load_tree(slug, name):
    """후보 트리(검사 전) — 트리 읽기는 출입구(TreeGateway) 하나로. 없으면 빈 출입구(거짓 — 옛 None 과 같게 걸러진다)."""
    t = TreeGateway.read(slug, name)
    return t if t is not None else TreeGateway(None)


# ------------------------------------------------------------------ 실제 시세 평가
def _history(trees, years):
    return Grade.history_back([t for t in trees if t], int(365 * years))


def _day_values(pe, i):
    """그날 값 — 등급 동사는 수동 = 모름 평가, 비중은 (값, 범위)."""
    out = {do: Cond.series(pe.gw.gate(pe.prod, do), pe.ctx[None])[i] for do in Cond.GATES}
    w, alt = pe.weight_of(i)
    out["weight"] = (None if w is None else round(w, 6), tuple(alt or ()))
    out["grade"] = pe.grade_key(i)
    return out


def _eval(tree, prod, hist, cal):
    pe = Grade.ProductEval(tree, prod, hist, cal)
    days = [_day_values(pe, i) for i in range(len(cal))]
    return {k: [d[k] for d in days] for k in COMPARED + ("grade",)}, pe


def _window(cal, years):
    start = (datetime.now() - timedelta(days=int(365 * years))).strftime("%Y%m%d")
    return [i for i, d in enumerate(cal) if d >= start]


def compare(ta, tb, hist, years):
    """두 트리를 상품·등급 동사(+비중)별로 날마다 비교 → {prod: {do: {agree, n, days:[date...]}}}."""
    res = {}
    for p in ta.products():
        if not tb.has(p):
            res[p] = {"missing_in_b": True}
            continue
        cal = [c.date for c in hist.get(p) or []]
        ea, _ = _eval(ta, p, hist, cal)
        eb, _ = _eval(tb, p, hist, cal)
        idx = _window(cal, years)
        res[p] = {}
        for sec in COMPARED + ("grade",):
            diff = [i for i in idx if ea[sec][i] != eb[sec][i]]
            res[p][sec] = {"n": len(idx), "agree": 1 - len(diff) / max(1, len(idx)),
                           "days": [cal[i] for i in diff], "_ia": ea, "_ib": eb, "_cal": cal}
    for p in tb.products():
        if not ta.has(p):
            res[p] = {"missing_in_a": True}
    return res


# ------------------------------------------------------------------ 원문 사례
def _synthetic(sc, symbols):
    days = int(sc.get("days") or 60)
    import datetime as _dt
    cal, d = [], _dt.date(2000, 1, 3)
    while len(cal) < days:                 # 실제 평일 달력
        if d.weekday() < 5:
            cal.append(d.strftime("%Y%m%d"))
        d += _dt.timedelta(days=1)
    series = sc.get("series") or {}

    def fit(xs, fill):
        xs = list(xs or [])
        if len(xs) >= days:
            return xs[-days:]
        return [xs[0] if xs else fill] * (days - len(xs)) + xs

    hist = {}
    for s in set(symbols) | set(series):
        sp = series.get(s)
        if sp:
            cl = fit(sp.get("close"), 100.0)
            hi = fit(sp.get("high"), None) if sp.get("high") else cl
            lo = fit(sp.get("low"), None) if sp.get("low") else cl
            op = fit(sp.get("open"), None) if sp.get("open") else cl
            vo = fit(sp.get("volume"), 1_000_000) if sp.get("volume") else [1_000_000] * days
        else:                           # 배경: 완만한 상승 · 저변동 · 거래량 일정
            cl = [100.0 * (1.001 ** i) for i in range(days)]
            hi = [c * 1.002 for c in cl]
            lo = [c * 0.998 for c in cl]
            op = cl
            vo = [1_000_000] * days
        hist[s] = [Candle(d, float(o), float(h), float(l), float(c), v)
                   for d, o, h, l, c, v in zip(cal, op, hi, lo, cl, vo)]
    return hist, cal


def _outcome(view, i):
    """등급 동사 값(opt 또는 pes 한쪽) → 그날 결과(안 산다·산다·관망) — 하나로 안 정해지면 None."""
    block, buy = view[Cond.BLOCK][i], view[Cond.BUY][i]
    if block is True:
        return Cond.BLOCK
    if block is False and buy is True:
        return Cond.BUY
    if block is False and buy is False:
        return WAIT
    return None


def _sell_hit(tree, p, hist, cal, m):
    """첫날 종가에 사서 들고 있었다면 마지막 날 판다 갈래가 걸렸나 — 참·거짓·모름(manual_as=m)."""
    ctx = Holding(0, hist[p][0].close).ctx(tree, p, hist, cal, manual_as=m)
    vals = [Cond.series(r.when, ctx)[-1] for r in tree.sells(p)]
    return True if True in vals else (False if all(v is False for v in vals) else None)


def scenario_result(tree, sc):
    """사례 하나 → (상태, 결과). 결과 = 그날 그 종목의 결과(SCENARIO.md: 안 산다·산다·관망·판다, 비중 % 가 있으면 함께).
    수동 조건 때문에 갈리면 '확인됨/안 됨' 두 경우를 본다 — 어느 쪽으로도 기대값이 안 나오면 불일치(재현불가로 덮지 않는다)."""
    p, expect = sc.get("prod"), sc.get("expect")
    want, pct = (expect.get("do"), expect.get("pct")) if isinstance(expect, dict) else (expect, None)
    if "section" in sc or want not in Cond.VERBS + (WAIT,) or not tree.has(p):
        return "형식오류", None                  # 옛 칸 사례(section·참/거짓 기대값) 또는 모르는 결과·상품
    hist, cal = _synthetic(sc, tree.symbols())
    if want == Cond.SELL:
        alts = {_sell_hit(tree, p, hist, cal, m) for m in (None, True, False)}
        got = {True: Cond.SELL, False: "안 판다", None: None}
        alts = {got[x] for x in alts}
    else:
        pe = Grade.ProductEval(tree, p, hist, cal)
        i = len(cal) - 1
        alts = {_outcome(pe.opt, i), _outcome(pe.pes, i)}
        if pct is not None and want == Cond.BUY:
            w, rng = pe.weight_of(i)
            ok_w = (w is not None and abs(w - float(pct)) <= 1e-6) or (w is None and float(pct) in (rng or []))
            if not ok_w:
                return "불일치", "비중 %s%%" % (w if w is not None else "/".join("%g" % x for x in rng or []) or "모름")
    alts.discard(None)
    if not alts:
        return "재현불가", None
    if alts == {want}:
        return "일치", want
    if want in alts:
        return "수동 확인 시 일치", sorted(alts)
    return "불일치", sorted(alts)


def run_scenarios(tree, scen):
    out = []
    for sc in (scen or {}).get("scenarios", []):
        try:
            st, got = scenario_result(tree, sc)
        except Exception as e:  # noqa: BLE001
            st, got = "평가오류 %s" % e, None
        out.append((sc, st, got))
    return out


# ------------------------------------------------------------------ 발화 통계
def _has_manual(n):
    return bool(Cond.manual_leaves(n))


def _stat_nodes(tree, prod):
    """통계 대상 라벨 노드 [(동사, 노드)] — 등급 동사(안 산다·산다)."""
    return [(do, n) for do in Cond.GATES for n in Cond.labeled(tree.gate(prod, do))]


def fire_stats(tree, hist, years):
    """→ (표, 경고, 같은 조건 쌍[(상품, 동사a, 라벨a, 동사b, 라벨b)])."""
    warns, table, same = [], [], []
    for p in tree.products():
        cal = [c.date for c in hist.get(p) or []]
        ev, pe = _eval(tree, p, hist, cal)
        ctx = pe.ctx[None]
        idx = _window(cal, years)
        N = max(1, len(idx))
        nodes = []
        top_avoid = {repr(n) for n in Grade._top_labeled(tree.gate(p, Cond.BLOCK))}
        for sec, n in _stat_nodes(tree, p):
            if _has_manual(n):
                continue                         # 수동이 섞이면 '안 뜸/모름'이 정상이다
            s = Cond.series(n, ctx)
            v = [s[i] for i in idx]
            if not all(x is None or isinstance(x, bool) for x in v):
                continue                         # 숫자 노드는 통계 대상 아님
            on, na = sum(1 for x in v if x is True), sum(1 for x in v if x is None)
            nodes.append((sec, n.get("label"), v, repr(n)))
            flag = ""
            if na == len(v):
                flag = "항상 판정 불가"
            elif on == 0:
                flag = "한 번도 안 뜸"
            elif on / N > 0.95:
                flag = "거의 매일(>95%)"
            elif na / N > 0.05:
                flag = "판정 불가 %d일" % na
            table.append((p, sec, n.get("label"), on / N * 100, flag))
            if flag:
                warns.append("%s %s '%s': %s" % (p, sec, n.get("label"), flag))
        for a in range(len(nodes)):
            for b in range(a + 1, len(nodes)):
                sa, la, va, ra = nodes[a]
                sb, lb, vb, rb = nodes[b]
                if la == lb or sum(1 for x in va if x is True) < 10:
                    continue
                if sa == sb and (ra in rb or rb in ra):
                    continue                         # 감싸는 노드와 그 안의 노드 — 같은 게 정상
                if va == vb:
                    same.append((p, sa, la, sb, lb))
                # 산다 ⇒ 안 산다: 안 산다는 맨 위 노드만(안쪽 하위 조건이 산다와 겹치는 건 정상)
                for (s1, l1, v1, r1), (s2, l2, v2, r2) in (((sa, la, va, ra), (sb, lb, vb, rb)),
                                                         ((sb, lb, vb, rb), (sa, la, va, ra))):
                    if s1 == Cond.BUY and s2 == Cond.BLOCK and r2 in top_avoid \
                            and sum(1 for x in v1 if x) >= 10 \
                            and all(v2[k] is True for k in range(len(v1)) if v1[k] is True):
                        warns.append("%s %s⇒%s: '%s' 가 뜨면 늘 '%s' 도 뜸" % (p, Cond.BUY, Cond.BLOCK, l1, l2))
        g = [ev["grade"][i] for i in idx]
        nb, nc = g.count("buy"), g.count("confirm")
        table.append((p, "등급", "✅ %d일 · 🟡 %d일 · ❔ %d일" % (nb, nc, g.count("unknown")), None, ""))
        if nb + nc == 0:
            warns.append("%s %s 도달 불가 — %d일 중 ✅·🟡 0일" % (p, Cond.BUY, len(g)))
        if g.count("unknown") / N > 0.05:
            warns.append("%s 판정 불가 %d일(데이터 부족)" % (p, g.count("unknown")))
    return table, warns, same


def weight_overflow(tree, hist, years):
    """상품 비중 합이 100% 를 넘는 날 [(날짜, 합)] — 비중을 아는 상품만 더한다(수동 범위는 최댓값)."""
    by_day = {}
    for p in tree.products():
        if tree.weight(p).qty.x is None:
            continue
        cal = [c.date for c in hist.get(p) or []]
        pe = Grade.ProductEval(tree, p, hist, cal)
        for i in _window(cal, years):
            w, alt = pe.weight_of(i)
            v = w if w is not None else (max(alt) if alt else None)
            if v is not None:
                by_day[cal[i]] = by_day.get(cal[i], 0.0) + v
    return sorted((d, s) for d, s in by_day.items() if s > 100 + 1e-9)


def manual_heads(tree):
    """{머리: 개수} — 사유 머리(COND_DSL 2절)로 수동 조건을 센다(같은 사유는 하나로)."""
    seen, cnt = set(), {}
    for p in tree.products():
        for _z, _l, _r, node in tree.expressions(p):
            for n in Cond.manual_leaves(node):
                key = n["manual"] if "manual" in n else _logic_key(n)   # "?" 식은 식이 신원
                if key in seen:
                    continue
                seen.add(key)
                text = Cond.manual_text(n)
                head = next((h for h in MANUAL_HEADS if text.startswith(h + ":")), "사유 머리 없음")
                cnt[head] = cnt.get(head, 0) + 1
    return cnt


# ------------------------------------------------------------------ 심판의 비교 도구(덤프 — 판단은 안 함)
def _zone_explain(pe, sec, i):
    if sec in Cond.GATES:
        return pe.explain(i)[sec]
    w, alt = pe.weight_of(i)
    return {"weight": w, "weight_range": alt, "tranches": _tranche_rows(pe.gw, pe.prod)}


def _tranche_rows(tree, prod):
    """분할 차수의 덤프·비교용 모양 [{label, ref, frac, when}]."""
    return [{"label": t.label, "ref": t.ref, "frac": t.qty.x, "when": t.when} for t in tree.tranches(prod)]


def _zone_node(tree, prod, sec):
    """등급 동사 하나의 식(any 묶음) — 안 산다·산다만(그 밖은 None)."""
    return tree.gate(prod, sec) if sec in Cond.GATES else None


def _section_key(tree, prod, sec):
    """등급 동사 하나의 식 지문(정규화) — 동작 비교로 안 보이는 차이(수동·"?" 식)까지 드러낸다."""
    return _logic_key(_zone_node(tree, prod, sec))


def _conditions(tree, prod):
    """상품의 이름 달린 조건들 {지문: {"label", "zones", "expr"}} — 동사 어디든(분할·비중·판다 갈래 안 포함).
    같은 식이 여러 동사에 쓰이면 한 항목에 동사를 모은다."""
    out = {}
    for z, _l, _r, node in tree.expressions(prod):
        def walk(n):
            if isinstance(n, dict):
                if n.get("label") and _factorable(n):
                    k = _logic_key(n)
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
    cal = [c.date for c in hist.get(prod) or []]
    idx = _window(cal, years)
    pa, pb = Grade.ProductEval(ta, prod, hist, cal), Grade.ProductEval(tb, prod, hist, cal)

    def ser(pe, v):
        if Cond.is_manual(v["expr"]):
            return None
        try:
            s = Cond.series(v["expr"], pe.ctx[None])
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
    """심볼을 뺀 식 모양 — 짝 찾기 전용(a 는 지수, b 는 상품 자신을 본 같은 갈래도 짝으로 맞춰 차이를 보이게)."""
    if isinstance(node, dict):
        return {k: _shape(v) for k, v in node.items() if k not in Cond.META and k not in ("sym", "syms")}
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
    ra, rb = _tranche_rows(ta, prod), _tranche_rows(tb, prod)
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
    ta, tb = _load_tree(slug, "tree_candidates/a.json"), _load_tree(slug, "tree_candidates/b.json")
    ta.validate()
    tb.validate()
    hist = _history([ta, tb], years)
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
            pa = Grade.ProductEval(ta, p, hist, cal)
            pb = Grade.ProductEval(tb, p, hist, cal)
            cases = []
            for d in picks:
                i = cal.index(d)
                prices = {}
                for s in sorted(ta.symbols([p]) | tb.symbols([p])):
                    cs = [c for c in hist.get(s) or [] if c.date <= d][-25:]
                    prices[s] = [[c.date, c.open, c.high, c.low, c.close, c.volume] for c in cs]
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
    """모양만 다르고 뜻이 같은 식을 같은 글자로 — 시세 기본값(sym $self·tf 1d) 생략, a<b → b>a, a≤b → b≥a, all/any/atleast 안의 순서 정렬
    (3값 논리에서 순서는 결과에 영향이 없다). META 는 이미 뗀 식을 받는다. 그 밖의 목록(판다·분할 규칙 등)은
    순서를 그대로 둔다."""
    if isinstance(node, list):
        return [_canon(x) for x in node]
    if not isinstance(node, dict):
        return node
    out = {k: _canon(v) for k, v in node.items()}
    if "px" in out:                                  # 시세 노드의 기본값은 적든 안 적든 같은 뜻 — 생략형으로 통일
        if out.get("sym") == "$self":
            del out["sym"]
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


def _logic_key(node):
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


def _factorable(node):
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
def _rule_keys(tree, expand=True):
    """{라벨: 규칙 뜻 지문}."""
    return {l: _logic_key(tree.body(l, expand)) for l in tree.labels()}


def pair_rules(ta, tb):
    """a·b 규칙 짝 — 뜻(펼친 식)이 같으면 common, 아니면 only_a·only_b (심판의 비교 도구 · 채점 공용)."""
    ka, kb = _rule_keys(ta), _rule_keys(tb)
    rb = {}
    for l, k in kb.items():
        rb.setdefault(k, []).append(l)
    common = [{"a": l, "b": rb[k][0]} for l, k in ka.items() if k in rb]
    return {"common": common, "only_a": [l for l, k in ka.items() if k not in rb],
            "only_b": [l for l, k in kb.items() if k not in set(ka.values())]}


def check_rules(tree, ta, tb):
    """최종 규칙마다 — a·b 가 같은 뜻으로 합의했으면 그대로, 아니면(한쪽에서 고름·심판이 새로 씀) why 필수."""
    stop = []
    ka, kb = set(_rule_keys(ta).values()), set(_rule_keys(tb).values())
    cnt = {"합의": 0, "a 쪽": 0, "b 쪽": 0, "심판이 새로": 0}
    for l, k in _rule_keys(tree).items():
        side = "합의" if (k in ka and k in kb) else ("a 쪽" if k in ka else ("b 쪽" if k in kb else "심판이 새로"))
        cnt[side] += 1
        if side != "합의" and not tree.why(l):
            stop.append("미심판 불일치: %s(%s)" % (l, side))
    print("  규칙 %d개: %s" % (sum(cnt.values()), " · ".join("%s %d" % kv for kv in cnt.items())))
    for x in stop[:8]:
        print("  ❌ %s — a·b 가 합의하지 않은 규칙은 원문 근거로 why" % x)
    if len(stop) > 8:
        print("  ❌ … 외 %d개" % (len(stop) - 8))
    return stop


def gate_agreement(ta, tb, hist, years):
    """참고 — a·b 의 등급 동사(안 산다·산다)·비중을 실제 시세로 날마다 비교한 일치율(정지 아님)."""
    for p, secs in compare(ta, tb, hist, years).items():
        if any(k.startswith("missing") for k in secs):
            print("  ⚠ %s 상품이 한쪽 추출에만 있음" % p)
            continue
        print("  · %-5s a·b 일치 %s" % (p, " · ".join("%s %.1f%%" % (k, secs[k]["agree"] * 100) for k in COMPARED)))


def same_meaning(tree):
    """같은 뜻 정리 위반 [(종류, 내용)] — 같은 식 두 벌 · 같은 측정 두 번 · 이름↔식 1:1."""
    out = []
    skipped = {u["rule"] for u in tree.skips()}
    by = {}
    for l, k in _rule_keys(tree, expand=False).items():
        if l not in skipped:
            by.setdefault(k, []).append(l)
    out.extend(("같은 식 두 벌", ls) for ls in by.values() if len(ls) > 1)
    by = {}
    for l in tree.labels():
        v = tree.value(l, expand=False)
        if v is not None:
            by.setdefault(_logic_key(v), []).append(l)
    out.extend(("같은 측정 두 번(참조 없이)", ls) for ls in by.values() if len(ls) > 1)
    for p in tree.products():
        names, logics = {}, {}

        def walk(node):
            if isinstance(node, dict):
                if node.get("label") and _factorable(node):
                    k = _logic_key(node)
                    names.setdefault(k, set()).add(node["label"])
                    logics.setdefault(node["label"], set()).add(k)
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        for do, label, _r, node in tree.expressions(p):
            if label is None and do in Cond.GATES:
                # 등급 묶음의 맨 위 항목은 규칙 이름을 단 갈래다 — 한 규칙의 여러 갈래(4개 이상 → 산다 · 2개 이하 →
                #   안 산다)는 이름이 같은 게 정상이라 그 안쪽만 본다.
                for member in node["any"]:
                    walk([v for k, v in member.items() if k not in Cond.META] if isinstance(member, dict) else member)
            else:
                walk(node)
        out.extend(("같은 이름 다른 식", [lb]) for lb, ks in logics.items() if len(ks) > 1)
    return out


def symbol_gaps(tree):
    """종목 기준지수·이름 심볼에 "?" 가 남은 자리(사용자 확인 대상)."""
    out = ["%s 기준지수" % p for p in tree.products() if tree.index(p) == Cond.UNKNOWN]
    out += ["%s" % n for n, syms in tree.name_symbols().items() if Cond.UNKNOWN in syms or not syms]
    return out


def _nameless_manual(node, out=None):
    """label 없는 수동 잎 목록(문장 수동·"?" 식) — 이게 있으면 화면에 '수동 확인'(이름 없음)으로 새거나
    조용히 사라진다. 이름은 추출자가 단다."""
    out = [] if out is None else out
    if isinstance(node, dict):
        if Cond.is_manual(node) and not node.get("label"):
            out.append(Cond.manual_text(node)[:40] if "manual" in node else json.dumps(node, ensure_ascii=False)[:60])
        for v in node.values():
            _nameless_manual(v, out)
    elif isinstance(node, list):
        for v in node:
            _nameless_manual(v, out)
    return out


def _unclassified_numeric_manual(node, out=None):
    """'저자 미명시' 문장 수동인데 '(정성)' 표시가 없는 잎 — 수치로 정할 수 있는 조건을 식 없이 문장으로 둔 것.
    저자가 숫자만 안 줬으면 식으로 적고 그 숫자 자리를 "?" 로 둔다(EXTRACTOR.md 5절). 문장 수동은 순수 주관 '(정성)'뿐
    (데이터 없음/연산 없음 머리는 스스로 분류돼 있어 면제)."""
    out = [] if out is None else out
    if isinstance(node, dict):
        m = node.get("manual")
        if (isinstance(m, str) and m.startswith("저자 미명시")
                and "(정성)" not in m and "(정성)" not in (node.get("label") or "")):
            out.append(node.get("label") or m[:40])
        for v in node.values():
            _unclassified_numeric_manual(v, out)
    elif isinstance(node, list):
        for v in node:
            _unclassified_numeric_manual(v, out)
    return out


def check_book(slug, years):
    stop, warn = [], []
    print("== %s" % slug)
    try:
        tree = TreeGateway.load(slug)
    except Cond.CondError as e:
        print("  ❌ tree.json 문법 오류: %s" % e)
        return ["%s 트리 문법" % slug], []
    if tree is None:
        print("  ❌ tree.json 없음 — 라이브 책은 조건 트리로만 판정한다")
        return ["%s 트리 없음" % slug], []
    # 00. 직렬화 형식 정지 — 구간② 파일은 공통 직렬화(Cond.compact_json)로만 쓴다(줄 수를 부풀리지 않게)
    loose = [n for n in ("tree.json", "tree_candidates/a.json", "tree_candidates/b.json", "tree_candidates/a.rules.json",
                         "tree_candidates/b.rules.json", "scenarios.json")
             if os.path.exists(book_file(slug, n)) and not Cond.is_compact(book_file(slug, n))]
    if loose:
        stop.append("%s 공통 직렬화 아님 %d개" % (slug, len(loose)))
        print("  ❌ 공통 직렬화가 아닌 파일 %s — 쓴 사람이 python -m dsl.tradeTool fmt <파일> 로 다시 쓴다" % loose)
    # 0. 이름 없는 수동 조건 정지 — 체크리스트가 조용히 사라지거나 '수동 확인'으로만 뜨면 안 된다
    nameless = _nameless_manual(tree.conditions())
    if nameless:
        stop.append("%s 이름 없는 수동 조건 %d개" % (slug, len(nameless)))
        print("  ❌ label 없는 수동 잎 %d개 — 화면에 '수동 확인'으로 샌다: %s" % (len(nameless), nameless[:3]))
    # 0b. 식 없는 수동 정지 — '저자 미명시' 는 수치로 정할 수 있으면 "?" 식, 순수 주관이면 '(정성)' 문장
    unclassified = _unclassified_numeric_manual(tree.conditions())
    if unclassified:
        stop.append("%s 식 없는 수동 조건 %d개" % (slug, len(unclassified)))
        print("  ❌ '(정성)' 아닌 문장 수동 %d개 — 수치로 정할 수 있으면 식으로 쓰고 숫자 자리를 \"?\" 로: %s"
              % (len(unclassified), unclassified[:3]))
    # 0c. 같은 뜻 정리 · skip 사유 머리 · 종목·심볼 "?"
    for kind, ls in same_meaning(tree):
        stop.append("%s %s: %s" % (slug, kind, " · ".join(ls)))
        print("  ❌ %s: %s — 이름 하나로 두고 다른 규칙은 {\"rule\"} 로 참조" % (kind, " · ".join(ls)))
    bad_skip = [u["rule"] for u in tree.skips() if not str(u.get("reason") or "").startswith(tuple(h + ":" for h in SKIP_HEADS))]
    if bad_skip:
        stop.append("%s 사유 머리 없는 skip %d개" % (slug, len(bad_skip)))
        print("  ❌ skip 사유가 '데이터 없음:'·'연산 없음:' 로 시작하지 않음: %s" % bad_skip[:3])
    gaps = symbol_gaps(tree)
    if gaps:
        stop.append("%s 종목·심볼 \"?\" 남음 %d개" % (slug, len(gaps)))
        print("  ❌ 종목·이름 심볼에 \"?\" 남음(사용자 확인): %s" % gaps[:5])
    ta, tb = _load_tree(slug, "tree_candidates/a.json"), _load_tree(slug, "tree_candidates/b.json")
    for t in (ta, tb):
        if t:
            try:
                t.validate()
            except Cond.CondError as e:
                print("  ❌ 후보 트리 문법 오류: %s" % e)
                return ["%s 후보 트리 문법" % slug], []
    hist = _history([tree, ta, tb], years)
    missing = sorted(s for s, cs in hist.items() if not cs)
    if missing:
        req = md_feed.requested()
        stop.append("%s 시세 없는 심볼 %s" % (slug, missing))
        print("  ❌ 시세 없는 심볼: %s" % ", ".join("%s(수집 요청 %s)" % (s, req.get(s, "-")) for s in missing))

    # 2. 이중 추출
    if not (ta and tb):
        stop.append("%s 독립 추출 a/b 없음" % slug)
        print("  ❌ tree_candidates/a.json·b.json 이 둘 다 있어야 한다(이중 추출)")
    else:
        stop.extend("%s %s" % (slug, x) for x in check_rules(tree, ta, tb))
        gate_agreement(ta, tb, hist, years)
        for name, t in (("a", ta), ("b", tb)):
            un = t.skips()
            if un:
                heads = {}
                for u in un:
                    h = next((x for x in MANUAL_HEADS if str(u.get("reason", "")).startswith(x)), "기타")
                    heads[h] = heads.get(h, 0) + 1
                print("  · 추출 %s 표현 못 한 규칙 %d: %s" % (name, len(un), " · ".join("%s %d" % kv for kv in heads.items())))

    # 4. 원문 사례
    scen = _load(slug, "scenarios.json")
    if not scen:
        warn.append("%s 원문 사례 시나리오 없음" % slug)
        print("  ⚠ scenarios.json 없음")
    else:
        res = run_scenarios(tree, scen)
        cnt = {}
        for sc, st, got in res:
            cnt[st] = cnt.get(st, 0) + 1
            if st in ("불일치", "형식오류") or st.startswith("평가오류"):
                stop.append("%s 사례 %s: %s" % (slug, st, sc.get("name")))
                print("  ❌ 사례 %s: %s [%s 기대 %s, 결과 %s] (%s)%s"
                      % (st, sc.get("name"), sc.get("prod"), sc.get("expect"), got, sc.get("ref"),
                         " — 옛 칸 사례(section): 사례 작성자가 SCENARIO.md 로 다시 쓴다" if "section" in sc else ""))
            elif st == "재현불가":
                warn.append("%s 사례 재현불가: %s" % (slug, sc.get("name")))
        print("  사례 %d개: %s" % (len(res), " · ".join("%s %d" % kv for kv in cnt.items())))

    # 5. 발화 통계
    table, fw, same = fire_stats(tree, hist, years)
    for p, sec, label, rate, flag in table:
        if rate is None:
            print("  %-5s %s" % (p, label))
    # 식은 달라도 판정이 3년간 같은 조건 — 같은 동사면 같은 조건 두 벌일 가능성(정지). 동사가 다르면(사지 마 ↔ 사라)
    #   남기는 게 맞고, 저자가 일부러 둘로 썼으면 두 규칙의 why 에 판례로 적는다(JUDGE 5절).
    for p, sa, la, sb, lb in same:
        msg = "%s 완전히 같은 조건: [%s] %s == [%s] %s" % (p, sa, la, sb, lb)
        if sa != sb or (tree.why(la) and tree.why(lb)):
            print("  ☑ %s — %s" % (msg, "동사가 다름" if sa != sb else "두 규칙 다 why"))
            continue
        stop.append("%s 판정이 완전히 같은 조건: %s · %s" % (slug, la, lb))
        print("  ❌ %s — 같은 동사면 느슨한 쪽 하나로, 저자가 일부러 둘로 썼으면 두 규칙 why 에 판례" % msg)
    for w in fw:
        print("  ⚠ " + w)
    warn.extend(fw)

    # 6. 비중 합
    over = weight_overflow(tree, hist, years)
    if over:
        stop.append("%s 비중 합 100%% 초과 %d일" % (slug, len(over)))
        print("  ❌ 비중 합 100%% 초과 %d일 (예: %s %.1f%%)" % (len(over), over[0][0], over[0][1]))

    # 7. 수동 사유 분류
    heads = manual_heads(tree)
    if heads:
        print("  수동 조건 사유: %s" % " · ".join("%s %d" % kv for kv in heads.items()))
        if heads.get("사유 머리 없음"):
            warn.append("%s 수동 사유 머리 없음 %d개(저자 미명시/데이터 없음/연산 없음)" % (slug, heads["사유 머리 없음"]))
    return stop, warn


# ------------------------------------------------------------------ 책 계약(--contract)
def contract(slug):
    """라이브 책 하나의 산출물 계약 위반 목록 — 소절 인덱스 · 트리 문법 · 트리 ref 가 실제 소절."""
    bad = []
    try:
        idx = json.load(open(source_index_json(slug), encoding="utf-8"))
        keys = set(idx.get("sections") or {})
        if not keys:
            bad.append("source_index.json 에 소절이 없다")
    except (OSError, ValueError) as e:
        bad.append("source_index.json 없음/깨짐: %s" % e)
        keys = set()
    try:
        tree = TreeGateway.open(TreeGateway.path(slug))
        tree.validate()
    except (OSError, ValueError, Cond.CondError) as e:
        bad.append("tree.json 문법: %s" % e)
        tree = None
    if tree is not None and keys:
        refs = tree.refs()
        # "2-1·2-3" 처럼 여러 소절을 함께 적은 ref 는 하나하나 본다
        parts = {p.strip() for r in refs for p in str(r).replace("·", ",").split(",") if p.strip()}
        missing = sorted(parts - keys)
        if missing:
            bad.append("tree.json 의 ref 가 없는 소절을 가리킴: %s" % ", ".join(missing))
    return bad


def contract_main(slugs):
    stop = []
    for slug in slugs:
        bad = contract(slug)
        print("  %s %-34s %s" % ("✅" if not bad else "❌", "책 계약 " + slug, "; ".join(bad)[:300] or "통과"))
        if bad:
            stop.append("책 계약 " + slug)
    if stop:
        print("책 계약 정지 — %s" % ", ".join(stop))
        return 1
    print("책 계약 통과")
    return 0


def main():
    argv = sys.argv[1:]
    if "--contract" in argv:
        return contract_main([a for a in argv if not a.startswith("-")] or live_slugs())
    years = float(argv[argv.index("--years") + 1]) if "--years" in argv else 3
    if "--dump" in argv:
        dump_disagreements(argv[0], int(argv[argv.index("--dump") + 1]), years)
        return 0
    slugs = [a for a in argv if not a.startswith("-") and not a.replace(".", "").isdigit()] or live_slugs()
    stop, warn = [], []
    for s in slugs:
        a, b = check_book(s, years)
        stop += a
        warn += b
    if stop:
        print("트리 검사 정지 %d건" % len(stop))
        return 1
    if warn:
        print("트리 검사 통과(경고 %d건 — 재추출 대상)" % len(warn))
        return 2
    print("트리 검사 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
