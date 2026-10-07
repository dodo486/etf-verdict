#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조건 트리(체크리스트) 검사 — 규칙이 원문 뜻대로 '동작'하나 (책 무관). 트리를 만들거나 고치지 않는다.

  최종 트리(tree.json)는 심판(서브에이전트)만 쓴다 — 추출자 a·b 의 후보를 원문과 대조해 융합한다. 이 파일은
  심판이 쓰는 비교 도구(갈린 날 덤프)와, 심판이 쓴 트리의 채점만 있다(코드가 최종 트리에 끼어들지 않는다).

왜 있나
  옛 검증층(창작·커버리지·규칙↔명세·의미검사·자동가능)은 원문과 규칙의 **글자**(숫자·단어·어휘)를
  대조했다. 그래서 '2'라는 글자만 있으면 2거래일 유지가 1일로 판정돼도 통과했고, 사전에 없는
  새 조건(RSI·볼린저…)은 '찾은 게 없으니 누락도 없음'으로 통과했다. 이 검사는 규칙을 실제 시세와
  원문 사례에 돌려 본다 — 조건 종류를 몰라도 같은 절차가 돈다. 트리의 뜻은 shared/(cond·tree_grade·
  trades) 한 벌이라 여기서 본 동작이 곧 구간③ 판정 엔진의 동작이다.

무엇을 하나 (books/<slug>/ 아래)
  1. 최종 트리(tree.json, 심판이 씀) — 라이브 책은 반드시 있어야 하고, 문법 검사를 통과해야 한다.
  2. 이중 추출 일치 — 서로 독립인 두 추출(tree_candidates/a.json·b.json)을 칸마다 식(정규화)으로 대조하고, 실제 시세
     수년치에서 날마다 평가해 비교한다(조건 칸 셋·조심 금액 배수·비중, 분할은 거래로). 식이 다르거나 하루라도 갈린 칸은
     심판 기록(tree.json 의 review)이 있어야 하고, 최종 트리는 그 칸에서 심판이 고른 쪽과 **동작이 같아야** 한다.
  3. 매도 규칙 이중 추출(후보 a·b 의 exit 칸) — 같은 진입 신호에 두 규칙으로 거래를 내 비교한다.
  4. 원문 사례 재현 — 원문만 보고 따로 쓴 시나리오(scenarios.json)를 합성 시세로 돌려 기대값과
     맞는지. 틀리면 실패 — 단 심판이 '시나리오가 틀렸다'고 사유를 남긴 것은 제외.
  5. 발화 통계 — 최종 트리의 라벨 노드를 실제 시세에서 날마다 평가해: 한 번도 안 뜸 · 거의 매일 ·
     항상 판정 불가 · 두 조건이 완전히 같음 · 진입이 뜨면 늘 회피도 뜸 · 매수 후보 도달 불가.
     (경고. 단 '완전히 같은 조건'은 같은 조건 두 벌일 수 있어 정지 — 원문이 일부러 둘로 썼으면 review.fire_ack 에 사유.)
  6. 비중 합 — 상품 비중(sizing.weight)의 합이 어느 날이든 100% 를 넘으면 정지.
  7. 수동 사유 분류 — manual 사유를 '저자 미명시 / 데이터 없음 / 연산 없음' 으로 세어 보고한다.
     사유 머리가 없으면 경고(어디로 보내야 할지 모르는 수동은 조용한 누락이 된다).

종료코드: 0 통과 · 1 정지(트리 없음/문법/미심판 불일치/최종≠승자/사례 실패/비중 초과) · 2 경고만.
사용:
  python -m checklist.verify_tree [slug ...] [--years 3]
  python -m checklist.verify_tree <slug> --dump N     심판의 비교 도구 — 판정이 갈린 날 N개씩을 logs/disagree-<slug>.json 으로(판단은 안 함)
  python -m checklist.verify_tree <slug> --dump-exits N   심판의 비교 도구 — 매도 규칙 a/b 가 다르게 청산한 거래 N개씩
