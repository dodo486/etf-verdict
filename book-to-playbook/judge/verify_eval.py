#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""계산기·등급 검사 (책 무관 · 크기 고정).

왜 있나
  옛 검증층은 전부 '글자 대조'였다 — 라벨·원문·판정식의 숫자/단어가 서로 나오는지만 봤고,
  계산이 실제로 맞는지는 아무도 실행해 보지 않았다. 그래서 '2거래일 유지'가 1일로 판정되고
  ('2' 라는 글자는 있으니 통과), '전고점 유지'가 연속 신고가를 세도 통과했다.
  규칙은 원시함수 조합뿐이므로, 계산기(judge/eval.py)를 실행으로 철저히 검증하면
  어떤 책의 어떤 조건이든 계산 버그가 들어올 자리가 없다. 책이 늘어도 이 검사는 늘지 않는다.

무엇을 하나 (기준은 전부 계산기와 독립적으로 구한다)
  1. 수치 연산 — pandas rolling/shift 로 계산한 값과 무작위 시계열(결측 포함)에서 대조
  2. 3값 논리 — '모름' 자리에 참/거짓을 전부 넣어 본 결과로 정답을 정의해 전수 대조
  3. 시간 연산(barssince·valuewhen, 조합: 최근 참 일수·연속 참 일수 · 여러 종목 중 N개 = atleast·of) — 단순 반복 구현과 대조
     · 하한(AtLeast) 비교 · 포지션 값(pos)
  4. 인과성 — 미래 데이터를 잘라도 과거 날짜 값이 같아야 한다(미래 참조 금지)
  5. 봉(tf) — 적힌 tf 의 봉만 읽는다(단위 무관: 분·초 같은 코드) · 창·lag 는 그 tf 봉 개수로 셈 · 장중은 오늘 칸에 접힘
     · 혼합 tf(장중 vs 일봉) · '오늘 미확정' 확정봉 규칙·look-ahead 0
  6. 등급 — 비중 범위 · 데이터 완전성 가드(워밍업 부족 → ❔, 충분 구간은 원시 등급 사다리와 같음)
  7. 표현력 회귀 — 발견된 버그 유형을 트리로 적어 원문 뜻대로 나오는지
  8. 사람이 답한 수동(Ctx answers) — 답 열쇠 규칙·극성·등급까지(서버 권위의 바탕)
  9. 값 기억·공유 — 묶은 식(판때기 노드)의 값 기억: $self 는 상품마다 · 노드 레벨 on(OFF)은 걸러내기 전과 같은 일봉축 ·
     수동·pos 없는 노드만 문맥끼리 공유(한 번 계산) · 수동·pos 는 문맥마다 · 확정 경계 범위(scope) 밖 심볼은 공유 안 함
  (트리 문법·출입구 계약은 tree/verify_gateway.py, 체결 워크·실전 경로는 backtest/verify_trading.py,
   화면 설명 구조는 web/verify_view.py 가 본다)

언제 돌리나: 계산기(judge/eval.py)·등급(judge/judge.py·grade_rules.json)을 바꿨을 때 —
  보통은 `python -m entry.run check` 가 함께 돌린다.

