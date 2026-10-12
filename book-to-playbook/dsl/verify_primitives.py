#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조건 트리 원시함수 검사 (책 무관 · 크기 고정).

왜 있나
  옛 검증층은 전부 '글자 대조'였다 — 라벨·원문·판정식의 숫자/단어가 서로 나오는지만 봤고,
  계산이 실제로 맞는지는 아무도 실행해 보지 않았다. 그래서 '2거래일 유지'가 1일로 판정되고
  ('2' 라는 글자는 있으니 통과), '전고점 유지'가 연속 신고가를 세도 통과했다.
  규칙은 이제 cond.py 의 원시함수 조합뿐이므로, 원시함수만 실행으로 철저히 검증하면
  어떤 책의 어떤 조건이든 계산 버그가 들어올 자리가 없다. 책이 늘어도 이 검사는 늘지 않는다.

무엇을 하나 (기준은 전부 cond.py 와 독립적으로 구한다)
  1. 수치 연산 — pandas rolling/shift 로 계산한 값과 무작위 시계열(결측 포함)에서 대조
  2. 3값 논리 — '모름' 자리에 참/거짓을 전부 넣어 본 결과로 정답을 정의해 전수 대조
  3. 시간 연산(barssince·valuewhen, 조합: 최근 참 일수·연속 참 일수 · 여러 종목 중 N개 = atleast·of) — 단순 반복 구현과 대조
  4. 인과성 — 미래 데이터를 잘라도 과거 날짜 값이 같아야 한다(미래 참조 금지)
  5. 문법 — 모르는 키·인자 수·빈 구역은 거부, 올바른 트리는 통과
  6. 표현력 회귀 — 이번에 발견된 버그 유형을 트리로 적어 원문 뜻대로 나오는지
  7. 트리 출입구(TreeGateway) 계약 — 판정·백테스트·검사기가 트리에 묻는 질문의 답 모양
  8. 사람이 답한 수동(Ctx answers) — 답 열쇠 규칙·극성·공통 정의·등급까지(서버 권위의 바탕)
  (체결 워크·실전 경로는 consumers/backtest/verify_trading.py, 화면 설명 구조는 signals/verify_view.py 가 본다)