"""
import json
import os
import sys
from collections import namedtuple
from datetime import datetime, timedelta

from shared import paths  # noqa: F401  (UTF-8 출력)
from shared.paths import BASE, LOGS, ensure_dir, live_slugs, write_text
from shared import cond, md_feed, trades as trades_mod, tree_grade

Candle = namedtuple("Candle", "date open high low close volume")
COMPARED = cond.SECTIONS + ("caution", "sizing")      # 날마다 비교하는 칸(분할·매도는 거래로)
MANUAL_HEADS = ("저자 미명시", "데이터 없음", "연산 없음")


def _load(slug, name):
    p = os.path.join(BASE, "books", slug, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


# ------------------------------------------------------------------ 실제 시세 평가
def _start(years):
    return (datetime.now() - timedelta(days=int(365 * years) + tree_grade.WARMUP_DAYS)).strftime("%Y%m%d")


def _history(trees, years):
    return tree_grade.history([t for t in trees if t], _start(years))


def _day_values(pe, i):
    """칸별 그날 값 — 조건 칸은 수동 = 모름 평가, 조심은 (금액 배수, 폭 미명시, 확인 필요), 비중은 (값, 범위)."""
    out = {sec: cond.series(pe.cfg[sec], pe.ctx[None])[i] for sec in cond.SECTIONS}
    f, unspec, unknown = pe.amount_factor(i)
    out["caution"] = (round(f, 6), bool(unspec), bool(unknown))
    w, alt = pe.weight_of(i)
    out["sizing"] = (None if w is None else round(w, 6), tuple(alt or ()))
    out["grade"] = pe.grade_key(i)
    return out


def _eval(tree, prod, hist, cal):
    pe = tree_grade.ProductEval(tree, prod, hist, cal)
    days = [_day_values(pe, i) for i in range(len(cal))]
    return {k: [d[k] for d in days] for k in COMPARED + ("grade",)}, pe


def _window(cal, years):
    start = (datetime.now() - timedelta(days=int(365 * years))).strftime("%Y%m%d")
    return [i for i, d in enumerate(cal) if d >= start]


def compare(ta, tb, hist, years):
    """두 트리를 상품·칸별로 날마다 비교 → {prod: {sec: {agree, n, days:[date...]}}}."""
    res = {}
    for p in ta["products"]:
        if p not in tb["products"]:
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
        res[p]["sizing"]["tranche_diff"] = compare_tranches(ta, tb, p, hist, cal, years)
    for p in tb["products"]:
        if p not in ta["products"]:
            res[p] = {"missing_in_a": True}
    return res


def _entry_starts(tree, prod, hist, cal, years):
    pe = tree_grade.ProductEval(tree, prod, hist, cal)
    starts, prev = [], False
    for i in _window(cal, years):
        b = pe.grade_key(i) in ("buy", "confirm")
        if b and not prev:
            starts.append(i)
        prev = b
    return starts


def _trade_key(t):
    return (t["entry"], t["exit"], tuple((x["date"], round(x["qty"], 6)) for x in t.get("buys", [])),
            tuple((x["date"], round(x["qty"], 6)) for x in t["sells"]))


def compare_tranches(ta, tb, prod, hist, cal, years):
    """분할 매수 비교 — a 의 진입 신호에 같은 매도 규칙(a 의 것)을 두고 두 분할로 거래를 내 갈린 거래."""
    trs_a, trs_b = trades_mod.tranches_of(ta, prod), trades_mod.tranches_of(tb, prod)
    if json.dumps(_inline(trs_a, ta.get("defs") or {}), sort_keys=True) == \
            json.dumps(_inline(trs_b, tb.get("defs") or {}), sort_keys=True):
        return []
    starts = _entry_starts(ta, prod, hist, cal, years)
    exits = _exit_rules(ta, prod) or trades_mod.STANDARD   # a 의 def 를 펼쳐서(b 트리 문맥에서 a 의 def 를 찾지 않게) · 책 규칙 없으면 표준
    xa = {t["entry"]: t for t in trades_mod.build_trades(ta, prod, hist, cal, starts, exits, trs_a)}
    xb = {t["entry"]: t for t in trades_mod.build_trades(tb, prod, hist, cal, starts, exits, trs_b)}
    return [(xa.get(k), xb.get(k)) for k in sorted(set(xa) | set(xb))
            if not (xa.get(k) and xb.get(k) and _trade_key(xa[k]) == _trade_key(xb[k]))]


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


def _scenario_node(cfg, sc):
    """사례가 가리키는 식 — 조건 칸은 칸 전체, caution 은 rule 라벨의 when, sizing 은 weight."""
    sec = sc.get("section")
    if sec in cond.SECTIONS:
        return cfg[sec]
    if sec == "caution":
        if not sc.get("rule"):                    # 규칙을 모르고 쓴 사례 = '어느 조심이든 걸려 금액을 줄이나'
            return {"any": [r["when"] for r in cfg["caution"]]}
        hit = [r for r in cfg["caution"] if r["label"] == sc.get("rule")]
        return hit[0]["when"] if len(hit) == 1 else None
    if sec == "sizing":
        return cfg["sizing"].get("weight")
    return None


def _match(got, expect):
    if isinstance(expect, bool) or expect is None:
        return got == bool(expect)
    return got is not None and abs(got - float(expect)) <= 1e-6 * max(1.0, abs(float(expect)))


def run_scenarios(tree, scen, overrides):
    out = []
    syms = cond.symbols_of(tree)
    for sc in (scen or {}).get("scenarios", []):
        name, p = sc.get("name"), sc.get("prod")
        node = _scenario_node(tree["products"][p], sc) if p in tree["products"] else None
        if node is None:
            out.append((sc, "형식오류", None))
            continue
        hist, cal = _synthetic(sc, syms)
        cfg = tree["products"][p]

        def mk(m):
            return cond.Ctx(hist, cal, p, cfg.get("index"), tree.get("defs") or {}, manual_as=m)
        try:
            got = cond.series(node, mk(None))[-1]
        except Exception as e:  # noqa: BLE001
            out.append((sc, "평가오류 %s" % e, None))
            continue
        if got is None:
            # 수동 조건 때문에 모름이면 '확인됨/안 됨' 두 경우로 다시 본다 — 어느 쪽으로도 기대값이
            # 안 나오면 수동과 무관하게 틀린 것이다(재현불가로 덮지 않는다).
            alt = [cond.series(node, mk(m))[-1] for m in (True, False)]
            if None in alt:
                st = "재현불가"
            elif any(_match(a, sc.get("expect")) for a in alt):
                st = "수동 확인 시 일치"
            elif name in overrides:
                st = "불일치(시나리오 오류로 심판)"
            else:
                st, got = "불일치", alt
        elif _match(got, sc.get("expect")):
            st = "일치"
        elif name in overrides:
            st = "불일치(시나리오 오류로 심판)"
        else:
            st = "불일치"
        out.append((sc, st, got))
    return out


# ------------------------------------------------------------------ 발화 통계
def _has_manual(n, defs):
    return bool(cond.manual_leaves(n, defs))


def _stat_nodes(cfg, defs):
    """통계 대상 라벨 노드 [(칸, 노드)] — 조건 칸 + 조심 규칙(규칙 자체와 그 안의 라벨 노드).
    장중 관측(observe) 안쪽은 뺀다 — asof 기준 분봉이 없는 날은 판정 불가가 정상이다(그날은 수동으로 푼다)."""
    out = [(sec, n) for sec in cond.SECTIONS for n in cond.labeled(cfg[sec], defs)]
    for r in cfg["caution"]:
        inner = cond.labeled(r["when"], defs)
        # when 자체가 이름 있는 조건(이름 붙은 def 참조 포함)이면 그 이름으로 센다 — 규칙 이름표로 한 번 더 세지 않는다
        named = isinstance(r["when"], dict) and (r["when"].get("label") or
                                                 any(_logic_key(n, defs) == _logic_key(r["when"], defs) for n in inner))
        if isinstance(r["when"], dict) and not named:
            out.append(("caution", dict(r["when"], label=r["label"])))
        out.extend(("caution", n) for n in inner)
    inside = set()
    for _sec, n in out:
        if "observe" in n:
            inside.update(id(x) for x in cond.labeled_all(n["observe"], defs))
    return [(sec, n) for sec, n in out if id(n) not in inside]


def fire_stats(tree, hist, years, ack=None):
    """ack = {경고문: 사유} — 심판이 '원문 그대로라 정상'이라 사유를 남긴 경고는 확인됨으로 센다."""
    ack = ack or {}
    warns, table = [], []
    defs = tree.get("defs") or {}
    for p, cfg in tree["products"].items():
        cal = [c.date for c in hist.get(p) or []]
        ev, pe = _eval(tree, p, hist, cal)
        ctx = pe.ctx[None]
        idx = _window(cal, years)
        N = max(1, len(idx))
        nodes = []
        top_avoid = {repr(n) for n in tree_grade._top_labeled(cfg["avoid"], defs)}
        for sec, n in _stat_nodes(cfg, defs):
            if _has_manual(n, defs):
                continue                         # 수동이 섞이면 '안 뜸/모름'이 정상이다
            s = cond.series(n, ctx)
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
                    warns.append("%s 완전히 같은 조건: [%s] %s == [%s] %s" % (p, sa, la, sb, lb))
                # 진입 ⇒ 회피: 회피는 맨 위 노드만(회피 안쪽 하위 조건이 진입과 겹치는 건 정상)
                for (s1, l1, v1, r1), (s2, l2, v2, r2) in (((sa, la, va, ra), (sb, lb, vb, rb)),
                                                         ((sb, lb, vb, rb), (sa, la, va, ra))):
                    if s1 == "entry" and s2 == "avoid" and r2 in top_avoid \
                            and sum(1 for x in v1 if x) >= 10 \
                            and all(v2[k] is True for k in range(len(v1)) if v1[k] is True):
                        warns.append("%s 진입⇒회피: '%s' 가 뜨면 늘 '%s' 도 뜸" % (p, l1, l2))
        g = [ev["grade"][i] for i in idx]
        nb, nc = g.count("buy"), g.count("confirm")
        table.append((p, "등급", "✅ %d일 · 🟡 %d일 · ❔ %d일" % (nb, nc, g.count("unknown")), None, ""))
        if nb + nc == 0:
            warns.append("%s 매수 후보 도달 불가 — %d일 중 ✅·🟡 0일" % (p, len(g)))
        if g.count("unknown") / N > 0.05:
            warns.append("%s 판정 불가 %d일(데이터 부족)" % (p, g.count("unknown")))
    acked = [w for w in warns if w in ack]
    return table, [w for w in warns if w not in ack], acked


def weight_overflow(tree, hist, years):
    """상품 비중 합이 100% 를 넘는 날 [(날짜, 합)] — 비중을 아는 상품만 더한다(수동 범위는 최댓값)."""
    by_day = {}
    for p in tree["products"]:
        if (tree["products"][p].get("sizing") or {}).get("weight") is None:
            continue
        cal = [c.date for c in hist.get(p) or []]
        pe = tree_grade.ProductEval(tree, p, hist, cal)
        for i in _window(cal, years):
            w, alt = pe.weight_of(i)
            v = w if w is not None else (max(alt) if alt else None)
            if v is not None:
                by_day[cal[i]] = by_day.get(cal[i], 0.0) + v
    return sorted((d, s) for d, s in by_day.items() if s > 100 + 1e-9)


def manual_heads(tree):
    """{머리: 개수} — 사유 머리(COND_DSL 2절)로 수동 조건을 센다(같은 사유는 하나로)."""
    seen, cnt = set(), {}
    defs = tree.get("defs") or {}
    for cfg in tree["products"].values():
        for _z, _l, _r, node in cond.zone_nodes(cfg):
            for n in cond.manual_leaves(node, defs):
                key = n["manual"] if "manual" in n else _logic_key(n, defs)   # "?" 식은 식이 신원
                if key in seen:
                    continue
                seen.add(key)
                text = cond.manual_text(n)
                head = next((h for h in MANUAL_HEADS if text.startswith(h + ":")), "사유 머리 없음")
                cnt[head] = cnt.get(head, 0) + 1
    return cnt


# ------------------------------------------------------------------ 심판의 비교 도구(덤프 — 판단은 안 함)
def _zone_explain(pe, sec, i):
    if sec in cond.SECTIONS:
        return pe.explain(i)[sec]
    if sec == "caution":
        return pe.caution_state(i)
    w, alt = pe.weight_of(i)
    return {"weight": w, "weight_range": alt, "tranches": pe.cfg["sizing"].get("tranches")}


def _section_key(tree, prod, sec):
    """칸 하나의 식 지문(정규화) — 동작 비교로 안 보이는 차이(수동·"?" 식)까지 드러낸다."""
    return _logic_key(tree["products"][prod].get(sec), tree.get("defs") or {})


def _conditions(tree, prod):
    """상품의 이름 달린 조건들 {지문: {"label", "zones", "expr"}} — 여섯 칸 어디든(조심·분할·매도 규칙 안 포함).
    같은 식이 여러 칸에 쓰이면 한 항목에 칸을 모은다."""
    defs = tree.get("defs") or {}
    out = {}
    for z, _l, _r, node in cond.zone_nodes(tree["products"][prod]):
        def walk(n):
            if isinstance(n, dict):
                if n.get("label") and _factorable(n):
                    k = _logic_key(n, defs)
                    it = out.setdefault(k, {"label": n["label"], "zones": [], "expr": json.loads(k)})
                    if z not in it["zones"]:
                        it["zones"].append(z)
                for v in n.values():
                    walk(v)
            elif isinstance(n, list):
                for v in n:
                    walk(v)
        walk(_inline(node, defs))
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
    pa, pb = tree_grade.ProductEval(ta, prod, hist, cal), tree_grade.ProductEval(tb, prod, hist, cal)

    def ser(pe, v):
        if cond.is_manual(v["expr"], {}):
            return None
        try:
            s = cond.series(v["expr"], pe.ctx[None])
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
                         "manual": cond.is_manual(v["expr"], {}), "same_behavior_as": same})
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
            if k not in cond.META:
                _descendant_keys(v, acc)
    elif isinstance(node, list):
        for v in node:
            _descendant_keys(v, acc)
    return acc


def _shape(node):
    """심볼을 뺀 식 모양 — 짝 찾기 전용(a 는 지수, b 는 상품 자신을 본 같은 갈래도 짝으로 맞춰 차이를 보이게)."""
    if isinstance(node, dict):
        return {k: _shape(v) for k, v in node.items() if k not in cond.META and k not in ("sym", "syms")}
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
    """규칙 목록(caution·exit·tranches)을 규칙 단위로 맞춘다 — 규칙의 when 은 tree_diff 로 더 내려간다."""
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
        others = [k for k in set(x) | set(y) if k not in cond.META and k != "when" and _ckey(x.get(k)) != _ckey(y.get(k))]
        if others:
            r["fields"] = {k: {"a": _strip_meta(x.get(k)), "b": _strip_meta(y.get(k))} for k in others}
        return r
    return _align(ra or [], rb or [], walk)


def zone_diff(ta, tb, prod, zone):
    """상품 한 칸의 a·b 트리 모양 비교(def 를 펼쳐서)."""
    xa = _inline(ta["products"][prod].get(zone), ta.get("defs") or {})
    xb = _inline(tb["products"][prod].get(zone), tb.get("defs") or {})
    if zone in cond.SECTIONS:
        return tree_diff(xa, xb)
    if zone in ("caution", "exit"):
        return {"status": "same" if _ckey(xa) == _ckey(xb) else "diff", "rules": _rules_diff(xa, xb)}
    out = {"status": "same" if _ckey(xa) == _ckey(xb) else "diff"}            # sizing
    if _ckey(xa.get("weight")) != _ckey(xb.get("weight")):
        out["weight"] = (tree_diff(xa["weight"], xb["weight"]) if isinstance(xa.get("weight"), dict)
                         and isinstance(xb.get("weight"), dict) else {"a": xa.get("weight"), "b": xb.get("weight")})
    if _ckey(xa.get("tranches")) != _ckey(xb.get("tranches")):
        out["tranches"] = _rules_diff(xa.get("tranches"), xb.get("tranches"))
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
    ta, tb = _load(slug, "tree_candidates/a.json"), _load(slug, "tree_candidates/b.json")
    cond.validate_tree(ta)
    cond.validate_tree(tb)
    hist = _history([ta, tb], years)
    cmp_ = compare(ta, tb, hist, years)
    out = {}
    for p, secs in cmp_.items():
        for sec, r in secs.items():
            if not isinstance(r, dict) or sec == "grade":
                continue
            sdiff = _section_key(ta, p, sec) != _section_key(tb, p, sec)
            if not (r["days"] or r.get("tranche_diff") or sdiff):
                continue
            cal = r["_cal"]
            step = max(1, len(r["days"]) // per)
            picks = r["days"][::step][:per]
            pa = tree_grade.ProductEval(ta, p, hist, cal)
            pb = tree_grade.ProductEval(tb, p, hist, cal)
            sub = {"products": {p: ta["products"][p]}, "defs": ta.get("defs")}
            subb = {"products": {p: tb["products"][p]}, "defs": tb.get("defs")}
            cases = []
            for d in picks:
                i = cal.index(d)
                prices = {}
                for s in sorted(cond.symbols_of(sub) | cond.symbols_of(subb)):
                    cs = [c for c in hist.get(s) or [] if c.date <= d][-25:]
                    prices[s] = [[c.date, c.open, c.high, c.low, c.close, c.volume] for c in cs]
                cases.append({"date": d, "a": r["_ia"][sec][i], "b": r["_ib"][sec][i],
                              "a_explain": _zone_explain(pa, sec, i), "b_explain": _zone_explain(pb, sec, i),
                              "prices_last25[date,o,h,l,c,v]": prices})
            entry = {"agree": r["agree"], "diff_days": len(r["days"]), "expr_differs": sdiff,
                     "a_tree": ta["products"][p][sec], "b_tree": tb["products"][p][sec], "cases": cases}
            if r.get("tranche_diff"):
                entry["tranche_trades_diff"] = [{"a": a, "b": b} for a, b in r["tranche_diff"][:per]]
            out["%s.%s" % (p, sec)] = entry
    ensure_dir(LOGS)
    path = os.path.join(LOGS, "disagree-%s.json" % slug)
    pairing = {p: pair_conditions(ta, tb, p, hist, years) for p in ta["products"] if p in tb["products"]}
    shape = {p: {z: zone_diff(ta, tb, p, z) for z in cond.ZONES} for p in ta["products"] if p in tb["products"]}
    write_text(path, json.dumps({"defs_a": ta.get("defs"), "defs_b": tb.get("defs"), "tree_diff": shape, "pairing": pairing,
                                 "sections": out}, ensure_ascii=False, indent=1, default=str))
    for p, t in pairing.items():
        print("  %s 조건 짝: 공통 %d · a에만 %d · b에만 %d" % (p, len(t["common"]), len(t["only_a"]), len(t["only_b"])))
    print("갈린 칸 %d개 → %s" % (len(out), path))


# ------------------------------------------------------------------ 트리 비교 도구(검사용)
def _inline(node, defs):
    """def 참조를 그 정의로 펼친다(다른 추출의 defs 와 이름이 겹쳐도 섞이지 않게)."""
    if isinstance(node, dict):
        if "def" in node and len([k for k in node if k not in cond.META]) == 1:
            body = _inline(defs[node["def"]], defs)
            if isinstance(body, dict):
                body = dict(body, **{k: v for k, v in node.items() if k in cond.META})
            return body
        return {k: _inline(v, defs) for k, v in node.items()}
    if isinstance(node, list):
        return [_inline(x, defs) for x in node]
    return node


def _strip_meta(node):
    """META(label·ref·id·note)를 모든 깊이에서 떼낸 '순수 로직'만 남긴다 — 되접기 신원 비교용."""
    if isinstance(node, dict):
        return {k: _strip_meta(v) for k, v in node.items() if k not in cond.META}
    if isinstance(node, list):
        return [_strip_meta(x) for x in node]
    return node


_FLIP = {"lt": "gt", "le": "ge"}


def _canon(node):
    """모양만 다르고 뜻이 같은 식을 같은 글자로 — 시세 기본값(sym $self·tf 1d) 생략, a<b → b>a, a≤b → b≥a, all/any/atleast 안의 순서 정렬
    (3값 논리에서 순서는 결과에 영향이 없다). META 는 이미 뗀 식을 받는다. 그 밖의 목록(caution·exit 규칙 등)은
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