사용: python -m judge.verify_eval   (실패 있으면 exit 1)
"""
import itertools
import json
import math
import random
import sys
from collections import namedtuple

import pandas as pd

from shared import paths  # noqa: F401  (UTF-8 출력)
from judge.eval import _cmp, Ctx, series
from judge.judge import GRADE_RULES, RuleSeries
from tree.gateway import (
    answer_key, AtLeast, BLOCK, BUY, CondError, GONE_OPS, _op_of, POS_FIELDS, TreeGateway, rule, synthetic, validate,
    warmup_of)   # 합성 트리는 출입구로 만든다(entry.verify_rules 명시 예외)

Candle = namedtuple("Candle", "date open high low close volume")
FAILS = []


def check(ok, what):
    if not ok:
        FAILS.append(what)


def same(a, b, tol=1e-9):
    if isinstance(a, AtLeast) != isinstance(b, AtLeast):
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
    return Ctx(hist, cal, "X", manual_as=manual_as)


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
                got = series({op: [C, n]}, ctx)
                bad = [i for i in range(len(xs)) if not same(got[i], ref[i], 1e-7)]
                check(not bad, "%s(%d) pandas 와 불일치 @%s (trial %d)" % (op, n, bad[:3], trial))
            ref = ps.rolling(n, min_periods=n).mean()
            got = series(AVG(C, n), ctx)
            check(all(same(got[i], ref[i], 1e-7) for i in range(len(xs))), "평균(sum÷n, %d) 불일치 (trial %d)" % (n, trial))
        for k in (0, 1, 5):
            ref = ps.shift(k)
            got = series({"lag": [C, k]}, ctx)
            check(all(same(got[i], ref[i]) for i in range(len(xs))), "lag(%d) 불일치" % k)
            if k:
                ref = (ps / ps.shift(k) - 1) * 100
                got = series(PCT(C, k), ctx)
                check(all(same(got[i], ref[i], 1e-7) for i in range(len(xs))), "변화율(%d일) 조합 불일치" % k)
        a = series({"sub": [C, {"lag": [C, 1]}]}, ctx)
        ref = ps - ps.shift(1)
        check(all(same(a[i], ref[i], 1e-7) for i in range(len(xs))), "sub 불일치")
        dz = series({"div": [C, 0]}, ctx)
        check(all(v is None for v in dz), "div 0 은 None 이어야 한다")
        prev = ps.shift(1)
        for op, ref in (("max", pd.concat([ps, prev], axis=1).max(axis=1, skipna=False)),
                        ("min", pd.concat([ps, prev], axis=1).min(axis=1, skipna=False))):
            got = series({op: [C, {"lag": [C, 1]}]}, ctx)
            check(all(same(got[i], ref[i], 1e-12) for i in range(len(xs))), "%s 불일치 (trial %d)" % (op, trial))
        ref = (ps - prev).abs()
        got = series({"abs": {"sub": [C, {"lag": [C, 1]}]}}, ctx)
        check(all(same(got[i], ref[i], 1e-7) for i in range(len(xs))), "abs 불일치 (trial %d)" % trial)
    # 지운 전용 지표 연산은 문법에서 거부된다(조합으로 쓴다)
    for op in GONE_OPS:
        try:
            validate({op: [C, 5]})
            FAILS.append("지운 연산 %s 가 문법을 통과" % op)
        except CondError:
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
            got = series({"all": cols}, ctx)[0]
            check(got == truth(all, xs) or (got is None and truth(all, xs) is None), "all%r" % (xs,))
            got = series({"any": cols}, ctx)[0]
            check(got == truth(any, xs) or (got is None and truth(any, xs) is None), "any%r" % (xs,))
            for n in range(1, 4):
                got = series({"atleast": n, "of": cols}, ctx)[0]
                exp = truth(lambda ys: sum(ys) >= n, xs)
                check(got is exp or got == exp, "atleast %d %r: %r≠%r" % (n, xs, got, exp))
    for x in vals:
        node = {"gt": [1 if x else -1, 0]} if x is not None else {"manual": "모름"}
        got = series({"not": node}, make_ctx([1.0]))[0]
        check(got == (None if x is None else not x), "not %r" % x)
    # manual 은 manual_as 를 따른다
    for m in (True, False, None):
        got = series({"manual": "장중"}, make_ctx([1.0], manual_as=m))[0]
        check(got is m, "manual_as=%r" % m)
    # 극성: not 아래 수동은 반대 가정 — manual_as=True(유리하게 풀림)면 '겹치면 쉼'은 참(쉴 이유 없음)
    rest = {"not": {"all": [{"gt": [1, 0]}, {"manual": "달러 강세"}]}}
    check(series(rest, make_ctx([1.0], manual_as=True))[0] is True, "not 아래 수동: 낙관이면 참")
    check(series(rest, make_ctx([1.0], manual_as=False))[0] is False, "not 아래 수동: 비관이면 거짓")
    dbl = {"not": {"not": {"manual": "x"}}}
    for m in (True, False):
        check(series(dbl, make_ctx([1.0], manual_as=m))[0] is m, "not not 수동 = manual_as")
    # case — 위에서부터 처음 참인 갈래. 앞 갈래가 모름이면 결과도 모름(뒤로 넘어가지 않는다)
    for c1, c2 in itertools.product(vals, repeat=2):
        node = {"case": [[{"gt": [1 if c1 else -1, 0]} if c1 is not None else {"manual": "a"}, 10],
                         [{"gt": [1 if c2 else -1, 0]} if c2 is not None else {"manual": "b"}, 20]], "else": 30}
        got = series(node, make_ctx([1.0]))[0]
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
            got = series(COUNT(c, n), ctx)
            for i in range(60):
                w = bits[i - n + 1:i + 1] if i - n + 1 >= 0 else None
                exp = None if (w is None or None in w) else float(sum(w))
                check(same(got[i], exp), "count(%d)@%d %r≠%r" % (n, i, got[i], exp))
        got = series(STREAK(c), ctx)
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
                exp = AtLeast(cnt)       # 모르는 날·데이터 시작에 닿음 → 최소 cnt
            check(same(got[i], exp), "연속 참 일수@%d %r≠%r" % (i, got[i], exp))
        got = series({"barssince": c}, ctx)
        vw = series({"valuewhen": [c, {"lag": [C, 0]}]}, ctx)
        val = [float(v) for v in range(60)]           # 결측 없는 값열(위치 = 값)
        vctx = make_ctx(xs, extra={"V": val})
        V = {"px": "close", "sym": "V"}
        mn = series({"minsince": [c, V]}, vctx)
        mx = series({"maxsince": [c, V]}, vctx)
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
                exp = AtLeast(i - stop)      # 그 사이 참 없음 → 최소 i-stop 거래일
            check(same(got[i], exp), "barssince@%d" % i)
            check(same(vw[i], ev), "valuewhen@%d" % i)
            check(same(mn[i], emn) and same(mx[i], emx), "min/maxsince@%d" % i)
    # 여러 종목 중 N개 = atleast·of(각 잎 sym = 그 티커 — across 폐지)
    ctx = make_ctx([1.0, 1.0], extra={"A": [1.0, 2.0], "B": [3.0, 1.0], "D": [None, 5.0]})
    up = lambda t: {"gt": [{"px": "close", "sym": t}, {"lag": [{"px": "close", "sym": t}, 1]}]}
    got = series({"atleast": 1, "of": [up("A"), up("B")]}, ctx)
    check(got == [None, True], "A·B 중 1개 상승 %r" % got)
    got = series({"atleast": 2, "of": [up("A"), up("B")]}, ctx)
    check(got == [None, False], "A·B 중 2개 상승 %r" % got)


def t_bounds():
    """하한 비교의 정답: 참값 v 가 하한 a 이상 아무 정수일 때 결과가 하나로 정해지면 그 값, 갈리면 None."""
    for a in range(0, 6):
        for b in range(0, 8):
            for op, f in (("gt", lambda v: v > b), ("ge", lambda v: v >= b),
                          ("lt", lambda v: v < b), ("le", lambda v: v <= b)):
                outs = {f(v) for v in range(a, a + 20)}
                exp = outs.pop() if len(outs) == 1 else None
                got = _cmp(op, AtLeast(a), float(b))
                check(got == exp and (got is None) == (exp is None), "하한 %s(≥%d, %d)" % (op, a, b))
                # 좌우를 바꾼 비교도 같아야 한다: b op' AtLeast
                mirror = {"gt": "lt", "ge": "le", "lt": "gt", "le": "ge"}[op]
                got2 = _cmp(mirror, float(b), AtLeast(a))
                check(got2 == exp and (got2 is None) == (exp is None), "하한 대칭 %s" % op)
    # 실제 쓰임: 데이터 시작부터 20일선 위(정확한 길이 모름)라도 '3일 이상'은 참
    xs = [100.0 + i for i in range(40)]
    up = {"gt": [C, AVG(C, 20)]}
    check(series({"ge": [STREAK(up), 3]}, make_ctx(xs))[-1] is True, "긴 상승 streak≥3 = 참")
    check(series({"lt": [STREAK(up), 3]}, make_ctx(xs))[-1] is False, "긴 상승 streak<3 = 거짓")
    check(series({"ge": [STREAK(up), 30]}, make_ctx(xs))[-1] is None, "streak≥30 은 모름(21일만 확인)")
    check(isinstance(series({"add": [STREAK(up), 1]}, make_ctx(xs))[-1], AtLeast), "하한+1 = 하한")
    check(series(AVG(STREAK(up), 2), make_ctx(xs))[-1] is None, "하한의 이동평균 = 모름")


def t_pos(rng):
    """포지션 값(ret·days·maxret·minret) — 단순 반복 구현과 대조, 진입 전은 None, 미래 무관."""
    for trial in range(20):
        xs = [x if x is not None else 100.0 for x in rand_series(rng, 60, miss=0)]
        e = rng.randrange(5, 50)
        px = xs[e] * (1 + rng.uniform(-0.01, 0.01))
        ctx = make_ctx(xs)
        ctx.pos = (e, px)
        got = {f: series({"pos": f}, ctx) for f in POS_FIELDS}
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
            check(same(series({"pos": "maxret"}, pre)[44], got["maxret"][44], 1e-9), "pos 미래 참조")
    # 평균 매입가가 날짜별로 바뀌는 경우(분할 매수) — ret 은 그날의 평균 매입가 기준
    xs = [100.0, 100.0, 110.0, 120.0, 90.0]
    ctx = make_ctx(xs)
    ctx.pos = (1, [None, 100.0, 100.0, 105.0, 105.0])
    got = series({"pos": "ret"}, ctx)
    check(got[0] is None and same(got[2], 10.0) and same(got[3], (120 / 105 - 1) * 100)
          and same(got[4], (90 / 105 - 1) * 100), "pos.ret 평균 매입가 목록 %r" % got)
    # 장부 값(filled·sold) — 체결 워크가 날짜별로 넣는다. 장부가 없으면 모름(옛 동작: minret 로 잘못 계산되던 자리)
    book = {"filled": {None: [0, 1, 1, 2, 2], "1차": [0, 1, 1, 1, 1], "2차": [0, 0, 0, 1, 1]},
            "sold": [None, 0.0, 0.0, 0.0, 0.5]}
    ctx.pos = (1, 100.0, book)
    F = lambda node: series(node, ctx)
    check(F({"pos": "filled"}) == [None, 1.0, 1.0, 2.0, 2.0] and F({"pos": "filled", "rule": "2차"}) == [None, 0.0, 0.0, 1.0, 1.0]
          and F({"pos": "filled", "rule": "없는 차수"}) == [None, 0.0, 0.0, 0.0, 0.0]
          and F({"pos": "sold"}) == [None, 0.0, 0.0, 0.0, 0.5], "pos filled·sold 장부 값")
    ctx = make_ctx(xs)                       # 새 문맥(계산 캐시는 문맥마다) — 장부 없이
    ctx.pos = (1, 100.0)
    check(F({"pos": "filled", "rule": "1차"}) == [None] * 5 and F({"pos": "sold"}) == [None] * 5, "장부 없으면 filled·sold 는 모름")
    for bad in ({"pos": "ret", "rule": "1차"}, {"pos": "filled", "rule": 3}):
        try:
            validate(bad)
            FAILS.append("잘못된 pos rule 통과 %r" % bad)
        except CondError:
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
            fs = series(node, full)
            for t in (30, 55, 89):
                pre = make_ctx(xs[:t + 1])
                ps = series(node, pre)
                check(same(ps[t], fs[t], 1e-9), "미래 참조: %s @%d" % (_op_of(node), t))


def t_tf():
    """봉(tf) — 엔진은 '적힌 tf 의 봉'만 읽는다(치환 없음). 최소 단위가 분이든 초든 같은 경로 — tf 단위로만 읽고
    창·lag 는 그 tf 봉 개수로 센다(COND_DSL 계약). 장중 조건은 asof 시점 값으로 '오늘 칸'에 접힌다(과거일은 모름).
    분봉 데이터가 없으면 모름(None). 혼합(장중 vs 일봉)은 각자 제 봉으로 읽고 비교한다."""
    import datetime as dt
    utc = dt.timezone.utc
    cal = ["20261001", "20261002"]
    dhist = {"X": [Candle(d, 100, 100, 100, 100, 1000) for d in cal]}
    # 문법: 1d · "<수><단위 s/m/h/d/w>" 는 받고, 그 밖·보조 키는 거부(허용 봉은 market.store.tf_seconds 한 곳).
    for b in ({"px": "close", "sym": "X", "tf": "5x"}, {"px": "close", "sym": "X", "tf": "m"},
              {"px": "close", "sym": "X", "offset": -10}):
        try:
            validate(b)
            FAILS.append("잘못된 tf/키 통과: %r" % b)
        except CondError:
            pass
    for tf in ("1d", "1m", "5m", "15m", "30m", "1h", "1s"):   # 어떤 tf 단위든 문법 통과(1d 도 분·초도)
        validate({"px": "close", "sym": "X", "tf": tf})

    # 분봉 데이터가 없으면 그 tf 조건은 모름(조용히 거짓 아님)
    ctx0 = Ctx(dhist, cal, "X", asof=dt.datetime(2026, 10, 2, 13, 20, tzinfo=utc))
    check(series({"px": "close", "sym": "X", "tf": "5m"}, ctx0) == [None, None], "분봉 데이터 없으면 5m 모름")

    # ★ 단위 무관 — 같은 식을 '분봉 원자'·'초봉 원자' 둘로 돌려 같은 결과(엔진은 봉 개수만 센다, 단위를 모름).
    #   close 10..21 을 5개씩 묶으면 5tf 봉 종가 = [14, 19, 21]. lag1 비교 → 오늘 칸만 참, 과거일 None(장중은 접힘).
    def run(atom, tf, asof):
        ctx = Ctx(dhist, cal, "X", asof=asof, atom={"X": atom})
        gt = {"gt": [{"px": "close", "sym": "X", "tf": tf}, {"lag": [{"px": "close", "sym": "X", "tf": tf}, 1]}]}
        return ctx._intraday_ctx(tf).px("X", "close"), series(gt, ctx)
    mins = [Candle("2026100213%02d" % m, 10 + m, 10 + m, 10 + m, 10 + m, 1) for m in range(12)]   # 13:00..13:11 (분)
    secs = [Candle("202610021300%02d" % s, 10 + s, 10 + s, 10 + s, 10 + s, 1) for s in range(12)]  # 13:00:00..11 (초)
    px_m, v_m = run(mins, "5m", dt.datetime(2026, 10, 2, 13, 11, tzinfo=utc))
    px_s, v_s = run(secs, "5s", dt.datetime(2026, 10, 2, 13, 0, 11, tzinfo=utc))
    check(px_m == [14, 19, 21], "5m px = resample(분봉) 종가 %r" % px_m)
    check(px_s == [14, 19, 21], "5s px = resample(초봉) 종가 — 같은 코드, 단위만 다름 %r" % px_s)
    check(v_m == [None, True] and v_s == [None, True], "lag 는 그 tf 봉 개수로 셈 + 장중은 오늘 칸에 접힘(과거 None)")

    # lag 가 '봉 개수'를 세는 증거(일수 아님): lag2 = 2봉 전(=14) 과 비교
    ctxs = Ctx(dhist, cal, "X", asof=dt.datetime(2026, 10, 2, 13, 0, 11, tzinfo=utc), atom={"X": secs})
    v2 = series({"gt": [{"px": "close", "sym": "X", "tf": "5s"}, {"lag": [{"px": "close", "sym": "X", "tf": "5s"}, 2]}]}, ctxs)
    check(v2 == [None, True], "lag2 = 2봉 전(14) — 봉 개수로 센다")

    # 혼합 tf — 장중 현재가(21) vs 일봉 종가(100): 각자 제 봉으로 읽고 비교, 장중 쪽이 오늘 칸에 접힌다
    vm = series({"gt": [{"px": "close", "sym": "X", "tf": "5s"}, {"px": "close", "sym": "X"}]}, ctxs)
    check(vm == [None, False], "혼합 tf: 장중 vs 일봉 — 각자 제 봉 읽고 비교 %r" % vm)

    try:
        validate({"observe": {"gt": [C, 1]}, "manual": "데이터 없음: x"})
        FAILS.append("지운 observe 노드가 문법을 통과")
    except CondError:
        pass


def t_atom_supply():
    """판단자 배선 — RuleSeries 가 atom(원자 봉)을 받으면 sub-day tf 게이트가 실제로 소비한다(안 주면 모름).
    공급 사슬(judge→Ctx)이 원자를 꿰는지 — 엔진은 verify_eval 봉(tf) 가 보고, 여기선 '판단자가 원자를 넘기나'를 본다."""
    import datetime as dt
    utc = dt.timezone.utc
    cal = ["20261001", "20261002"]
    hist = {"X": [Candle("20261001", 90, 90, 90, 90, 1000), Candle("20261002", 100, 100, 100, 100, 1000)]}
    atom = {"X": [Candle("2026100213%02d" % m, 10 + m, 10 + m, 10 + m, 10 + m, 1) for m in range(12)]}  # 종가 10..21 상승
    # 산다: 현재 5분봉 종가 > 직전 5분봉 (장중 상승) — sub-day tf 게이트
    tree = TreeGateway.of(synthetic(["X"],
        rule("장중상승", BUY, {"gt": [{"px": "close", "sym": "$self", "tf": "5m"},
                                      {"lag": [{"px": "close", "sym": "$self", "tf": "5m"}, 1]}]})))
    asof = dt.datetime(2026, 10, 2, 13, 11, tzinfo=utc)
    no = RuleSeries(tree, "X", hist, cal, asof=asof)                 # 원자 없음 → 모름
    yes = RuleSeries(tree, "X", hist, cal, asof=asof, atom=atom)     # 원자 공급 → 소비
    check(no.opt[BUY][-1] is None, "원자 안 주면 sub-day 게이트는 모름(None) %r" % no.opt[BUY][-1])
    check(yes.opt[BUY][-1] is True, "원자 주면 sub-day 게이트가 실제 소비(21>19=참) %r" % yes.opt[BUY][-1])

    # pos 수익률·현재가 = asof '지금값'(원자). 평단 100 보유 · 일봉 종가 100 · 원자 현재가 112.
    ph = {"X": [Candle("20261001", 100, 100, 100, 100, 1), Candle("20261002", 100, 100, 100, 100, 1)]}
    pa = {"X": [Candle("2026100213%02d" % m, 110 + m, 110 + m, 110 + m, 110 + m, 1) for m in range(3)]}  # 현재가 112
    aa = dt.datetime(2026, 10, 2, 13, 11, tzinfo=utc)
    check(same(series({"pos": "ret"}, Ctx(ph, cal, "X", pos=(0, 100.0), asof=aa, atom=pa))[-1], 12.0),
          "pos.ret 는 원자 현재가(112)로 — 어제 종가 아니라 지금값(장중 매도 조건)")
    check(same(series({"pos": "ret"}, Ctx(ph, cal, "X", pos=(0, 100.0), asof=aa))[-1], 0.0),
          "원자 없으면 일봉 종가(100)로 폴백 — 패리티")


def t_settled_mtf():
    """★ 혼합 tf·확정(settled) 규칙·일봉축 '마지막 확정봉'·look-ahead 0 — 이 덩어리의 최우선 correctness 증명(영구).

    1) 일봉축 '마지막 확정봉' 재해석(장중 asof): tf:1d 식의 평가 index 를 'asof 이하 마지막 확정 일봉'으로 당긴다.
       장중 asof 면 오늘 봉은 미확정이라 오늘 칸에도 '어제 확정값'이 나온다(None 아님) — 실전 '일봉 regime=어제값'.
       EOD/마감시각/장후 asof 면 오늘 봉까지 확정이라 항등(당김 없음, 기존과 동일). 마감 1분 전은 아직 미확정 → 어제값.
    2) look-ahead 0 (★확장·전수): 장중 asof 에서 tf:1d 잎·그 위 모든 파생값이 '오늘 미확정 봉 유무'와 무관하고,
       오늘 미확정 종가(999)가 어떤 일봉 파생값에도 절대 새지 않는다. 오늘 칸 값 == 어제 확정 칸 값(당겨왔으므로)도 전수.
    3) 캘린더 없음·asof None → 아무것도 안 당김(no-op, 일봉 파리티 보존).
    4) 혼합 tf 트리: tf:1d AND tf:5m 를 중첩해도 1d 잎만 일봉축으로 당기고 두 축이 섞인 식(all)은 당기지 않는다
       (per-leaf 스코프). 5m 잎은 모름(None)이라 all 은 모름.
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
    intraday = Ctx(full, cal, "X", asof=dt.datetime(2026, 10, 2, 13, 20, tzinfo=utc), session_close=sc)
    check(series(node1d, intraday) == [100.0, 100.0], "일봉축: 장중엔 오늘 칸도 어제 확정값(100)으로 당김")
    atclose = Ctx(full, cal, "X", asof=dt.datetime(2026, 10, 2, 20, 0, tzinfo=utc), session_close=sc)
    check(series(node1d, atclose) == [100.0, 200.0], "settled: 마감 == asof 는 확정(오늘 봉 그대로, 당김 없음)")
    pre = Ctx(full, cal, "X", asof=dt.datetime(2026, 10, 2, 19, 59, tzinfo=utc), session_close=sc)
    check(series(node1d, pre) == [100.0, 100.0], "일봉축: 마감 1분 전은 아직 미확정 → 어제값으로 당김")
    post = Ctx(full, cal, "X", asof=dt.datetime(2026, 10, 2, 21, 0, tzinfo=utc), session_close=sc)
    check(series(node1d, post) == [100.0, 200.0], "settled: 장 끝난 뒤는 확정(항등)")

    # 2) look-ahead 0 (★확장·전수) — 장중 asof 에서 오늘 칸이 '어제 확정값'으로 당겨지고, 미확정 종가 999 는 안 샘.
    with_today = hist_of([100.0, 999.0])    # 오늘 봉 있음(미확정, 종가 999)
    cal_wo = ["20261001"]
    without = {"X": [Candle("20261001", 100.0, 100.0, 100.0, 100.0, 1000)]}   # 오늘 봉 없음(현재 feed 모습)
    derived = [node1d, AVG(node1d, 1), {"highest": [node1d, 1]}, {"lag": [node1d, 0]},
               {"gt": [node1d, 50]}, STREAK({"gt": [node1d, 50]})]
    for h in (10, 13, 15, 19, 20, 21):       # 장중~장후 여러 asof
        a = dt.datetime(2026, 10, 2, h, 0, tzinfo=utc)
        cw = Ctx(with_today, cal, "X", asof=a, session_close=sc)
        cwo = Ctx(without, cal_wo, "X", asof=a, session_close=sc)
        for node in derived:
            vw = series(node, cw)
            vwo = series(node, cwo)
            # 마지막 확정일(10/01, index 0) 값이 오늘 봉 유무와 무관해야 한다
            check(same(vw[0], vwo[0], 1e-9),
                  "look-ahead: %s @10/01 이 오늘 봉 유무에 흔들림(asof %dh) %r≠%r"
                  % (_op_of(node), h, vw[0], vwo[0]))
            # 장중(마감 전) asof 에선 미확정 종가 999 가 어떤 일봉 파생값에도 새어들면 안 된다 — look-ahead 0.
            #   (마감 == asof·장후(h>=20)엔 오늘 봉이 확정이라 999 는 '확정된 오늘 종가'로 정당히 쓰인다.)
            if h < 20:
                check(all(not same(x, 999.0, 1e-9) for x in vw if x is not None),
                      "look-ahead: 미확정 종가 999 가 샘(asof %dh) %r" % (h, vw))
                # ★확장: 장중엔 오늘 칸(index 1)이 '어제 확정 칸(index 0)'과 같아야 한다(일봉축으로 당겨왔으므로).
                check(same(vw[1], vw[0], 1e-9),
                      "일봉축 확장: 장중 오늘 칸 %s 가 어제 확정값과 달라짐(asof %dh) %r" % (_op_of(node), h, vw))

    # 3) no-op — 캘린더 없음·asof None 이면 장중이라도 아무것도 안 가린다(일봉 파리티 보존)
    a = dt.datetime(2026, 10, 2, 13, 20, tzinfo=utc)
    check(series(node1d, Ctx(full, cal, "X", asof=a, session_close={})) == [100.0, 200.0],
          "no-op: 캘린더 없으면 안 가림(캘린더 없다고 일봉 전부 지우지 않는다)")
    check(series(node1d, Ctx(full, cal, "X", asof=None, session_close=sc)) == [100.0, 200.0],
          "no-op: asof None(라이브 지금)은 안 가림")

    # 4) 혼합 tf 트리 — tf:1d AND tf:5m 를 중첩. 1d 잎만 일봉축으로 당기고(per-leaf), 섞인 all 은 당기지 않는다.
    #    c5 asof = 10/02 13:34(장중). 1d 잎은 어제(10/01) 확정 100 으로 당겨져 오늘 칸도 참(100>50). 5m 잎은 모름 → all 모름.
    c5 = Ctx({"X": [Candle(d, 100, 100, 100, 100, 1000) for d in cal]}, cal, "X",
                  asof=dt.datetime(2026, 10, 2, 13, 34, tzinfo=utc), session_close=sc)
    mixed = {"all": [{"gt": [{"px": "close", "sym": "X", "tf": "1d"}, 50]},      # 일봉축 어제 확정 100 > 50 → 참
                     {"lt": [{"px": "close", "sym": "X", "tf": "5m"}, 50]}]}     # 5분봉 = 모름
    mv = series(mixed, c5)
    check(mv == [None, None], "혼합 tf: 5분봉 잎이 모름이면 all 도 모름(조용히 거짓 아님) %r" % mv)
    leaf1d = series({"px": "close", "sym": "X", "tf": "1d"}, c5)
    leaf5m = series({"px": "close", "sym": "X", "tf": "5m"}, c5)
    check(leaf1d == [100.0, 100.0], "per-leaf: 1d 잎은 장중에도 어제 확정값으로 당김 %r" % leaf1d)
    check(leaf5m == [None, None], "per-leaf: 5m 잎은 모름 %r" % leaf5m)


