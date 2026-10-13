#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""화면층 검사기 — 조건 설명(web/explain.view — 값은 판단자 ProductJudge.value)의 구조·측정 증거, 트리 ↔ 화면 대조
(트리 규칙이 전부 화면에 식과 함께 나오나 — web/verdict_view.uncovered)(책 무관 · 크기 고정).

판정 JSON 의 view 는 화면(checklist-ui)이 조건 칸을 그리고 수동 조건의 답 열쇠(mkey·shared)를 만드는 모양이다
(값은 서버가 낸다 — 서버 권위). 그 모양(논리 노드의 op·kids, 잎의 식 글 expr, "?" 창 설명)을 손으로 정한 답과
대조한다.

(책 페이지 구획·UI 사본은 페이지를 조립하는 web/book_page.py 가 본다.)

사용: python -m web.verify_view   (실패 있으면 exit 1)
"""
import sys
from collections import namedtuple

from shared import paths  # noqa: F401  (UTF-8 출력)
from tree.gateway import BLOCK, BUY, SELL, rule, synthetic
from judge.judge import Judge
from web.explain import view
from web.verdict_view import _format, uncovered

Candle = namedtuple("Candle", "date open high low close volume")
C = {"px": "close", "sym": "X"}
FAILS = []


def check(ok, what):
    if not ok:
        FAILS.append(what)


def t_view():
    """화면 설명 구조 — 논리 묶음·not 아래 수동·잎의 식 글(라벨·수동이 식을 가리지 않음)·"?" 창 설명."""
    xs = [100.0] * 30 + [130.0]
    cal = ["2022%04d" % i for i in range(len(xs))]
    hist = {"X": [Candle(d, c, c, c, c, 1000) for d, c in zip(cal, xs)]}
    jump = {"ge": [{"mul": [{"sub": [{"div": [C, {"lag": [C, 1]}]}, 1]}, 100]}, 20]}   # 전일 대비 +20% 이상
    judge = Judge.of(synthetic(["X"])).product("X", hist, days=cal)
    val = lambda n: judge.value(n, len(xs) - 1)          # noqa: E731
    node = {"all": [dict(jump, label="급등", ref="1"), {"not": {"label": "수동", "manual": "x"}}]}
    v = view(node, val)
    check(v["op"] == "all" and v["kids"][0]["v"] is True and v["kids"][0]["label"] == "급등"
          and v["kids"][1]["op"] == "not" and v["kids"][1]["kids"][0]["manual"] == "x", "view 구조 %r" % v)
    hid = view({"atleast": 1, "of": [jump, {"manual": "y"}]}, val)
    check(hid["op"] == "atleast" and hid["n"] == 1 and hid["kids"][0]["v"] is True
          and hid["kids"][0].get("expr") == "(((X 종가 ÷ X 종가(1일 전)) − 1) × 100) ≥ 20",
          "라벨 없는 잎도 숨기지 않고 식 글로 %r" % hid)
    # 라벨·수동 사유가 식을 가리지 않는다 — 라벨 달린 잎·"?" 수동 잎 모두 식 글(expr)을 단다
    lab = view(dict(jump, label="급등"), val)
    check(lab.get("expr", "").endswith("≥ 20"), "라벨 달린 잎의 식 글 %r" % lab)
    q = view({"label": "기준 미명시", "gt": [C, "?"]}, val)
    check(q.get("manual") and q.get("expr") == "X 종가 > ?(미명시)", "\"?\" 수동 잎의 식 글 %r" % q)
    # 상품 판 — 다른 상품 전용(노드 on) 조건은 꺼짐(off)으로 식과 함께, $self·$index 글은 실제 티커로
    off = view({"label": "Y 전용", "on": ["Y"], "gt": [C, 1]}, val, "X")
    check(off.get("off") == ["Y"] and off.get("expr") == "X 종가 > 1", "다른 상품 전용 조건 %r" % off)
    me = view({"label": "자기", "gt": [{"px": "close", "sym": "$self"}, {"px": "close", "sym": "$index"}]},
              lambda n: None, "X", "IX")                    # 글만 본다(값은 판단자 몫)
    check(me.get("expr") == "X 종가 > IX 종가" and me["detail"][0]["lhsd"] == "X 종가", "역할 → 실제 티커 %r" % me)
    # 창 길이·lag 가 "?"(저자 미명시)인 식도 근거 설명이 죽지 않는다 — "?일" 로 보인다
    unk = {"label": "최근 ?일 급등", "ge": [{"lag": [C, "?"]}, {"lowest": [C, "?"]}]}
    d = view(unk, val).get("detail") or []
    check(d and d[0]["lhsd"] == "X 종가 ?일 전" and d[0]["rhsd"] == "?일 최저", "\"?\" 창 설명 %r" % d)


def t_cover():
    """트리 ↔ 화면 — 트리의 규칙은 전부 화면 어딘가(칸 또는 칸 밖)에, 조건은 식 글과 함께 나온다(조용히 빠지지 않는다)."""
    xs = [100.0] * 30 + [130.0]
    cal = ["2022%04d" % i for i in range(len(xs))]
    hist = {"X": [Candle(d, c, c, c, c, 1000) for d, c in zip(cal, xs)]}
    up = {"gt": [C, {"lag": [C, 1]}]}
    tree = synthetic(["X"],
                     rule("오름 피함", BLOCK, {"rule": "쓰는 이름"}, ref="1"),
                     {"label": "쓰는 이름", "ref": "1", "value": up},
                     {"label": "안 쓰는 이름", "ref": "2", "value": {"lt": [C, 50]}},
                     {"label": "못 옮김", "ref": "3", "skip": "데이터 없음: 계좌"},
                     rule("보유 중 추가", BUY, {"gt": [{"pos": "ret"}, 5]}, ref="4"),
                     rule("기준 미명시", BUY, {"gt": [C, "?"]}, ref="5"),
                     rule("급락 매도", SELL, {"lt": [C, 90]}, ref="6"))
    book = Judge.of(tree)
    top = _format("합성", book, hist, book.decisions(hist))
    bad = uncovered(book.tree, top)
    check(not bad, "트리 ↔ 화면 대조 %r" % bad)
    kinds = {x["label"]: x["kind"] for x in top["outside"]}
    check(kinds == {"안 쓰는 이름": "name", "못 옮김": "skip", "보유 중 추가": "branch"}, "칸 밖 규칙 %r" % kinds)
    v = top["verdicts"][0]
    check(v["sells"][0]["when"] == "X 종가 < 90", "판다 조건 글 %r" % v["sells"][0])
    q = [k for k in v["gates"][BUY]["kids"] if k.get("label") == "기준 미명시"]
    check(q and q[0].get("manual") and q[0].get("expr") == "X 종가 > ?(미명시)", "\"?\" 산다 규칙의 식 글 %r" % q)


def main(argv=()):
    before = len(FAILS)
    for name, t in (("화면 설명 구조", t_view), ("트리 ↔ 화면 대조", t_cover)):
        try:
            t()
        except Exception as e:  # noqa: BLE001 — 검사기 자체가 죽어도 실패로 센다
            FAILS.append("%s: 예외 %r" % (name, e))
    n = len(FAILS) - before
    print("  %s 화면 설명 구조%s" % ("✅" if n == 0 else "❌", "" if n == 0 else " — 실패 %d" % n))
    if FAILS:
        for f in FAILS[:30]:
            print("    · " + f)
        print("화면층 검사 실패 %d건 — 정지" % len(FAILS))
        return 1
    print("화면층 검사 통과 — 화면 설명 구조 · 트리 ↔ 화면 대조")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