def _logic_key(node, defs):
    """같은 식인지 가리는 지문 — def 를 끝까지 펼치고 META(이름·출처)를 뗀 뒤 정규화(_canon)한 식.
    문장·이름과 무관하게 식이 같으면 같은 조건이다("?" 수동 식도 식 그대로 비교된다)."""
    return json.dumps(_canon(_strip_meta(_inline(node, defs))), ensure_ascii=False, sort_keys=True)


_RULE_OPS = ("all", "any", "atleast", "not", "manual")


def _cond_op(node):
    """노드의 연산 키 하나(META·보조키 제외). 조건 노드가 아니면(연산 0개·2개 이상) None.
    entry 래퍼({when,scale,…})나 리스트·원시값을 조건으로 오인하지 않게 cond 의 판정을 그대로 쓴다."""
    if not isinstance(node, dict):
        return None
    try:
        return cond._op_of(node)
    except cond.CondError:
        return None


def _factorable(node):
    """공통 def 로 뽑거나 되접을 '규칙 덩어리'인가 — 유효한 조건 노드이면서, 규칙 연산(all/any/atleast/
    not/manual)이거나 '이름표 달린 비교'(VIX 10% 같은 gt/ge/lt/le). 원시값·arith·case·sizing 구조
    (frac/weight…)·entry 래퍼는 제외한다(래퍼는 _cond_op 가 None, 나머지는 op 가 집합 밖이라 자동 제외)."""
    op = _cond_op(node)
    if op is None:
        return False
    if op in _RULE_OPS:
        return True
    return op in cond.CMP and bool(node.get("label"))