def t_grade():
    """비중(산다 qty cash) — 수동 때문에 모르면 범위(화면 설명 구조는 web/verify_view.py)."""
    xs = [100.0] * 30 + [130.0]
    cal = ["2022%04d" % i for i in range(len(xs))]
    hist = {"X": [Candle(d, c, c, c, c, 1000) for d, c in zip(cal, xs)]}
    tree = TreeGateway.of(synthetic(["X"],
                                    rule("비중", BUY, None, ("cash", {"case": [[{"manual": "모드"}, 14]], "else": 34}))))
    pe = RuleSeries(tree, "X", hist, cal)
    w, alt = pe.weight_of(len(xs) - 1)
    check(w is None and alt == [14.0, 34.0], "수동 모드 비중은 모름 + 범위 %r %r" % (w, alt))


def t_answers():
    """사람이 답한 수동(Ctx answers) — 열쇠 = 상품 + "|" + (문장 | "?" 식). 답은 manual_as 보다 먼저,
    not 아래에서도 잎 값 그대로(not 이 뒤집을 뿐), 없는 열쇠는 manual_as, answers=None 이면 옛 동작 그대로."""
    cal = ["2022%04d" % i for i in range(3)]
    hist = {p: [Candle(d, 100, 100, 100, 100, 1000) for d in cal] for p in ("A", "B", "M")}
    m = {"manual": "실적 좋음"}
    unk = {"ge": [{"px": "close", "sym": "M"}, "?"], "label": "M 높음"}

    def v(node, ma, answers):
        return series(node, Ctx(hist, cal, "A", manual_as=ma, answers=answers))[0]
    k = answer_key
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
    tree = TreeGateway.of(synthetic(["A"], rule("실적", BUY, {"all": [m]})))
    got = [RuleSeries(tree, "A", hist, cal, answers=a).grade_key(2)
           for a in (None, {"A|실적 좋음": True}, {"A|실적 좋음": False})]
    check(got == ["confirm", "buy", "wait"], "등급까지 답으로 풀린다(확인 대기 → 산다·관망) %r" % got)


