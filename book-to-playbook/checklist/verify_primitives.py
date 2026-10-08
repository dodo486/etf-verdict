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
  3. 시간 연산(count·streak·barssince·valuewhen·across) — 단순 반복 구현과 대조
  4. 인과성 — 미래 데이터를 잘라도 과거 날짜 값이 같아야 한다(미래 참조 금지)
  5. 문법 — 모르는 키·인자 수·빈 구역은 거부, 올바른 트리는 통과
  6. 표현력 회귀 — 이번에 발견된 버그 유형을 트리로 적어 원문 뜻대로 나오는지
  7. 트리 출입구(TreeGateway) 계약 — 판정·백테스트·검사기가 트리에 묻는 질문의 답 모양
  8. 사람이 답한 수동(Ctx answers) — 답 열쇠 규칙·극성·공통 정의·등급까지(서버 권위의 바탕)
  (체결 워크·실전 경로는 trading/verify_trading.py, 화면 설명 구조는 web/verify_view.py 가 본다)

사용: python -m checklist.verify_primitives   (실패 있으면 exit 1)
"""
import itertools
import json
import math
import random
import sys
from collections import namedtuple

import pandas as pd

from shared import paths  # noqa: F401  (UTF-8 출력)
from checklist import cond
from checklist.tree_gateway import TreeGateway, empty_product, synthetic   # 합성 트리는 출입구로 만든다(verify_code 명시 예외)

Candle = namedtuple("Candle", "date open high low close volume")
FAILS = []


def check(ok, what):
    if not ok:
        FAILS.append(what)


def same(a, b, tol=1e-9):
    if isinstance(a, cond.AtLeast) != isinstance(b, cond.AtLeast):
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
    return cond.Ctx(hist, cal, "X", manual_as=manual_as)


def rand_series(rng, n, miss=0.05):
    x, out = 100.0, []
    for _ in range(n):
        x *= 1 + rng.gauss(0, 0.02)
        out.append(None if rng.random() < miss else round(x, 4))
    return out


C = {"px": "close"}


# ------------------------------------------------------------------ 1. 수치 연산
def t_numeric(rng):
    for trial in range(30):
        xs = rand_series(rng, 120)
        ctx = make_ctx(xs)
        ps = pd.Series([float("nan") if v is None else v for v in xs])
        for n in (1, 3, 5, 20):
            refs = {
                "ma": ps.rolling(n, min_periods=n).mean(),
                "sum": ps.rolling(n, min_periods=n).sum(),
                "highest": ps.rolling(n, min_periods=n).max(),
                "lowest": ps.rolling(n, min_periods=n).min(),
                "stdev": ps.rolling(n, min_periods=n).std(ddof=0),
            }
            for op, ref in refs.items():
                got = cond.series({op: [C, n]}, ctx)
                bad = [i for i in range(len(xs)) if not same(got[i], ref[i], 1e-7)]
                check(not bad, "%s(%d) pandas 와 불일치 @%s (trial %d)" % (op, n, bad[:3], trial))
        for k in (0, 1, 5):
            ref = ps.shift(k)
            got = cond.series({"lag": [C, k]}, ctx)
            check(all(same(got[i], ref[i]) for i in range(len(xs))), "lag(%d) 불일치" % k)
            if k:
                ref = (ps / ps.shift(k) - 1) * 100
                got = cond.series({"pct": [C, k]}, ctx)
                check(all(same(got[i], ref[i], 1e-7) for i in range(len(xs))), "pct(%d) 불일치" % k)
        a = cond.series({"sub": [C, {"lag": [C, 1]}]}, ctx)
        ref = ps - ps.shift(1)
        check(all(same(a[i], ref[i], 1e-7) for i in range(len(xs))), "sub 불일치")
        dz = cond.series({"div": [C, 0]}, ctx)
        check(all(v is None for v in dz), "div 0 은 None 이어야 한다")
        prev = ps.shift(1)
        for op, ref in (("max", pd.concat([ps, prev], axis=1).max(axis=1, skipna=False)),
                        ("min", pd.concat([ps, prev], axis=1).min(axis=1, skipna=False))):
            got = cond.series({op: [C, {"lag": [C, 1]}]}, ctx)
            check(all(same(got[i], ref[i], 1e-12) for i in range(len(xs))), "%s 불일치 (trial %d)" % (op, trial))
        ref = (ps - prev).abs()
        got = cond.series({"abs": {"sub": [C, {"lag": [C, 1]}]}}, ctx)
        check(all(same(got[i], ref[i], 1e-7) for i in range(len(xs))), "abs 불일치 (trial %d)" % trial)
    # ema / rsi — 알려진 성질
    ctx = make_ctx([50.0] * 40)
    e = cond.series({"ema": [C, 10]}, ctx)
    check(all(same(v, 50.0) for v in e[9:]) and all(v is None for v in e[:9]), "상수열 ema = 상수")
    up = make_ctx([float(i) for i in range(1, 60)])
    r = cond.series({"rsi": [C, 14]}, up)
    check(r[13] is None and same(r[14], 100.0) and same(r[-1], 100.0), "단조증가 rsi = 100")
    alt = make_ctx([100 + (1 if i % 2 else -1) for i in range(80)])
    r = cond.series({"rsi": [C, 14]}, alt)
    check(40 < r[-1] < 60, "등락 교대 rsi ≈ 50 (got %r)" % r[-1])
    # ema 독립 계산(SMA 시드 + 2/(n+1))
    xs = rand_series(rng, 60, miss=0)
    ctx = make_ctx(xs)
    got = cond.series({"ema": [C, 5]}, ctx)
    ref, k = [None] * 4 + [sum(xs[:5]) / 5], 2 / 6
    for x in xs[5:]:
        ref.append(x * k + ref[-1] * (1 - k))
    check(all(same(a, b, 1e-9) for a, b in zip(got, ref)), "ema 독립계산과 불일치")


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
            got = cond.series({"all": cols}, ctx)[0]
            check(got == truth(all, xs) or (got is None and truth(all, xs) is None), "all%r" % (xs,))
            got = cond.series({"any": cols}, ctx)[0]
            check(got == truth(any, xs) or (got is None and truth(any, xs) is None), "any%r" % (xs,))
            for n in range(1, 4):
                got = cond.series({"atleast": n, "of": cols}, ctx)[0]
                exp = truth(lambda ys: sum(ys) >= n, xs)
                check(got is exp or got == exp, "atleast %d %r: %r≠%r" % (n, xs, got, exp))
    for x in vals:
        node = {"gt": [1 if x else -1, 0]} if x is not None else {"manual": "모름"}
        got = cond.series({"not": node}, make_ctx([1.0]))[0]
        check(got == (None if x is None else not x), "not %r" % x)
    # manual 은 manual_as 를 따른다
    for m in (True, False, None):
        got = cond.series({"manual": "장중"}, make_ctx([1.0], manual_as=m))[0]
        check(got is m, "manual_as=%r" % m)
    # 극성: not 아래 수동은 반대 가정 — manual_as=True(유리하게 풀림)면 '겹치면 쉼'은 참(쉴 이유 없음)
    rest = {"not": {"all": [{"gt": [1, 0]}, {"manual": "달러 강세"}]}}
    check(cond.series(rest, make_ctx([1.0], manual_as=True))[0] is True, "not 아래 수동: 낙관이면 참")
    check(cond.series(rest, make_ctx([1.0], manual_as=False))[0] is False, "not 아래 수동: 비관이면 거짓")
    dbl = {"not": {"not": {"manual": "x"}}}
    for m in (True, False):
        check(cond.series(dbl, make_ctx([1.0], manual_as=m))[0] is m, "not not 수동 = manual_as")
    # case — 위에서부터 처음 참인 갈래. 앞 갈래가 모름이면 결과도 모름(뒤로 넘어가지 않는다)
    for c1, c2 in itertools.product(vals, repeat=2):
        node = {"case": [[{"gt": [1 if c1 else -1, 0]} if c1 is not None else {"manual": "a"}, 10],
                         [{"gt": [1 if c2 else -1, 0]} if c2 is not None else {"manual": "b"}, 20]], "else": 30}
        got = cond.series(node, make_ctx([1.0]))[0]
        exp = 10 if c1 else (None if c1 is None else (20 if c2 else (None if c2 is None else 30)))
        check(same(got, None if exp is None else float(exp)), "case %r %r → %r (기대 %r)" % (c1, c2, got, exp))
    # 조건 → 숫자(상승일 1, 아니면 0) 의 합 = count 와 같아야 한다
    xs = [100.0, 101.0, 100.0, 102.0, 103.0, 101.0, 104.0]
    up = {"gt": [C, {"lag": [C, 1]}]}
    s1 = cond.series({"sum": [{"case": [[up, 1]], "else": 0}, 5]}, make_ctx(xs))
    s2 = cond.series({"count": [up, 5]}, make_ctx(xs))
    check(all(same(a, b) for a, b in zip(s1, s2)), "sum(case) = count")


# ------------------------------------------------------------------ 3. 시간 연산
def t_time(rng):
    for trial in range(40):
        bits = [rng.choice([True, False, False, None if rng.random() < 0.1 else True])
                for _ in range(60)]
        xs = [1.0 if b else (-1.0 if b is False else None) for b in bits]
        ctx = make_ctx(xs)
        c = {"gt": [C, 0]}
        for n in (1, 3, 7):
            got = cond.series({"count": [c, n]}, ctx)
            for i in range(60):
                w = bits[i - n + 1:i + 1] if i - n + 1 >= 0 else None
                exp = None if (w is None or None in w) else float(sum(w))
                check(same(got[i], exp), "count(%d)@%d %r≠%r" % (n, i, got[i], exp))
        got = cond.series({"streak": c}, ctx)
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
                exp = cond.AtLeast(cnt)       # 모르는 날·데이터 시작에 닿음 → 최소 cnt
            check(same(got[i], exp), "streak@%d %r≠%r" % (i, got[i], exp))
        got = cond.series({"barssince": c}, ctx)
        vw = cond.series({"valuewhen": [c, {"lag": [C, 0]}]}, ctx)
        val = [float(v) for v in range(60)]           # 결측 없는 값열(위치 = 값)
        vctx = make_ctx(xs, extra={"V": val})
        V = {"px": "close", "sym": "V"}
        mn = cond.series({"minsince": [c, V]}, vctx)
        mx = cond.series({"maxsince": [c, V]}, vctx)
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
                exp = cond.AtLeast(i - stop)      # 그 사이 참 없음 → 최소 i-stop 거래일
            check(same(got[i], exp), "barssince@%d" % i)
            check(same(vw[i], ev), "valuewhen@%d" % i)
            check(same(mn[i], emn) and same(mx[i], emx), "min/maxsince@%d" % i)
    # across
    ctx = make_ctx([1.0, 1.0], extra={"A": [1.0, 2.0], "B": [3.0, 1.0], "D": [None, 5.0]})
    up = {"gt": [{"px": "close", "sym": "$s"}, {"lag": [{"px": "close", "sym": "$s"}, 1]}]}
    got = cond.series({"across": {"syms": ["A", "B"], "cond": up}}, ctx)
    check(got == [None, 1.0], "across A·B 상승 수 %r" % got)
    got = cond.series({"across": {"syms": ["A", "D"], "cond": up}}, ctx)
    check(got == [None, None], "across 결측 종목 → None %r" % got)


def t_bounds():
    """하한 비교의 정답: 참값 v 가 하한 a 이상 아무 정수일 때 결과가 하나로 정해지면 그 값, 갈리면 None."""
    for a in range(0, 6):
        for b in range(0, 8):
            for op, f in (("gt", lambda v: v > b), ("ge", lambda v: v >= b),
                          ("lt", lambda v: v < b), ("le", lambda v: v <= b)):
                outs = {f(v) for v in range(a, a + 20)}
                exp = outs.pop() if len(outs) == 1 else None
                got = cond._cmp(op, cond.AtLeast(a), float(b))
                check(got == exp and (got is None) == (exp is None), "하한 %s(≥%d, %d)" % (op, a, b))
                # 좌우를 바꾼 비교도 같아야 한다: b op' AtLeast
                mirror = {"gt": "lt", "ge": "le", "lt": "gt", "le": "ge"}[op]
                got2 = cond._cmp(mirror, float(b), cond.AtLeast(a))
                check(got2 == exp and (got2 is None) == (exp is None), "하한 대칭 %s" % op)
    # 실제 쓰임: 데이터 시작부터 20일선 위(정확한 길이 모름)라도 '3일 이상'은 참
    xs = [100.0 + i for i in range(40)]
    up = {"gt": [C, {"ma": [C, 20]}]}
    check(cond.series({"ge": [{"streak": up}, 3]}, make_ctx(xs))[-1] is True, "긴 상승 streak≥3 = 참")
    check(cond.series({"lt": [{"streak": up}, 3]}, make_ctx(xs))[-1] is False, "긴 상승 streak<3 = 거짓")
    check(cond.series({"ge": [{"streak": up}, 30]}, make_ctx(xs))[-1] is None, "streak≥30 은 모름(21일만 확인)")
    check(isinstance(cond.series({"add": [{"streak": up}, 1]}, make_ctx(xs))[-1], cond.AtLeast), "하한+1 = 하한")
    check(cond.series({"ma": [{"streak": up}, 2]}, make_ctx(xs))[-1] is None, "하한의 이동평균 = 모름")


def t_pos(rng):
    """포지션 값(ret·days·maxret·minret) — 단순 반복 구현과 대조, 진입 전은 None, 미래 무관."""
    for trial in range(20):
        xs = [x if x is not None else 100.0 for x in rand_series(rng, 60, miss=0)]
        e = rng.randrange(5, 50)
        px = xs[e] * (1 + rng.uniform(-0.01, 0.01))
        ctx = make_ctx(xs)
        ctx.pos = (e, px)
        got = {f: cond.series({"pos": f}, ctx) for f in cond.POS_FIELDS}
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
            check(same(cond.series({"pos": "maxret"}, pre)[44], got["maxret"][44], 1e-9), "pos 미래 참조")
    # 평균 매입가가 날짜별로 바뀌는 경우(분할 매수) — ret 은 그날의 평균 매입가 기준
    xs = [100.0, 100.0, 110.0, 120.0, 90.0]
    ctx = make_ctx(xs)
    ctx.pos = (1, [None, 100.0, 100.0, 105.0, 105.0])
    got = cond.series({"pos": "ret"}, ctx)
    check(got[0] is None and same(got[2], 10.0) and same(got[3], (120 / 105 - 1) * 100)
          and same(got[4], (90 / 105 - 1) * 100), "pos.ret 평균 매입가 목록 %r" % got)
    # pos 는 매수 구역에서 금지, 매도 규칙 형식 검사
    bad = synthetic({"X": empty_product(entry={"gt": [{"pos": "ret"}, 0]})})
    try:
        TreeGateway.of(bad)
        FAILS.append("entry 에 pos 가 통과")
    except cond.CondError:
        pass
    for ex in ([{"label": "x", "when": {"gt": [{"pos": "ret"}, 1]}, "sell": 0.3}],
               [{"label": "x", "when": {"gt": [{"pos": "ret"}, 1]}, "sell": {"initial": 1.5}}],
               [{"when": {"gt": [{"pos": "ret"}, 1]}, "sell": "all"}],
               [{"label": "x", "when": {"gt": [{"pos": "ret"}, 1]}, "sell": "all", "stop": 1}]):
        try:
            TreeGateway.of(synthetic({"X": empty_product(exit=ex)}))
            FAILS.append("잘못된 매도 규칙 통과: %r" % ex)
        except cond.CondError:
            pass
    try:
        TreeGateway.of(synthetic({"X": empty_product(
            exit=[{"label": "축소", "when": {"gt": [{"pos": "ret"}, 1]}, "sell": {"remaining": None}}])}))
    except cond.CondError as e:
        FAILS.append("매도 비율 null(저자 미명시) 거부: %s" % e)


# ------------------------------------------------------------------ 4. 인과성
CAUSAL_NODES = [
    {"ma": [C, 5]}, {"ema": [C, 5]}, {"rsi": [C, 5]}, {"stdev": [C, 5]},
    {"highest": [C, 10]}, {"pct": [C, 3]}, {"lag": [C, 2]},
    {"count": [{"gt": [C, {"lag": [C, 1]}]}, 5]},
    {"streak": {"gt": [C, {"ma": [C, 5]}]}},
    {"barssince": {"ge": [C, {"highest": [C, 10]}]}},
    {"valuewhen": [{"gt": [C, {"highest": [{"lag": [C, 1]}, 10]}]}, {"highest": [{"lag": [C, 1]}, 10]}]},
    {"minsince": [{"gt": [C, {"highest": [{"lag": [C, 1]}, 10]}]}, C]},
    {"atleast": 2, "of": [{"gt": [C, 100]}, {"lt": [{"pct": [C, 1]}, 0]}, {"gt": [C, {"ma": [C, 3]}]}]},
    {"max": [C, {"ma": [C, 5]}]}, {"abs": {"pct": [C, 1]}},
    {"case": [[{"gt": [C, {"ma": [C, 5]}]}, {"highest": [C, 3]}]], "else": {"lowest": [C, 3]}},
]


def t_causal(rng):
    for trial in range(15):
        xs = rand_series(rng, 90)
        full = make_ctx(xs)
        for node in CAUSAL_NODES:
            fs = cond.series(node, full)
            for t in (30, 55, 89):
                pre = make_ctx(xs[:t + 1])
                ps = cond.series(node, pre)
                check(same(ps[t], fs[t], 1e-9), "미래 참조: %s @%d" % (cond._op_of(node), t))


# ------------------------------------------------------------------ 5. 문법
def t_syntax():
    bad = [
        {"gt": [C]}, {"ma": [C, 0]}, {"ma": [C, 2.5]}, {"px": "price"}, {"foo": 1},
        {"gt": [C, 1], "lt": [C, 2]}, True, {"atleast": 2}, {"def": "없음"},
        {"across": {"syms": [], "cond": C}}, {"manual": ""}, {"gt": [C, 1], "op": "above"},
        {"px": "close", "tf": "1h"}, {"abs": [C, 1]}, {"case": [[C, 1]]}, {"case": [C, 1], "else": 0},
        {"max": [C]},
    ]
    for b in bad:
        try:
            cond.validate(b)
            FAILS.append("거부해야 할 노드가 통과: %r" % (b,))
        except cond.CondError:
            pass
    good = {"all": [{"gt": [C, {"ma": [C, 20]}], "label": "20일선 위", "ref": "3-2"},
                    {"atleast": 2, "of": [{"manual": "장중"}, {"ge": [{"px": "volume"}, 1]}]}]}
    try:
        cond.validate(good)
    except cond.CondError as e:
        FAILS.append("올바른 노드가 거부: %s" % e)
    try:
        cond.validate({"case": [[{"gt": [C, 1]}, 2]], "else": {"px": "close", "tf": "1d"}})
    except cond.CondError as e:
        FAILS.append("올바른 case·tf 가 거부: %s" % e)
    for z in cond.ZONES:
        cfg = empty_product()
        cfg.pop(z)
        try:
            TreeGateway.of(synthetic({"X": cfg}))
            FAILS.append("%s 칸 없는 트리가 통과" % z)
        except cond.CondError:
            pass
    try:
        TreeGateway.of(synthetic({"X": empty_product()}))
    except cond.CondError as e:
        FAILS.append("빈 칸 여섯 개 트리가 거부: %s" % e)
    W = {"gt": [C, 1]}
    bad_cfgs = [
        {"caution": [{"label": "a", "when": W}]},                                # scale 미명시
        {"caution": [{"label": "a", "when": W, "scale": 1.5}]},
        {"caution": [{"label": "a", "when": {"gt": [{"pos": "ret"}, 0]}, "scale": 0.5}]},
        {"sizing": {"weight": 30}},                                               # tranches 미명시
        {"sizing": {"weight": 30, "tranches": [{"label": "1", "frac": 0.5}, {"label": "2", "frac": 0.4, "when": W}]}},
        {"sizing": {"weight": 30, "tranches": [{"label": "1", "frac": 0.5, "when": W},
                                               {"label": "2", "frac": 0.5, "when": W}]}},
        {"sizing": {"weight": 30, "tranches": [{"label": "1", "frac": 0.5}, {"label": "2", "frac": 0.5}]}},
        {"sizing": {"weight": {"pos": "ret"}, "tranches": []}},
        {"sizing": {"weight": None, "tranches": [{"label": "1", "frac": None}, {"label": "2", "frac": 0.5, "when": W}]}},
        {"sizing": {"weight": None, "tranches": [{"label": "1"}]}},                 # frac 미명시
    ]
    for b in bad_cfgs:
        try:
            TreeGateway.of(synthetic({"X": empty_product(**b)}))
            FAILS.append("잘못된 칸이 통과: %r" % b)
        except cond.CondError:
            pass
    good = empty_product(caution=[{"label": "a", "when": W, "scale": None}],
                         sizing={"weight": {"case": [[W, 14]], "else": 34},
                                 "tranches": [{"label": "1", "frac": 0.25},
                                              {"label": "2", "frac": 0.75, "when": {"ge": [{"pos": "ret"}, 3]}}]})
    try:
        TreeGateway.of(synthetic({"X": good}))
        TreeGateway.of(synthetic({"X": empty_product(sizing={"weight": None, "tranches": [
            {"label": "1", "frac": None}, {"label": "2", "frac": None, "when": {"manual": "저자 미명시: x"}}]})}))
    except cond.CondError as e:
        FAILS.append("올바른 caution·sizing 이 거부: %s" % e)


def t_asof():
    """장중(tf="1m") 값 — asof(관측 시점) 이하 그날 마지막 분봉. asof 이후 분봉·다른 날 분봉은 안 쓴다.
    분봉 데이터가 없으면 None(장중 observe → manual). 분봉 키는 UTC(YYYYMMDDHHMM)."""
    import datetime as dt
    utc = dt.timezone.utc
    cal = ["20261001", "20261002"]
    # minute_series: 날짜별 asof 이하 마지막 분봉. dict 봉·단일 종가 둘 다 받는다.
    m = {"202610011950": 1.0, "202610012100": 2.0, "202610021315": 3.0, "202610021320": 4.0, "202610021321": 5.0}
    asof = dt.datetime(2026, 10, 2, 13, 20, tzinfo=utc)      # 10/02 13:20 UTC
    got = cond.minute_series(m, cal, "close", asof)
    check(got == [2.0, 4.0], "asof 이하 그날 마지막 분봉 %r" % got)
    # asof 가 이르면 그날 분봉이 아직 없다 → None(미래 분봉을 쓰지 않는다)
    early = cond.minute_series(m, cal, "close", dt.datetime(2026, 10, 2, 13, 0, tzinfo=utc))
    check(early == [2.0, None], "asof 전 분봉은 쓰지 않는다(그날 None) %r" % early)
    # 그날 분봉이 아예 없으면 None(다른 날 분봉으로 넘어가지 않는다)
    check(cond.minute_series({"202610011950": 1.0}, cal, "close", asof) == [1.0, None], "그날 분봉 없으면 None")
    check(cond.minute_series({}, cal, "close", asof) == [None, None], "분봉 전무 → 전부 None(장중 observe → manual)")
    # OHLCV dict 봉도 받는다(목표 분봉 구조)
    md = {"202610021320": {"open": 10, "high": 12, "low": 9, "close": 11, "volume": 500}}
    check(cond.minute_series(md, cal, "high", asof) == [None, 12.0], "dict 분봉 필드 선택")
    # 문법: tf 는 "1d"/"1m"/"5m" 만, 그 밖은 거부. px 에 모르는 보조 키가 붙으면 '노드에 연산 둘'로 거부된다.
    for b in ({"px": "close", "tf": "1h"}, {"px": "close", "tf": "15m"},
              {"px": "close", "offset": -10}):
        try:
            cond.validate(b)
            FAILS.append("잘못된 tf 통과: %r" % b)
        except cond.CondError:
            pass
    cond.validate({"px": "close", "tf": "1m"})      # 분봉 노드는 통과
    cond.validate({"px": "close", "tf": "5m"})      # 5분봉 노드도 통과
    # 평가: 장중 분봉 값 > 전일 종가(선물이 전일 종가 위). tf="1m" 를 asof 로 자른다.
    hist = {"X": [Candle(d, 100, 100, 100, 100, 1000) for d in cal]}

    class H(dict):
        minutes = {"X": {"202610021320": 101.0}}
    ctx = cond.Ctx(H(hist), cal, "X", asof=asof)
    v = cond.series({"gt": [{"px": "close", "sym": "X", "tf": "1m"}, {"px": "close"}]}, ctx)
    check(v == [None, True], "장중 분봉 값 > 전일 종가(그날만 분봉 있음) %r" % v)
    # observe — 관측되면 그 값, 관측값이 없으면 수동처럼(manual_as, not 아래 극성 포함)
    obs = {"observe": {"gt": [{"px": "close", "sym": "X", "tf": "1m"}, {"px": "close"}]}, "manual": "데이터 없음: x"}
    for mas in (True, False, None):
        c2 = cond.Ctx(H(hist), cal, "X", asof=asof, manual_as=mas)
        check(cond.series(obs, c2) == [mas, True], "observe manual_as=%r" % mas)
        check(cond.series({"not": obs}, c2)[0] == (None if mas is None else mas), "not observe 극성 manual_as=%r" % mas)
    # 제외 모드(백테스트) — 관측값 없는 observe(0일째: 분봉 없음)는 묶음에서 빠진다.
    ex = cond.Ctx(H(hist), cal, "X", asof=asof, unobserved="exclude")
    T_, F_ = {"gt": [1, 0]}, {"gt": [0, 1]}
    cases = [({"all": [obs, T_]}, [True, True]), ({"all": [obs, F_]}, [False, False]),
             ({"any": [obs, F_]}, [False, True]), ({"atleast": 2, "of": [obs, T_, T_]}, [True, True]),
             ({"atleast": 2, "of": [obs, T_, F_]}, [False, True]), ({"not": obs}, [cond.EXCLUDED, False]),
             ({"all": [obs]}, [cond.EXCLUDED, True])]
    for node, want in cases:
        got = cond.series(node, ex)
        check(got == want, "제외 모드 %s → %r (기대 %r)" % (list(node)[0], got, want))
    check(cond.series({"gt": [{"case": [[obs, 1]], "else": 0}, 0]}, ex)[0] is None, "제외 표지는 다른 연산엔 모름으로")
    try:
        cond.validate({"observe": {"gt": [C, 1]}})
        FAILS.append("사유 없는 observe 통과")
    except cond.CondError:
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
    intraday = cond.Ctx(full, cal, "X", asof=dt.datetime(2026, 10, 2, 13, 20, tzinfo=utc), session_close=sc)
    check(cond.series(node1d, intraday) == [100.0, 100.0], "일봉축: 장중엔 오늘 칸도 어제 확정값(100)으로 당김")
    atclose = cond.Ctx(full, cal, "X", asof=dt.datetime(2026, 10, 2, 20, 0, tzinfo=utc), session_close=sc)
    check(cond.series(node1d, atclose) == [100.0, 200.0], "settled: 마감 == asof 는 확정(오늘 봉 그대로, 당김 없음)")
    pre = cond.Ctx(full, cal, "X", asof=dt.datetime(2026, 10, 2, 19, 59, tzinfo=utc), session_close=sc)
    check(cond.series(node1d, pre) == [100.0, 100.0], "일봉축: 마감 1분 전은 아직 미확정 → 어제값으로 당김")
    post = cond.Ctx(full, cal, "X", asof=dt.datetime(2026, 10, 2, 21, 0, tzinfo=utc), session_close=sc)
    check(cond.series(node1d, post) == [100.0, 200.0], "settled: 장 끝난 뒤는 확정(항등)")

    # 2) look-ahead 0 (★확장·전수) — 장중 asof 에서 오늘 칸이 '어제 확정값'으로 당겨지고, 미확정 종가 999 는 안 샘.
    with_today = hist_of([100.0, 999.0])    # 오늘 봉 있음(미확정, 종가 999)
    cal_wo = ["20261001"]
    without = {"X": [Candle("20261001", 100.0, 100.0, 100.0, 100.0, 1000)]}   # 오늘 봉 없음(현재 feed 모습)
    derived = [node1d, {"ma": [node1d, 1]}, {"highest": [node1d, 1]}, {"lag": [node1d, 0]},
               {"gt": [node1d, 50]}, {"streak": {"gt": [node1d, 50]}}]
    for h in (10, 13, 15, 19, 20, 21):       # 장중~장후 여러 asof
        a = dt.datetime(2026, 10, 2, h, 0, tzinfo=utc)
        cw = cond.Ctx(with_today, cal, "X", asof=a, session_close=sc)
        cwo = cond.Ctx(without, cal_wo, "X", asof=a, session_close=sc)
        for node in derived:
            vw = cond.series(node, cw)
            vwo = cond.series(node, cwo)
            # 마지막 확정일(10/01, index 0) 값이 오늘 봉 유무와 무관해야 한다
            check(same(vw[0], vwo[0], 1e-9),
                  "look-ahead: %s @10/01 이 오늘 봉 유무에 흔들림(asof %dh) %r≠%r"
                  % (cond._op_of(node), h, vw[0], vwo[0]))
            # 장중(마감 전) asof 에선 미확정 종가 999 가 어떤 일봉 파생값에도 새어들면 안 된다 — look-ahead 0.
            #   (마감 == asof·장후(h>=20)엔 오늘 봉이 확정이라 999 는 '확정된 오늘 종가'로 정당히 쓰인다.)
            if h < 20:
                check(all(not same(x, 999.0, 1e-9) for x in vw if x is not None),
                      "look-ahead: 미확정 종가 999 가 샘(asof %dh) %r" % (h, vw))
                # ★확장: 장중엔 오늘 칸(index 1)이 '어제 확정 칸(index 0)'과 같아야 한다(일봉축으로 당겨왔으므로).
                check(same(vw[1], vw[0], 1e-9),
                      "일봉축 확장: 장중 오늘 칸 %s 가 어제 확정값과 달라짐(asof %dh) %r" % (cond._op_of(node), h, vw))

    # 3) no-op — 캘린더 없음·asof None 이면 장중이라도 아무것도 안 가린다(일봉 파리티 보존)
    a = dt.datetime(2026, 10, 2, 13, 20, tzinfo=utc)
    check(cond.series(node1d, cond.Ctx(full, cal, "X", asof=a, session_close={})) == [100.0, 200.0],
          "no-op: 캘린더 없으면 안 가림(캘린더 없다고 일봉 전부 지우지 않는다)")
    check(cond.series(node1d, cond.Ctx(full, cal, "X", asof=None, session_close=sc)) == [100.0, 200.0],
          "no-op: asof None(라이브 지금)은 안 가림")

    # 4) 5분봉 집계 — 1분봉→5분 OHLC, 세션(날) 경계 안 넘음, asof 로 자른 마지막 5분봉 = 재집계와 일치
    m = {"202610021330": {"open": 10, "high": 11, "low": 9, "close": 10, "volume": 100},
         "202610021331": {"open": 10, "high": 13, "low": 8, "close": 12, "volume": 50},
         "202610021334": {"open": 12, "high": 12, "low": 7, "close": 9, "volume": 70},   # 1330 버킷 끝
         "202610021335": {"open": 9, "high": 9, "low": 9, "close": 9, "volume": 10},     # 1335 버킷 시작
         "202610011959": {"open": 5, "high": 5, "low": 5, "close": 5, "volume": 1}}      # 전날 — 다른 세션
    agg = cond.aggregate_5m(m)
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
    c5 = cond.Ctx(H({"X": [Candle(d, 100, 100, 100, 100, 1000) for d in cal]}), cal, "X",
                  asof=dt.datetime(2026, 10, 2, 13, 34, tzinfo=utc), session_close=sc)
    got5 = c5.px("X", "close", "5m")
    # 10/01 엔 그날 5분봉(1955 버킷, close 5)이 있고, 10/02 엔 asof 이하 마지막이 1330 버킷(close 9).
    check(got5 == [5.0, 9.0], "5m px: 날짜별 asof 이하 마지막 5분봉 close(10/01=5·10/02=9) %r" % got5)
    # asof 를 1335 이후로 밀면 10/02 는 1335 버킷(high 9)까지 보인다
    c5b = cond.Ctx(H({"X": [Candle(d, 100, 100, 100, 100, 1000) for d in cal]}), cal, "X",
                   asof=dt.datetime(2026, 10, 2, 13, 40, tzinfo=utc), session_close=sc)
    check(c5b.px("X", "high", "5m") == [5.0, 9.0], "5m px: 10/02 1335 버킷까지(high 9)")

    # 5) 혼합 tf 트리 — tf:1d(어제 확정) AND tf:5m(asof 이하) 를 저자 논리처럼 중첩. 1d 잎만 일봉축으로 당기고(per-leaf),
    #    5m 잎은 asof-오늘 축 그대로다 — 두 축이 섞인 all 노드는 당기지 않는다.
    #    c5 asof = 10/02 13:34(장중). 1d 잎은 어제(10/01) 확정 100 으로 당겨져 오늘 칸도 참(100>50). 5분봉은 asof 이하
    #    마지막(10/02 는 1330 버킷 close 9, 10/01 은 1955 버킷 close 5) 둘 다 50 미만 → 참. 그래서 오늘 칸도 AND 참.
    mixed = {"all": [{"gt": [{"px": "close", "sym": "X", "tf": "1d"}, 50]},      # 일봉축 어제 확정 100 > 50 → 참
                     {"lt": [{"px": "close", "sym": "X", "tf": "5m"}, 50]}]}     # 5분봉 종가 5·9 < 50 → 참
    mv = cond.series(mixed, c5)
    check(mv[0] is True, "혼합 tf: 확정일(10/01) 일봉·5분봉 각 축이 저자 AND 를 그대로 합침(참) %r" % mv)
    check(mv[1] is True, "혼합 tf: 오늘(10/02 장중)도 1d 잎=어제 확정값·5m 잎=asof 이하값 둘 다 참 → AND 참 %r" % mv)
    # per-leaf 스코프 확인: 1d 잎 단독은 장중에도 어제값으로 당겨지고, 5m 잎 단독은 asof-오늘 축(1330 버킷 9)을 본다.
    leaf1d = cond.series({"px": "close", "sym": "X", "tf": "1d"}, c5)
    leaf5m = cond.series({"px": "close", "sym": "X", "tf": "5m"}, c5)
    check(leaf1d == [100.0, 100.0], "per-leaf: 1d 잎은 장중에도 어제 확정값으로 당김 %r" % leaf1d)
    check(leaf5m == [5.0, 9.0], "per-leaf: 5m 잎은 당기지 않고 asof 이하 마지막 5분봉 축 그대로 %r" % leaf5m)
    # 5분봉 데이터가 아예 없으면 그 잎은 None → all = None(조용히 거짓 아님). 일봉은 어제(10/01) 100 으로 여전히 참.
    class H0(dict):
        minutes = {"X": {}}
    c5none = cond.Ctx(H0({"X": [Candle(d, 100, 100, 100, 100, 1000) for d in cal]}), cal, "X",
                      asof=dt.datetime(2026, 10, 2, 13, 0, tzinfo=utc), session_close=sc)
    check(cond.series(mixed, c5none)[0] is None, "혼합 tf: 데이터 없는 5분봉 축은 None(모름) → all None")


def t_grade():
    """등급 금액 판정 — 걸린 caution 의 scale 곱, 폭 미명시·확인 필요 구분, 비중 범위(화면 설명 구조는 web/verify_view.py)."""
    from checklist import grade
    xs = [100.0] * 30 + [130.0]
    cal = ["2022%04d" % i for i in range(len(xs))]
    hist = {"X": [Candle(d, c, c, c, c, 1000) for d, c in zip(cal, xs)]}
    jump = {"ge": [{"pct": [C, 1]}, 20]}
    cfg = empty_product(caution=[{"label": "급등 1/3", "when": jump, "scale": 0.3333},
                                 {"label": "급등 반", "when": jump, "scale": 0.5},
                                 {"label": "급등 폭 없음", "when": jump, "scale": None},
                                 {"label": "수동", "when": {"manual": "x"}, "scale": 0.5},
                                 {"label": "안 걸림", "when": {"not": jump}, "scale": 0.1}],
                        sizing={"weight": {"case": [[{"manual": "모드"}, 14]], "else": 34}, "tranches": []})
    tree = TreeGateway.of(synthetic({"X": cfg}))
    pe = grade.ProductEval(tree, "X", hist, cal)
    f, unspec, unknown = pe.amount_factor(len(xs) - 1)
    check(same(f, 0.3333 * 0.5) and unspec == ["급등 폭 없음"] and unknown == ["수동"],
          "amount_factor %r %r %r" % (f, unspec, unknown))
    w, alt = pe.weight_of(len(xs) - 1)
    check(w is None and alt == [14.0, 34.0], "수동 모드 비중은 모름 + 범위 %r %r" % (w, alt))


def t_answers():
    """사람이 답한 수동(Ctx answers) — 열쇠 = (shared ? "*" : 상품) + "|" + (문장 | "?" 식). 답은 manual_as 보다 먼저,
    not 아래에서도 잎 값 그대로(not 이 뒤집을 뿐), 없는 열쇠는 manual_as, answers=None 이면 옛 동작 그대로."""
    from checklist import grade
    cal = ["2022%04d" % i for i in range(3)]
    hist = {p: [Candle(d, 100, 100, 100, 100, 1000) for d in cal] for p in ("A", "B", "M")}
    m = {"manual": "실적 좋음"}
    unk = {"ge": [{"px": "close", "sym": "M"}, "?"], "label": "M 높음"}
    defs = {"시장": {"all": [{"manual": "시장 좋음"}, {"gt": [{"px": "close", "sym": "M"}, 0]}]},
            "자기": {"all": [{"manual": "자기 확인"}, {"gt": [C, 0]}]}}

    def v(node, ma, answers):
        return cond.series(node, cond.Ctx(hist, cal, "A", None, defs, manual_as=ma, answers=answers))[0]
    k = cond.answer_key
    check(k(m, "A", False) == "A|실적 좋음" and k(m, "A", True) == "*|실적 좋음", "답 열쇠(상품·공통)")
    check(k(unk, "A", False) == "A|?" + json.dumps({"ge": [{"px": "close", "sym": "M"}, "?"]}, ensure_ascii=False,
                                                    sort_keys=True), "답 열쇠(\"?\" 식 — META 뗀 식)")
    for ma in (True, False, None):
        for ans in (True, False):
            check(v(m, ma, {"A|실적 좋음": ans}) is ans, "답이 manual_as(%r) 보다 먼저" % ma)
            check(v({"not": m}, ma, {"A|실적 좋음": ans}) is (not ans), "not 아래 답은 잎 값 그대로(not 이 뒤집음)")
        check(v({"not": m}, ma, {}) is ma and v({"not": m}, ma, None) is ma, "답 없으면 극성 규칙 그대로(%r)" % ma)
    check(v(m, None, {"B|실적 좋음": True}) is None, "다른 상품의 답은 안 먹는다")
    check(v({"def": "시장"}, None, {"*|시장 좋음": True}) is True and v({"def": "시장"}, None, {"A|시장 좋음": True}) is None,
          "공통 정의(상품마다 같은 값) 안 수동 = \"*\" 열쇠")
    check(v({"def": "자기"}, None, {"A|자기 확인": True}) is True and v({"def": "자기"}, None, {"*|자기 확인": True}) is None,
          "상품마다 다른 정의($self) 안 수동 = 상품 열쇠")
    check(v(unk, True, {k(unk, "A", False): False}) is False, "\"?\" 식도 답으로 풀린다")
    obs = {"observe": {"gt": [C, 0]}, "manual": "장중"}
    check(v(obs, None, {"A|장중": False}) is True, "관측된 observe 는 답보다 관측값")
    tree = TreeGateway.of(synthetic({"A": empty_product(entry={"all": [m]})}))
    got = [grade.ProductEval(tree, "A", hist, cal, answers=a).grade_key(2)
           for a in (None, {"A|실적 좋음": True}, {"A|실적 좋음": False})]
    check(got == ["confirm", "buy", "wait"], "등급까지 답으로 풀린다(확인 대기 → 매수 후보·관망) %r" % got)


# ------------------------------------------------------------------ 데이터 완전성 가드(워밍업 부족 → 불완전)
def t_warmup_guard():
    """★ 실제 발견된 버그 방지(영구): 시세가 rate-limit 로 잘려(워밍업 부족) 와도 엔진이 그 불완전 데이터로
    조용히 ✅/🚫 확신을 내면 모르고 매매하게 된다. 가드는 트리가 쓰는 가장 긴 lookback(워밍업)을 트리에서
    직접 뽑아, 그보다 확정 봉이 적은 초기 구간의 1d 신호를 '불완전 데이터(❔)'로 표면화한다.

    확인:
      1) 필요 워밍업을 트리에서 바르게 계산한다(창 n-1·lag k·rsi n·count n-1 가 가장 깊은 사슬로 누적되고,
         streak/barssince 류는 AtLeast/None 으로 스스로 불확실을 드러내므로 워밍업에 넣지 않는다).
      2) 워밍업을 일부러 잘라낸(필요보다 적은 봉) 입력 → 그 초기 구간은 incomplete=True 이고 grade_key 가 ❔.
      3) 워밍업이 충분한 구간 → incomplete=False, 가드 끼기 전과 등급이 '그대로'(오탐 0).
    """
    from checklist import grade

    # 1) warmup_of / 출입구 warmup 산식 — 손으로 셀 수 있는 노드들로 전수 대조.
    D = {"ma20": {"ma": [C, 20]}, "hi60": {"highest": [C, 60]}}
    cases = [
        (C, 0), ({"px": "close"}, 0), ({"manual": "x"}, 0), (5, 0),
        ({"ma": [C, 20]}, 19), ({"highest": [C, 60]}, 59), ({"sum": [C, 10]}, 9),
        ({"lag": [C, 5]}, 5), ({"pct": [C, 3]}, 3), ({"rsi": [C, 14]}, 14), ({"count": [C, 10]}, 9),
        ({"ma": [{"lag": [C, 5]}, 20]}, 24),                      # 중첩: lag5 안에 ma20 → 5 + 19
        ({"streak": {"gt": [C, {"ma": [C, 20]}]}}, 19),          # streak 자체는 안 더함, 안쪽 ma20 만
        ({"barssince": {"ge": [C, {"highest": [C, 60]}]}}, 59),
        ({"valuewhen": [{"gt": [C, 0]}, {"ma": [C, 30]}]}, 29),  # max(안쪽) = 29
        ({"all": [{"ma": [C, 5]}, {"highest": [C, 60]}]}, 59),   # 논리 묶음 = 자식 최댓값
        ({"atleast": 1, "of": [{"lag": [C, 2]}, {"ma": [C, 10]}]}, 9),
        ({"not": {"ma": [C, 7]}}, 6), ({"abs": {"pct": [C, 4]}}, 4),
        ({"case": [[{"gt": [C, 0]}, {"ma": [C, 8]}]], "else": {"highest": [C, 40]}}, 39),
        ({"def": "hi60"}, 59),                                   # 정의 펼침
    ]
    for node, exp in cases:
        got = cond.warmup_of(node, D)
        check(got == exp, "warmup_of %r → %d (기대 %d)" % (node, got, exp))

    # 트리 상품 워밍업 = 조건 칸(filter/entry/avoid) 전체의 최댓값. 규칙 칸(caution 등)은 안 센다.
    cfg = empty_product(filter={"gt": [C, {"ma": [C, 50]}]},
                        entry={"gt": [C, {"highest": [C, 60]}]}, avoid={"lt": [C, {"ma": [C, 10]}]},
                        caution=[{"label": "c", "when": {"gt": [C, {"ma": [C, 200]}]}, "scale": 0.5}])
    tree = TreeGateway.of(synthetic({"P": cfg}))
    check(tree.warmup("P") == 59, "warmup = 조건 칸 최댓값(highest60 → 59), caution(ma200) 제외")

    # 2) 워밍업 자르기 — 필요 워밍업 60(=highest60)짜리 트리. 충분한 봉 vs 모자란 봉.
    W = tree.warmup("P")                                          # 59
    need = W + 1                                                  # 첫 완전 봉이 서려면 확정 봉이 이만큼
    rng = random.Random(7)
    xs = [x if x is not None else 100.0 for x in rand_series(rng, need + 40, miss=0)]
    cal = ["2024%04d" % i for i in range(len(xs))]
    hist = {"P": [Candle(d, c, c, c, c, 1000) for d, c in zip(cal, xs)]}
    pe = grade.ProductEval(tree, "P", hist, cal)
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
        for rule in grade.GRADE_RULES["rules"]:
            if all(views[rule["view"]][sec][i] is want for sec, want in rule["when"].items()):
                return rule["key"]
        return grade.GRADE_RULES["default"]
    bad = [i for i in range(W, len(xs)) if pe.grade_key(i) != raw_grade(pe, i)]
    check(not bad, "워밍업 충분 구간 등급 == 가드 없는 원시 등급(오탐 0) @%r" % bad[:3])

    # 트렁케이트 비교: 같은 꼬리 구간을 '긴 이력'과 '짧게 잘린 이력'으로 각각 판정 — 긴 쪽은 신호를 내지만
    # 짧게 잘린 쪽은 워밍업이 모자란 꼬리 봉을 ❔ 로 뺀다(바로 그 '251봉 vs 594봉' 버그를 잡는 경로).
    short = {"P": [Candle(d, c, c, c, c, 1000) for d, c in zip(cal, xs)][-30:]}   # 꼬리 30봉만(워밍업 없음)
    short_cal = [c.date for c in short["P"]]
    pe_short = grade.ProductEval(tree, "P", short, short_cal)
    check(all(pe_short.incomplete(i) for i in range(len(short_cal))),
          "짧게 잘린 이력(워밍업 없음)은 전 구간 불완전 — 긴 이력이면 신호 낼 꼬리까지 ❔ 로 뺀다")
    last = len(cal) - 1
    check(not pe.incomplete(last) and pe_short.incomplete(len(short_cal) - 1),
          "같은 마지막 날: 긴 이력=완전(신호 OK) · 잘린 이력=불완전(판정 보류) — 조용한 오판 차단")


# ------------------------------------------------------------------ 6. 표현력 회귀(이번 버그 유형)
def t_regress():
    # (a) '20일선 회복 후 2거래일 유지' — 1일만 위면 거짓, 회복일+2일이면 참
    hold = {"ge": [{"streak": {"gt": [C, {"ma": [C, 20]}]}}, 3]}
    xs = [100.0] * 25 + [90.0] * 5 + [110.0]
    check(cond.series(hold, make_ctx(xs))[-1] is False, "2일 유지: 1일만 위인데 참")
    check(cond.series(hold, make_ctx(xs + [111.0, 112.0]))[-1] is True, "2일 유지: 3일 위인데 거짓")
    # (b) '전고점 돌파 후 돌파선 위 유지' — 돌파선 고정. 105 돌파 후 104·104.5 는 유지
    prior = {"highest": [{"lag": [C, 1]}, 20]}
    brk = {"gt": [C, prior]}
    level = {"valuewhen": [brk, prior]}
    held_ok = {"gt": [{"minsince": [brk, C]}, level]}        # 돌파 이후 최저 종가가 돌파선 위
    days = {"add": [{"barssince": brk}, 1]}                  # 돌파일 포함 경과일
    xs = [100.0] * 21 + [105.0, 104.0, 104.5]
    ctx = make_ctx(xs)
    check(cond.series(held_ok, ctx)[-1] is True and same(cond.series(days, ctx)[-1], 3.0),
          "돌파 유지: 돌파선(100) 고정 → 104·104.5 는 유지 3일")
    check(cond.series(held_ok, make_ctx(xs + [99.0]))[-1] is False, "돌파 유지: 돌파선 아래 마감이면 실패")
    # (c) '짧은 눌림(2일) 끝 반등' — 눌림 일수에 반등일을 넣지 않는다
    hi = {"barssince": {"ge": [C, {"highest": [C, 20]}]}}
    rebound = {"gt": [C, {"lag": [C, 1]}]}
    pull2 = {"all": [rebound, {"ge": [{"lag": [hi, 1]}, 2]}, {"le": [{"lag": [hi, 1]}, 2]}]}
    xs = [float(100 + i) for i in range(25)] + [122.0, 121.0, 122.5]   # 고점 124 → 2일 하락 → 반등
    check(cond.series(pull2, make_ctx(xs))[-1] is True, "눌림 2일 후 반등: 참이어야")
    xs1 = [float(100 + i) for i in range(25)] + [122.0, 123.0]          # 1일 하락 → 반등
    check(cond.series(pull2, make_ctx(xs1))[-1] is False, "눌림 1일 후 반등: 거짓이어야")
    # (d) 판정 불가는 위로 전파 — 4개 중 2개에서 2개가 모름이면 결과도 모름일 수 있다
    four = {"atleast": 2, "of": [{"gt": [C, 0]}, {"lt": [C, 0]}, {"manual": "a"}, {"manual": "b"}]}
    check(cond.series(four, make_ctx([1.0]))[0] is None, "4개 중 2개(1참·1거짓·2모름) → 모름")


def t_no_excluded_live():
    """불변식(화면 Fix #1): 실전 판정이 쓰는 문맥(unobserved != "exclude")에서는 EXCLUDED 가 절대 나오지 않는다.
    EXCLUDED 는 '관측 못 한 조건을 빼고 판단'(백테스트 전용)이라, 실전 판정·화면(#verdict-data — 서버가 사람이 답한
    수동까지 반영해 내는 판정)에 섞이면 라이브가 백테스트 규칙으로 판정하게 된다. 그 입력이 애초에 실전 경로로 올 수
    없음을 여기서 강제한다.

    여기서는 기본/실전 문맥에서 관측값 없는 observe·수동·그 논리 묶음(전부 제외가 될 법한 묶음)조차 EXCLUDED 를
    내지 않고 true/false/None 만 냄을 실행으로 확인한다. 실전 판정 경로가 unobserved="exclude" 를 쓰지 않는지는
    구간③ 검사(trading/verify_trading.py)가 소스로 확인한다.
    """
    import datetime as dt
    # 기본/낙관/비관 문맥 어디서도 EXCLUDED 가 안 나와야 한다 — 관측 없는 observe 와 그 논리 묶음까지.
    # (EXCLUDED 는 cond.py 에서 ctx.unobserved=="exclude" 일 때만 난다 — 실전은 그 모드가 아니다.)
    cal = ["20261001", "20261002"]
    hist = {"X": [Candle(d, 100, 100, 100, 100, 1000) for d in cal]}
    asof = dt.datetime(2026, 10, 2, 20, 0, tzinfo=dt.timezone.utc)

    class H(dict):
        minutes = {"X": {}}          # 분봉 없음 → observe 는 관측값이 없다(실전에서 흔함)

    obs = {"observe": {"gt": [{"px": "close", "sym": "X", "tf": "1m"}, {"px": "close"}]}, "manual": "데이터 없음: x"}
    nodes = [obs, {"manual": "y"}, {"all": [obs]}, {"any": [obs]}, {"not": obs},
             {"all": [obs, {"manual": "z"}]}, {"atleast": 1, "of": [obs, {"manual": "w"}]}]
    for manual_as in (None, True, False):
        ctx = cond.Ctx(H(hist), cal, "X", asof=asof, manual_as=manual_as)   # 실전 기본: unobserved 미지정
        for node in nodes:
            got = cond.series(node, ctx)
            bad = [x for x in got if x is cond.EXCLUDED]
            check(not bad, "실전 문맥(manual_as=%r) %s 가 EXCLUDED 를 냄 %r" % (manual_as, list(node)[0], got))


# ------------------------------------------------------------------ 7. 트리 출입구(TreeGateway) 계약
def t_gateway():
    """판정·백테스트·검사기가 트리에 묻는 질문의 답 모양 — 형식이 바뀌어도(여섯 칸 → rules) 이 답은 같아야 한다."""
    W = {"gt": [C, {"ma": [C, 20]}]}
    M = {"gt": [{"px": "close", "sym": "NQ=F", "tf": "1m"}, 0]}
    D = {"공통": dict(W, label="20일선 위", ref="1-1"), "장중": dict(M, label="선물 양", ref="1-2"),
         "지수": {"gt": [{"px": "close", "sym": "$index"}, 0], "label": "지수 양", "ref": "1-3"}}
    EX = [{"label": "익절", "ref": "5-1", "when": {"ge": [{"pos": "ret"}, 9]}, "sell": "all", "note": "n"}]
    PB = empty_product(filter={"def": "공통"})
    data = {
        "source": {"book": "샘플"}, "defs": D,
        "products": {
            "A": empty_product(index="^NDX", note="a 노트",
                               filter={"def": "공통"}, entry={"all": [{"def": "장중"}, {"def": "지수"}]},
                               avoid={"lt": [{"rsi": [C, 14]}, 30], "label": "과매도", "ref": "2-1"},
                               caution=[{"label": "c1", "ref": "3-1", "when": {"def": "공통"}, "scale": 0.5}],
                               sizing={"label": "비중", "ref": "4-1", "weight": 30,
                                       "tranches": [{"label": "1차", "ref": "4-2", "frac": 0.5},
                                                    {"label": "2차", "frac": 0.5, "when": {"ge": [{"pos": "ret"}, 3]}}]},
                               exit=EX),
            "B": PB},
        "unexpressed": [{"rule": "r", "ref": "9-9", "reason": "데이터 없음: x"}],
        "review": {"sections": {"A.entry": {"winner": "a", "why": "w"}}, "exits": {"A": {"winner": "b"}},
                   "scenario_overrides": {"s": "x"}, "fire_ack": {"경고": "ok"}}}
    g = TreeGateway.of(data)
    check(g.products() == ["A", "B"] and g.has("A") and not g.has("Z"), "products/has")
    check(g.index("A") == "^NDX" and g.index("B") is None and g.note("A") == "a 노트", "index/note")
    check(g.book() == "샘플" and TreeGateway({"products": {}}).book("slug") == "slug", "book(source.book, 기본값)")
    check(set(g.defs()) == {"공통", "장중", "지수"} and g.raw_defs() is D, "defs/raw_defs")
    check(g.section("A", "filter") == {"def": "공통"}, "section")
    ex = g.expressions("A")
    check([(z, l) for z, l, _r, _n in ex] == [("filter", None), ("entry", None), ("avoid", None), ("caution", "c1"),
                                              ("sizing", "비중"), ("sizing", "2차"), ("exit", "익절")], "expressions 순서 %r" % ex)
    c = g.cautions("A")[0]
    check((c.label, c.ref, c.qty, c.when, c.note) == ("c1", "3-1", ("order", 0.5), {"def": "공통"}, None), "cautions Rule")
    sz = g.sizing("A")
    check((sz.label, sz.ref, sz.qty) == ("비중", "4-1", ("cash", 30)) and g.sizing("B").qty == ("cash", None), "sizing Rule")
    trs = g.tranches("A")
    check([(t.label, t.qty, t.when is None) for t in trs] == [("1차", ("budget", 0.5), True), ("2차", ("budget", 0.5), False)]
          and trs[1].shown("label", "ref") == {"label": "2차"}, "tranches Rule·shown(적힌 키만)")
    e = g.exit_rules("A")[0]
    check((e.label, e.qty, e.note) == ("익절", ("held", 1.0), "n") and g.exit_rules("B") == [], "exit_rules")
    check(e.with_when({"manual": "x"}).when == {"manual": "x"} and e.when != {"manual": "x"}, "with_when 사본")
    std = TreeGateway.as_rules([{"label": "s", "when": W, "sell": {"initial": 0.5}},
                                {"label": "r", "when": W, "sell": {"remaining": None}}])
    check(std[0].qty == ("bought", 0.5) and std[1].qty == ("held", None)
          and std[0].raw() == {"label": "s", "when": W, "sell": {"initial": 0.5}}, "as_rules·qty(매도 비율)")
    check(g.symbols() == {"A", "B", "^NDX", "NQ=F"} and g.symbols(["B"]) == {"B", "NQ=F"}, "symbols %r" % g.symbols())
    check(g.minute_symbols() == {"NQ=F"} and g.timeframes() == {"1d", "1m"}, "minute_symbols/timeframes")
    check(g.warmup("A") == 19 and g.warmup("B") == 19 and g.warmup() == 19, "warmup")
    check(g.refs() == {"1-1", "1-2", "1-3", "2-1", "3-1", "4-1", "4-2", "5-1"}, "refs %r" % g.refs())
    check(g.def_users() == {"공통": {"A", "B"}, "장중": {"A"}, "지수": {"A"}}, "def_users %r" % g.def_users())
    check(g.unexpressed()[0]["ref"] == "9-9", "unexpressed")
    check(g.review_sections() == {"A.entry": {"winner": "a", "why": "w"}} and g.review_exits() == {"A": {"winner": "b"}}
          and g.scenario_overrides() == {"s": "x"} and g.fire_ack() == {"경고": "ok"}, "review")
    check(g.scenario_node("A", "filter") == {"def": "공통"} and g.scenario_node("A", "caution", "c1") == {"def": "공통"}
          and g.scenario_node("A", "caution") == {"any": [{"def": "공통"}]} and g.scenario_node("A", "sizing") == 30
          and g.scenario_node("A", "caution", "없음") is None and g.scenario_node("Z", "filter") is None, "scenario_node")
    check(g.raw_zone("A", "exit") is EX and g.raw_product("B") is PB and g.whole() is data, "raw_* 는 원본 그대로")
    check(not TreeGateway({}) and bool(g) and TreeGateway.load("__없는책__") is None, "빈·없는 트리는 거짓/None")
    for broken in ({"products": {}}, {"products": {"X": empty_product()}, "zzz": 1},
                   {"products": {"X": dict(empty_product(), extra=1)}}):
        try:
            TreeGateway.of(broken)
            FAILS.append("형식이 틀린 트리가 통과: %r" % list(broken))
        except cond.CondError:
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
                     ("EXCLUDED 실전 불변식", t_no_excluded_live), ("트리 출입구 계약", t_gateway),
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
        print("원시함수 검사 실패 %d건 — 발행 정지" % len(FAILS))
        return 1
    print("원시함수 검사 통과 — 수치·3값·시간·인과·문법·회귀·출입구")
    return 0


if __name__ == "__main__":
    sys.exit(main())
