#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""판정 화면 데이터(웹 화면층, 책 무관) — 오늘 판정을 판정 JSON(#verdict-data)·알림 문장으로 빚는다.

판정(시세 조달 + 판단)은 구간③ 판단자(judge/judge.Judge.decisions)가 내고, 이 파일은 그 Decision 과 설명을
사람과 화면이 읽는 모양으로 빚기만 한다 — 화면은 트리를 다시 해석하지 않고 이 출력만 그린다(판단/표시 분리:
화면은 판정을 계산하지 않는다). 라이브는 entry/live 허브가 판정 사실을 _format 으로, 일일 배치(entry.notify)는 render 로 빚는다.

출력 계약(알림 · 화면 · /api/verdict 가 소비):
  top     : {slug, title, ts, date, source, cash, verbs[], grades{}, verdicts[], outside[], missing{}, positions_note}
            outside = 체크리스트 칸에 안 실린 트리 규칙 전부(outside() — 화면이 '칸 밖 규칙'으로 보인다)
            verbs = 동사 셋(정본 tree.gateway.VERBS — 화면 머리글) · grades = 등급 글자표(정본 judge.judge.GRADES)
  verdict : {prod, index, note, date, close, chg, key, grade, reason,
             gates{안 산다, 산다: view}, opt{..}, pes{..},     등급 동사 둘의 중첩 설명 + 낙관·비관 값
             size{label, ref, expr, weight, weight_range, units, tranches[{label, ref, ratio, units, when, view?}]},   얼마나(산다 qty)
                                                     units = 오늘 물량(시작자본 1.0 기준 — judge.to_units, 비중 모르면 None)
             sells[{label, ref, sell(문장 — judge.sell_text), note, when(조건 식 글), view}], exit_policy("book"|"none" — judge.exit_policy),
             positions[{…, sells[], next_tranche}]}                  positions = 내 포지션(로컬 파일)이 있을 때만
