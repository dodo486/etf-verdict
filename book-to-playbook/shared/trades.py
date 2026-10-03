#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""매도·분할 규칙 리더(머리) — 트리(books/<slug>/tree.json)의 exit/sizing 규칙을 읽어 준다(책 무관).

이 모듈은 '규칙을 읽기만' 한다 — 체결·돈 루프는 계산기(shared/portfolio)의 글루가 돈다
(단방향 폭포수: 계산기가 여기 헬퍼를 호출해 규칙을 받아, 자기 포지션 상태를 cond 로 평가한다).

  · exits_of    : 책에 매도 규칙이 있으면 그걸, 없으면 표준(STANDARD)을. (규칙 목록, 출처) 로 돌려준다.
  · tranches_of : 분할 매수 차수. 저자가 비율을 안 줬으면(frac null) 전량 한 번(비율을 지어내지 않는다).
  · tranche_note: 위의 '비율 미명시' 사실을 결과에 표시할 문구.
  · standard_label / STANDARD : 책에 매도 규칙이 없는 상품에 쓰는 '책 무관 기본값'(결과엔 '표준 기준(책 아님)').
    표준 규칙의 숫자(+9%/−5%/10일)는 코드가 아니라 shared/exit_defaults.json 한 곳에 있다(하드코딩 0 — grade_rules 패턴).
"""
import json
import os

# 표준 매도 규칙의 '정본'은 코드가 아니라 데이터(shared/exit_defaults.json)에 있다 — 숫자를 코드에 복붙하지 않는다.
STANDARD = json.load(
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "exit_defaults.json"),
         encoding="utf-8"))["standard"]
FULL = [{"label": "전량", "frac": 1.0}]


def _std_const(field, op):
    """STANDARD 에서 (pos.<field> op 상수) 꼴 규칙의 상수를 꺼낸다 — 숫자를 다시 적지 않고 구조에서 끌어온다."""
    for r in STANDARD:
        w = r.get("when") or {}
        args = w.get(op)
        if args and isinstance(args[0], dict) and args[0].get("pos") == field:
            return args[1]
    return None


def standard_label():
    """표준 매도 규칙의 짧은 표시 문자열(예 '+9%/−5%/10일') — STANDARD config 에서 파생(단일 출처).
    숫자는 전부 exit_defaults.json 에서 끌어온다 — 화면·코드 어디에도 복붙하지 않는다."""
    tp, sl, dys = _std_const("ret", "ge"), _std_const("ret", "le"), _std_const("days", "ge")
    return ("+%g%%/%g%%/%g일" % (tp, sl, dys)).replace("-", "−")  # 음수 부호만 유니코드 글리프로(숫자는 config)


def exits_of(tree, prod):
    """(규칙 목록, 출처) — 책 규칙이 없으면 표준."""
    ex = tree["products"][prod].get("exit")
    return (ex, "책") if ex else (STANDARD, "표준 기준(책 아님)")


def tranches_of(tree, prod):
    """시뮬레이션에 쓰는 분할 — 저자가 비율을 안 줬으면(frac null) 전량 한 번으로 계산한다
    (비율을 지어내지 않는다 — 결과에 tranche_note 로 표시)."""
    trs = (tree["products"][prod].get("sizing") or {}).get("tranches") or FULL
    return FULL if trs[0].get("frac") is None else trs


def tranche_note(tree, prod):
    trs = (tree["products"][prod].get("sizing") or {}).get("tranches") or []
    return "분할 비율 저자 미명시 — 전량 한 번 매수로 계산" if trs and trs[0].get("frac") is None else None