# ------------------------------------------------------------------ 6. 데이터 완전성 가드(워밍업 부족 → 불완전)
def t_warmup_guard():
    """★ 실제 발견된 버그 방지(영구): 시세가 rate-limit 로 잘려(워밍업 부족) 와도 엔진이 그 불완전 데이터로
    조용히 ✅/⛔ 확신을 내면 모르고 매매하게 된다. 가드는 트리가 쓰는 가장 긴 lookback(워밍업)을 트리에서
    직접 뽑아, 그보다 확정 봉이 적은 초기 구간의 1d 신호를 '불완전 데이터(❔)'로 표면화한다.

    확인:
      1) 필요 워밍업을 트리에서 바르게 계산한다(창 n-1·lag k 가 가장 깊은 사슬로 누적되고,
         barssince 류는 AtLeast/None 으로 스스로 불확실을 드러내므로 워밍업에 넣지 않는다).
      2) 워밍업을 일부러 잘라낸(필요보다 적은 봉) 입력 → 그 초기 구간은 incomplete=True 이고 grade_key 가 ❔.
      3) 워밍업이 충분한 구간 → incomplete=False, 가드 끼기 전과 등급이 '그대로'(오탐 0).
    """

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
        got = warmup_of(node)
        check(got == exp, "warmup_of %r → %d (기대 %d)" % (node, got, exp))

    # 트리 상품 워밍업 = 등급을 내는 갈래(산다·안 산다) 전체의 최댓값.
    tree = TreeGateway.of(synthetic(["P"], rule("신고가", BUY, {"gt": [C, {"highest": [C, 60]}]}),
                                    rule("10일선 아래", BLOCK, {"lt": [C, AVG(C, 10)]})))
    check(tree.warmup("P") == 59, "warmup = 등급 갈래 최댓값(highest60 → 59)")

    # 2) 워밍업 자르기 — 필요 워밍업 60(=highest60)짜리 트리. 충분한 봉 vs 모자란 봉.
    W = tree.warmup("P")                                          # 59
    need = W + 1                                                  # 첫 완전 봉이 서려면 확정 봉이 이만큼
    rng = random.Random(7)
    xs = [x if x is not None else 100.0 for x in rand_series(rng, need + 40, miss=0)]
    cal = ["2024%04d" % i for i in range(len(xs))]
    hist = {"P": [Candle(d, c, c, c, c, 1000) for d, c in zip(cal, xs)]}
    pe = RuleSeries(tree, "P", hist, cal)
    # 초기 W 개 봉(index 0..W-1)은 확정 봉이 모자라 incomplete → grade_key 가 ❔(unknown).
    check(all(pe.incomplete(i) for i in range(W)), "워밍업 부족 구간(0..%d) 전부 incomplete" % (W - 1))
    check(all(pe.grade_key(i) == "unknown" for i in range(W)),
          "워밍업 부족 구간 1d 등급은 ❔(판정 불가)여야 — 조용히 ✅/⛔ 안 냄")
    # 워밍업이 충분해진 뒤(index >= W)는 incomplete=False — 신호를 낸다.
    check(not any(pe.incomplete(i) for i in range(W, len(xs))), "워밍업 채운 뒤는 incomplete 아님(오탐 0)")

    # 3) 오탐 0(가드 불변식) — 가드가 끼기 전 '원시 등급'(워밍업 무시)과, 워밍업 충분한 구간의 등급이 같아야.
    #    _raw_grade = incomplete 검사를 건너뛴 등급. 충분 구간에서 두 값이 완전히 일치하면 가드는 정상 데이터를
    #    절대 건드리지 않는다는 뜻(파리티 오탐 0 의 단위테스트판).
    def raw_grade(pe_, i):
        views = {"opt": pe_.opt, "pes": pe_.pes}
        for rule in GRADE_RULES["rules"]:
            if all(views[rule["view"]][sec][i] is want for sec, want in rule["when"].items()):
                return rule["key"]
        return GRADE_RULES["default"]
    bad = [i for i in range(W, len(xs)) if pe.grade_key(i) != raw_grade(pe, i)]
    check(not bad, "워밍업 충분 구간 등급 == 가드 없는 원시 등급(오탐 0) @%r" % bad[:3])

    # 트렁케이트 비교: 같은 꼬리 구간을 '긴 이력'과 '짧게 잘린 이력'으로 각각 판정 — 긴 쪽은 신호를 내지만
    # 짧게 잘린 쪽은 워밍업이 모자란 꼬리 봉을 ❔ 로 뺀다(바로 그 '251봉 vs 594봉' 버그를 잡는 경로).
    short = {"P": [Candle(d, c, c, c, c, 1000) for d, c in zip(cal, xs)][-30:]}   # 꼬리 30봉만(워밍업 없음)
    short_cal = [c.date for c in short["P"]]
    pe_short = RuleSeries(tree, "P", short, short_cal)
    check(all(pe_short.incomplete(i) for i in range(len(short_cal))),
          "짧게 잘린 이력(워밍업 없음)은 전 구간 불완전 — 긴 이력이면 신호 낼 꼬리까지 ❔ 로 뺀다")
    last = len(cal) - 1
    check(not pe.incomplete(last) and pe_short.incomplete(len(short_cal) - 1),
          "같은 마지막 날: 긴 이력=완전(신호 OK) · 잘린 이력=불완전(판정 보류) — 조용한 오판 차단")