view 는 노드 하나당 항목 하나 {v, op?, n?, kids?, label?, ref?, manual?, note?, expr?, off?, detail?} (web/explain.view —
값은 판단자 ProductJudge.value 가 낸다, 값 없는 규칙 설명은 web/explain.static_view + ProductJudge.blank_value)
— 수동은 '모름'(사람이 답했으면 그 답 — render(answers=))으로 둔 그날 값. 화면은 다시 계산하지 않고 그대로 그린다.
"""
from datetime import datetime, timedelta, timezone

from shared.paths import book_meta
from market import md_feed
from tree.gateway import BLOCK, BUY, GATES, SELL, VERBS, _uses_pos, product_specific
from judge.judge import GRADES, NO_EXIT_NOTE, Judge, exit_policy, live_units, sell_text
from web import explain
from web.raw_tree import e as prose

SOURCE = "jhts 시세팀(일봉)"


def book_title(slug):
    """books.json 에서 이 책의 제목(알림/콘솔 헤더용). 없으면 slug.
    명단 읽기는 공용 함수(paths.book_meta) 한 곳을 쓴다 — 직접 파싱하지 않는다."""
    return book_meta(slug).get("title") or slug


# ------------------------------------------------------------------ 상품 하나
def reason_of(key, ex, manual):
    """등급 사유 한 줄 — 무엇이 걸렸는지 라벨로. ex = 동사별 맨 위 라벨 노드 값, manual = [(동사, 라벨, ref)]."""
    def labels(do, val):
        return [l for l, _, v in ex.get(do, []) if l and v is val]
    if key == "avoid":
        hit = labels(BLOCK, True)
        return "%s: %s" % (BLOCK, " · ".join(hit[:3]) if hit else "조건 참")
    if key == "wait":
        return "%s 신호 없음 — 관망" % BUY
    if key == "confirm":
        items = [l for d, l, _ in manual if d == BUY] + \
                ["(%s 아님) %s" % (BLOCK, l) for d, l, _ in manual if d == BLOCK]
        return "수동·장중 확인 시 %s: %s" % (BUY, " · ".join(items[:4]))
    if key == "buy":
        ok = labels(BUY, True)
        return "%s: %s" % (BUY, " · ".join(ok[:3]) if ok else "조건 충족")
    return "데이터 부족으로 판정 불가"


def gate_views(judge, day=None):
    """등급 동사별 조건 설명 {동사: view} — day None 이면 값 없는 설명(시세 없는 상품의 체크리스트 구조)."""
    if day is None:
        return {do: explain.static_view(judge.gate(do), judge.blank_value, judge.product, judge.index) for do in GATES}
    return {do: explain.view(judge.gate(do), lambda n: judge.value(n, day), judge.product, judge.index) for do in GATES}


def _describe(judge, branch):
    """갈래 하나(비중·분할·판다)의 값 없는 설명."""
    return explain.static_view(branch.when, judge.blank_value, judge.product, judge.index)


def _when(judge, branch):
    """갈래 조건의 식 글(그 상품 판 — $self·$index 는 실제 티커) — 화면이 규칙 이름 옆에 '언제'를 그대로 보인다. 조건 없으면 None."""
    return None if branch.when is None else explain.role_text(prose(branch.when), judge.product, judge.index)


def _rule_views(judge, a=None):
    """얼마나(비중·분할)·판다 규칙의 화면 모양 — 시세가 있든 없든 같은 모양(규칙 설명은 값 없는 설명).
    a = 그날 Amount(judge.amount) — 없으면(시세 없음) 비중·물량은 None."""
    sz = judge.weight()
    x = sz.qty.x
    return {"size": {"label": sz.label, "ref": sz.ref, "note": sz.note,
                     "expr": prose(x) if isinstance(x, (dict, list)) else None,   # 비중이 식(모드별 등)이면 그 식 글
                     "weight": a and a.weight, "weight_range": a and a.weight_range, "weight_set": a and a.weight_set,
                     "units": a and live_units(a),            # 오늘 물량(시작자본 1.0 기준, 화면이 × 총 투자금)
                     "tranches": [{"label": t.label, "ref": t.ref, "ratio": t.qty.x,
                                   "units": a and live_units(a, t.qty),
                                   "when": _when(judge, t), "view": _describe(judge, t)} for t in judge.tranches()]},
            "sells": [{"label": r.label, "ref": r.ref, "allprod": r.allprod,
                       "allsame": bool(r.allprod) and not product_specific(r.when or {}),   # 상품마다 같은 규칙 → 공통 섹션
                       "sell": sell_text(r.qty, r.repeat),
                       "note": r.note, "when": _when(judge, r), "view": _describe(judge, r)} for r in judge.sells()],
            "exit_policy": exit_policy(judge.sells())}


def _common_by_rule(v):
    """공통 배치는 규칙 단위 — 한 규칙의 갈래 중 하나라도 상품마다 갈리면(allsame 아님) 그 규칙의 갈래 전부를 상품 카드로.
    (갈래마다 따로 정하면 한 규칙이 공통 섹션과 상품 카드로 쪼개져 보인다.)"""
    items = [k for g in (v.get("gates") or {}).values() for k in (g or {}).get("kids") or []] + list(v.get("sells") or [])
    split = {k.get("label") for k in items if k.get("allprod") and not k.get("allsame")}
    for k in items:
        if k.get("label") in split:
            k.pop("allsame", None)
    return v


def product_verdict(judge, d, mine):
    """상품 하나의 판정 JSON — 판정(Decision d)과 노드 값은 판단자(judge/judge)가 내고, 여기는 설명(web/explain)·화면 모양으로 빚기만 한다.
    mine = 이 상품의 내 포지션(로컬 파일)."""
    base = {"prod": judge.product, "index": judge.index, "note": judge.note}
    if not d.has_data:
        # 시세가 없어도 체크리스트 '구조'(규칙·조건 항목)는 정적으로 보여준다 — 값은 모름(❔), 지어내지 않는다.
        req = md_feed.requested().get(judge.product, "-")
        return _common_by_rule(dict(base, key="unknown", grade=GRADES["unknown"], date="", close=None, chg=None,
                    reason="%s 시세 없음(수집 요청 %s) — 아래는 판정 전 체크리스트 구조" % (judge.product, req),
                    gates=gate_views(judge), opt={}, pes={}, **_rule_views(judge)))
    reason = reason_of(d.key, d.top, d.manual)
    # 데이터 완전성 가드 — 지금 가진 확정 봉이 트리가 쓰는 가장 긴 창(필요 워밍업)보다 짧으면 등급은 ❔(불완전
    #   데이터, 판정 보류)로 떨어져 있다(grade_key). 사유를 '모르고 매매 금지'로 분명히 적는다(✅/⛔ 확신 금지).
    if d.incomplete:
        reason = "불완전 데이터(판정 보류) — 확정 봉 %d개 < 필요 워밍업 %d개, 창이 덜 차 신뢰불가" % (d.confirmed, d.warmup)
    v = dict(base, date=d.date, close=d.close,
             chg=(d.close / d.prev_close - 1) * 100 if d.prev_close else None,
             key=d.key, grade=d.grade, reason=reason, gates=gate_views(judge, d.day),
             opt=d.opt, pes=d.pes, **_rule_views(judge, d.amount))
    pos = [dict(_holding_view(judge, d.day, hs), entry_date=x["entry_date"], entry_px=x["entry_px"], filled=x.get("filled", 1))
           for hs, x in zip(d.holdings, mine)]
    if pos:
        v["positions"] = pos
    return _common_by_rule(v)


def _holding_view(judge, day, hs):
    """보유 하나(HoldingStatus) → {ret, days, sells:[{label, ref, sell, v, view}], next_tranche:{label, ref, ratio, v, view}|None}.
    갈래 설명의 값은 그 보유 문맥으로 판단자에게 묻는다(judge.value(노드, day, hs.holding))."""
    if hs.error:
        return {"error": hs.error}
    val = lambda n: judge.value(n, day, hs.holding)      # noqa: E731
    out = {"ret": hs.ret, "days": hs.days,
           "sells": [{"label": r.label, "ref": r.ref, "sell": sell_text(r.qty, r.repeat), "v": v,
                      "view": explain.view(r.when, val, judge.product, judge.index)} for r, v in hs.sells]}
    nt = hs.next_tranche
    out["next_tranche"] = None if nt is None else {
        "label": nt[0].label, "ref": nt[0].ref, "ratio": nt[0].qty.x, "v": nt[1], "view": explain.view(nt[0].when, val, judge.product, judge.index)}
    return out


# ------------------------------------------------------------------ 칸 밖 규칙(트리 ↔ 화면 대조)
def _placed(verdicts):
    """화면 칸(①안 산다 ②산다 ③판다 ④얼마나)에 실린 갈래 수 {(라벨, 동사): 상품들 중 최대 개수}."""
    out = {}
    for v in verdicts:
        cnt = {}
        for do, g in (v.get("gates") or {}).items():
            for k in (g or {}).get("kids") or []:
                cnt[(k.get("label"), do)] = cnt.get((k.get("label"), do), 0) + 1
        sz = v.get("size") or {}
        if sz.get("label"):
            cnt[(sz["label"], BUY)] = cnt.get((sz["label"], BUY), 0) + 1
        for t in sz.get("tranches") or []:
            cnt[(t["label"], BUY)] = cnt.get((t["label"], BUY), 0) + 1
        for r in v.get("sells") or []:
            cnt[(r["label"], SELL)] = cnt.get((r["label"], SELL), 0) + 1
        for key, n in cnt.items():
            out[key] = max(out.get(key, 0), n)
    return out


def _referenced(verdicts):
    """화면 설명 안 어디든 이름으로 실린 라벨(참조로 펼쳐진 이름 조건 포함)."""
    seen = set()

    def walk(x):
        if isinstance(x, dict):
            if x.get("label"):
                seen.add(x["label"])
            for y in x.values():
                walk(y)
        elif isinstance(x, list):
            for y in x:
                walk(y)
    walk(verdicts)
    return seen


def _rule_refs(x, acc=None):
    """적힌 식 안의 {"rule": 이름} 참조 이름들."""
    acc = set() if acc is None else acc
    if isinstance(x, dict):
        if isinstance(x.get("rule"), str) and "pos" not in x:
            acc.add(x["rule"])
        for y in x.values():
            _rule_refs(y, acc)
    elif isinstance(x, (list, tuple)):
        for y in x:
            _rule_refs(y, acc)
    return acc


def outside(tree, verdicts):
    """트리의 규칙 중 체크리스트 칸에 안 실린 것 [{label, ref, on, kind, reason, text}] — 화면이 '칸 밖 규칙'으로 전부 보인다.
    사람은 트리를 웹으로만 검증하므로, 트리에 있는데 화면 어디에도 없는 규칙이 하나도 없어야 한다(조용히 빠지지 않게).
    kind: skip(못 옮김) · name(이름 조건 — 어느 칸에도 안 쓰임) · branch(행동 갈래인데 칸에 안 실림)."""
    cards = tree.cards()
    # 다른 규칙이 {"rule": 이름} 으로 쓰는 이름 조건 — 그 규칙 줄의 식 글에 펼쳐져 보인다(칸 밖 아님)
    named = _referenced(verdicts) | _rule_refs([(c.value, [(b.when, b.qty and b.qty.x) for b in c.branches]) for c in cards])
    placed, out = _placed(verdicts), []
    for c in cards:
        base = {"label": c.label, "ref": c.ref, "on": c.on}
        if c.skip:
            out.append(dict(base, kind="skip", reason=c.skip, text=None))
            continue
        if not c.branches:
            if c.label not in named:
                out.append(dict(base, kind="name", reason="이름 조건 — 어느 행동 규칙도 쓰지 않아 체크리스트 칸에 안 나온다",
                                text=prose(c.value) if c.value is not None else None))
            continue
        left = {}
        for b in c.branches:
            left.setdefault(b.do, []).append(b)
        for do, bs in left.items():
            for b in bs[placed.get((c.label, do), 0):]:
                why = ("조건 없는 갈래" if b.when is None else "포지션 조건(보유 중) 갈래" if _uses_pos(b.when)
                       else "행동 갈래")
                q = "" if b.qty is None else " [qty %s %s]" % (b.qty[0], prose(b.qty[1]))   # 적힌 그대로(변환 안 함)
                out.append(dict(base, kind="branch", reason="%s — 체크리스트 칸에 안 실림" % why,
                                text="%s%s%s" % (do, q, "" if b.when is None else " · 언제 " + prose(b.when))))
    return out


def uncovered(tree, top):
    """트리 ↔ 화면 대조(검사기용) — 화면 데이터(top)에서 보이지 않는 것 [문장]. 비어야 정상.
    · 트리 규칙 이름이 칸(라벨)에도 칸 밖(outside)에도 없다 · 화면 잎(논리 묶음·문장 수동 아님)에 식 글(expr)이 없다."""
    cards = tree.cards()
    shown = (_referenced(top["verdicts"]) | {x["label"] for x in top.get("outside") or []}
             | _rule_refs([(c.value, [(b.when, b.qty and b.qty.x) for b in c.branches]) for c in cards]))
    bad = ["규칙 %r 가 화면 어디에도 없다" % c.label for c in cards if c.label not in shown]

    def walk(it, where):                                       # 조건 설명 항목(view) 하나와 그 자식들
        if not isinstance(it, dict):
            return
        if not it.get("op") and "manual" not in it and not it.get("expr"):
            bad.append("%s: 식 글 없는 조건 %r" % (where, it.get("label")))
        if it.get("mkey") and not it.get("op") and not it.get("expr"):
            bad.append("%s: \"?\" 수동 조건의 식 글 없음 %r" % (where, it.get("label")))
        for k in it.get("kids") or []:
            walk(k, where)
    for v in top["verdicts"]:
        for do, g in (v.get("gates") or {}).items():
            walk(g, "%s %s" % (v.get("prod"), do))
    return bad


# ------------------------------------------------------------------ 책 하나
def render(slug, asof=None, answers=None):
    """asof = 관측 시각(UTC datetime). None 이면 지금 — 장중(tf="1m") 조건을 이 시점 이하로 자른다.
    answers = 화면에서 사람이 답한 수동 {tree.gateway.answer_key: 참/거짓} — 판단자가 그 답으로 등급·조건 값·금액을 낸다
    (서버 권위 — 화면은 다시 계산하지 않는다). None 이면 답 없는 판정, 주면 top["answers"] 로 되돌려 준다.

    판정(Judge.decisions)과 모양 빚기(_format)를 쪼개 둔다 — 라이브 2단 pub-sub(entry/live)에서 신호
    핸들러가 판정 사실을 내 verdict_bus 에 올리면, 화면 소비자가 그 사실로 _format 만 부른다(한 번 계산)."""
    book = Judge.open(slug)
    if book is None:
        return _format(slug, None, {}, [], answers=answers)
    prices = book.prices()
    return _format(slug, book, prices, book.decisions(prices, asof=asof, answers=answers), answers=answers)


def _format(slug, book, prices, decisions, answers=None):
    """판정 사실(Judge.decisions 의 결과)을 top(화면·알림·/api/verdict 가 소비하는 dict)으로 빚는다 —
    라이브 2단 pub-sub 의 화면 소비자가 verdict_bus 에서 받은 사실로 이걸 부른다(같은 모양을 라이브·배치가 공유)."""
    now = datetime.now(timezone.utc).astimezone()
    top = {"slug": slug, "title": book_title(slug), "ts": now.isoformat(), "source": SOURCE,
           "verdicts": [], "missing": {}, "cash": None,
           # 등급 글자표(키→라벨)를 실어보낸다 — 화면이 따로 복붙하지 않고 이걸 받아 쓴다(단일 출처).
           "grades": GRADES,
           # 동사 셋(화면 머리글·판정 JSON 키) — tree.gateway.VERBS 가 정본이다. 화면은 복붙하지 않고 이걸 받아 쓴다.
           "verbs": list(VERBS),
           # 매도 정책 "none"(책에 매도 규칙 없음) 문구 — 정본 judge/judge.NO_EXIT_NOTE(화면이 받아 쓴다).
           "no_exit_note": NO_EXIT_NOTE}
    if book is None:
        top["error"] = "조건 트리 없음 — books/%s/tree.json 이 있어야 판정한다" % slug
        return top
    weights, all_known = [], True
    for _p, d, judge, mine in decisions:
        v = product_verdict(judge, d, mine)
        top["verdicts"].append(v)
        sz = v.get("size") or {}
        if sz.get("weight_set"):
            if sz.get("weight") is None:
                all_known = False
            else:
                weights.append(sz["weight"])
    if weights and all_known:
        top["cash"] = max(0.0, 100.0 - sum(weights))
    top["outside"] = outside(book.tree, top["verdicts"])
    top["date"] = max((v.get("date") or "" for v in top["verdicts"]), default=None)
    top["missing"] = {s: md_feed.requested().get(s, "-") for s in Judge.missing(prices)}
    if answers is not None:
        top["answers"] = answers
    if any(mine for _p, _d, _j, mine in decisions):
        top["positions_note"] = "내 포지션(books/%s/positions.json) 기준 — 로컬 화면에서만 쓴다" % slug
    return top


# ------------------------------------------------------------------ 출력 텍스트 / 알림
def build_text(top):
    now = datetime.fromisoformat(top["ts"])
    L = ["📈 %s  (%s KST · %s 종가 기준)" % (top.get("title") or top["slug"], now.strftime("%Y-%m-%d %H:%M"),
                                         top.get("date") or "-")]
    if top.get("error"):
        L.append("❔ " + top["error"])
        return "\n".join(L)
    L.append("─" * 30)
    for v in top["verdicts"]:
        L.append("%s  %s" % (v["prod"], v["grade"]))
        L.append("   %s" % v["reason"])
        sz = v.get("size") or {}
        if sz.get("weight") is not None:
            L.append("   비중 %.0f%%" % sz["weight"])
        elif sz.get("weight_range"):
            L.append("   비중 확인 필요: %s%%" % " / ".join("%.0f" % x for x in sz["weight_range"]))
        for ps in v.get("positions") or []:
            hit = [e["label"] for e in ps.get("sells", []) if e.get("v") is True]
            L.append("   보유(%s, %+.1f%%) 매도 신호: %s" % (ps.get("entry_date"), ps.get("ret") or 0,
                                                     " · ".join(hit) if hit else "없음"))
    if top.get("cash") is not None:
        L.append("현금 %.0f%%" % top["cash"])
    if top.get("missing"):
        L.append("⚠ 시세 없음(수집 요청): " + ", ".join("%s #%s" % kv for kv in top["missing"].items()))
    L.append("─" * 30)
    L.append("※ 관측 시점(asof) 기준 판정 — 종가 조건은 마지막 확정 일봉, 장중 조건은 그 시점 분봉. "
             "🟡 는 수동(장중 분봉 미연결·저자 미명시) 조건을 직접 확인한 뒤 진입. 규칙 출처 = 저자 명시.")
    return "\n".join(L)
