#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검사기 ② — 조건 트리 원시함수 검사 (책 무관 · 크기 고정).

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

사용: python -m verdict.verify_primitives   (실패 있으면 exit 1)
"""
import itertools
import math
import random
import sys
from collections import namedtuple

import pandas as pd

from shared import paths  # noqa: F401  (UTF-8 출력)
from shared import cond

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
    bad = {"products": {"X": dict(cond.EMPTY_ZONE, entry={"gt": [{"pos": "ret"}, 0]})}}
    try:
        cond.validate_tree(bad)
        FAILS.append("entry 에 pos 가 통과")
    except cond.CondError:
        pass
    for ex in ([{"label": "x", "when": {"gt": [{"pos": "ret"}, 1]}, "sell": 0.3}],
               [{"label": "x", "when": {"gt": [{"pos": "ret"}, 1]}, "sell": {"initial": 1.5}}],
               [{"when": {"gt": [{"pos": "ret"}, 1]}, "sell": "all"}],
               [{"label": "x", "when": {"gt": [{"pos": "ret"}, 1]}, "sell": "all", "stop": 1}]):
        try:
            cond.validate_exits(ex, {}, "exit")
            FAILS.append("잘못된 매도 규칙 통과: %r" % ex)
        except cond.CondError:
            pass


def t_trades():
    """체결 규칙 평가 워크(shared.trades.build_trades) — 손으로 답을 셀 수 있는 시세로 진입·분할 매도·동시 발동·미청산·보유 중 신호 건너뛰기."""
    from shared import trades as trades_mod

    def mk(rows):
        cal = ["2021%04d" % i for i in range(len(rows))]
        hist = {"X": [Candle(d, o, max(o, c), min(o, c), c, 1000) for d, (o, c) in zip(cal, rows)]}
        tree = {"products": {"X": dict(cond.EMPTY_ZONE)}}
        return tree, hist, cal

    R = {"pos": "ret"}
    # (1) 신호 0일 → 1일 시가 100 진입. 2일 종가 108(+8%) → 1차(처음 30%) 3일 시가 110 매도.
    #     4일 종가 116(+16%) → 2차(처음 30%) 5일 시가 117. 6일 종가 99(−1%) & maxret≥15 → 잔량 전량 7일 시가 98.
    rows = [(100, 100), (100, 101), (105, 108), (110, 112), (114, 116), (117, 110), (105, 99), (98, 97), (97, 97)]
    tree, hist, cal = mk(rows)
    ex = [{"label": "1차", "when": {"ge": [R, 7]}, "sell": {"initial": 0.3}},
          {"label": "2차", "when": {"ge": [R, 15]}, "sell": {"initial": 0.3}},
          {"label": "잔량", "when": {"all": [{"ge": [{"pos": "maxret"}, 15]}, {"lt": [R, 0]}]}, "sell": "all"}]
    t = trades_mod.build_trades(tree, "X", hist, cal, [0], ex)
    check(len(t) == 1 and t[0]["closed"], "분할: 거래 1건 청산")
    if t:
        t = t[0]
        exp = (0.3 * 110 + 0.3 * 117 + 0.4 * 98) / 100 * 100 - 100
        check([(x["date"], x["px"], round(x["qty"], 6), x["rule"]) for x in t["sells"]] ==
              [(cal[3], 110, 0.3, "1차"), (cal[5], 117, 0.3, "2차"), (cal[7], 98, 0.4, "잔량")],
              "분할: 매도 날짜·가격·수량 %r" % t["sells"])
        check(same(t["ret"], exp, 1e-9), "분할: 수익률 %r≠%r" % (t["ret"], exp))
        check(t["entry"] == cal[1] and t["entry_px"] == 100 and t["exit"] == cal[7] and t["days"] == 6, "분할: 진입·청산·보유일")
    # (2) 같은 날 두 규칙(처음 50% + 남은 50%) — 적힌 순서: 0.5 팔고 남은 0.5의 절반 → 남은 0.25 는 미청산
    rows = [(100, 100), (100, 100), (100, 110), (120, 120), (120, 125)]
    tree, hist, cal = mk(rows)
    ex = [{"label": "a", "when": {"ge": [R, 5]}, "sell": {"initial": 0.5}},
          {"label": "b", "when": {"ge": [R, 5]}, "sell": {"remaining": 0.5}}]
    t = trades_mod.build_trades(tree, "X", hist, cal, [0], ex)[0]
    check([round(x["qty"], 6) for x in t["sells"]] == [0.5, 0.25] and not t["closed"], "동시 발동 순서·미청산")
    exp = (0.5 * 120 + 0.25 * 120 + 0.25 * 125) / 100 * 100 - 100        # 남은 0.25 는 마지막 종가 125 로 평가
    check(same(t["ret"], exp, 1e-9), "미청산 평가 %r≠%r" % (t["ret"], exp))
    # (3) 보유 중 신호 건너뛰기 · 청산 다음 날부터 다시 진입
    rows = [(100, 100)] * 3 + [(100, 106), (106, 106)] + [(100, 100)] * 4
    tree, hist, cal = mk(rows)
    ex = [{"label": "익절", "when": {"ge": [R, 5]}, "sell": "all"}]
    t = trades_mod.build_trades(tree, "X", hist, cal, [0, 1, 2, 5], ex)
    check([x["entry"] for x in t] == [cal[1], cal[6]], "보유 중 신호 건너뜀: %r" % [x["entry"] for x in t])
    check(t[0]["exit"] == cal[4] and t[0]["sells"][0]["px"] == 106, "청산일·가격")
    # (4) 같은 규칙은 한 번만 — 다시 조건이 참이 돼도 두 번 팔지 않는다
    rows = [(100, 100), (100, 108), (108, 100), (100, 109), (109, 109)]
    tree, hist, cal = mk(rows)
    t = trades_mod.build_trades(tree, "X", hist, cal, [0], [{"label": "1차", "when": {"ge": [R, 7]}, "sell": {"initial": 0.3}}])[0]
    check(len(t["sells"]) == 1, "규칙 한 번만")
    # (5) 마지막 날 신호 → 다음 날이 없어 체결 못 함(미청산), fixed20 은 20거래일 모자라면 None
    rows = [(100, 100), (100, 100), (100, 120)]
    tree, hist, cal = mk(rows)
    t = trades_mod.build_trades(tree, "X", hist, cal, [0], [{"label": "x", "when": {"ge": [R, 5]}, "sell": "all"}])[0]
    check(not t["closed"] and t["sells"] == [] and t["fixed20"] is None, "마지막 날 신호는 체결 안 됨")
    # (6) fixed20 = 진입일 포함 20번째 거래일 종가
    rows = [(100, 100)] + [(100, 100 + i) for i in range(1, 30)]
    tree, hist, cal = mk(rows)
    t = trades_mod.build_trades(tree, "X", hist, cal, [0], [])[0]
    check(same(t["fixed20"], (rows[20][1] / 100 - 1) * 100, 1e-9), "fixed20 정의")
    # (7) manual 은 '매도가 안 나가는 쪽'으로 풀린다 — 확인 못 한 조건 때문에 팔지 않는다(not 아래도 마찬가지)
    rows = [(100, 100), (100, 100), (100, 100), (100, 100)]
    tree, hist, cal = mk(rows)
    t = trades_mod.build_trades(tree, "X", hist, cal, [0], [{"label": "m", "when": {"manual": "실적"}, "sell": "all"}])[0]
    check(t["sells"] == [], "manual 매도는 안 걸림")
    t = trades_mod.build_trades(tree, "X", hist, cal, [0], [{"label": "nm", "when": {"not": {"manual": "x"}}, "sell": "all"}])[0]
    check(t["sells"] == [], "not 아래 manual 도 매도를 일으키지 않는다(안쪽을 참으로 풀어 not = 거짓)")
    # (8) 분할 매수 — 1차 25% 1일 시가 100. 2차(종가 ≥ +5%) 2일 종가 106 → 3일 시가 108 에 30%.
    #     평균 매입가 = (0.25·100 + 0.30·108)/0.55 = 104.36… 4일 종가 115(+10.2%) → 익절(산 물량 전부) 5일 시가 116.
    rows = [(100, 100), (100, 101), (103, 106), (108, 109), (112, 115), (116, 117), (117, 117)]
    tree, hist, cal = mk(rows)
    trs = [{"label": "1차", "frac": 0.25}, {"label": "2차", "frac": 0.30, "when": {"ge": [R, 5]}},
           {"label": "3차", "frac": 0.45, "when": {"ge": [R, 50]}}]
    t = trades_mod.build_trades(tree, "X", hist, cal, [0],
                        [{"label": "익절", "when": {"ge": [R, 10]}, "sell": {"initial": 1.0}}], trs)[0]
    avg = (0.25 * 100 + 0.30 * 108) / 0.55
    check([(b["date"], b["px"], b["qty"]) for b in t["buys"]] == [(cal[1], 100, 0.25), (cal[3], 108, 0.30)],
          "분할: 매수 날짜·가격·수량 %r" % t["buys"])
    check(t["closed"] and [(x["date"], x["px"], round(x["qty"], 6)) for x in t["sells"]] == [(cal[5], 116, 0.55)],
          "분할: 평균 매입가 기준 +10퍼센트 익절 %r" % t["sells"])
    check(same(t["ret"], (116 / avg - 1) * 100, 1e-9), "분할: 수익률 = 판 금액 ÷ 산 금액")
    # 같은 날 매도가 걸리면 그날은 추가 매수하지 않는다
    rows = [(100, 100), (100, 100), (100, 106), (106, 106), (106, 106)]
    tree, hist, cal = mk(rows)
    t = trades_mod.build_trades(tree, "X", hist, cal, [0],
                        [{"label": "반", "when": {"ge": [R, 5]}, "sell": {"remaining": 0.5}}], trs)[0]
    check([b["date"] for b in t["buys"]] == [cal[1], cal[4]],      # 2일 매도 신호 → 3일 시가 매수 안 함, 3일 신호 → 4일 매수
          "매도가 걸린 날은 추가 매수 안 함 %r" % t["buys"])
    # 분할이 없으면 한 번에 전량(옛 규약과 같은 결과) · 비율이 저자 미명시(null)여도 전량(비율을 지어내지 않는다)
    t = trades_mod.build_trades(tree, "X", hist, cal, [0], [], [])[0]
    check([b["qty"] for b in t["buys"]] == [1.0], "분할 없음 = 전량")
    nul = [{"label": "1차", "frac": None}, {"label": "2차", "frac": None, "when": {"ge": [R, 5]}}]
    t = trades_mod.build_trades(tree, "X", hist, cal, [0], [], nul)[0]
    check([b["qty"] for b in t["buys"]] == [1.0], "분할 비율 미명시 = 전량 한 번")
    # 주: 백테스트 수익률 정의(_fwd)는 구간④ 계산기(operations/backtest)로 옮겼다 — 이 검사기는 구간③(머리/공통층)
    #     원시함수만 본다. operations(계산기)를 import 하면 단방향(폭포수) 역류이므로 여기서 _fwd 는 검사하지 않는다
    #     (operations 자체 검증에서 다룬다).


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
        cfg = dict(cond.EMPTY_ZONE)
        cfg.pop(z)
        try:
            cond.validate_tree({"products": {"X": cfg}})
            FAILS.append("%s 칸 없는 트리가 통과" % z)
        except cond.CondError:
            pass
    try:
        cond.validate_tree({"products": {"X": dict(cond.EMPTY_ZONE)}})
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
            cond.validate_tree({"products": {"X": dict(cond.EMPTY_ZONE, **b)}})
            FAILS.append("잘못된 칸이 통과: %r" % b)
        except cond.CondError:
            pass
    good = dict(cond.EMPTY_ZONE, caution=[{"label": "a", "when": W, "scale": None}],
                sizing={"weight": {"case": [[W, 14]], "else": 34},
                        "tranches": [{"label": "1", "frac": 0.25},
                                     {"label": "2", "frac": 0.75, "when": {"ge": [{"pos": "ret"}, 3]}}]})
    try:
        cond.validate_tree({"products": {"X": good}})
        cond.validate_tree({"products": {"X": dict(cond.EMPTY_ZONE, sizing={"weight": None, "tranches": [
            {"label": "1", "frac": None}, {"label": "2", "frac": None, "when": {"manual": "저자 미명시: x"}}]})}})
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
    """★ 혼합 tf·확정(settled) 규칙·look-ahead 0 — 이 덩어리의 최우선 correctness 증명(영구).

    1) settled 규칙: 장중 asof 면 '마감이 asof 이후'인 일봉(진행 중 그날 봉)은 None(안 봄). 마감 == asof 는 확정.
    2) look-ahead 0: tf:1d 조건 값이 '오늘 미확정 일봉 포함/제외'와 무관(오늘 종가를 절대 안 본다) — 전수.
    3) 캘린더 없음·asof None → 아무것도 안 가림(no-op, 일봉 파리티 보존).
    4) 5분봉 집계: 1분봉→5분 OHLC 가 세션 경계를 안 넘고, asof 로 자른 마지막 5분봉이 1분봉 재집계와 일치.
    5) 혼합 tf 트리: 한 트리가 tf:1d(확정 전일) AND tf:5m(asof 이하) 를 저자 논리처럼 중첩해도 각 잎이 자기 축을 본다.
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

    # 1) settled 규칙 — 장중(13:20)·마감시각(20:00)·마감전(19:59)·장후(21:00)
    full = hist_of([100.0, 200.0])      # 오늘(10/02) 미확정 봉 종가 200 이 feed 에 들어온 (최악의) 경우
    intraday = cond.Ctx(full, cal, "X", asof=dt.datetime(2026, 10, 2, 13, 20, tzinfo=utc), session_close=sc)
    check(cond.series(node1d, intraday) == [100.0, None], "settled: 장중엔 오늘 미확정 일봉 None(전일만)")
    atclose = cond.Ctx(full, cal, "X", asof=dt.datetime(2026, 10, 2, 20, 0, tzinfo=utc), session_close=sc)
    check(cond.series(node1d, atclose) == [100.0, 200.0], "settled: 마감 == asof 는 확정(읽는다)")
    pre = cond.Ctx(full, cal, "X", asof=dt.datetime(2026, 10, 2, 19, 59, tzinfo=utc), session_close=sc)
    check(cond.series(node1d, pre) == [100.0, None], "settled: 마감 1분 전은 아직 미확정")
    post = cond.Ctx(full, cal, "X", asof=dt.datetime(2026, 10, 2, 21, 0, tzinfo=utc), session_close=sc)
    check(cond.series(node1d, post) == [100.0, 200.0], "settled: 장 끝난 뒤는 확정")

    # 2) look-ahead 0 — '오늘 미확정 봉 포함/제외'와 무관(전수: 여러 asof × 여러 일봉 파생값)
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
            # 그리고 미확정 종가 999 가 어떤 확정값에도 새어들면 안 된다(장중 asof)
            if h < 20:
                check(all(not same(x, 999.0, 1e-9) for x in vw if x is not None),
                      "look-ahead: 미확정 종가 999 가 샘(asof %dh) %r" % (h, vw))

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

    # 5) 혼합 tf 트리 — tf:1d(확정 전일) AND tf:5m(asof 이하) 를 저자 논리처럼 중첩. 각 잎이 자기 축을 본다.
    #    저자 논리는 '같은 asof 의 확정 일봉 + 장중 5분봉'을 합치는 것이므로, 일봉이 확정된 마지막 날(10/01, i=0)에서
    #    두 축이 모두 값을 가진다(일봉 100 확정, 5분봉 5). 오늘(10/02, i=1)은 일봉 미확정이라 1d 잎이 None → AND None
    #    (= 아직 못 정함, look-ahead 금지의 정직한 결과. 올바른 index 선택은 장중 재생 드라이버 = 다음 덩어리).
    mixed = {"all": [{"gt": [{"px": "close", "sym": "X", "tf": "1d"}, 50]},      # 확정 일봉 100 > 50 → 참
                     {"lt": [{"px": "close", "sym": "X", "tf": "5m"}, 50]}]}     # 5분봉 종가 5 < 50 → 참
    mv = cond.series(mixed, c5)
    check(mv[0] is True, "혼합 tf: 확정일(10/01) 일봉·5분봉 각 축이 저자 AND 를 그대로 합침(참) %r" % mv)
    check(mv[1] is None, "혼합 tf: 오늘(미확정 일봉)은 1d 잎 None → AND None(look-ahead 금지의 정직한 결과) %r" % mv)
    # 5분봉 데이터가 아예 없으면 그 잎은 None → all = None(조용히 거짓 아님). 일봉은 확정일(10/01) 100 으로 여전히 참.
    class H0(dict):
        minutes = {"X": {}}
    c5none = cond.Ctx(H0({"X": [Candle(d, 100, 100, 100, 100, 1000) for d in cal]}), cal, "X",
                      asof=dt.datetime(2026, 10, 2, 13, 0, tzinfo=utc), session_close=sc)
    check(cond.series(mixed, c5none)[0] is None, "혼합 tf: 데이터 없는 5분봉 축은 None(모름) → all None")


