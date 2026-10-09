#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""구간③ 검사기 — 체결 규칙 평가 워크(trades.build_trades)·실전 판정 경로 불변식(책 무관 · 크기 고정) + 신호 패리티(--parity).

조건 트리 원시함수·등급 검사는 구간② verify/verify_primitives.py 가 하고, 여기는 그 위에서 도는 구간③ 코드만 본다.
  1. 거래 시뮬레이터 — 손으로 답을 셀 수 있는 시세로 진입·분할 매도·동시 발동·미청산·보유 중 신호 건너뛰기
     · 매도 정책 — 책에 매도 규칙이 없으면 거래 없이 매수 신호 뒤 N거래일 보유만(대체 매도 규칙을 지어내지 않는다)
  2. 실전 판정 경로는 unobserved="exclude"(백테스트 전용)를 쓰지 않는다 — 소스로 확인
  3. (--parity) 신호 패리티 — "백테스트 신호 == 실시간 신호"를 **실제 진입점으로 돌려** 증명한다(라이브 책의 tree.json·시세 필요).

## 신호 패리티(--parity) — 왜 남아 있나

백테스트와 라이브는 이제 같은 판정기(Judge.grade)를 지난다. 그래도 둘이 **구조적으로 같을 수는 없다** —
입력이 다르기 때문이다: 백테스트는 전체 이력을 한 번 세워 과거 날 i 를 꺼내고(asof 없음), 라이브는 그날 D 마감
직후 가진 이력(D 이하로 잘린 hist)으로 마지막 봉을 asof(그날 마감 시각)에 판정한다. 이 둘이 같으려면 cond 연산이
인과적이고(미래를 안 봄) asof 확정봉 가리기(settled)가 일봉 마감과 맞아야 한다 — 그걸 실행으로 확인한다.

  · 백테스트 경로 : `consumers.backtest.run(slug, days=N)` 의 `daily` 행 → {date, prod, key, grade}.
                    (내부에서 judge.signal_series 가 Judge(tree, p, hist, cal).grade(i) 를 전체 달력에 돌린다.)
  · 실시간 경로   : 각 과거일 D 에 대해 hist 를 D 이하로 잘라(judge.truncate) `Judge(tree, p, hist, asof).latest()`
                    — 라이브 판정 엔진(trading.engine.live_decisions)이 등급을 얻는 바로 그 호출이다.
                    asof 는 그날 마감 시점(UTC).
  전 상품 × 창(데이터 있는 최근 WINDOW 거래일) 전부에서 두 경로의 (key, grade) 가 **일치**하는지. 불일치가 하나라도
  있으면 (상품·날짜·백테스트·실시간) 을 전부 나열한다 — 숨기지 않는다.
  분봉 데이터가 없으면 장중(tf="1m") observe 조건은 두 경로 모두 None→manual 로 떨어진다(의도된 동작). 따라서
  **일봉 신호**의 패리티를 증명한다. 분봉이 연결되면 같은 코드가 그 축도 덮는다(asof 를 분봉 범위로 주면 된다).

사용:
  python -m verify.verify_trading                                     # 1·2 (실패 있으면 exit 1)
  python -m verify.verify_trading --parity [--window 120] [--slug trend]  # 3 — 100% 일치면 exit 0, 불일치 있으면 전체 목록 + exit 1