사용: python -m dsl.verify_primitives   (실패 있으면 exit 1)
"""
import itertools
import json
import math
import random
import sys
from collections import namedtuple

import pandas as pd

from shared import paths  # noqa: F401  (UTF-8 출력)
from dsl.tradeTool import Cond
from dsl.tree_gateway import TreeGateway, rule, synthetic   # 합성 트리는 출입구로 만든다(entry.verify_rules 명시 예외)

Candle = namedtuple("Candle", "date open high low close volume")
FAILS = []


def check(ok, what):
    if not ok:
        FAILS.append(what)


def same(a, b, tol=1e-9):
    if isinstance(a, Cond.AtLeast) != isinstance(b, Cond.AtLeast):
        return False                          # 하한과 정확한 값은 다르다
    if a is None or b is None or (isinstance(b, float) and math.isnan(b)):
        return a is None and (b is None or (isinstance(b, float) and math.isnan(b)))
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or a == b
    return abs(a - b) <= tol * max(1.0, abs(b))


def make_ctx(closes, extra=None, manual_as=None):
    """closes(결측 None 허용) → 단일 종목 'X' 문맥. extra={심볼: closes}."""
    cal = ["2020%04d" % i for i in range(len(closes))]

    def candles(cs):
        return [Candle(d, c, c, c, c, 1000) for d, c in zip(cal, cs) if c is not None]

    hist = {"X": candles(closes)}
    for s, cs in (extra or {}).items():
        hist[s] = candles(cs)
    return Cond.Ctx(hist, cal, "X", manual_as=manual_as)


def rand_series(rng, n, miss=0.05):
    x, out = 100.0, []
    for _ in range(n):
        x *= 1 + rng.gauss(0, 0.02)
        out.append(None if rng.random() < miss else round(x, 4))
    return out


C = {"px": "close", "sym": "X"}


def AVG(s, n):
    """N일 평균 — 전용 연산 없이 sum ÷ n (COND_DSL 6절 조합)."""
    return {"div": [{"sum": [s, n]}, n]}


def PCT(s, k):
    """k일 전 대비 변화율(%) — (s ÷ lag(s,k) − 1) × 100 (COND_DSL 6절 조합)."""
    return {"mul": [{"sub": [{"div": [s, {"lag": [s, k]}]}, 1]}, 100]}


def COUNT(c, n):
    """최근 n일 중 c 가 참인 날 수 — sum(case(c,1,0), n)."""
    return {"sum": [{"case": [[c, 1]], "else": 0}, n]}


def STREAK(c):
    """오늘부터 거꾸로 c 가 연속 참인 날 수 — barssince(not c)."""
    return {"barssince": {"not": c}}


# ------------------------------------------------------------------ 1. 수치 연산
def t_numeric(rng):
    for trial in range(30):
        xs = rand_series(rng, 120)
        ctx = make_ctx(xs)
        ps = pd.Series([float("nan") if v is None else v for v in xs])
        for n in (1, 3, 5, 20):
            refs = {
                "sum": ps.rolling(n, min_periods=n).sum(),
                "highest": ps.rolling(n, min_periods=n).max(),
                "lowest": ps.rolling(n, min_periods=n).min(),
            }
            for op, ref in refs.items():
                got = Cond.series({op: [C, n]}, ctx)
                bad = [i for i in range(len(xs)) if not same(got[i], ref[i], 1e-7)]
                check(not bad, "%s(%d) pandas 와 불일치 @%s (trial %d)" % (op, n, bad[:3], trial))
            ref = ps.rolling(n, min_periods=n).mean()
            got = Cond.series(AVG(C, n), ctx)
            check(all(same(got[i], ref[i], 1e-7) for i in range(len(xs))), "평균(sum÷n, %d) 불일치 (trial %d)" % (n, trial))
        for k in (0, 1, 5):
            ref = ps.shift(k)
            got = Cond.series({"lag": [C, k]}, ctx)
            check(all(same(got[i], ref[i]) for i in range(len(xs))), "lag(%d) 불일치" % k)
            if k:
                ref = (ps / ps.shift(k) - 1) * 100
                got = Cond.series(PCT(C, k), ctx)
                check(all(same(got[i], ref[i], 1e-7) for i in range(len(xs))), "변화율(%d일) 조합 불일치" % k)
        a = Cond.series({"sub": [C, {"lag": [C, 1]}]}, ctx)
        ref = ps - ps.shift(1)
        check(all(same(a[i], ref[i], 1e-7) for i in range(len(xs))), "sub 불일치")
        dz = Cond.series({"div": [C, 0]}, ctx)
        check(all(v is None for v in dz), "div 0 은 None 이어야 한다")
        prev = ps.shift(1)
        for op, ref in (("max", pd.concat([ps, prev], axis=1).max(axis=1, skipna=False)),
                        ("min", pd.concat([ps, prev], axis=1).min(axis=1, skipna=False))):
            got = Cond.series({op: [C, {"lag": [C, 1]}]}, ctx)
            check(all(same(got[i], ref[i], 1e-12) for i in range(len(xs))), "%s 불일치 (trial %d)" % (op, trial))
        ref = (ps - prev).abs()
        got = Cond.series({"abs": {"sub": [C, {"lag": [C, 1]}]}}, ctx)
        check(all(same(got[i], ref[i], 1e-7) for i in range(len(xs))), "abs 불일치 (trial %d)" % trial)
    # 지운 전용 지표 연산은 문법에서 거부된다(조합으로 쓴다)
    for op in Cond.GONE_OPS:
        try:
            Cond.validate({op: [C, 5]})
            FAILS.append("지운 연산 %s 가 문법을 통과" % op)
        except Cond.CondError:
            pass


# ------------------------------------------------------------------ 2. 3값 논리
def t_logic():
    """정답 정의: '모름' 자리에 참/거짓을 전부 넣어 결과가 하나로 정해지면 그 값, 갈리면 None."""
    vals = (True, False, None)

    def truth(f, xs):
        holes = [i for i, x in enumerate(xs) if x is None]
        outs = set()
        for fill in itertools.product((True, False), repeat=len(holes)):
            ys = list(xs)
            for i, b in zip(holes, fill):
                ys[i] = b
            outs.add(f(ys))
        return outs.pop() if len(outs) == 1 else None

    for k in range(0, 4):
        for xs in itertools.product(vals, repeat=k):
            cols = [{"gt": [x, 0]} if x is not None else {"manual": "모름"} for x in
                    [(1 if x else -1) if x is not None else None for x in xs]]
            ctx = make_ctx([1.0])
            got = Cond.series({"all": cols}, ctx)[0]
            check(got == truth(all, xs) or (got is None and truth(all, xs) is None), "all%r" % (xs,))
            got = Cond.series({"any": cols}, ctx)[0]
            check(got == truth(any, xs) or (got is None and truth(any, xs) is None), "any%r" % (xs,))
            for n in range(1, 4):
                got = Cond.series({"atleast": n, "of": cols}, ctx)[0]
                exp = truth(lambda ys: sum(ys) >= n, xs)
                check(got is exp or got == exp, "atleast %d %r: %r≠%r" % (n, xs, got, exp))
    for x in vals:
        node = {"gt": [1 if x else -1, 0]} if x is not None else {"manual": "모름"}
        got = Cond.series({"not": node}, make_ctx([1.0]))[0]
        check(got == (None if x is None else not x), "not %r" % x)
    # manual 은 manual_as 를 따른다
    for m in (True, False, None):
        got = Cond.series({"manual": "장중"}, make_ctx([1.0], manual_as=m))[0]
        check(got is m, "manual_as=%r" % m)
    # 극성: not 아래 수동은 반대 가정 — manual_as=True(유리하게 풀림)면 '겹치면 쉼'은 참(쉴 이유 없음)
    rest = {"not": {"all": [{"gt": [1, 0]}, {"manual": "달러 강세"}]}}
    check(Cond.series(rest, make_ctx([1.0], manual_as=True))[0] is True, "not 아래 수동: 낙관이면 참")
    check(Cond.series(rest, make_ctx([1.0], manual_as=False))[0] is False, "not 아래 수동: 비관이면 거짓")
    dbl = {"not": {"not": {"manual": "x"}}}
    for m in (True, False):
        check(Cond.series(dbl, make_ctx([1.0], manual_as=m))[0] is m, "not not 수동 = manual_as")
    # case — 위에서부터 처음 참인 갈래. 앞 갈래가 모름이면 결과도 모름(뒤로 넘어가지 않는다)
    for c1, c2 in itertools.product(vals, repeat=2):
        node = {"case": [[{"gt": [1 if c1 else -1, 0]} if c1 is not None else {"manual": "a"}, 10],
                         [{"gt": [1 if c2 else -1, 0]} if c2 is not None else {"manual": "b"}, 20]], "else": 30}
        got = Cond.series(node, make_ctx([1.0]))[0]
        exp = 10 if c1 else (None if c1 is None else (20 if c2 else (None if c2 is None else 30)))
        check(same(got, None if exp is None else float(exp)), "case %r %r → %r (기대 %r)" % (c1, c2, got, exp))


# ------------------------------------------------------------------ 3. 시간 연산
def t_time(rng):
    for trial in range(40):
        bits = [rng.choice([True, False, False, None if rng.random() < 0.1 else True])
                for _ in range(60)]
        xs = [1.0 if b else (-1.0 if b is False else None) for b in bits]
        ctx = make_ctx(xs)
        c = {"gt": [C, 0]}
        for n in (1, 3, 7):
            got = Cond.series(COUNT(c, n), ctx)
            for i in range(60):
                w = bits[i - n + 1:i + 1] if i - n + 1 >= 0 else None
                exp = None if (w is None or None in w) else float(sum(w))
                check(same(got[i], exp), "count(%d)@%d %r≠%r" % (n, i, got[i], exp))
        got = Cond.series(STREAK(c), ctx)
        for i in range(60):
            cnt, exp = 0, None
            for j in range(i, -1, -1):
                if bits[j] is False:
                    exp = float(cnt)
                    break
                if bits[j] is None:
                    break
                cnt += 1
            if exp is None and cnt > 0:
                exp = Cond.AtLeast(cnt)       # 모르는 날·데이터 시작에 닿음 → 최소 cnt
            check(same(got[i], exp), "연속 참 일수@%d %r≠%r" % (i, got[i], exp))
        got = Cond.series({"barssince": c}, ctx)
        vw = Cond.series({"valuewhen": [c, {"lag": [C, 0]}]}, ctx)
        val = [float(v) for v in range(60)]           # 결측 없는 값열(위치 = 값)
        vctx = make_ctx(xs, extra={"V": val})
        V = {"px": "close", "sym": "V"}
        mn = Cond.series({"minsince": [c, V]}, vctx)
        mx = Cond.series({"maxsince": [c, V]}, vctx)
        for i in range(60):
            exp = ev = emn = emx = None
            stop = -1
            for j in range(i, -1, -1):
                if bits[j] is None:
                    stop = j
                    break
                if bits[j]:
                    exp, ev = float(i - j), xs[j]
                    emn, emx = min(val[j:i + 1]), max(val[j:i + 1])
                    break
            if exp is None and i - stop > 0:
                exp = Cond.AtLeast(i - stop)      # 그 사이 참 없음 → 최소 i-stop 거래일
            check(same(got[i], exp), "barssince@%d" % i)
            check(same(vw[i], ev), "valuewhen@%d" % i)
            check(same(mn[i], emn) and same(mx[i], emx), "min/maxsince@%d" % i)
    # 여러 종목 중 N개 = atleast·of(각 잎 sym = 그 티커 — across 폐지)
    ctx = make_ctx([1.0, 1.0], extra={"A": [1.0, 2.0], "B": [3.0, 1.0], "D": [None, 5.0]})
    up = lambda t: {"gt": [{"px": "close", "sym": t}, {"lag": [{"px": "close", "sym": t}, 1]}]}
    got = Cond.series({"atleast": 1, "of": [up("A"), up("B")]}, ctx)
    check(got == [None, True], "A·B 중 1개 상승 %r" % got)
    got = Cond.series({"atleast": 2, "of": [up("A"), up("B")]}, ctx)
    check(got == [None, False], "A·B 중 2개 상승 %r" % got)


def t_bounds():
    """하한 비교의 정답: 참값 v 가 하한 a 이상 아무 정수일 때 결과가 하나로 정해지면 그 값, 갈리면 None."""
    for a in range(0, 6):
        for b in range(0, 8):
            for op, f in (("gt", lambda v: v > b), ("ge", lambda v: v >= b),
                          ("lt", lambda v: v < b), ("le", lambda v: v <= b)):
                outs = {f(v) for v in range(a, a + 20)}
                exp = outs.pop() if len(outs) == 1 else None
                got = Cond._cmp(op, Cond.AtLeast(a), float(b))
                check(got == exp and (got is None) == (exp is None), "하한 %s(≥%d, %d)" % (op, a, b))
                # 좌우를 바꾼 비교도 같아야 한다: b op' AtLeast
                mirror = {"gt": "lt", "ge": "le", "lt": "gt", "le": "ge"}[op]
                got2 = Cond._cmp(mirror, float(b), Cond.AtLeast(a))
                check(got2 == exp and (got2 is None) == (exp is None), "하한 대칭 %s" % op)
    # 실제 쓰임: 데이터 시작부터 20일선 위(정확한 길이 모름)라도 '3일 이상'은 참
    xs = [100.0 + i for i in range(40)]
    up = {"gt": [C, AVG(C, 20)]}
    check(Cond.series({"ge": [STREAK(up), 3]}, make_ctx(xs))[-1] is True, "긴 상승 streak≥3 = 참")
    check(Cond.series({"lt": [STREAK(up), 3]}, make_ctx(xs))[-1] is False, "긴 상승 streak<3 = 거짓")
    check(Cond.series({"ge": [STREAK(up), 30]}, make_ctx(xs))[-1] is None, "streak≥30 은 모름(21일만 확인)")
    check(isinstance(Cond.series({"add": [STREAK(up), 1]}, make_ctx(xs))[-1], Cond.AtLeast), "하한+1 = 하한")
    check(Cond.series(AVG(STREAK(up), 2), make_ctx(xs))[-1] is None, "하한의 이동평균 = 모름")


def t_pos(rng):
    """포지션 값(ret·days·maxret·minret) — 단순 반복 구현과 대조, 진입 전은 None, 미래 무관."""
    for trial in range(20):
        xs = [x if x is not None else 100.0 for x in rand_series(rng, 60, miss=0)]
        e = rng.randrange(5, 50)
        px = xs[e] * (1 + rng.uniform(-0.01, 0.01))
        ctx = make_ctx(xs)
        ctx.pos = (e, px)
        got = {f: Cond.series({"pos": f}, ctx) for f in Cond.POS_FIELDS}
        for i in range(60):
            if i < e:
                check(all(got[f][i] is None for f in got), "pos 진입 전 None @%d" % i)
                continue
            r = [(xs[j] / px - 1) * 100 for j in range(e, i + 1)]
            check(same(got["ret"][i], r[-1], 1e-9), "pos.ret @%d" % i)
            check(same(got["days"][i], float(i - e)), "pos.days @%d" % i)
            check(same(got["maxret"][i], max(r), 1e-9) and same(got["minret"][i], min(r), 1e-9), "pos.max/min @%d" % i)
        pre = make_ctx(xs[:45])
        pre.pos = (e, px)
        if e < 45:
            check(same(Cond.series({"pos": "maxret"}, pre)[44], got["maxret"][44], 1e-9), "pos 미래 참조")
    # 평균 매입가가 날짜별로 바뀌는 경우(분할 매수) — ret 은 그날의 평균 매입가 기준
    xs = [100.0, 100.0, 110.0, 120.0, 90.0]
    ctx = make_ctx(xs)
    ctx.pos = (1, [None, 100.0, 100.0, 105.0, 105.0])
    got = Cond.series({"pos": "ret"}, ctx)
    check(got[0] is None and same(got[2], 10.0) and same(got[3], (120 / 105 - 1) * 100)
          and same(got[4], (90 / 105 - 1) * 100), "pos.ret 평균 매입가 목록 %r" % got)
    # 장부 값(filled·sold) — 체결 워크가 날짜별로 넣는다. 장부가 없으면 모름(옛 동작: minret 로 잘못 계산되던 자리)
    book = {"filled": {None: [0, 1, 1, 2, 2], "1차": [0, 1, 1, 1, 1], "2차": [0, 0, 0, 1, 1]},
            "sold": [None, 0.0, 0.0, 0.0, 0.5]}
    ctx.pos = (1, 100.0, book)
    F = lambda node: Cond.series(node, ctx)
    check(F({"pos": "filled"}) == [None, 1.0, 1.0, 2.0, 2.0] and F({"pos": "filled", "rule": "2차"}) == [None, 0.0, 0.0, 1.0, 1.0]
          and F({"pos": "filled", "rule": "없는 차수"}) == [None, 0.0, 0.0, 0.0, 0.0]
          and F({"pos": "sold"}) == [None, 0.0, 0.0, 0.0, 0.5], "pos filled·sold 장부 값")
    ctx = make_ctx(xs)                       # 새 문맥(계산 캐시는 문맥마다) — 장부 없이
    ctx.pos = (1, 100.0)
    check(F({"pos": "filled", "rule": "1차"}) == [None] * 5 and F({"pos": "sold"}) == [None] * 5, "장부 없으면 filled·sold 는 모름")
    for bad in ({"pos": "ret", "rule": "1차"}, {"pos": "filled", "rule": 3}):
        try:
            Cond.validate(bad)
            FAILS.append("잘못된 pos rule 통과 %r" % bad)
        except Cond.CondError:
            pass


# ------------------------------------------------------------------ 4. 인과성
CAUSAL_NODES = [
    AVG(C, 5),
    {"highest": [C, 10]}, PCT(C, 3), {"lag": [C, 2]},
    COUNT({"gt": [C, {"lag": [C, 1]}]}, 5),
    STREAK({"gt": [C, AVG(C, 5)]}),
    {"barssince": {"ge": [C, {"highest": [C, 10]}]}},
    {"valuewhen": [{"gt": [C, {"highest": [{"lag": [C, 1]}, 10]}]}, {"highest": [{"lag": [C, 1]}, 10]}]},
    {"minsince": [{"gt": [C, {"highest": [{"lag": [C, 1]}, 10]}]}, C]},
    {"atleast": 2, "of": [{"gt": [C, 100]}, {"lt": [PCT(C, 1), 0]}, {"gt": [C, AVG(C, 3)]}]},
    {"max": [C, AVG(C, 5)]}, {"abs": PCT(C, 1)},
    {"case": [[{"gt": [C, AVG(C, 5)]}, {"highest": [C, 3]}]], "else": {"lowest": [C, 3]}},
]


def t_causal(rng):
    for trial in range(15):
        xs = rand_series(rng, 90)
        full = make_ctx(xs)
        for node in CAUSAL_NODES:
            fs = Cond.series(node, full)
            for t in (30, 55, 89):
                pre = make_ctx(xs[:t + 1])
                ps = Cond.series(node, pre)
                check(same(ps[t], fs[t], 1e-9), "미래 참조: %s @%d" % (Cond._op_of(node), t))


# ------------------------------------------------------------------ 5. 문법
def t_syntax():
    bad = [
        {"gt": [C]}, {"sum": [C, 0]}, {"sum": [C, 2.5]}, {"ma": [C, 20]}, {"px": "price"}, {"foo": 1},
        {"gt": [C, 1], "lt": [C, 2]}, True, {"atleast": 2}, {"def": "없음"},
        {"across": {"syms": ["A"], "cond": C}}, {"manual": ""}, {"gt": [C, 1], "op": "above"},
        {"px": "close", "sym": "X", "tf": "1h"}, {"px": "close"}, {"px": "close", "sym": "$self"},
        {"px": "close", "sym": "$index"}, {"abs": [C, 1]}, {"case": [[C, 1]]}, {"case": [C, 1], "else": 0},
        {"max": [C]},
    ]
    for b in bad:
        try:
            Cond.validate(b)
            FAILS.append("거부해야 할 노드가 통과: %r" % (b,))
        except Cond.CondError:
            pass
    good = {"all": [{"gt": [C, AVG(C, 20)], "label": "20일선 위", "ref": "3-2"},
                    {"atleast": 2, "of": [{"manual": "장중"}, {"ge": [{"px": "volume", "sym": "X"}, 1]}]}]}
    try:
        Cond.validate(good)
    except Cond.CondError as e:
        FAILS.append("올바른 노드가 거부: %s" % e)
    try:
        Cond.validate({"case": [[{"gt": [C, 1]}, 2]], "else": {"px": "close", "sym": "X", "tf": "1d"}})
    except Cond.CondError as e:
        FAILS.append("올바른 case·tf 가 거부: %s" % e)
    W = {"gt": [C, 1]}
    good = synthetic(["X"], rule("비중", Cond.BUY, None, ("cash", {"case": [[W, 14]], "else": 34})),
                     rule("1차", Cond.BUY, None, ("budget", 0.25)),
                     rule("2차", Cond.BUY, {"ge": [{"pos": "ret"}, 3]}, ("budget", 0.75)),
                     rule("모름", Cond.BUY, {"manual": "저자 미명시: x"}, ("budget", "?")))
    try:
        TreeGateway.of(good)
    except Cond.CondError as e:
        FAILS.append("올바른 v3 트리가 거부: %s" % e)


def t_asof():
    """장중(tf="1m") 값 — asof(관측 시점) 이하 그날 마지막 분봉. asof 이후 분봉·다른 날 분봉은 안 쓴다.
    분봉 데이터가 없으면 None(모름). 분봉 키는 UTC(YYYYMMDDHHMM)."""
    import datetime as dt
    utc = dt.timezone.utc
    cal = ["20261001", "20261002"]
    # minute_series: 날짜별 asof 이하 마지막 분봉. dict 봉·단일 종가 둘 다 받는다.
    m = {"202610011950": 1.0, "202610012100": 2.0, "202610021315": 3.0, "202610021320": 4.0, "202610021321": 5.0}
    asof = dt.datetime(2026, 10, 2, 13, 20, tzinfo=utc)      # 10/02 13:20 UTC
    got = Cond.minute_series(m, cal, "close", asof)
    check(got == [2.0, 4.0], "asof 이하 그날 마지막 분봉 %r" % got)
    # asof 가 이르면 그날 분봉이 아직 없다 → None(미래 분봉을 쓰지 않는다)
    early = Cond.minute_series(m, cal, "close", dt.datetime(2026, 10, 2, 13, 0, tzinfo=utc))
    check(early == [2.0, None], "asof 전 분봉은 쓰지 않는다(그날 None) %r" % early)
    # 그날 분봉이 아예 없으면 None(다른 날 분봉으로 넘어가지 않는다)
    check(Cond.minute_series({"202610011950": 1.0}, cal, "close", asof) == [1.0, None], "그날 분봉 없으면 None")
    check(Cond.minute_series({}, cal, "close", asof) == [None, None], "분봉 전무 → 전부 None(모름)")
    # OHLCV dict 봉도 받는다(목표 분봉 구조)
    md = {"202610021320": {"open": 10, "high": 12, "low": 9, "close": 11, "volume": 500}}
    check(Cond.minute_series(md, cal, "high", asof) == [None, 12.0], "dict 분봉 필드 선택")
    # 문법: tf 는 "1d"/"1m"/"5m" 만, 그 밖은 거부. px 에 모르는 보조 키가 붙으면 '노드에 연산 둘'로 거부된다.
    for b in ({"px": "close", "sym": "X", "tf": "1h"}, {"px": "close", "sym": "X", "tf": "15m"},
              {"px": "close", "sym": "X", "offset": -10}):
        try:
            Cond.validate(b)
            FAILS.append("잘못된 tf 통과: %r" % b)
        except Cond.CondError:
            pass
    Cond.validate({"px": "close", "sym": "X", "tf": "1m"})      # 분봉 노드는 통과
    Cond.validate({"px": "close", "sym": "X", "tf": "5m"})      # 5분봉 노드도 통과
    # 평가: 장중 분봉 값 > 전일 종가(선물이 전일 종가 위). tf="1m" 를 asof 로 자른다.
    hist = {"X": [Candle(d, 100, 100, 100, 100, 1000) for d in cal]}

    class H(dict):
        minutes = {"X": {"202610021320": 101.0}}
    ctx = Cond.Ctx(H(hist), cal, "X", asof=asof)
    v = Cond.series({"gt": [{"px": "close", "sym": "X", "tf": "1m"}, {"px": "close", "sym": "X"}]}, ctx)
    check(v == [None, True], "장중 분봉 값 > 전일 종가(그날만 분봉 있음) %r" % v)
    try:
        Cond.validate({"observe": {"gt": [C, 1]}, "manual": "데이터 없음: x"})
        FAILS.append("지운 observe 노드가 문법을 통과")
    except Cond.CondError:
        pass


def t_settled_mtf():
    """★ 혼합 tf·확정(settled) 규칙·일봉축 '마지막 확정봉'·look-ahead 0 — 이 덩어리의 최우선 correctness 증명(영구).

    1) 일봉축 '마지막 확정봉' 재해석(장중 asof): tf:1d 식의 평가 index 를 'asof 이하 마지막 확정 일봉'으로 당긴다.
       장중 asof 면 오늘 봉은 미확정이라 오늘 칸에도 '어제 확정값'이 나온다(None 아님) — 실전 '일봉 regime=어제값'.
       EOD/마감시각/장후 asof 면 오늘 봉까지 확정이라 항등(당김 없음, 기존과 동일). 마감 1분 전은 아직 미확정 → 어제값.
    2) look-ahead 0 (★확장·전수): 장중 asof 에서 tf:1d 잎·그 위 모든 파생값이 '오늘 미확정 봉 유무'와 무관하고,
       오늘 미확정 종가(999)가 어떤 일봉 파생값에도 절대 새지 않는다. 오늘 칸 값 == 어제 확정 칸 값(당겨왔으므로)도 전수.
    3) 캘린더 없음·asof None → 아무것도 안 당김(no-op, 일봉 파리티 보존).
    4) 5분봉 집계: 1분봉→5분 OHLC 가 세션 경계를 안 넘고, asof 로 자른 마지막 5분봉이 1분봉 재집계와 일치.
    5) 혼합 tf 트리: tf:1d(어제 확정) AND tf:5m(asof 이하)를 저자 논리처럼 중첩해도 1d 잎만 일봉축으로 당기고
       5m 잎은 asof-오늘 축 그대로 — 두 축이 섞인 식(all)은 당기지 않는다(per-leaf 스코프).
    """
    import datetime as dt
    utc = dt.timezone.utc
    cal = ["20261001", "20261002"]
    # 세션 마감: 둘 다 20:00 UTC. (미 정규장 13:30~20:00 UTC — 한 UTC 날짜 안에서 닫힌다.)
    sc = {"X": {"20261001": dt.datetime(2026, 10, 1, 20, 0, tzinfo=utc),
                "20261002": dt.datetime(2026, 10, 2, 20, 0, tzinfo=utc)}}

    def hist_of(closes):      # closes = cal 길이, None 이면 그 날 봉 없음(일봉 feed 가 오늘 봉을 아직 안 줌)
        return {"X": [Candle(d, c, c, c, c, 1000) for d, c in zip(cal, closes) if c is not None]}

    node1d = {"px": "close", "sym": "X", "tf": "1d"}

    # 1) 일봉축 '마지막 확정봉' — 장중(13:20)엔 오늘 칸도 어제 확정값, 마감시각(20:00)·장후(21:00)엔 오늘 봉 확정(항등).
    full = hist_of([100.0, 200.0])      # 오늘(10/02) 미확정 봉 종가 200 이 feed 에 들어온 (최악의) 경우
    intraday = Cond.Ctx(full, cal, "X", asof=dt.datetime(2026, 10, 2, 13, 20, tzinfo=utc), session_close=sc)
    check(Cond.series(node1d, intraday) == [100.0, 100.0], "일봉축: 장중엔 오늘 칸도 어제 확정값(100)으로 당김")
    atclose = Cond.Ctx(full, cal, "X", asof=dt.datetime(2026, 10, 2, 20, 0, tzinfo=utc), session_close=sc)
    check(Cond.series(node1d, atclose) == [100.0, 200.0], "settled: 마감 == asof 는 확정(오늘 봉 그대로, 당김 없음)")
    pre = Cond.Ctx(full, cal, "X", asof=dt.datetime(2026, 10, 2, 19, 59, tzinfo=utc), session_close=sc)
    check(Cond.series(node1d, pre) == [100.0, 100.0], "일봉축: 마감 1분 전은 아직 미확정 → 어제값으로 당김")
    post = Cond.Ctx(full, cal, "X", asof=dt.datetime(2026, 10, 2, 21, 0, tzinfo=utc), session_close=sc)
    check(Cond.series(node1d, post) == [100.0, 200.0], "settled: 장 끝난 뒤는 확정(항등)")

    # 2) look-ahead 0 (★확장·전수) — 장중 asof 에서 오늘 칸이 '어제 확정값'으로 당겨지고, 미확정 종가 999 는 안 샘.
    with_today = hist_of([100.0, 999.0])    # 오늘 봉 있음(미확정, 종가 999)
    cal_wo = ["20261001"]
    without = {"X": [Candle("20261001", 100.0, 100.0, 100.0, 100.0, 1000)]}   # 오늘 봉 없음(현재 feed 모습)
    derived = [node1d, AVG(node1d, 1), {"highest": [node1d, 1]}, {"lag": [node1d, 0]},
               {"gt": [node1d, 50]}, STREAK({"gt": [node1d, 50]})]
    for h in (10, 13, 15, 19, 20, 21):       # 장중~장후 여러 asof
        a = dt.datetime(2026, 10, 2, h, 0, tzinfo=utc)
        cw = Cond.Ctx(with_today, cal, "X", asof=a, session_close=sc)
        cwo = Cond.Ctx(without, cal_wo, "X", asof=a, session_close=sc)
        for node in derived:
            vw = Cond.series(node, cw)
            vwo = Cond.series(node, cwo)
            # 마지막 확정일(10/01, index 0) 값이 오늘 봉 유무와 무관해야 한다
            check(same(vw[0], vwo[0], 1e-9),
                  "look-ahead: %s @10/01 이 오늘 봉 유무에 흔들림(asof %dh) %r≠%r"
                  % (Cond._op_of(node), h, vw[0], vwo[0]))
            # 장중(마감 전) asof 에선 미확정 종가 999 가 어떤 일봉 파생값에도 새어들면 안 된다 — look-ahead 0.
            #   (마감 == asof·장후(h>=20)엔 오늘 봉이 확정이라 999 는 '확정된 오늘 종가'로 정당히 쓰인다.)
            if h < 20:
                check(all(not same(x, 999.0, 1e-9) for x in vw if x is not None),
                      "look-ahead: 미확정 종가 999 가 샘(asof %dh) %r" % (h, vw))
                # ★확장: 장중엔 오늘 칸(index 1)이 '어제 확정 칸(index 0)'과 같아야 한다(일봉축으로 당겨왔으므로).
                check(same(vw[1], vw[0], 1e-9),
                      "일봉축 확장: 장중 오늘 칸 %s 가 어제 확정값과 달라짐(asof %dh) %r" % (Cond._op_of(node), h, vw))

    # 3) no-op — 캘린더 없음·asof None 이면 장중이라도 아무것도 안 가린다(일봉 파리티 보존)
    a = dt.datetime(2026, 10, 2, 13, 20, tzinfo=utc)
    check(Cond.series(node1d, Cond.Ctx(full, cal, "X", asof=a, session_close={})) == [100.0, 200.0],
          "no-op: 캘린더 없으면 안 가림(캘린더 없다고 일봉 전부 지우지 않는다)")
    check(Cond.series(node1d, Cond.Ctx(full, cal, "X", asof=None, session_close=sc)) == [100.0, 200.0],
          "no-op: asof None(라이브 지금)은 안 가림")

    # 4) 5분봉 집계 — 1분봉→5분 OHLC, 세션(날) 경계 안 넘음, asof 로 자른 마지막 5분봉 = 재집계와 일치
    m = {"202610021330": {"open": 10, "high": 11, "low": 9, "close": 10, "volume": 100},
         "202610021331": {"open": 10, "high": 13, "low": 8, "close": 12, "volume": 50},
         "202610021334": {"open": 12, "high": 12, "low": 7, "close": 9, "volume": 70},   # 1330 버킷 끝
         "202610021335": {"open": 9, "high": 9, "low": 9, "close": 9, "volume": 10},     # 1335 버킷 시작
         "202610011959": {"open": 5, "high": 5, "low": 5, "close": 5, "volume": 1}}      # 전날 — 다른 세션
    agg = Cond.aggregate_5m(m)
    check(agg["202610021330"] == {"open": 10, "high": 13, "low": 7, "close": 9, "volume": 220},
          "5m 집계: 1330 버킷 OHLC(첫open·최고high·최저low·끝close·합volume) %r" % agg.get("202610021330"))
    check(agg["202610021335"]["close"] == 9 and "202610011955" in agg,
          "5m 집계: 5분 경계로 새 버킷 · 전날(다른 세션)은 별도 버킷(경계 안 넘음)")
    # 세션 경계: 전날 1955 버킷(1959→5내림)에 10/02 분봉이 섞이지 않는다
    check(agg["202610011955"]["close"] == 5 and agg["202610011955"]["volume"] == 1,
          "5m 집계: 전날 버킷엔 전날 분봉만(세션 경계 안 넘음)")

    class H(dict):
        minutes = {"X": m}
    # asof 가 10/02 13:34 → 그날 마지막 완성/진행 5분봉 = 1330 버킷(1335 는 asof 이후). px tf="5m" 는 이 버킷 close.
    c5 = Cond.Ctx(H({"X": [Candle(d, 100, 100, 100, 100, 1000) for d in cal]}), cal, "X",
                  asof=dt.datetime(2026, 10, 2, 13, 34, tzinfo=utc), session_close=sc)
    got5 = c5.px("X", "close", "5m")
    # 10/01 엔 그날 5분봉(1955 버킷, close 5)이 있고, 10/02 엔 asof 이하 마지막이 1330 버킷(close 9).
    check(got5 == [5.0, 9.0], "5m px: 날짜별 asof 이하 마지막 5분봉 close(10/01=5·10/02=9) %r" % got5)
    # asof 를 1335 이후로 밀면 10/02 는 1335 버킷(high 9)까지 보인다
    c5b = Cond.Ctx(H({"X": [Candle(d, 100, 100, 100, 100, 1000) for d in cal]}), cal, "X",
                   asof=dt.datetime(2026, 10, 2, 13, 40, tzinfo=utc), session_close=sc)
    check(c5b.px("X", "high", "5m") == [5.0, 9.0], "5m px: 10/02 1335 버킷까지(high 9)")

    # 5) 혼합 tf 트리 — tf:1d(어제 확정) AND tf:5m(asof 이하) 를 저자 논리처럼 중첩. 1d 잎만 일봉축으로 당기고(per-leaf),
    #    5m 잎은 asof-오늘 축 그대로다 — 두 축이 섞인 all 노드는 당기지 않는다.
    #    c5 asof = 10/02 13:34(장중). 1d 잎은 어제(10/01) 확정 100 으로 당겨져 오늘 칸도 참(100>50). 5분봉은 asof 이하
    #    마지막(10/02 는 1330 버킷 close 9, 10/01 은 1955 버킷 close 5) 둘 다 50 미만 → 참. 그래서 오늘 칸도 AND 참.
    mixed = {"all": [{"gt": [{"px": "close", "sym": "X", "tf": "1d"}, 50]},      # 일봉축 어제 확정 100 > 50 → 참
                     {"lt": [{"px": "close", "sym": "X", "tf": "5m"}, 50]}]}     # 5분봉 종가 5·9 < 50 → 참
    mv = Cond.series(mixed, c5)
    check(mv[0] is True, "혼합 tf: 확정일(10/01) 일봉·5분봉 각 축이 저자 AND 를 그대로 합침(참) %r" % mv)
    check(mv[1] is True, "혼합 tf: 오늘(10/02 장중)도 1d 잎=어제 확정값·5m 잎=asof 이하값 둘 다 참 → AND 참 %r" % mv)
    # per-leaf 스코프 확인: 1d 잎 단독은 장중에도 어제값으로 당겨지고, 5m 잎 단독은 asof-오늘 축(1330 버킷 9)을 본다.
    leaf1d = Cond.series({"px": "close", "sym": "X", "tf": "1d"}, c5)
    leaf5m = Cond.series({"px": "close", "sym": "X", "tf": "5m"}, c5)
    check(leaf1d == [100.0, 100.0], "per-leaf: 1d 잎은 장중에도 어제 확정값으로 당김 %r" % leaf1d)
    check(leaf5m == [5.0, 9.0], "per-leaf: 5m 잎은 당기지 않고 asof 이하 마지막 5분봉 축 그대로 %r" % leaf5m)
    # 5분봉 데이터가 아예 없으면 그 잎은 None → all = None(조용히 거짓 아님). 일봉은 어제(10/01) 100 으로 여전히 참.
    class H0(dict):
        minutes = {"X": {}}
    c5none = Cond.Ctx(H0({"X": [Candle(d, 100, 100, 100, 100, 1000) for d in cal]}), cal, "X",
                      asof=dt.datetime(2026, 10, 2, 13, 0, tzinfo=utc), session_close=sc)
    check(Cond.series(mixed, c5none)[0] is None, "혼합 tf: 데이터 없는 5분봉 축은 None(모름) → all None")


def t_grade():
    """비중(산다 qty cash) — 수동 때문에 모르면 범위(화면 설명 구조는 signals/verify_view.py)."""
    from dsl.tradeTool import Grade
    xs = [100.0] * 30 + [130.0]
    cal = ["2022%04d" % i for i in range(len(xs))]
    hist = {"X": [Candle(d, c, c, c, c, 1000) for d, c in zip(cal, xs)]}
    tree = TreeGateway.of(synthetic(["X"],
                                    rule("비중", Cond.BUY, None, ("cash", {"case": [[{"manual": "모드"}, 14]], "else": 34}))))
    pe = Grade.RuleSeries(tree.product("X"), hist, cal)
    w, alt = pe.weight_of(len(xs) - 1)
    check(w is None and alt == [14.0, 34.0], "수동 모드 비중은 모름 + 범위 %r %r" % (w, alt))


def t_answers():
    """사람이 답한 수동(Ctx answers) — 열쇠 = 상품 + "|" + (문장 | "?" 식). 답은 manual_as 보다 먼저,
    not 아래에서도 잎 값 그대로(not 이 뒤집을 뿐), 없는 열쇠는 manual_as, answers=None 이면 옛 동작 그대로."""
    from dsl.tradeTool import Grade
    cal = ["2022%04d" % i for i in range(3)]
    hist = {p: [Candle(d, 100, 100, 100, 100, 1000) for d in cal] for p in ("A", "B", "M")}
    m = {"manual": "실적 좋음"}
    unk = {"ge": [{"px": "close", "sym": "M"}, "?"], "label": "M 높음"}

    def v(node, ma, answers):
        return Cond.series(node, Cond.Ctx(hist, cal, "A", manual_as=ma, answers=answers))[0]
    k = Cond.answer_key
    check(k(m, "A") == "A|실적 좋음", "답 열쇠(상품)")
    check(k(unk, "A") == "A|?" + json.dumps({"ge": [{"px": "close", "sym": "M"}, "?"]}, ensure_ascii=False,
                                                    sort_keys=True), "답 열쇠(\"?\" 식 — META 뗀 식)")
    for ma in (True, False, None):
        for ans in (True, False):
            check(v(m, ma, {"A|실적 좋음": ans}) is ans, "답이 manual_as(%r) 보다 먼저" % ma)
            check(v({"not": m}, ma, {"A|실적 좋음": ans}) is (not ans), "not 아래 답은 잎 값 그대로(not 이 뒤집음)")
        check(v({"not": m}, ma, {}) is ma and v({"not": m}, ma, None) is ma, "답 없으면 극성 규칙 그대로(%r)" % ma)
    check(v(m, None, {"B|실적 좋음": True}) is None, "다른 상품의 답은 안 먹는다")
    check(v(unk, True, {k(unk, "A"): False}) is False, "\"?\" 식도 답으로 풀린다")
    tree = TreeGateway.of(synthetic(["A"], rule("실적", Cond.BUY, {"all": [m]})))
    got = [Grade.RuleSeries(tree.product("A"), hist, cal, answers=a).grade_key(2)
           for a in (None, {"A|실적 좋음": True}, {"A|실적 좋음": False})]
    check(got == ["confirm", "buy", "wait"], "등급까지 답으로 풀린다(확인 대기 → 매수 후보·관망) %r" % got)


# ------------------------------------------------------------------ 데이터 완전성 가드(워밍업 부족 → 불완전)
def t_warmup_guard():
    """★ 실제 발견된 버그 방지(영구): 시세가 rate-limit 로 잘려(워밍업 부족) 와도 엔진이 그 불완전 데이터로
    조용히 ✅/🚫 확신을 내면 모르고 매매하게 된다. 가드는 트리가 쓰는 가장 긴 lookback(워밍업)을 트리에서
    직접 뽑아, 그보다 확정 봉이 적은 초기 구간의 1d 신호를 '불완전 데이터(❔)'로 표면화한다.

    확인:
      1) 필요 워밍업을 트리에서 바르게 계산한다(창 n-1·lag k 가 가장 깊은 사슬로 누적되고,
         barssince 류는 AtLeast/None 으로 스스로 불확실을 드러내므로 워밍업에 넣지 않는다).
      2) 워밍업을 일부러 잘라낸(필요보다 적은 봉) 입력 → 그 초기 구간은 incomplete=True 이고 grade_key 가 ❔.
      3) 워밍업이 충분한 구간 → incomplete=False, 가드 끼기 전과 등급이 '그대로'(오탐 0).
    """
    from dsl.tradeTool import Grade

    # 1) warmup_of / 출입구 warmup 산식 — 손으로 셀 수 있는 노드들로 전수 대조.
    cases = [
        (C, 0), ({"px": "close", "sym": "Y"}, 0), ({"manual": "x"}, 0), (5, 0),
        (AVG(C, 20), 19), ({"highest": [C, 60]}, 59), ({"sum": [C, 10]}, 9),
        ({"lag": [C, 5]}, 5), (PCT(C, 3), 3), (COUNT({"gt": [C, 0]}, 10), 9),
        (AVG({"lag": [C, 5]}, 20), 24),                          # 중첩: lag5 안에 평균20 → 5 + 19
        (STREAK({"gt": [C, AVG(C, 20)]}), 19),                   # 연속 일수 자체는 안 더함, 안쪽 평균20 만
        ({"barssince": {"ge": [C, {"highest": [C, 60]}]}}, 59),
        ({"valuewhen": [{"gt": [C, 0]}, AVG(C, 30)]}, 29),       # max(안쪽) = 29
        ({"all": [AVG(C, 5), {"highest": [C, 60]}]}, 59),        # 논리 묶음 = 자식 최댓값
        ({"atleast": 1, "of": [{"lag": [C, 2]}, AVG(C, 10)]}, 9),
        ({"not": AVG(C, 7)}, 6), ({"abs": PCT(C, 4)}, 4),
        ({"case": [[{"gt": [C, 0]}, AVG(C, 8)]], "else": {"highest": [C, 40]}}, 39),
    ]
    for node, exp in cases:
        got = Cond.warmup_of(node)
        check(got == exp, "warmup_of %r → %d (기대 %d)" % (node, got, exp))

    # 트리 상품 워밍업 = 등급을 내는 갈래(산다·안 산다) 전체의 최댓값.
    tree = TreeGateway.of(synthetic(["P"], rule("신고가", Cond.BUY, {"gt": [C, {"highest": [C, 60]}]}),
                                    rule("10일선 아래", Cond.BLOCK, {"lt": [C, AVG(C, 10)]})))
    check(tree.warmup("P") == 59, "warmup = 등급 갈래 최댓값(highest60 → 59)")

    # 2) 워밍업 자르기 — 필요 워밍업 60(=highest60)짜리 트리. 충분한 봉 vs 모자란 봉.
    W = tree.warmup("P")                                          # 59
    need = W + 1                                                  # 첫 완전 봉이 서려면 확정 봉이 이만큼
    rng = random.Random(7)
    xs = [x if x is not None else 100.0 for x in rand_series(rng, need + 40, miss=0)]
    cal = ["2024%04d" % i for i in range(len(xs))]
    hist = {"P": [Candle(d, c, c, c, c, 1000) for d, c in zip(cal, xs)]}
    pe = Grade.RuleSeries(tree.product("P"), hist, cal)
    # 초기 W 개 봉(index 0..W-1)은 확정 봉이 모자라 incomplete → grade_key 가 ❔(unknown).
    check(all(pe.incomplete(i) for i in range(W)), "워밍업 부족 구간(0..%d) 전부 incomplete" % (W - 1))
    check(all(pe.grade_key(i) == "unknown" for i in range(W)),
          "워밍업 부족 구간 1d 등급은 ❔(판정 불가)여야 — 조용히 ✅/🚫 안 냄")
    # 워밍업이 충분해진 뒤(index >= W)는 incomplete=False — 신호를 낸다.
    check(not any(pe.incomplete(i) for i in range(W, len(xs))), "워밍업 채운 뒤는 incomplete 아님(오탐 0)")

    # 3) 오탐 0(가드 불변식) — 가드가 끼기 전 '원시 등급'(워밍업 무시)과, 워밍업 충분한 구간의 등급이 같아야.
    #    _raw_grade = incomplete 검사를 건너뛴 등급. 충분 구간에서 두 값이 완전히 일치하면 가드는 정상 데이터를
    #    절대 건드리지 않는다는 뜻(파리티 오탐 0 의 단위테스트판).
    def raw_grade(pe_, i):
        views = {"opt": pe_.opt, "pes": pe_.pes}
        for rule in Grade.GRADE_RULES["rules"]:
            if all(views[rule["view"]][sec][i] is want for sec, want in rule["when"].items()):
                return rule["key"]
        return Grade.GRADE_RULES["default"]
    bad = [i for i in range(W, len(xs)) if pe.grade_key(i) != raw_grade(pe, i)]
    check(not bad, "워밍업 충분 구간 등급 == 가드 없는 원시 등급(오탐 0) @%r" % bad[:3])

    # 트렁케이트 비교: 같은 꼬리 구간을 '긴 이력'과 '짧게 잘린 이력'으로 각각 판정 — 긴 쪽은 신호를 내지만
    # 짧게 잘린 쪽은 워밍업이 모자란 꼬리 봉을 ❔ 로 뺀다(바로 그 '251봉 vs 594봉' 버그를 잡는 경로).
    short = {"P": [Candle(d, c, c, c, c, 1000) for d, c in zip(cal, xs)][-30:]}   # 꼬리 30봉만(워밍업 없음)
    short_cal = [c.date for c in short["P"]]
    pe_short = Grade.RuleSeries(tree.product("P"), short, short_cal)
    check(all(pe_short.incomplete(i) for i in range(len(short_cal))),
          "짧게 잘린 이력(워밍업 없음)은 전 구간 불완전 — 긴 이력이면 신호 낼 꼬리까지 ❔ 로 뺀다")
    last = len(cal) - 1
    check(not pe.incomplete(last) and pe_short.incomplete(len(short_cal) - 1),
          "같은 마지막 날: 긴 이력=완전(신호 OK) · 잘린 이력=불완전(판정 보류) — 조용한 오판 차단")


# ------------------------------------------------------------------ 6. 표현력 회귀(이번 버그 유형)
def t_regress():
    # (a) '20일선 회복 후 2거래일 유지' — 1일만 위면 거짓, 회복일+2일이면 참
    hold = {"ge": [STREAK({"gt": [C, AVG(C, 20)]}), 3]}
    xs = [100.0] * 25 + [90.0] * 5 + [110.0]
    check(Cond.series(hold, make_ctx(xs))[-1] is False, "2일 유지: 1일만 위인데 참")
    check(Cond.series(hold, make_ctx(xs + [111.0, 112.0]))[-1] is True, "2일 유지: 3일 위인데 거짓")
    # (b) '전고점 돌파 후 돌파선 위 유지' — 돌파선 고정. 105 돌파 후 104·104.5 는 유지
    prior = {"highest": [{"lag": [C, 1]}, 20]}
    brk = {"gt": [C, prior]}
    level = {"valuewhen": [brk, prior]}
    held_ok = {"gt": [{"minsince": [brk, C]}, level]}        # 돌파 이후 최저 종가가 돌파선 위
    days = {"add": [{"barssince": brk}, 1]}                  # 돌파일 포함 경과일
    xs = [100.0] * 21 + [105.0, 104.0, 104.5]
    ctx = make_ctx(xs)
    check(Cond.series(held_ok, ctx)[-1] is True and same(Cond.series(days, ctx)[-1], 3.0),
          "돌파 유지: 돌파선(100) 고정 → 104·104.5 는 유지 3일")
    check(Cond.series(held_ok, make_ctx(xs + [99.0]))[-1] is False, "돌파 유지: 돌파선 아래 마감이면 실패")
    # (c) '짧은 눌림(2일) 끝 반등' — 눌림 일수에 반등일을 넣지 않는다
    hi = {"barssince": {"ge": [C, {"highest": [C, 20]}]}}
    rebound = {"gt": [C, {"lag": [C, 1]}]}
    pull2 = {"all": [rebound, {"ge": [{"lag": [hi, 1]}, 2]}, {"le": [{"lag": [hi, 1]}, 2]}]}
    xs = [float(100 + i) for i in range(25)] + [122.0, 121.0, 122.5]   # 고점 124 → 2일 하락 → 반등
    check(Cond.series(pull2, make_ctx(xs))[-1] is True, "눌림 2일 후 반등: 참이어야")
    xs1 = [float(100 + i) for i in range(25)] + [122.0, 123.0]          # 1일 하락 → 반등
    check(Cond.series(pull2, make_ctx(xs1))[-1] is False, "눌림 1일 후 반등: 거짓이어야")
    # (d) 판정 불가는 위로 전파 — 4개 중 2개에서 2개가 모름이면 결과도 모름일 수 있다
    four = {"atleast": 2, "of": [{"gt": [C, 0]}, {"lt": [C, 0]}, {"manual": "a"}, {"manual": "b"}]}
    check(Cond.series(four, make_ctx([1.0]))[0] is None, "4개 중 2개(1참·1거짓·2모름) → 모름")


# ------------------------------------------------------------------ 7. 트리 출입구(TreeGateway) 계약
def t_gateway():
    """판정·백테스트·검사기가 트리(v3 규칙 목록)에 묻는 질문의 답 모양 — {"rule"} 은 펼쳐서 건넨다.
    종목 모델은 on(어느 상품) + sym(구체 티커) 둘뿐 — 폐지된 표기(names·products.index·$ 심볼·across)는 거부."""
    W = {"gt": [C, AVG(C, 20)]}
    M = {"gt": [{"px": "close", "sym": "NQ=F", "tf": "1m"}, 0]}
    UP = lambda t: {"gt": [{"px": "close", "sym": t}, 0]}
    data = {
        "version": 3,
        "products": {"A": {"note": "a 노트", "ref": "0-1"}, "B": {}},
        "rules": [
            {"label": "20일선 위", "ref": "1-1", "value": W},
            {"label": "선물 양", "ref": "1-2", "on": ["A"],
             "then": [{"when": {"all": [{"rule": "20일선 위"}, M]}, "do": Cond.BUY}]},
            {"label": "지수 음", "ref": "2-1",
             "then": [{"when": {"lt": [{"px": "close", "sym": "^NDX"}, 0]}, "do": Cond.BLOCK}]},
            {"label": "비중", "ref": "4-1", "then": [{"do": Cond.BUY, "qty": {"of": "cash", "x": 30}}]},
            {"label": "1차", "ref": "4-2", "on": ["A"], "then": [{"do": Cond.BUY, "qty": {"of": "budget", "x": 0.5}}]},
            {"label": "2차", "on": ["A"], "then": [{"when": {"ge": [{"pos": "filled", "rule": "1차"}, 1]},
                                                   "do": Cond.BUY, "qty": {"of": "budget", "x": 0.5}}]},
            {"label": "익절", "ref": "5-1",
             "then": [{"when": {"ge": [{"pos": "ret"}, 9]}, "do": Cond.SELL, "qty": {"of": "held", "x": 1}}]},
            {"label": "묶음 상승", "ref": "6-1", "on": ["A"],
             "then": [{"when": {"atleast": 1, "of": [UP("N1"), UP("N2")]}, "do": Cond.BUY}]},
            {"label": "못 옮김", "ref": "9-9", "skip": "데이터 없음: x"}]}
    g = TreeGateway.of(data)
    check(g.products() == ["A", "B"] and g.has("A") and not g.has("Z"), "products/has")
    check(g.note("A") == "a 노트" and g.note("B") is None, "note")
    ent = g.gate("A", Cond.BUY)["any"]
    check([n["label"] for n in ent] == ["선물 양", "묶음 상승"] and g.gate("B", Cond.BUY) == {"any": []},
          "gate(산다) = 산다 갈래(포지션·조건 없는 갈래 제외, on 반영) %r" % ent)
    check(ent and ent[0]["all"][0] == dict(W, label="20일선 위", ref="1-1") and ent[0]["allprod"] is False,
          "{rule} 는 그 규칙 value 로 펼치고 이름·소절을 싣는다 %r" % (ent[:1],))
    check(len(ent) > 1 and ent[1]["of"] == [UP("N1"), UP("N2")], "여러 종목 = atleast·of 그대로(각 잎 구체 티커)")
    av = g.gate("A", Cond.BLOCK)["any"]
    check([(n["label"], n["allprod"]) for n in av] == [("지수 음", True)], "gate(안 산다) %r" % av)
    try:
        g.gate("A", Cond.SELL)
        FAILS.append("판다는 등급 동사가 아닌데 gate 가 받음")
    except Cond.CondError:
        pass
    sz = g.weight("A")
    check((sz.label, sz.ref, sz.qty) == ("비중", "4-1", ("cash", 30)), "weight = 산다 qty cash")
    trs = g.tranches("A")
    check([(t.label, t.qty, t.when) for t in trs] == [("1차", ("budget", 0.5), None),
                                                       ("2차", ("budget", 0.5), {"ge": [{"pos": "filled", "rule": "1차"}, 1]})]
          and g.tranches("B") == [], "tranches = 산다 qty budget(pos filled 의 rule = 장부 열쇠로 남김) %r"
          % [(t.label, t.when) for t in trs])
    e = g.sells("A")
    check([(r.label, r.qty) for r in e] == [("익절", ("held", 1))], "sells = 판다 %r" % [(r.label, r.qty) for r in e])
    check(g.symbols() == {"A", "B", "X", "^NDX", "NQ=F", "N1", "N2"} and g.symbols(["B"]) == {"B", "^NDX"},
          "symbols = 상품 + 식의 sym %r · %r" % (g.symbols(), g.symbols(["B"])))
    check(g.minute_symbols() == {"NQ=F"} and g.timeframes() == {"1d", "1m"}, "minute_symbols/timeframes")
    check(g.warmup("A") == 19 and g.warmup("B") == 0 and g.warmup() == 19, "warmup")
    check(g.refs() == {"0-1", "1-1", "1-2", "2-1", "4-1", "4-2", "5-1", "6-1", "9-9"}, "refs %r" % g.refs())
    check(g.skips() == [{"rule": "못 옮김", "ref": "9-9", "reason": "데이터 없음: x"}], "skip 규칙")
    check(not TreeGateway({}) and bool(g) and TreeGateway.load("__없는책__") is None, "빈·없는 트리")
    check(W in g.conditions() and {"all": [{"rule": "20일선 위"}, M]} in g.conditions(), "conditions = 적힌 그대로의 조건식")
    # on 은 상품만 · qty 식의 {"rule"} 은 펼친다 · 규칙 note 는 갈래까지
    g2 = TreeGateway.of(dict(data, rules=data["rules"] + [rule("A 전용 익절", Cond.SELL, W, ("held", 0.5), on=["A"], note="메모"),
                                                          rule("식 비중", Cond.BUY, None, ("cash", {"rule": "20일선 위"}))]))
    s2 = [r for r in g2.sells("A") if r.label == "A 전용 익절"]
    check(s2 and s2[0].note == "메모" and not [r for r in g2.sells("B") if r.label == "A 전용 익절"],
          "on 반영 · note 전달")
    check(TreeGateway.of(dict(data, rules=[rule("식", Cond.BUY, None, ("cash", {"rule": "w"})),
                                           {"label": "w", "value": W}])).weight("A").qty.x == dict(W, label="w"),
          "qty 식의 {rule} 펼침")
    check(g.refs() >= {"0-1"}, "refs 에 상품 ref 포함")
    # 규칙 단위 질문(구간② 검사기) — 이름 목록 · 뜻(펼침/그대로) · 측정 · why · 옛 양식 키
    check(g.labels()[:2] == ["20일선 위", "선물 양"] and g.body("없음") is None, "labels/body 없는 이름")
    b2 = g.body("선물 양")
    check(b2["products"] == ["A"] and b2["branches"][0]["do"] == Cond.BUY
          and b2["branches"][0]["when"]["all"][0] == dict(W, label="20일선 위", ref="1-1")
          and g.body("선물 양", expand=False)["branches"][0]["when"]["all"][0] == {"rule": "20일선 위"},
          "body 펼침/그대로 %r" % b2)
    check(g.value("20일선 위") == W and g.value("선물 양") is None and g.why("선물 양") is None
          and TreeGateway.of(dict(data, rules=data["rules"] + [dict(rule("w", Cond.BUY, W), why="원문 3-1")])).why("w") == "원문 3-1",
          "value/why")
    bad = dict(data, rules=data["rules"] + [rule("x", Cond.BUY, {"rule": "없는 이름"})])
    check(TreeGateway.of(bad).gate("A", Cond.BUY)["any"][-1].get("manual", "").startswith("연산 없음: 미해결 참조"),
          "없는 이름 참조는 수동(연산 없음)으로 드러낸다")
    R0 = {"label": "r", "then": [{"when": W, "do": Cond.SELL}]}
    old_sym = lambda sym: dict(data, rules=[{"label": "r", "then": [{"when": {"lt": [{"px": "close", "sym": sym}, 0]},
                                                                      "do": Cond.BLOCK}]}])
    for broken in (dict(data, version=2), dict(data, products={}), dict(data, rules=[]),
                   dict(data, rules=data["rules"] + [data["rules"][0]]),
                   dict(data, rules=data["rules"] + [rule("y", "쉰다", {"all": []})]),
                   dict(data, review={}),                                         # 옛 양식 키
                   dict(data, products={"A": {"ref": "0-1", "exit_note": "x"}}),
                   dict(data, names={"$묶음": {"syms": ["N1"]}}),                    # 폐지: 이름 심볼
                   dict(data, products={"A": {"index": "^NDX"}, "B": {}}),          # 폐지: 상품의 기준지수 칸
                   old_sym("$self"), old_sym("$index"),                            # 폐지: $ 심볼
                   dict(data, rules=[{"label": "r", "then": [{"when": {"lt": [{"px": "close"}, 0]}, "do": Cond.BLOCK}]}]),  # sym 생략
                   dict(data, rules=[{"label": "r", "then": [{"when": {"ge": [{"across": {"syms": ["N1"], "cond": UP("N1")}}, 1]},
                                                              "do": Cond.BUY}]}]),     # 폐지: across
                   dict(data, rules=[dict(R0, scale=0.5)]),                         # 규칙에 모르는 키
                   dict(data, rules=[{"label": "r", "then": [{"when": W, "do": Cond.SELL, "sell": "all"}]}]),
                   dict(data, rules=[{"label": "r", "then": [{"when": W, "do": Cond.SELL, "qty": {"of": "cash", "x": 1}}]}]),
                   dict(data, rules=[{"label": "r", "then": [{"when": W, "do": Cond.BLOCK, "qty": {"of": "held", "x": 1}}]}]),
                   dict(data, rules=[{"label": "r", "then": [{"when": W, "do": Cond.BUY, "repeat": True}]}]),
                   dict(data, rules=[dict(R0, skip="연산 없음: x")]),                  # then 과 skip 같이
                   dict(data, rules=[{"label": "r", "note": "식 없음"}]),               # then·value·skip 다 없음
                   dict(data, rules=[dict(R0, on=["Z"])]),                            # on 이 없는 종목
                   dict(data, rules=[{"then": R0["then"]}]),                         # label 없음
                   dict(data, rules=[{"label": "r", "then": [{"do": Cond.SELL}]}]),     # 판다인데 when 없음
                   dict(data, rules=[{"label": "r", "value": {"foo": 1}}])):           # 참조 안 된 이름 조건도 문법 검사
        try:
            TreeGateway.of(broken)
            FAILS.append("형식이 틀린 트리가 통과: %r" % sorted(broken))
        except Cond.CondError:
            pass


def main():
    rng = random.Random(20261001)
    for name, fn in (("수치 연산", lambda: t_numeric(rng)), ("3값 논리", t_logic),
                     ("시간 연산", lambda: t_time(rng)), ("하한", t_bounds), ("포지션", lambda: t_pos(rng)),
                     ("인과성", lambda: t_causal(rng)),
                     ("문법", t_syntax), ("관측 시점(asof)", t_asof),
                     ("혼합 tf·확정봉·look-ahead 0", t_settled_mtf),
                     ("등급·금액", t_grade), ("데이터 완전성 가드(워밍업)", t_warmup_guard),
                     ("표현력 회귀", t_regress),
                     ("트리 출입구 계약", t_gateway),
                     ("수동 답(answers)", t_answers)):
        before = len(FAILS)
        try:
            fn()
        except Exception as e:  # noqa: BLE001 — 검사기 자체가 죽어도 실패로 센다
            FAILS.append("%s: 예외 %r" % (name, e))
        n = len(FAILS) - before
        print("  %s %s%s" % ("✅" if n == 0 else "❌", name, "" if n == 0 else " — 실패 %d" % n))
    if FAILS:
        for f in FAILS[:30]:
            print("    · " + f)
        print("원시함수 검사 실패 %d건 — 정지" % len(FAILS))
        return 1
    print("원시함수 검사 통과 — 수치·3값·시간·인과·문법·회귀·출입구")
    return 0


if __name__ == "__main__":
    sys.exit(main())
