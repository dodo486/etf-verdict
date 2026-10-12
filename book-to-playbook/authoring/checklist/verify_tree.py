#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조건 트리(체크리스트) 검사 — 규칙이 원문 뜻대로 '동작'하나 (책 무관). 트리를 만들거나 고치지 않는다.

  최종 트리(tree.json)는 심판(서브에이전트)만 쓴다 — 추출자 a·b 의 후보를 원문과 대조해 융합한다. 이 파일은
  심판이 쓴 트리의 채점만 한다(코드가 최종 트리에 끼어들지 않는다). 심판의 비교 도구(갈린 날 덤프)와 '같은 뜻' 잣대는
  authoring/checklist/compare.py — 채점도 그 잣대 한 벌로 한다.

왜 있나
  옛 검증층(창작·커버리지·규칙↔명세·의미검사·자동가능)은 원문과 규칙의 **글자**(숫자·단어·어휘)를
  대조했다. 그래서 '2'라는 글자만 있으면 2거래일 유지가 1일로 판정돼도 통과했고, 사전에 없는
  새 조건(RSI·볼린저…)은 '찾은 게 없으니 누락도 없음'으로 통과했다. 이 검사는 규칙을 실제 시세와
  원문 사례에 돌려 본다 — 조건 종류를 몰라도 같은 절차가 돈다. 트리의 뜻은 dsl/(cond·grade)
  한 벌이라 여기서 본 동작이 곧 구간③ 판정 엔진의 동작이다. 트리·시세는 판정과 같은 판단자(signals/judge.Judge).

무엇을 하나 (books/<slug>/ 아래) — 정지·경고의 뜻과 고칠 곳은 authoring/checklist/JUDGE.md 5절
  1. 최종 트리(tree.json, 심판이 씀) — 라이브 책은 반드시 있어야 하고, 문법 검사를 통과해야 한다.
     v3 형식 밖의 키(옛 review·오타)·동사에 안 맞는 qty 는 문법 오류로 정지(출입구 validate).
  2. 이중 추출 일치 — 서로 독립인 두 추출(tree_candidates/a.json·b.json)과 최종 트리를 **규칙 단위**로 맞춘다(규칙의 뜻 =
     이름·출처·메모를 뗀 펼친 식). a·b 가 같은 식으로 합의하지 않은 최종 규칙(한쪽에서 고름·심판이 새로 씀)은 그 규칙의
     `why` 가 있어야 한다(미심판 불일치). 등급 동사(안 산다·산다)·비중은 실제 시세 수년치로 날마다 비교해 일치율을 보인다(참고).
  3. 같은 뜻 정리 — 같은 식 두 벌(규칙 둘이 같은 뜻 · 같은 측정을 참조 없이 두 번) · 이름↔식 1:1(같은 이름 다른 식 ·
     같은 식 다른 이름) · skip 사유 머리(데이터 없음:·연산 없음:) · 시세 잎 티커(sym)에 "?" 남음 → 정지.
  4. 원문 사례 재현 — 원문만 보고 따로 쓴 시나리오(scenarios.json)를 합성 시세로 돌려 그날 결과(안 산다·산다·관망·판다,
     비중 % 포함)가 기대값과 맞는지. 틀리면 정지(사례가 원문을 잘못 읽었으면 심판이 보고 — 사례 작성자가 다시 쓴다).
  5. 발화 통계 — 최종 트리의 라벨 노드를 실제 시세에서 날마다 평가해: 한 번도 안 뜸 · 거의 매일 ·
     항상 판정 불가 · 두 조건이 완전히 같음 · 산다가 뜨면 늘 안 산다도 뜸 · 산다 도달 불가.
     (경고. 단 '완전히 같은 조건'은 같은 조건 두 벌일 수 있어 정지 — 동사가 다르거나 두 규칙 다 why 가 있으면 둔다.)
  6. 비중 합 — 상품 비중(산다 qty cash)의 합이 어느 날이든 100% 를 넘으면 정지.
  7. 수동 사유 분류 — manual 사유를 '저자 미명시 / 데이터 없음 / 연산 없음' 으로 세어 보고한다.
     사유 머리가 없으면 경고(어디로 보내야 할지 모르는 수동은 조용한 누락이 된다).