def name_conflicts(tree):
    """한 상품 안에서 이름과 로직이 1:1 이 아닌 라벨 노드 [(상품, 종류, [이름…])] — 사람은 이름으로 조건을 구분한다.
      · '같은 로직 다른 이름' — 한 조건이 두 이름으로 보여 두 조건처럼 읽힌다(심판이 한 이름으로 써야 한다).
      · '같은 이름 다른 로직' — 다른 두 조건이 한 이름으로 보여 한 조건이 두 번 뜬 것처럼 읽힌다(이름을 갈라야 한다).
    상품 사이는 보지 않는다 — $index·$self 는 상품마다 다른 종목이라 'S&P500 …'/'나스닥100 …'처럼 이름이 다른 게 맞다."""
    defs = tree.get("defs") or {}
    out = []
    for p, cfg in tree["products"].items():
        names, logics = {}, {}

        def walk(node):
            if isinstance(node, dict):
                if node.get("label") and _factorable(node):
                    k = _logic_key(node, defs)
                    names.setdefault(k, set()).add(node["label"])
                    logics.setdefault(node["label"], set()).add(k)
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        walk(_inline(cfg, defs))
        out.extend((p, "같은 로직 다른 이름", sorted(ls)) for ls in names.values() if len(ls) > 1)
        out.extend((p, "같은 이름 다른 로직", [lb]) for lb, ks in logics.items() if len(ks) > 1)
    return out