# ------------------------------------------------------------------ 7. 표현력 회귀(이번 버그 유형)
def t_regress():
    # (a) '20일선 회복 후 2거래일 유지' — 1일만 위면 거짓, 회복일+2일이면 참
    hold = {"ge": [STREAK({"gt": [C, AVG(C, 20)]}), 3]}
    xs = [100.0] * 25 + [90.0] * 5 + [110.0]
    check(series(hold, make_ctx(xs))[-1] is False, "2일 유지: 1일만 위인데 참")
    check(series(hold, make_ctx(xs + [111.0, 112.0]))[-1] is True, "2일 유지: 3일 위인데 거짓")
    # (b) '전고점 돌파 후 돌파선 위 유지' — 돌파선 고정. 105 돌파 후 104·104.5 는 유지
    prior = {"highest": [{"lag": [C, 1]}, 20]}
    brk = {"gt": [C, prior]}
    level = {"valuewhen": [brk, prior]}
    held_ok = {"gt": [{"minsince": [brk, C]}, level]}        # 돌파 이후 최저 종가가 돌파선 위
    days = {"add": [{"barssince": brk}, 1]}                  # 돌파일 포함 경과일
    xs = [100.0] * 21 + [105.0, 104.0, 104.5]
    ctx = make_ctx(xs)
    check(series(held_ok, ctx)[-1] is True and same(series(days, ctx)[-1], 3.0),
          "돌파 유지: 돌파선(100) 고정 → 104·104.5 는 유지 3일")
    check(series(held_ok, make_ctx(xs + [99.0]))[-1] is False, "돌파 유지: 돌파선 아래 마감이면 실패")
    # (c) '짧은 눌림(2일) 끝 반등' — 눌림 일수에 반등일을 넣지 않는다
    hi = {"barssince": {"ge": [C, {"highest": [C, 20]}]}}
    rebound = {"gt": [C, {"lag": [C, 1]}]}
    pull2 = {"all": [rebound, {"ge": [{"lag": [hi, 1]}, 2]}, {"le": [{"lag": [hi, 1]}, 2]}]}
    xs = [float(100 + i) for i in range(25)] + [122.0, 121.0, 122.5]   # 고점 124 → 2일 하락 → 반등
    check(series(pull2, make_ctx(xs))[-1] is True, "눌림 2일 후 반등: 참이어야")
    xs1 = [float(100 + i) for i in range(25)] + [122.0, 123.0]          # 1일 하락 → 반등
    check(series(pull2, make_ctx(xs1))[-1] is False, "눌림 1일 후 반등: 거짓이어야")
    # (d) 판정 불가는 위로 전파 — 4개 중 2개에서 2개가 모름이면 결과도 모름일 수 있다
    four = {"atleast": 2, "of": [{"gt": [C, 0]}, {"lt": [C, 0]}, {"manual": "a"}, {"manual": "b"}]}
    check(series(four, make_ctx([1.0]))[0] is None, "4개 중 2개(1참·1거짓·2모름) → 모름")