빠른 계약(--quick) — 시세 없이 바로 갈리는 것만(라이브 책마다, 실패 → 정지):
  · books/<slug>/source_index.json — 원문이 소절 단위로 잘려 있다(소절 키 = 체크리스트 ref)
  · books/<slug>/tree.json — 체크리스트가 문법을 통과한다(v3 규칙·동사 셋)
  · 트리의 ref 가 전부 실제 소절 키다(없는 소절을 근거로 삼지 않는다)
  (책 페이지 구획·UI 사본은 페이지를 조립하는 consumers/display/book_page.py 가 본다)

종료코드: 0 통과 · 1 정지(트리 없음/문법/미심판 불일치/같은 뜻 두 벌/사례 실패/비중 초과 …) · 2 경고만. --quick 은 0 · 1.
사용: python -m authoring.checklist.verify_tree [slug ...] [--years 3]
      python -m authoring.checklist.verify_tree --quick [slug ...]   빠른 계약만
"""
import json
import os
import sys
from collections import namedtuple

from shared import paths  # noqa: F401  (UTF-8 출력)
from shared.paths import book_file, live_slugs, source_index_json
from dsl.tradeTool import Cond, Grade
from market import md_feed
from signals.judge import Holding, Judge
from authoring.checklist.compare import (COMPARED, compare, evaluate, factorable, history, logic_key,
                                         rule_keys, window)

Candle = namedtuple("Candle", "date open high low close volume")
MANUAL_HEADS = ("저자 미명시", "데이터 없음", "연산 없음")
SKIP_HEADS = ("데이터 없음", "연산 없음")                 # skip 은 식으로 못 쓰는 잔여만(JUDGE 5절 · 충실성)
WAIT = "관망"                                           # 사례의 그날 결과 넷 = 동사 둘(안 산다·산다) + 관망 + 판다


def _load(slug, name):
    """산출물 JSON(원문 사례 scenarios.json 등 — 트리 아님) — 없으면 None."""
    p = book_file(slug, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


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


def _outcome(judge, i, view):
    """등급 동사 값(view = "opt" 낙관 · "pes" 비관) → 그날 결과(안 산다·산다·관망) — 하나로 안 정해지면 None."""
    block, buy = judge.gate_value(Cond.BLOCK, i, view), judge.gate_value(Cond.BUY, i, view)
    if block is True:
        return Cond.BLOCK
    if block is False and buy is True:
        return Cond.BUY
    if block is False and buy is False:
        return WAIT
    return None


def _sell_hit(judge, m):
    """첫날 종가에 사서 들고 있었다면 마지막 날 판다 갈래가 걸렸나 — 참·거짓·모름(manual_as=m)."""
    holding = Holding(0, judge.price("close")[0])
    vals = [judge.evaluate(r.when, m, holding)[-1] for r in judge.sells()]
    return True if True in vals else (False if all(v is False for v in vals) else None)


def scenario_result(tree, sc):
    """사례 하나 → (상태, 결과). 결과 = 그날 그 종목의 결과(SCENARIO.md: 안 산다·산다·관망·판다, 비중 % 가 있으면 함께).
    수동 조건 때문에 갈리면 '확인됨/안 됨' 두 경우를 본다 — 어느 쪽으로도 기대값이 안 나오면 불일치(재현불가로 덮지 않는다)."""
    p, expect = sc.get("prod"), sc.get("expect")
    want, pct = (expect.get("do"), expect.get("pct")) if isinstance(expect, dict) else (expect, None)
    if "section" in sc or want not in Cond.VERBS + (WAIT,) or not tree.has(p):
        return "형식오류", None                  # 옛 칸 사례(section·참/거짓 기대값) 또는 모르는 결과·상품
    hist, cal = _synthetic(sc, tree.symbols())
    judge = tree.product(p, hist, days=cal)
    if want == Cond.SELL:
        alts = {_sell_hit(judge, m) for m in (None, True, False)}
        got = {True: Cond.SELL, False: "안 판다", None: None}
        alts = {got[x] for x in alts}
    else:
        i = len(cal) - 1
        alts = {_outcome(judge, i, "opt"), _outcome(judge, i, "pes")}
        if pct is not None and want == Cond.BUY:
            w, rng = judge.weight_at(i)
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
        ev, judge = evaluate(tree, p, hist)
        cal = judge.days
        idx = window(cal, years)
        N = max(1, len(idx))
        nodes = []
        top_avoid = {repr(n) for n in Grade._top_labeled(tree.gate(p, Cond.BLOCK))}
        for sec, n in _stat_nodes(tree, p):
            if _has_manual(n):
                continue                         # 수동이 섞이면 '안 뜸/모름'이 정상이다
            s = judge.evaluate(n)
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
        judge = tree.product(p, hist)
        cal = judge.days
        for i in window(cal, years):
            w, alt = judge.weight_at(i)
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
                key = n["manual"] if "manual" in n else logic_key(n)   # "?" 식은 식이 신원
                if key in seen:
                    continue
                seen.add(key)
                text = Cond.manual_text(n)
                head = next((h for h in MANUAL_HEADS if text.startswith(h + ":")), "사유 머리 없음")
                cnt[head] = cnt.get(head, 0) + 1
    return cnt


def check_rules(tree, ta, tb):
    """최종 규칙마다 — a·b 가 같은 뜻으로 합의했으면 그대로, 아니면(한쪽에서 고름·심판이 새로 씀) why 필수."""
    stop = []
    ka, kb = set(rule_keys(ta).values()), set(rule_keys(tb).values())
    cnt = {"합의": 0, "a 쪽": 0, "b 쪽": 0, "심판이 새로": 0}
    for l, k in rule_keys(tree).items():
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
    for l, k in rule_keys(tree, expand=False).items():
        if l not in skipped:
            by.setdefault(k, []).append(l)
    out.extend(("같은 식 두 벌", ls) for ls in by.values() if len(ls) > 1)
    by = {}
    for l in tree.labels():
        v = tree.value(l, expand=False)
        if v is not None:
            by.setdefault(logic_key(v), []).append(l)
    out.extend(("같은 측정 두 번(참조 없이)", ls) for ls in by.values() if len(ls) > 1)
    for p in tree.products():
        names, logics = {}, {}

        def walk(node):
            if isinstance(node, dict):
                if node.get("label") and factorable(node):
                    k = logic_key(node)
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
    """시세 잎의 티커(sym)가 "?" 로 남은 자리(사용자 확인 대상 — 저자가 어느 종목인지 안 줌) → [식의 라벨]."""
    out = []

    def walk(n, lab):
        if isinstance(n, dict):
            lab = n.get("label") or lab
            if "px" in n and n.get("sym") == Cond.UNKNOWN:
                out.append(lab or "(이름 없음)")
            for k, v in n.items():
                if k not in Cond.META:
                    walk(v, lab)
        elif isinstance(n, list):
            for v in n:
                walk(v, lab)
    for c in tree.conditions():
        walk(c, None)
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
        tree = Judge.open(slug)
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
        stop.append("%s 티커 \"?\" 남음 %d개" % (slug, len(gaps)))
        print("  ❌ 시세 잎 티커(sym)에 \"?\" 남음(사용자 확인): %s" % gaps[:5])
    ta, tb = Judge.read(slug, "a"), Judge.read(slug, "b")
    for t in (ta, tb):
        if t:
            try:
                t.validate()
            except Cond.CondError as e:
                print("  ❌ 후보 트리 문법 오류: %s" % e)
                return ["%s 후보 트리 문법" % slug], []
    hist = history([tree, ta, tb], years)
    missing = Judge.missing(hist)
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


# ------------------------------------------------------------------ 빠른 계약(--quick)
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
        tree = Judge.read(slug)
        if not tree:
            raise ValueError("tree.json 없음")
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


def quick_main(slugs):
    stop = []
    for slug in slugs:
        bad = contract(slug)
        print("  %s %-34s %s" % ("✅" if not bad else "❌", "트리 계약 " + slug, "; ".join(bad)[:300] or "통과"))
        if bad:
            stop.append("트리 계약 " + slug)
    if stop:
        print("트리 계약 정지 — %s" % ", ".join(stop))
        return 1
    print("트리 계약 통과 — 소절 인덱스·트리 문법·ref")
    return 0


def main():
    argv = sys.argv[1:]
    if "--quick" in argv:
        return quick_main([a for a in argv if not a.startswith("-")] or live_slugs())
    years = float(argv[argv.index("--years") + 1]) if "--years" in argv else 3
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