# ------------------------------------------------------------------ 매도 규칙(exit 칸) 이중 추출 비교
def _exit_rules(cand, prod):
    """후보 트리의 상품 매도 규칙(exit 칸)을 def 를 펼쳐 돌려준다."""
    defs = cand.get("defs") or {}
    rules = ((cand.get("products") or {}).get(prod) or {}).get("exit") or []
    return [dict(r, when=_inline(r["when"], defs)) for r in rules]


def compare_exits(tree, ea, eb, hist, years):
    """같은 진입 신호에 두 매도 규칙을 돌려 진입일별로 짝지어 비교 → {prod: {n, diff:[(ta, tb)]}}."""
    out = {}
    for p in tree["products"]:
        cal = [c.date for c in hist.get(p) or []]
        starts = _entry_starts(tree, p, hist, cal, years)
        ta = {t["entry"]: t for t in trades_mod.build_trades(tree, p, hist, cal, starts, _exit_rules(ea, p))}
        tb = {t["entry"]: t for t in trades_mod.build_trades(tree, p, hist, cal, starts, _exit_rules(eb, p))}
        keys = sorted(set(ta) | set(tb))
        diff = [(ta.get(k), tb.get(k)) for k in keys
                if not (ta.get(k) and tb.get(k) and _trade_key(ta[k]) == _trade_key(tb[k]))]
        out[p] = {"n": len(keys), "diff": diff}
    return out