"""
import inspect
import os
import sys
from collections import namedtuple
from datetime import datetime, timedelta, timezone

from shared.paths import BASE, live_slugs, read_text  # (UTF-8 출력 고정 포함)
from dsl.tradeTool import Grade
from dsl.tree_gateway import TreeGateway, empty_product, synthetic
from consumers.backtest import trades as trades_mod
from signals.commonTool import open_history

Candle = namedtuple("Candle", "date open high low close volume")
FAILS = []


def check(ok, what):
    if not ok:
        FAILS.append(what)


def same(a, b, tol=1e-9):
    return a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(b))


def t_trades():
    """체결 규칙 평가 워크(trades.build_trades) — 손으로 답을 셀 수 있는 시세로 진입·분할 매도·동시 발동·미청산·보유 중 신호 건너뛰기."""
    def mk(rows):
        cal = ["2021%04d" % i for i in range(len(rows))]
        hist = {"X": [Candle(d, o, max(o, c), min(o, c), c, 1000) for d, (o, c) in zip(cal, rows)]}
        tree = TreeGateway.of(synthetic({"X": empty_product()}))
        return tree, hist, cal

    def bt(tree, hist, cal, starts, ex, trs=None):
        """매도·분할 규칙 dict(트리 형식) → 출입구 Rule 로 감싸 build_trades 에."""
        return trades_mod.build_trades(tree, "X", hist, cal, starts, TreeGateway.as_rules(ex),
                                       None if trs is None else TreeGateway.as_rules(trs))

    R = {"pos": "ret"}
    # (1) 신호 0일 → 1일 시가 100 진입. 2일 종가 108(+8%) → 1차(처음 30%) 3일 시가 110 매도.
    #     4일 종가 116(+16%) → 2차(처음 30%) 5일 시가 117. 6일 종가 99(−1%) & maxret≥15 → 잔량 전량 7일 시가 98.
    rows = [(100, 100), (100, 101), (105, 108), (110, 112), (114, 116), (117, 110), (105, 99), (98, 97), (97, 97)]
    tree, hist, cal = mk(rows)
    ex = [{"label": "1차", "when": {"ge": [R, 7]}, "sell": {"initial": 0.3}},
          {"label": "2차", "when": {"ge": [R, 15]}, "sell": {"initial": 0.3}},
          {"label": "잔량", "when": {"all": [{"ge": [{"pos": "maxret"}, 15]}, {"lt": [R, 0]}]}, "sell": "all"}]
    t = bt(tree, hist, cal, [0], ex)
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
    t = bt(tree, hist, cal, [0], ex)[0]
    check([round(x["qty"], 6) for x in t["sells"]] == [0.5, 0.25] and not t["closed"], "동시 발동 순서·미청산")
    exp = (0.5 * 120 + 0.25 * 120 + 0.25 * 125) / 100 * 100 - 100        # 남은 0.25 는 마지막 종가 125 로 평가
    check(same(t["ret"], exp, 1e-9), "미청산 평가 %r≠%r" % (t["ret"], exp))
    # (3) 보유 중 신호 건너뛰기 · 청산 다음 날부터 다시 진입
    rows = [(100, 100)] * 3 + [(100, 106), (106, 106)] + [(100, 100)] * 4
    tree, hist, cal = mk(rows)
    ex = [{"label": "익절", "when": {"ge": [R, 5]}, "sell": "all"}]
    t = bt(tree, hist, cal, [0, 1, 2, 5], ex)
    check([x["entry"] for x in t] == [cal[1], cal[6]], "보유 중 신호 건너뜀: %r" % [x["entry"] for x in t])
    check(t[0]["exit"] == cal[4] and t[0]["sells"][0]["px"] == 106, "청산일·가격")
    # (4) 같은 규칙은 한 번만 — 다시 조건이 참이 돼도 두 번 팔지 않는다
    rows = [(100, 100), (100, 108), (108, 100), (100, 109), (109, 109)]
    tree, hist, cal = mk(rows)
    t = bt(tree, hist, cal, [0], [{"label": "1차", "when": {"ge": [R, 7]}, "sell": {"initial": 0.3}}])[0]
    check(len(t["sells"]) == 1, "규칙 한 번만")
    # (5) 매도 비율 null(저자 미명시) — 걸려도 팔지 않고 문구로 드러낸다
    ex = [{"label": "축소", "when": {"ge": [R, 7]}, "sell": {"remaining": None}}]
    t = bt(tree, hist, cal, [0], ex)[0]
    check(t["sells"] == [] and not t["closed"], "비율 미명시 매도는 팔지 않음 %r" % t["sells"])
    check("「축소」" in (trades_mod.unsized_note(tree, "X", TreeGateway.as_rules(ex)) or ""), "비율 미명시 매도 문구")
    # (5) 마지막 날 신호 → 다음 날이 없어 체결 못 함(미청산), fixed20 은 20거래일 모자라면 None
    rows = [(100, 100), (100, 100), (100, 120)]
    tree, hist, cal = mk(rows)
    t = bt(tree, hist, cal, [0], [{"label": "x", "when": {"ge": [R, 5]}, "sell": "all"}])[0]
    check(not t["closed"] and t["sells"] == [] and t["fixed20"] is None, "마지막 날 신호는 체결 안 됨")
    # (6) fixed20 = 진입일 포함 20번째 거래일 종가
    rows = [(100, 100)] + [(100, 100 + i) for i in range(1, 30)]
    tree, hist, cal = mk(rows)
    t = bt(tree, hist, cal, [0], [])[0]
    check(same(t["fixed20"], (rows[20][1] / 100 - 1) * 100, 1e-9), "fixed20 정의")
    # (7) manual 은 '매도가 안 나가는 쪽'으로 풀린다 — 확인 못 한 조건 때문에 팔지 않는다(not 아래도 마찬가지)
    rows = [(100, 100), (100, 100), (100, 100), (100, 100)]
    tree, hist, cal = mk(rows)
    t = bt(tree, hist, cal, [0], [{"label": "m", "when": {"manual": "실적"}, "sell": "all"}])[0]
    check(t["sells"] == [], "manual 매도는 안 걸림")
    t = bt(tree, hist, cal, [0], [{"label": "nm", "when": {"not": {"manual": "x"}}, "sell": "all"}])[0]
    check(t["sells"] == [], "not 아래 manual 도 매도를 일으키지 않는다(안쪽을 참으로 풀어 not = 거짓)")
    # (8) 분할 매수 — 1차 25% 1일 시가 100. 2차(종가 ≥ +5%) 2일 종가 106 → 3일 시가 108 에 30%.
    #     평균 매입가 = (0.25·100 + 0.30·108)/0.55 = 104.36… 4일 종가 115(+10.2%) → 익절(산 물량 전부) 5일 시가 116.
    rows = [(100, 100), (100, 101), (103, 106), (108, 109), (112, 115), (116, 117), (117, 117)]
    tree, hist, cal = mk(rows)
    trs = [{"label": "1차", "frac": 0.25}, {"label": "2차", "frac": 0.30, "when": {"ge": [R, 5]}},
           {"label": "3차", "frac": 0.45, "when": {"ge": [R, 50]}}]
    t = bt(tree, hist, cal, [0],
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
    t = bt(tree, hist, cal, [0],
                        [{"label": "반", "when": {"ge": [R, 5]}, "sell": {"remaining": 0.5}}], trs)[0]
    check([b["date"] for b in t["buys"]] == [cal[1], cal[4]],      # 2일 매도 신호 → 3일 시가 매수 안 함, 3일 신호 → 4일 매수
          "매도가 걸린 날은 추가 매수 안 함 %r" % t["buys"])
    # 분할이 없으면 한 번에 전량(옛 규약과 같은 결과) · 비율이 저자 미명시(null)여도 전량(비율을 지어내지 않는다)
    t = bt(tree, hist, cal, [0], [], [])[0]
    check([b["qty"] for b in t["buys"]] == [1.0], "분할 없음 = 전량")
    nul = [{"label": "1차", "frac": None}, {"label": "2차", "frac": None, "when": {"ge": [R, 5]}}]
    t = bt(tree, hist, cal, [0], [], nul)[0]
    check([b["qty"] for b in t["buys"]] == [1.0], "분할 비율 미명시 = 전량 한 번")


def t_no_exit():
    """매도 정책 — 책에 매도 규칙이 없으면("none") 거래를 지어내지 않고(대체 매도 규칙 없음) 매수 신호 뒤
    N거래일 보유 수익률(summary 의 ✅+🟡 줄)만 남는다. 규칙이 있으면 "book" — 거래 시뮬레이션."""
    from consumers.backtest import runner
    today = datetime.now()
    cal = [(today - timedelta(days=60 - k)).strftime("%Y%m%d") for k in range(60)]
    hist = {"X": [Candle(d, 100 + k, 101 + k, 99 + k, 100 + k, 1000) for k, d in enumerate(cal)]}
    ex = [{"label": "익절", "when": {"ge": [{"pos": "ret"}, 5]}, "sell": "all"}]
    for exits, pol in (([], "none"), (ex, "book")):
        tree = TreeGateway.of(synthetic({"X": empty_product(exit=exits)}))
        check(trades_mod.exit_policy(tree, "X") == pol, "exit_policy %r" % pol)
        res = runner.run("x", 365, hist=hist, tree=tree)
        t = res["trades"]["X"]
        check(t["exit_policy"] == pol, "backtest 매도 정책 %r" % t)
        if pol == "none":
            check(set(t) == {"exit_policy"}, "매도 규칙 없음 — 거래를 만들지 않는다 %r" % sorted(t))
            b = res["summary"]["X"]["grades"][runner.BUY_OR_CONFIRM]
            check(b["signals"] == 1 and b["fwd"][5]["n"] == 1, "매도 규칙 없음 — 매수 신호 뒤 N일 보유만 %r" % b)
        else:
            check(t["stats"]["trades"] == 1 and t["trades"][0]["closed"], "매도 규칙 있음 — 거래 시뮬레이션 %r" % t["stats"])


def t_sizing():
    """금액 정책(trades.size_of) — 매수 크기 = 분할 비율 × 비중(%)/100 × 조심 배수. 크기는 그날 판정의 Judge.amount
    (라이브 화면과 같은 경로)에서 온다. 폭 미명시 조심·확인 필요 조심·비중 모름은 ×1 로 두고 횟수를 센다."""
    from signals.judge import Judge
    R = {"pos": "ret"}
    ON = {"gt": [{"px": "close"}, 0]}                     # 늘 참
    rows = [(100, 100), (100, 100), (100, 106), (106, 106), (106, 108), (108, 108)]
    cal = ["2021%04d" % i for i in range(len(rows))]
    hist = {"X": [Candle(d, o, max(o, c), min(o, c), c, 1000) for d, (o, c) in zip(cal, rows)]}
    trs = [{"label": "1차", "frac": 0.25}, {"label": "2차", "frac": 0.75, "when": {"ge": [R, 5]}}]

    def run(caution, weight):
        tree = TreeGateway.of(synthetic({"X": empty_product(caution=caution, sizing={"weight": weight, "tranches": trs})}))
        j = Judge(tree, "X", hist, cal)
        tl = trades_mod.build_trades(tree, "X", hist, cal, [0], [], amount=j.amount)
        return tl[0]["buys"], trades_mod._parity_stats(tl)["size_counts"]

    # 조심 배수 ×0.5 · 비중 40% → 1차 0.25×0.4×0.5 · 2차(2일 +6% → 3일 시가) 0.75×0.4×0.5
    b, sz = run([{"label": "반", "when": ON, "scale": 0.5}], 40)
    check([round(x["qty"], 9) for x in b] == [0.05, 0.15] and [x["date"] for x in b] == [cal[1], cal[3]],
          "비중·조심 배수·분할 비율 곱 %r" % b)
    check(sz["buys"] == 2 and sz["cut"] == 2 and not trades_mod.size_notes(sz), "조심으로 줄인 횟수 %r" % sz)
    # 폭 미명시 조심(scale null) → ×1(줄이지 않음) + 횟수 · 비중 저자 미명시 → 상품 예산 100%
    b, sz = run([{"label": "폭", "when": ON, "scale": None}], None)
    check([x["qty"] for x in b] == [0.25, 0.75], "폭 미명시 조심·비중 미명시는 ×1 %r" % b)
    notes = trades_mod.size_notes(sz)
    check(sz["unspecified"] == 2 and sz["weight_unset"] == 2 and sz["cut"] == 0
          and any("폭 미명시 조심 2회" in n for n in notes) and any("비중 저자 미명시" in n for n in notes),
          "폭 미명시·비중 미명시 횟수와 문구 %r %r" % (sz, notes))
    # 확인 필요(수동) 조심 → ×1 + 횟수 · 비중 식은 있으나 값 모름("?") → 100% + 횟수
    b, sz = run([{"label": "수동", "when": {"manual": "x"}, "scale": 0.5}], {"case": [[ON, "?"]], "else": "?"})
    check([x["qty"] for x in b] == [0.25, 0.75] and sz["unknown"] == 2 and sz["weight_unknown"] == 2,
          "확인 필요 조심·비중 모름은 ×1 %r %r" % (b, sz))
    # 수량 변환 하나(to_units) — 다섯 basis · 모름(None)은 None
    Qty, Led, tu = TreeGateway.as_rules([{"frac": 1}])[0].qty.__class__, trades_mod.Ledger, trades_mod.to_units
    led = Led(budget=0.4, order=0.5, bought=0.6, held=0.3)
    got = [tu(Qty(of, x), led) for of, x in (("cash", 30), ("budget", 0.25), ("order", 0.5), ("bought", 0.3),
                                              ("held", 0.5))]
    check(all(same(g, w) for g, w in zip(got, (0.3, 0.05, 0.5, 0.18, 0.15))) and tu(Qty("held", None), led) is None,
          "to_units 다섯 basis %r" % got)
    # 매수(분할 차수)와 매도(산/남은 물량 비율)가 같은 변환 하나를 지난다
    seen, orig = [], trades_mod.to_units
    trades_mod.to_units = lambda q, ld: seen.append(q.of) or orig(q, ld)
    try:
        tree = TreeGateway.of(synthetic({"X": empty_product(sizing={"weight": 40, "tranches": trs})}))
        ex = TreeGateway.as_rules([{"label": "반", "when": {"ge": [R, 5]}, "sell": {"initial": 0.5}},
                                   {"label": "끝", "when": {"ge": [R, 5]}, "sell": "all"}])
        trades_mod.build_trades(tree, "X", hist, cal, [0], ex, amount=Judge(tree, "X", hist, cal).amount)
    finally:
        trades_mod.to_units = orig
    check({"budget", "cash", "order", "bought", "held"} <= set(seen), "매수·매도·비중·조심이 to_units 하나로 %r" % seen)


def t_live_path():
    """실전 판정 경로가 cond.Ctx 를 unobserved="exclude"(관측 못 한 조건 빼기 — 백테스트 전용)로 만들지 않는다 —
    라이브 판정·화면(#verdict-data)이 백테스트 규칙으로 판정하지 않게(verify.verify_primitives 의 실행 불변식과 짝)."""
    from signals import judge
    # 실전 경로 = 판정기(signals/judge) + 그 Decision 을 판정 JSON 으로 빚는 consumers/display/verdict_view
    #   (소스 글자로 읽는다 — unobserved=exclude 가 실전 경로에 없어야 한다).
    for name, src in (("signals/judge.py", inspect.getsource(judge)),
                      ("consumers/display/verdict_view.py", read_text(os.path.join(BASE, "consumers", "display", "verdict_view.py")))):
        check('unobserved="exclude"' not in src and "unobserved='exclude'" not in src,
              "%s 실전 경로가 unobserved=exclude 를 쓰지 않아야(백테스트 전용)" % name)


# ------------------------------------------------------------------ 3. 신호 패리티(--parity)
WINDOW = 120            # 비교할 최근 거래일 수(상품마다 데이터 있는 범위 안에서)
CLOSE_HHMM_UTC = 21     # 미 증시 마감 ≈ 21:00 UTC(서머타임 20:00·표준 21:00) — asof 를 '그날 마감 시점'으로
                        # 둘 때의 시각. 분봉이 없어 일봉 결과엔 영향 없지만, 라이브와 같은 모양의 asof 를 준다.


def _asof_of(date_str):
    """날짜(YYYYMMDD) → 그날 마감 시점(UTC datetime). 라이브 render 가 받는 asof 와 같은 모양."""
    return datetime.strptime(date_str, "%Y%m%d").replace(hour=CLOSE_HHMM_UTC, tzinfo=timezone.utc)


def compare(slug, window=WINDOW):
    """한 책의 두 경로를 실제로 돌려 (상품·날짜)별 (key, grade) 를 비교한다.
    → {total, match, mismatches:[{prod, date, bt_key, bt_grade, live_key, live_grade}], products, window}."""
    from consumers.backtest import runner               # 패리티만 쓰는 실제 드라이버 진입점(1·2 검사는 안 부른다)
    from signals.judge import Judge, truncate
    # 라이브 판정(render)과 같은 방식으로 전체 일봉을 한 번 받는다(워밍업 포함).
    # window 만큼 + 워밍업을 넉넉히 — backtest.run 의 days 도 이 창을 덮게 준다.
    tree, full = open_history(slug, window * 2 + 30)

    # 백테스트 경로: 실제 드라이버 진입점. daily 행에서 (prod, date) → (key, grade).
    bt = runner.run(slug, days=window * 2 + 30, hist=full, tree=tree)
    bt_daily = {(r["prod"], r["date"]): (r["key"], r["grade"]) for r in bt["daily"]}

    mismatches = []
    total = 0
    for p in tree.products():
        cs = full.get(p) or []
        if not cs:
            continue
        # 비교할 날짜 = 이 상품의 데이터 중 '최근 window 거래일'. 백테스트 daily 에도 있는 날만 센다
        # (양쪽 다 판정한 날끼리만 비교 — 한쪽이 범위 밖이면 비교 대상이 아니다).
        dates = [c.date for c in cs][-window:]
        for d in dates:
            bt_row = bt_daily.get((p, d))
            if bt_row is None:
                continue
            # 실시간 경로: 라이브가 D 마감 직후 봤을 입력(D 이하 이력·그날 마감 asof)으로 Judge.latest.
            key, _close = Judge(tree, p, truncate(full, d), asof=_asof_of(d)).latest()
            live_row = (key, Grade.GRADES[key])
            total += 1
            if live_row != bt_row:
                mismatches.append({"prod": p, "date": d, "bt_key": bt_row[0], "bt_grade": bt_row[1],
                                   "live_key": live_row[0], "live_grade": live_row[1]})
    return {"slug": slug, "total": total, "match": total - len(mismatches),
            "mismatches": mismatches, "products": tree.products(), "window": window}


def parity_text(reports):
    L = ["📐 신호 패리티 검사 — 백테스트 신호 == 실시간 신호 (일봉, 실제 드라이버 진입점)"]
    grand_total = sum(r["total"] for r in reports)
    grand_match = sum(r["match"] for r in reports)
    for r in reports:
        pct = (r["match"] / r["total"] * 100) if r["total"] else 0.0
        L.append("")
        L.append("■ %s  (상품 %s · 최근 %d거래일)" % (r["slug"], " · ".join(r["products"]), r["window"]))
        L.append("   비교 %d · 일치 %d · 불일치 %d  (%.2f%%)" % (r["total"], r["match"], len(r["mismatches"]), pct))
        for m in r["mismatches"]:
            L.append("   ✗ %-6s %s  백테스트=%s / 실시간=%s" % (m["prod"], m["date"], m["bt_grade"], m["live_grade"]))
    L.append("")
    L.append("─" * 50)
    if grand_total and grand_match == grand_total:
        L.append("신호 PARITY ✅  — 총 %d 비교 전부 일치 (백테스트 == 실시간, 일봉)." % grand_total)
    elif grand_total:
        L.append("신호 불일치 ❌  — 총 %d 비교 중 %d 일치 · %d 불일치."
                 % (grand_total, grand_match, grand_total - grand_match))
    else:
        L.append("비교할 데이터 없음 — 시세가 비어 있거나 창이 0이다.")
    L.append("※ 분봉(장중, tf=\"1m\")은 데이터 미연결 → 두 경로 모두 None→manual(🟡)로 떨어져 결과에 영향 없음(정상).")
    L.append("   이 검사는 일봉 신호의 패리티를 증명한다. 분봉이 연결되면 같은 코드가 asof 축으로 그 축도 덮는다.")
    return "\n".join(L)


def parity_main(argv):
    window = int(argv[argv.index("--window") + 1]) if "--window" in argv else WINDOW
    slugs = [argv[argv.index("--slug") + 1]] if "--slug" in argv else live_slugs()
    if not slugs:
        print("live 책이 없습니다(books.json 의 live:true). --slug <책> 으로 지정하세요.", file=sys.stderr)
        return 2
    reports = [compare(s, window) for s in slugs]
    print(parity_text(reports))
    ok = all(r["total"] and not r["mismatches"] for r in reports) and any(r["total"] for r in reports)
    return 0 if ok else 1


def main(argv):
    if "--parity" in argv:
        return parity_main(argv)
    for name, fn in (("거래 시뮬레이터", t_trades), ("매도 정책(규칙 없음)", t_no_exit), ("금액 정책", t_sizing),
                     ("실전 경로 unobserved", t_live_path)):
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
        print("구간③ 검사 실패 %d건 — 발행 정지" % len(FAILS))
        return 1
    print("구간③ 검사 통과 — 거래 시뮬레이터·실전 경로")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