def t_memo():
    """값 기억·공유 — 판때기 노드(gateway.bind)의 값 기억과 공유 값 기억(Ctx shared)이 값을 바꾸지 않는다."""
    import datetime as dt
    utc = dt.timezone.utc
    cal = ["2026100%d" % d for d in range(1, 8)]
    xs = [100.0, 101.0, 100.0, 102.0, 103.0, 101.0, 104.0]
    hist = {s: [Candle(d, c * k, c * k, c * k, c * k, 1000) for d, c in zip(cal, xs)]
            for s, k in (("A", 1.0), ("B", 2.0), ("N", 3.0))}
    sc = {s: {d: dt.datetime(2026, 10, int(d[-1]), 20, 0, tzinfo=utc) for d in cal} for s in ("A", "B", "N")}
    intraday = dt.datetime(2026, 10, 7, 13, 0, tzinfo=utc)
    up = lambda sym: {"gt": [{"px": "close", "sym": sym}, {"lag": [{"px": "close", "sym": sym}, 1]}]}
    # 노드 레벨 on(OFF) — 대상 밖 상품에선 '항상 참'이면서 부모의 일봉축 판정은 걸러내기 전과 같다(수동을 품었으면 안 당김)
    ctx = lambda prod, **kw: Ctx(hist, cal, prod, asof=intraday, session_close=sc, **kw)
    off = series({"barssince": {"all": [up("$self"), {"manual": "m", "on": ["Z"]}]}}, ctx("A"))
    ref = series({"barssince": {"all": [up("$self"), {"manual": "m"}]}}, ctx("A", manual_as=True))
    check(off == ref, "노드 레벨 on: 대상 밖 = 항상 참 + 일봉축은 걸러내기 전 식 기준 %r ≠ %r" % (off, ref))
    check(series({"manual": "m", "on": ["Z"]}, ctx("A")) == [True] * len(cal), "노드 레벨 on: 대상 밖 노드 = 항상 참")
    # $self 는 상품마다 다른 노드 — 같은 공유 기억이어도 값이 섞이지 않는다
    shared = {}
    ca, cb = Ctx(hist, cal, "A", shared=shared), Ctx(hist, cal, "B", shared=shared)
    self_px = {"px": "close", "sym": "$self"}
    check(series(self_px, ca)[0] == 100.0 and series(self_px, cb)[0] == 200.0, "$self 는 문맥의 상품으로 묶인다")
    # 수동·pos 없는 노드(N 상승)는 공유 기억으로 한 번만 계산 — 두 상품이 같은 시계열 객체를 받는다
    n0 = len(shared)
    va = series(up("N"), ca)
    check(series(dict(up("N"), label="딴 이름"), cb) is va and len(shared) > n0, "같은 식은 상품끼리 한 번 계산(공유)")
    # 수동은 상품마다(답 열쇠가 상품별) — 공유 기억에 들어가지 않는다
    ans = {answer_key({"manual": "m"}, "A"): True}
    sa = Ctx(hist, cal, "A", shared=shared, answers=ans)
    sb = Ctx(hist, cal, "B", shared=shared, answers=ans)
    check(series({"manual": "m"}, sa)[0] is True and series({"manual": "m"}, sb)[0] is None,
          "수동 답은 상품마다 — 공유되지 않는다")
    # pos 는 그 문맥의 보유분 — 공유 기억에 들어가지 않는다
    pa = Ctx(hist, cal, "A", pos=(0, 100.0), shared=shared)
    pb = Ctx(hist, cal, "A", pos=(0, 50.0), shared=shared)
    check(same(series({"pos": "ret"}, pa)[1], 1.0) and same(series({"pos": "ret"}, pb)[1], 102.0), "pos 는 문맥마다 — 공유되지 않는다")
    # 확정 경계 범위(scope) 밖 심볼을 읽는 식은 공유 기억을 쓰지 않는다(그 문맥은 그 심볼의 경계를 모른다)
    scoped = Ctx(hist, cal, "A", shared={}, scope=frozenset({"A"}))
    series(up("N"), scoped)
    check(not scoped.shared, "범위 밖 심볼 식은 공유 기억에 넣지 않는다")


def main():
    rng = random.Random(20261001)     # 같은 씨앗 하나를 순서대로 나눠 쓴다(순서 = 옛 검사와 같음)
    for name, fn in (("수치 연산", lambda: t_numeric(rng)), ("3값 논리", t_logic),
                     ("시간 연산", lambda: t_time(rng)), ("하한", t_bounds), ("포지션", lambda: t_pos(rng)),
                     ("인과성", lambda: t_causal(rng)), ("봉(tf)", t_tf),
                     ("판단자 원자 공급", t_atom_supply),
                     ("혼합 tf·확정봉·look-ahead 0", t_settled_mtf),
                     ("등급·금액", t_grade), ("데이터 완전성 가드(워밍업)", t_warmup_guard),
                     ("표현력 회귀", t_regress),
                     ("수동 답(answers)", t_answers), ("값 기억·공유", t_memo)):
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
        print("계산기 검사 실패 %d건 — 정지" % len(FAILS))
        return 1
    print("계산기 검사 통과 — 수치·3값·시간·인과·봉·등급·회귀·수동 답·값 기억")
    return 0


if __name__ == "__main__":
    sys.exit(main())