def dump_exit_disagreements(slug, per, years):
    """매도 규칙이 갈린 거래 덤프(심판의 비교 도구). 진입 신호는 후보 a 의 것으로 맞춘다(같은 진입에 두 매도 규칙)."""
    ea, eb = _load(slug, "tree_candidates/a.json"), _load(slug, "tree_candidates/b.json")
    tree = ea
    hist = _history([ea, eb], years)
    cmp_ = compare_exits(tree, ea, eb, hist, years)
    out = {}
    for p, r in cmp_.items():
        cs = hist.get(p) or []
        idx = {c.date: i for i, c in enumerate(cs)}
        step = max(1, len(r["diff"]) // per)
        cases = []
        for a, b in r["diff"][::step][:per]:
            ent = (a or b)["entry"]
            ends = [x for x in ((a or {}).get("exit"), (b or {}).get("exit")) if x]
            i0 = idx[ent]
            i1 = min(len(cs) - 1, max(idx[x] for x in ends) + 1) if ends else min(len(cs) - 1, i0 + 60)
            cases.append({"entry": ent, "a": a, "b": b,
                          "bars_from_entry[date,o,h,l,c]": [[c.date, c.open, c.high, c.low, c.close]
                                                            for c in cs[i0:i1 + 1]]})
        out[p] = {"trades": r["n"], "diff": len(r["diff"]),
                  "a_rules": ea["products"][p].get("exit"), "b_rules": eb["products"][p].get("exit"),
                  "cases": cases}
    ensure_dir(LOGS)
    path = os.path.join(LOGS, "exit-disagree-%s.json" % slug)
    write_text(path, json.dumps({"defs_a": ea.get("defs"), "defs_b": eb.get("defs"), "products": out},
                                ensure_ascii=False, indent=1, default=str))
    for p, v in out.items():
        print("  %s 거래 %d 중 %d 갈림" % (p, v["trades"], v["diff"]))
    print("-> %s" % path)


def check_exits(tree, ea, eb, hist, years, review):
    """후보 a·b 의 exit 칸을 거래별로 비교 -> 갈린 상품은 심판 기록 필수 + 심판이 a/b 를 골랐으면 최종 트리의
    규칙이 그쪽과 같은 거래를 내야 한다(custom 이면 최종 트리 자체가 심판의 답이라 대조할 상대가 없다)."""
    stop = []
    decided = review.get("exits") or {}
    for p, r in compare_exits(tree, ea, eb, hist, years).items():
        sdiff = _section_key(ea, p, "exit") != _section_key(eb, p, "exit")
        line = "  %s %-14s 거래 %d 중 %d 갈림%s" % ("✅" if not (r["diff"] or sdiff) else "≠", p + ".exit", r["n"],
                                               len(r["diff"]), " · 식 다름" if sdiff else "")
        d = decided.get(p)
        if r["diff"] or sdiff:
            if not d or d.get("winner") not in ("a", "b", "custom") or not d.get("why"):
                stop.append("%s.exit 미심판 불일치" % p)
                line += "  ❌ 심판 기록 없음"
            else:
                line += "  -> 심판: %s" % d["winner"]
        elif d and d.get("winner") in ("b", "custom"):
            if not d.get("why"):
                stop.append("%s.exit 심판 사유 없음" % p)
            line += "  -> 심판: %s (두 추출이 같아도 원문 판단으로 바꿈)" % d["winner"]
        # 최종 트리의 규칙은 승자(심판 기록이 없으면 a)와 같은 거래를 내야 한다
        win_name = (d or {}).get("winner", "a")
        if win_name == "custom":
            print(line)
            continue
        if _section_key(tree, p, "exit") != _section_key(ea if win_name == "a" else eb, p, "exit"):
            stop.append("%s.exit 최종 규칙의 식이 %s 와 다름" % (p, win_name))
            line += "  ❌ 최종 != %s(식)" % win_name
        print(line)
    return stop


# ------------------------------------------------------------------ 책 하나
def _check_pair(slug, tree, ta, tb, hist, years, review):
    stop = []
    cmp_ = compare(ta, tb, hist, years)
    decided = review.get("sections") or {}
    for p, secs in cmp_.items():
        if any(k.startswith("missing") for k in secs):
            stop.append("%s %s 상품이 한쪽 추출에만 있음" % (slug, p))
            continue
        for sec in COMPARED:
            r = secs[sec]
            key = "%s.%s" % (p, sec)
            tdiff = r.get("tranche_diff") or []
            sdiff = _section_key(ta, p, sec) != _section_key(tb, p, sec)   # 수동·"?" 식 차이는 동작 비교로 안 보인다
            differs = bool(r["days"] or tdiff or sdiff)
            line = "  %s %-14s 일치 %5.1f%% (%d일 중 %d일 갈림%s%s)" % (
                "≠" if differs else "✅", key, r["agree"] * 100, r["n"], len(r["days"]),
                " · 분할 거래 %d건 갈림" % len(tdiff) if tdiff else "", " · 식 다름" if sdiff else "")
            if differs:
                d = decided.get(key)
                if not d or d.get("winner") not in ("a", "b", "custom") or not d.get("why"):
                    stop.append("%s 미심판 불일치" % key)
                    line += "  ❌ 심판 기록 없음"
                else:
                    line += "  → 심판: %s" % d["winner"]
                    if d["winner"] in ("a", "b"):
                        win = ta if d["winner"] == "a" else tb
                        if _section_key(tree, p, sec) != _section_key(win, p, sec):
                            stop.append("%s 최종 트리의 식이 승자(%s)와 다름" % (key, d["winner"]))
                            line += " ❌ 최종≠승자(식)"
            print(line)
    return stop


def duplicate_bodies(tree):
    """같은 식이 두 번 이상 '정의'된 이름 달린 조건 [[이름…]] — 참조({"def"})가 아니라 본문이 여러 벌인 것.
    같은 조건은 def 하나에 한 번 쓰고 쓰는 곳은 참조해야 한다(두 벌이면 화면에 두 번 뜨고 답이 엇갈린다).
    포지션 값(pos)을 쓰는 식은 문법상 def 에 둘 수 없어(매도·분할 규칙 안에 직접) 참조로 접을 길이 없으니 제외한다."""
    defs = tree.get("defs") or {}
    seen = {}

    def walk(n):
        if isinstance(n, dict):
            if n.get("label") and _factorable(n) and not cond._uses_pos(n, defs):
                seen.setdefault(_logic_key(n, defs), []).append(n["label"])
            for k, v in n.items():
                if k not in cond.META:
                    walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(defs)
    walk(tree["products"])
    return [ls for ls in seen.values() if len(ls) > 1]


def _nameless_manual(node, out=None):
    """label 없는 수동 잎 목록(문장 수동·"?" 식) — 이게 있으면 화면에 '수동 확인'(이름 없음)으로 새거나
    조용히 사라진다. 이름은 추출자가 단다."""
    out = [] if out is None else out
    if isinstance(node, dict):
        if cond.is_manual(node) and not node.get("label"):
            out.append(cond.manual_text(node)[:40] if "manual" in node else json.dumps(node, ensure_ascii=False)[:60])
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
        tree = tree_grade.load_tree(slug)
    except cond.CondError as e:
        print("  ❌ tree.json 문법 오류: %s" % e)
        return ["%s 트리 문법" % slug], []
    if tree is None:
        print("  ❌ tree.json 없음 — 라이브 책은 조건 트리로만 판정한다")
        return ["%s 트리 없음" % slug], []
    # 00. 직렬화 형식 정지 — 구간② 파일은 공통 직렬화(cond.compact_json)로만 쓴다(줄 수를 부풀리지 않게)
    loose = [n for n in ("tree.json", "tree_candidates/a.json", "tree_candidates/b.json", "tree_candidates/a.rules.json",
                         "tree_candidates/b.rules.json", "scenarios.json")
             if os.path.exists(os.path.join(BASE, "books", slug, n))
             and not cond.is_compact(os.path.join(BASE, "books", slug, n))]
    if loose:
        stop.append("%s 공통 직렬화 아님 %d개" % (slug, len(loose)))
        print("  ❌ 공통 직렬화가 아닌 파일 %s — 쓴 사람이 python -m shared.cond fmt <파일> 로 다시 쓴다" % loose)
    # 0. 이름 없는 수동 조건 정지 — 체크리스트가 조용히 사라지거나 '수동 확인'으로만 뜨면 안 된다
    nameless = _nameless_manual(tree)
    if nameless:
        stop.append("%s 이름 없는 수동 조건 %d개" % (slug, len(nameless)))
        print("  ❌ label 없는 수동 잎 %d개 — 화면에 '수동 확인'으로 샌다: %s" % (len(nameless), nameless[:3]))
    # 0a. 이름↔로직 1:1 정지 — 한 조건이 두 이름이거나 두 조건이 한 이름이면 사람이 잘못 읽는다(심판이 고쳐 써야 함)
    conflicts = name_conflicts(tree)
    for kind in ("같은 로직 다른 이름", "같은 이름 다른 로직"):
        hit = [(p, ls) for p, k, ls in conflicts if k == kind]
        if hit:
            stop.append("%s %s %d개" % (slug, kind, len(hit)))
            print("  ❌ %s %d개 — %s: %s"
                  % (kind, len(hit), "심판이 한 이름으로 tree.json 을 다시 쓴다" if kind.startswith("같은 로직")
                     else "심판이 이름을 갈라 tree.json 을 다시 쓴다", hit[:2]))
    # 0c. 같은 식 두 벌 정지 — 같은 조건은 def 하나·참조로
    dups = duplicate_bodies(tree)
    if dups:
        stop.append("%s 같은 식이 두 번 정의됨 %d개" % (slug, len(dups)))
        print("  ❌ 같은 식이 두 번 이상 정의됨 %d개 — 심판이 def 하나로 쓰고 참조한다: %s" % (len(dups), dups[:3]))
    # 0b. 식 없는 수동 정지 — '저자 미명시' 는 수치로 정할 수 있으면 "?" 식, 순수 주관이면 '(정성)' 문장
    unclassified = _unclassified_numeric_manual(tree)
    if unclassified:
        stop.append("%s 식 없는 수동 조건 %d개" % (slug, len(unclassified)))
        print("  ❌ '(정성)' 아닌 문장 수동 %d개 — 수치로 정할 수 있으면 식으로 쓰고 숫자 자리를 \"?\" 로: %s"
              % (len(unclassified), unclassified[:3]))
    review = tree.get("review") or {}             # 심판의 판정 근거 — 최종 트리와 한 파일(심판만 쓴다)
    ta, tb = _load(slug, "tree_candidates/a.json"), _load(slug, "tree_candidates/b.json")
    for t in (ta, tb):
        if t:
            try:
                cond.validate_tree(t)
            except cond.CondError as e:
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
        stop.extend(_check_pair(slug, tree, ta, tb, hist, years, review))
        for name, t in (("a", ta), ("b", tb)):
            un = t.get("unexpressed") or []
            if un:
                heads = {}
                for u in un:
                    h = next((x for x in MANUAL_HEADS if str(u.get("reason", "")).startswith(x)), "기타")
                    heads[h] = heads.get(h, 0) + 1
                print("  · 추출 %s 표현 못 한 규칙 %d: %s" % (name, len(un), " · ".join("%s %d" % kv for kv in heads.items())))

    # 3. 매도 규칙(exit 칸) 이중 추출
    if ta and tb:
        stop.extend(check_exits(tree, ta, tb, hist, years, review))

    # 4. 원문 사례
    scen = _load(slug, "scenarios.json")
    if not scen:
        warn.append("%s 원문 사례 시나리오 없음" % slug)
        print("  ⚠ scenarios.json 없음")
    else:
        res = run_scenarios(tree, scen, review.get("scenario_overrides") or {})
        cnt = {}
        for sc, st, got in res:
            cnt[st] = cnt.get(st, 0) + 1
            if st in ("불일치", "형식오류") or st.startswith("평가오류"):
                stop.append("%s 사례 %s: %s" % (slug, st, sc.get("name")))
                print("  ❌ 사례 %s: %s [%s.%s%s 기대 %s, 결과 %s] (%s)"
                      % (st, sc.get("name"), sc.get("prod"), sc.get("section"),
                         (":" + sc["rule"]) if sc.get("rule") else "", sc.get("expect"), got, sc.get("ref")))
            elif st == "재현불가":
                warn.append("%s 사례 재현불가: %s" % (slug, sc.get("name")))
        print("  사례 %d개: %s" % (len(res), " · ".join("%s %d" % kv for kv in cnt.items())))

    # 5. 발화 통계
    table, fw, acked = fire_stats(tree, hist, years, review.get("fire_ack") or {})
    for p, sec, label, rate, flag in table:
        if rate is None:
            print("  %-5s %s" % (p, label))
    same = [w for w in fw if "완전히 같은 조건" in w]   # 식은 달라도 판정이 3년간 같음 — 같은 조건 두 벌일 가능성
    if same:
        stop.append("%s 판정이 완전히 같은 조건 %d쌍(사유 없음)" % (slug, len(same)))
    fw = [w for w in fw if w not in same]
    for w in same:
        print("  ❌ " + w + " — 같은 조건이면 하나로, 원문이 일부러 둘로 썼으면 review.fire_ack 에 사유")
    for w in fw:
        print("  ⚠ " + w)
    for w in acked:
        print("  ☑ %s — 확인됨: %s" % (w, review["fire_ack"][w]))
    warn.extend(fw)
    stale = [w for w in (review.get("fire_ack") or {}) if w not in acked]
    if stale:
        warn.append("%s 쓰이지 않는 확인 기록 %d개" % (slug, len(stale)))
        print("  ⚠ tree.json review.fire_ack 중 더는 안 뜨는 경고 %d개 — 지울 것: %s" % (len(stale), stale[:2]))

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


def main():
    argv = sys.argv[1:]
    years = float(argv[argv.index("--years") + 1]) if "--years" in argv else 3
    if "--dump" in argv:
        dump_disagreements(argv[0], int(argv[argv.index("--dump") + 1]), years)
        return 0
    if "--dump-exits" in argv:
        dump_exit_disagreements(argv[0], int(argv[argv.index("--dump-exits") + 1]), years)
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
