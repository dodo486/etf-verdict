#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""화면층 검사기 — 조건 → 화면 항목(condition_view._view)의 구조·측정 증거 (책 무관 · 크기 고정).

판정 JSON 의 view 는 화면 3값 엔진(checklist-ui)이 사람이 체크한 수동 조건으로 등급을 다시 낼 때 쓰는 모양이다.
그 모양(논리 노드의 op·kids, 라벨 없는 잎의 hidden, "?" 창 설명)을 손으로 정한 답과 대조한다.

사용: python -m web.verify_view   (실패 있으면 exit 1)
"""
import sys
from collections import namedtuple

from shared import paths  # noqa: F401  (UTF-8 출력)
from checklist import grade
from checklist.tree_gateway import TreeGateway, empty_product, synthetic
from web import condition_view as cv

Candle = namedtuple("Candle", "date open high low close volume")
C = {"px": "close"}
FAILS = []


def check(ok, what):
    if not ok:
        FAILS.append(what)


def t_view():
    """화면 설명 구조 — 논리 묶음·not 아래 수동·라벨 없는 잎(hidden)·"?" 창 설명."""
    xs = [100.0] * 30 + [130.0]
    cal = ["2022%04d" % i for i in range(len(xs))]
    hist = {"X": [Candle(d, c, c, c, c, 1000) for d, c in zip(cal, xs)]}
    jump = {"ge": [{"pct": [C, 1]}, 20]}
    tree = TreeGateway.of(synthetic({"X": empty_product()}))
    pe = grade.ProductEval(tree, "X", hist, cal)
    node = {"all": [dict(jump, label="급등", ref="1"), {"not": {"label": "수동", "manual": "x"}}]}
    v = cv._view(node, pe.defs, pe.ctx[None], len(xs) - 1)
    check(v["op"] == "all" and v["kids"][0]["v"] is True and v["kids"][0]["label"] == "급등"
          and v["kids"][1]["op"] == "not" and v["kids"][1]["kids"][0]["manual"] == "x", "view 구조 %r" % v)
    hid = cv._view({"atleast": 1, "of": [jump, {"manual": "y"}]}, pe.defs, pe.ctx[None], len(xs) - 1)
    check(hid["op"] == "atleast" and hid["n"] == 1 and hid["kids"][0].get("hidden") is True
          and hid["kids"][0]["v"] is True, "라벨 없는 잎은 hidden 으로 값과 함께 %r" % hid)
    # 창 길이·lag 가 "?"(저자 미명시)인 식도 근거 설명이 죽지 않는다 — "?일" 로 보인다
    unk = {"label": "최근 ?일 급등", "ge": [{"pct": [C, "?"]}, {"lowest": [C, "?"]}]}
    d = cv._view(unk, pe.defs, pe.ctx[None], len(xs) - 1).get("detail") or []
    check(d and d[0]["lhsd"] == "?일 전 대비 변화율" and d[0]["rhsd"] == "?일 최저", "\"?\" 창 설명 %r" % d)


def main():
    before = len(FAILS)
    try:
        t_view()
    except Exception as e:  # noqa: BLE001 — 검사기 자체가 죽어도 실패로 센다
        FAILS.append("화면 설명 구조: 예외 %r" % e)
    n = len(FAILS) - before
    print("  %s 화면 설명 구조%s" % ("✅" if n == 0 else "❌", "" if n == 0 else " — 실패 %d" % n))
    if FAILS:
        for f in FAILS[:30]:
            print("    · " + f)
        print("화면층 검사 실패 %d건 — 발행 정지" % len(FAILS))
        return 1
    print("화면층 검사 통과 — 화면 설명 구조")
    return 0


if __name__ == "__main__":
    sys.exit(main())