def t_grade():
    """tree_grade 금액 판정 — 걸린 caution 의 scale 곱, 폭 미명시·확인 필요 구분, 비중 범위, 화면 설명 구조."""
    from shared import tree_grade
    xs = [100.0] * 30 + [130.0]
    cal = ["2022%04d" % i for i in range(len(xs))]
    hist = {"X": [Candle(d, c, c, c, c, 1000) for d, c in zip(cal, xs)]}
    jump = {"ge": [{"pct": [C, 1]}, 20]}
    cfg = dict(cond.EMPTY_ZONE,
               caution=[{"label": "급등 1/3", "when": jump, "scale": 0.3333},
                        {"label": "급등 반", "when": jump, "scale": 0.5},
                        {"label": "급등 폭 없음", "when": jump, "scale": None},
                        {"label": "수동", "when": {"manual": "x"}, "scale": 0.5},
                        {"label": "안 걸림", "when": {"not": jump}, "scale": 0.1}],
               sizing={"weight": {"case": [[{"manual": "모드"}, 14]], "else": 34}, "tranches": []})
    tree = {"products": {"X": cfg}}
    cond.validate_tree(tree)
    pe = tree_grade.ProductEval(tree, "X", hist, cal)
    f, unspec, unknown = pe.amount_factor(len(xs) - 1)
    check(same(f, 0.3333 * 0.5) and unspec == ["급등 폭 없음"] and unknown == ["수동"],
          "amount_factor %r %r %r" % (f, unspec, unknown))
    w, alt = pe.weight_of(len(xs) - 1)
    check(w is None and alt == [14.0, 34.0], "수동 모드 비중은 모름 + 범위 %r %r" % (w, alt))
    node = {"all": [dict(jump, label="급등", ref="1"), {"not": {"label": "수동", "manual": "x"}}]}
    v = pe.view(node, len(xs) - 1)
    check(v["op"] == "all" and v["kids"][0]["v"] is True and v["kids"][0]["label"] == "급등"
          and v["kids"][1]["op"] == "not" and v["kids"][1]["kids"][0]["manual"] == "x", "view 구조 %r" % v)
    hid = pe.view({"atleast": 1, "of": [jump, {"manual": "y"}]}, len(xs) - 1)
    check(hid["op"] == "atleast" and hid["n"] == 1 and hid["kids"][0].get("hidden") is True
          and hid["kids"][0]["v"] is True, "라벨 없는 잎은 hidden 으로 값과 함께 %r" % hid)


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
    EXCLUDED/빈-전부-제외 노드가 브라우저(verdict_engine → #verdict-data)에 실리면, 화면 3값 엔진
    (checklist-ui ev/and3/or3)에는 그 개념이 없어 null 로 오해해 등급이 엔진과 갈라진다. 그 입력이 애초에
    실전 경로로 올 수 없음을 여기서 강제한다.

    확인:
      (1) verdict_engine(실전 판정)은 cond.Ctx 를 만들 때 unobserved="exclude" 를 쓰지 않는다 — 소스로 확인.
      (2) 기본/실전 문맥에서는 관측값 없는 observe·수동·그 논리 묶음(전부 제외가 될 법한 묶음)조차 EXCLUDED 를
          내지 않고 true/false/None 만 낸다 — 실행으로 확인.
    """
    import datetime as dt
    import inspect
    from verdict import verdict_engine
    src = inspect.getsource(verdict_engine)
    check('unobserved="exclude"' not in src and "unobserved='exclude'" not in src,
          "verdict_engine 실전 경로가 unobserved=exclude 를 쓰지 않아야(백테스트 전용)")
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


def main():
    rng = random.Random(20261001)
    for name, fn in (("수치 연산", lambda: t_numeric(rng)), ("3값 논리", t_logic),
                     ("시간 연산", lambda: t_time(rng)), ("하한", t_bounds), ("포지션", lambda: t_pos(rng)), ("거래 시뮬레이터", t_trades),
                     ("인과성", lambda: t_causal(rng)),
                     ("문법", t_syntax), ("관측 시점(asof)", t_asof),
                     ("혼합 tf·확정봉·look-ahead 0", t_settled_mtf),
                     ("등급·금액", t_grade), ("표현력 회귀", t_regress),
                     ("EXCLUDED 실전 불변식", t_no_excluded_live)):
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
    print("원시함수 검사 통과 — 수치·3값·시간·인과·문법·회귀")
    return 0


if __name__ == "__main__":
    sys.exit(main())
