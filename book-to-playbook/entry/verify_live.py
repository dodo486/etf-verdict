#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""라이브 허브(entry/live.LiveHub) 검사 — 합성 책 둘 · 가짜 시세원(네트워크 없음)으로 하루씩 흘려 넣는다.

틱마다 확인한다:
  (a) 발행한 판정 == 같은 시세로 낸 배치 판정(Judge.decisions — 상품마다 등급 키·날짜·동사 값·비중)이고,
      허브의 최신 top == 배치 판정을 같은 모양으로 빚은 것(ts 빼고)
  (b) 이번 틱에 바뀐 심볼을 구독한 상품만 다시 판정했다(판정 호출의 상품 집합을 센다 — 공유 심볼은 두 상품·두 책을 깨움)
  (c) 바뀐 것이 없는 틱은 아무것도 계산·발행하지 않는다
  (d) 심볼 여럿이 같이 바뀌어도 책마다 발행은 한 번
그리고 틱마다 최신 등급 == 같은 시세의 백테스트 신호(Judge.signals) 마지막 칸, 마지막 날은 전체 시세의 신호와도 같다.
수동 답(judge_with)은 같은 판단자·같은 시세로 계산 — 배치 render 와 같은 판정.

실행: python -m entry.verify_live
"""
import sys
from collections import namedtuple
from datetime import datetime, timedelta, timezone

from entry.live import LiveHub
from judge.judge import Judge
from market.store import Store
from tree.gateway import BLOCK, BUY, answer_key, rule, synthetic
from web.verdict_view import _format

Candle = namedtuple("Candle", "date open high low close volume")
FAILS = []


def check(ok, what):
    if not ok:
        FAILS.append(what)


def up(sym):
    return {"gt": [{"px": "close", "sym": sym}, {"lag": [{"px": "close", "sym": sym}, 1]}]}


def down(sym):
    return {"lt": [{"px": "close", "sym": sym}, {"lag": [{"px": "close", "sym": sym}, 1]}]}


# 책 1: A·B 는 S 를 같이 본다(공유 심볼), C 는 T 를 본다. 수동 하나(C 만) — judge_with 검사용.
BOOK1 = synthetic(["A", "B", "C"],
                  rule("추세 위", BUY, up("$self"), ("cash", 30)),
                  rule("S 하락", BLOCK, down("S"), on=["A", "B"]),
                  rule("T 하락", BLOCK, down("T"), on=["C"]),
                  rule("사람 확인", BLOCK, {"manual": "뉴스 악재"}, on=["C"]))
# 책 2: D 도 S 를 본다 — S 한 번 바뀌면 두 책이 각각 한 번씩 발행
BOOK2 = synthetic(["D"], rule("추세 위", BUY, {"all": [up("$self"), up("S")]}))
SUBS = {"vl1": {"A": {"A", "S"}, "B": {"B", "S"}, "C": {"C", "T"}}, "vl2": {"D": {"D", "S"}}}


class Feed:
    """심볼 → {날짜: 종가}. cursor 날짜까지만 보인다(하루씩 흘려 넣기). 같은 날짜 값을 바꾸면 '수정된 봉'."""

    def __init__(self):
        self.data, self.cursor = {}, None

    def __call__(self, symbols, start):
        return {s: [Candle(d, c, c, c, c, 1000) for d, c in sorted(self.data.get(s, {}).items())
                    if start <= d <= self.cursor] for s in symbols}

    def now(self):
        return datetime.strptime(self.cursor, "%Y%m%d").replace(hour=23, tzinfo=timezone.utc)


def snap(decisions):
    """판정 비교 열쇠 — 상품마다 (등급 키, 날짜, 낙관·비관 동사 값, 비중). 종가 등 나머지는 top 비교(strip)가 본다."""
    return {p: (d.key, d.date, d.opt, d.pes, d.amount.weight if d.amount else None)
            for p, d, _pj, _m in decisions}


def strip(top):
    return {k: v for k, v in top.items() if k != "ts"}


def main():
    today = datetime.now()
    cal = [(today - timedelta(days=80 - k)).strftime("%Y%m%d") for k in range(80)]
    cal = [d for d in cal if datetime.strptime(d, "%Y%m%d").weekday() < 5][-40:]
    syms = ("A", "B", "C", "D", "S", "T")
    full = {s: {d: 100.0 + ((k * (3 + i) + i) % 7) - 3 for k, d in enumerate(cal)} for i, s in enumerate(syms)}
    # 하루씩 무엇이 들어오나 — 처음 10일은 워밍업(전부). 그 뒤 날마다 바뀌는 심볼을 골라 둔다.
    plan = [set(syms)] * 10
    pattern = [{"S"}, {"T"}, set(), {"A", "S"}, set(syms), {"C"}, {"S", "T"}, {"D"}, set(), {"A", "B", "C", "D", "S", "T"}]
    while len(plan) < len(cal):
        plan.append(pattern[(len(plan) - 10) % len(pattern)])

    feed = Feed()
    store = Store(fetch=feed, now=feed.now, market_of=lambda s: None)
    judges = {"vl1": Judge.of(BOOK1, "vl1"), "vl2": Judge.of(BOOK2, "vl2")}
    for slug, j in judges.items():
        check({p: set(s) for p, s in j.subscriptions().items()} == SUBS[slug],
              "구독표 %s: %r" % (slug, j.subscriptions()))
    calls = []                                   # (slug, 판정한 상품 집합)
    for slug, j in judges.items():
        def wrapped(prices, asof=None, answers=None, products=None, _slug=slug, _orig=j.decisions, _j=j):
            calls.append((_slug, set(products or _j.products())))
            return _orig(prices, asof=asof, answers=answers, products=products)
        j.decisions = wrapped
    hub = LiveHub(slugs=list(judges), store=store, judges=judges)
    events = []
    seen = {s: {} for s in syms}                 # 지금까지 들어온 봉(가짜 시세원에 드러낸 것)
    shown = None                                 # 지난 틱에 시세원이 보이던 것
    for n, (day, new) in enumerate(zip(cal, plan)):
        for s in new:
            seen[s][day] = full[s][day]
        # 수정된 봉 — 4일째마다 A 의 마지막 봉을 잠정값으로 먼저 보이고, 다음 틱에 확정값으로 고친다
        provisional = n >= 10 and n % 4 == 0 and "A" not in new and seen["A"]
        if provisional:
            last = max(seen["A"])
            seen["A"][last] = full["A"][last] + 0.5
        feed.data, feed.cursor = {s: dict(v) for s, v in seen.items()}, day
        if n < 10:
            continue                             # 워밍업 — 첫 틱 전 적재분
        if shown is None:
            hub._sync()                          # 버스·구독 만들기 + 첫 적재(첫 틱 전) — 발행을 셀 구독자를 달려고
            for slug in judges:
                hub.verdict_bus[slug].subscribe(lambda ev: events.append(ev))
            changed = set(syms)                  # 첫 틱 = 전부 새로
        else:
            changed = {s for s in syms if feed.data[s] != shown[s]}
        shown = feed.data
        calls.clear()
        events.clear()
        published = hub.tick()
        prices = store.prices()
        want = {}
        for slug, subs in SUBS.items():
            woken = {p for p, ss in subs.items() if ss & changed}
            if woken:
                want[slug] = woken
        got = {}
        for slug, prods in calls:
            got.setdefault(slug, set()).update(prods)
        check(got == want, "틱 %s: 다시 판정한 상품 %r ≠ 바뀐 심볼 %r 의 구독 상품 %r" % (day, got, changed, want))      # (b)
        check(len(calls) == len(got), "틱 %s: 책마다 판정 호출 한 번 %r" % (day, calls))
        check(published == set(want) and sorted(e["slug"] for e in events) == sorted(want),
              "틱 %s: 책마다 발행 한 번 %r · %r" % (day, published, [e["slug"] for e in events]))               # (c)(d)
        if not changed:
            check(not calls and not events, "틱 %s: 바뀐 것 없음 → 계산·발행 없음" % day)
        for slug, j in judges.items():
            batch = Judge.decisions.__get__(j)(prices)                                  # 감싸지 않은 원래 판정
            ev = next((e for e in events if e["slug"] == slug), None)
            if ev is not None:
                check(snap(ev["decisions"]) == snap(batch), "틱 %s %s: 발행 판정 ≠ 배치 판정" % (day, slug))   # (a)
            check(strip(hub.latest(slug)) == strip(_format(slug, j, prices, batch)),
                  "틱 %s %s: 최신 top ≠ 배치 판정 top" % (day, slug))
            sig = Judge.signals.__get__(j)(prices)
            check({p: d[0] for p, d in snap(batch).items()} == {p: pts[-1]["key"] for p, (_pj, pts) in sig.items()},
                  "틱 %s %s: 판정 등급 ≠ 백테스트 신호 마지막 칸" % (day, slug))
        if provisional:
            seen["A"][last] = full["A"][last]   # 다음 틱에 확정값으로(그 틱의 바뀐 심볼에 A 가 든다)

    # 마지막 날 — 하루씩 흘려 넣은 결과 == 같은 봉 전부를 한 번에 받아 낸 백테스트 신호(저장소를 거치지 않고)
    whole = {s: [Candle(d, c, c, c, c, 1000) for d, c in sorted(v.items())] for s, v in shown.items()}
    for slug, j in judges.items():
        sig = Judge.signals.__get__(j)(whole)
        live = {v["prod"]: v["key"] for v in hub.latest(slug)["verdicts"]}
        check(live == {p: pts[-1]["key"] for p, (_pj, pts) in sig.items()},
              "마지막 날 %s: 틱 재생 %r ≠ 전체 신호" % (slug, live))
    calls.clear()
    events.clear()
    check(hub.tick() == set() and not calls and not events, "같은 시세로 한 번 더 틱 → 계산·발행 없음")

    # 수동 답 — 허브 judge_with == 같은 시세의 배치(answers) 판정, 재조회 없이
    ans = {answer_key({"manual": "뉴스 악재"}, "C"): True}
    j1 = judges["vl1"]
    batch = Judge.decisions.__get__(j1)(store.prices(), answers=ans)
    top = hub.judge_with("vl1", ans)
    check(strip(top) == strip(_format("vl1", j1, store.prices(), batch, answers=ans)), "judge_with ≠ 배치(answers) 판정")
    check(next(v["key"] for v in top["verdicts"] if v["prod"] == "C") == "avoid", "judge_with: C 수동 악재 참 → 안 산다")

    if FAILS:
        for f in FAILS:
            print("  FAIL", f)
        print("라이브 허브 검사 정지 %d건" % len(FAILS))
        return 1
    print("라이브 허브 검사 통과 — 바뀐 상품만 판정 · 틱당 책마다 발행 하나 · 바뀐 것 없으면 무발행 · 판정 == 배치 · 재생 == 신호")
    return 0


if __name__ == "__main__":
    sys.exit(main())
