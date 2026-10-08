#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""구간③ 검사기 — 체결 규칙 평가 워크(trades.build_trades)와 실전 판정 경로 불변식 (책 무관 · 크기 고정).

조건 트리 원시함수·등급 검사는 구간② checklist/verify_primitives.py 가 하고, 여기는 그 위에서 도는 구간③ 코드만 본다.
  1. 거래 시뮬레이터 — 손으로 답을 셀 수 있는 시세로 진입·분할 매도·동시 발동·미청산·보유 중 신호 건너뛰기
  2. 실전 판정 경로는 unobserved="exclude"(백테스트 전용)를 쓰지 않는다 — 소스로 확인

사용: python -m trading.verify_trading   (실패 있으면 exit 1)
"""
import inspect
import os
import sys
from collections import namedtuple

from shared.paths import BASE, read_text  # (UTF-8 출력 고정 포함)
from checklist.tree_gateway import TreeGateway, empty_product, synthetic
from trading import trades as trades_mod

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


def t_live_path():
    """실전 판정 경로가 cond.Ctx 를 unobserved="exclude" 로 만들지 않는다 — EXCLUDED 가 화면(#verdict-data)에 실리면
    화면 3값 엔진(checklist-ui)엔 그 개념이 없어 등급이 갈라진다(checklist.verify_primitives 의 실행 불변식과 짝)."""
    from trading import judge
    # 실전 경로 = 판정기(trading/judge) + 그 Decision 을 판정 JSON 으로 빚는 web/verdict_view(구간③은 web 을 import
    #   하지 않으므로 소스 글자로 읽는다).
    for name, src in (("trading/judge.py", inspect.getsource(judge)),
                      ("web/verdict_view.py", read_text(os.path.join(BASE, "web", "verdict_view.py")))):
        check('unobserved="exclude"' not in src and "unobserved='exclude'" not in src,
              "%s 실전 경로가 unobserved=exclude 를 쓰지 않아야(백테스트 전용)" % name)


def main():
    for name, fn in (("거래 시뮬레이터", t_trades), ("실전 경로 unobserved", t_live_path)):
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
    sys.exit(main())
