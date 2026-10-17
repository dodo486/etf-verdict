#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""트리 언어·출입구 검사 (책 무관 · 크기 고정).

무엇을 보나 — 시세를 계산하지 않고 '트리를 어떻게 적고 읽는가'만 본다
  1. 문법 — 모르는 키·인자 수·빈 구역·지운 연산은 거부, 올바른 노드·v3 트리는 통과(tree.gateway.validate)
  2. 트리 출입구(TreeGateway) 계약 — 판정·백테스트·검사기가 트리에 묻는 질문의 답 모양,
     형식이 틀린(옛 양식·폐지 표기) 트리는 거부
  3. 판때기(board)·노드 풀 — $self·$index → 티커 · 노드 레벨 on 걸러내기(OFF) · 필요 심볼·워밍업 ·
     같은 식은 상품·책을 넘어 노드 하나 · 수동·pos 를 품은 식은 상품끼리 공유하지 않음
  (계산기·등급·워밍업 가드·수동 답은 judge/verify_eval.py, 체결 워크는 backtest/verify_trading.py,
   화면 설명 구조는 web/verify_view.py 가 본다)

언제 돌리나: 트리 문법(tree/gateway.py 의 validate·이름표)이나 TreeGateway 를 바꿨을 때 —
  보통은 `python -m entry.run check` 가 함께 돌린다.

사용: python -m tree.verify_gateway   (실패 있으면 exit 1)
"""
import sys

from shared import paths  # noqa: F401  (UTF-8 출력)
from tree.gateway import BLOCK, BUY, CondError, Node, SELL, TreeGateway, bind, rule, synthetic, validate

FAILS = []


def check(ok, what):
    if not ok:
        FAILS.append(what)


C = {"px": "close", "sym": "X"}


def AVG(s, n):
    """N일 평균 — 전용 연산 없이 sum ÷ n (COND_DSL 6절 조합)."""
    return {"div": [{"sum": [s, n]}, n]}


# ------------------------------------------------------------------ 1. 문법
def t_syntax():
    bad = [
        {"gt": [C]}, {"sum": [C, 0]}, {"sum": [C, 2.5]}, {"ma": [C, 20]}, {"px": "price"}, {"foo": 1},
        {"gt": [C, 1], "lt": [C, 2]}, True, {"atleast": 2}, {"def": "없음"},
        {"across": {"syms": ["A"], "cond": C}}, {"manual": ""}, {"gt": [C, 1], "op": "above"},
        {"px": "close", "sym": "X", "tf": "5x"}, {"px": "close", "sym": "X", "tf": "m"}, {"px": "close"}, {"px": "close", "sym": "$s"},
        {"px": "close", "sym": "$빅테크"}, {"abs": [C, 1]}, {"case": [[C, 1]]}, {"case": [C, 1], "else": 0},
        {"max": [C]},
    ]
    for b in bad:
        try:
            validate(b)
            FAILS.append("거부해야 할 노드가 통과: %r" % (b,))
        except CondError:
            pass
    good = {"all": [{"gt": [C, AVG(C, 20)], "label": "20일선 위", "ref": "3-2"},
                    {"atleast": 2, "of": [{"manual": "장중"}, {"ge": [{"px": "volume", "sym": "X"}, 1]}]}]}
    try:
        validate(good)
    except CondError as e:
        FAILS.append("올바른 노드가 거부: %s" % e)
    try:
        validate({"case": [[{"gt": [C, 1]}, 2]], "else": {"px": "close", "sym": "X", "tf": "1d"}})
        for tf in ("1d", "1m", "5m", "15m", "30m", "1h", "1s"):   # 봉 단위는 1d + <수><단위 s/m/h/d/w> 전부 통과
            validate({"px": "close", "sym": "X", "tf": tf})
    except CondError as e:
        FAILS.append("올바른 case·tf 가 거부: %s" % e)
    W = {"gt": [C, 1]}
    good = synthetic(["X"], rule("비중", BUY, None, ("cash", {"case": [[W, 14]], "else": 34})),
                     rule("1차", BUY, None, ("budget", 0.25)),
                     rule("2차", BUY, {"ge": [{"pos": "ret"}, 3]}, ("budget", 0.75)),
                     rule("모름", BUY, {"manual": "저자 미명시: x"}, ("budget", "?")))
    try:
        TreeGateway.of(good)
    except CondError as e:
        FAILS.append("올바른 v3 트리가 거부: %s" % e)


# ------------------------------------------------------------------ 2. 트리 출입구(TreeGateway) 계약
def t_gateway():
    """판정·백테스트·검사기가 트리(v3 규칙 목록)에 묻는 질문의 답 모양 — {"rule"} 은 펼쳐서 건넨다.
    상품마다 달라지는 것은 해석기가 채운다($self·$index = products 의 index) — 폐지된 표기($s·names·across)는 거부."""
    W = {"gt": [C, AVG(C, 20)]}
    M = {"gt": [{"px": "close", "sym": "NQ=F", "tf": "1m"}, 0]}
    UP = lambda t: {"gt": [{"px": "close", "sym": t}, 0]}
    data = {
        "version": 3,
        "products": {"A": {"index": "^NDX", "note": "a 노트", "ref": "0-1"}, "B": {"index": "^SOX"}},
        "rules": [
            {"label": "20일선 위", "ref": "1-1", "value": W},
            {"label": "선물 양", "ref": "1-2", "on": ["A"],
             "then": [{"when": {"all": [{"rule": "20일선 위"}, M]}, "do": BUY}]},
            {"label": "지수 음", "ref": "2-1",
             "then": [{"when": {"lt": [{"px": "close", "sym": "$index"}, 0]}, "do": BLOCK}]},
            {"label": "비중", "ref": "4-1", "then": [{"do": BUY, "qty": {"of": "cash", "x": 30}}]},
            {"label": "1차", "ref": "4-2", "on": ["A"], "then": [{"do": BUY, "qty": {"of": "budget", "x": 0.5}}]},
            {"label": "2차", "on": ["A"], "then": [{"when": {"ge": [{"pos": "filled", "rule": "1차"}, 1]},
                                                   "do": BUY, "qty": {"of": "budget", "x": 0.5}}]},
            {"label": "익절", "ref": "5-1",
             "then": [{"when": {"ge": [{"pos": "ret"}, 9]}, "do": SELL, "qty": {"of": "held", "x": 1}}]},
            {"label": "묶음 상승", "ref": "6-1", "on": ["A"],
             "then": [{"when": {"atleast": 1, "of": [UP("N1"), UP("N2")]}, "do": BUY}]},
            {"label": "못 옮김", "ref": "9-9", "skip": "데이터 없음: x"}]}
    g = TreeGateway.of(data)
    check(g.products() == ["A", "B"] and g.has("A") and not g.has("Z"), "products/has")
    check(g.index("A") == "^NDX" and g.index("B") == "^SOX" and g.note("A") == "a 노트", "index/note")
    ent = g.gate("A", BUY)["any"]
    check([n["label"] for n in ent] == ["선물 양", "묶음 상승"] and g.gate("B", BUY) == {"any": []},
          "gate(산다) = 산다 갈래(포지션·조건 없는 갈래 제외, on 반영) %r" % ent)
    check(ent and ent[0]["all"][0] == dict(W, label="20일선 위", ref="1-1") and ent[0]["allprod"] is False,
          "{rule} 는 그 규칙 value 로 펼치고 이름·소절을 싣는다 %r" % (ent[:1],))
    check(len(ent) > 1 and ent[1]["of"] == [UP("N1"), UP("N2")], "여러 종목 = atleast·of 그대로(각 잎 구체 티커)")
    av = g.gate("A", BLOCK)["any"]
    check([(n["label"], n["allprod"]) for n in av] == [("지수 음", True)], "gate(안 산다) %r" % av)
    try:
        g.gate("A", SELL)
        FAILS.append("판다는 등급 동사가 아닌데 gate 가 받음")
    except CondError:
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
    check(g.symbols() == {"A", "B", "X", "^NDX", "^SOX", "NQ=F", "N1", "N2"} and g.symbols(["B"]) == {"B", "^SOX"},
          "symbols = 상품 + 식의 sym %r · %r" % (g.symbols(), g.symbols(["B"])))
    check(g.warmup("A") == 19 and g.warmup("B") == 0 and g.warmup() == 19, "warmup")
    check(g.refs() == {"0-1", "1-1", "1-2", "2-1", "4-1", "4-2", "5-1", "6-1", "9-9"}, "refs %r" % g.refs())
    check(g.skips() == [{"rule": "못 옮김", "ref": "9-9", "reason": "데이터 없음: x"}], "skip 규칙")
    check(not TreeGateway({}) and bool(g) and TreeGateway.load("__없는책__") is None, "빈·없는 트리")
    check(W in g.conditions() and {"all": [{"rule": "20일선 위"}, M]} in g.conditions(), "conditions = 적힌 그대로의 조건식")
    cd = {c.label: c for c in g.cards()}
    check(list(cd) == g.labels() and cd["20일선 위"].value == W and cd["20일선 위"].branches == []
          and cd["선물 양"].on == ["A"] and cd["선물 양"].branches[0].when == {"all": [{"rule": "20일선 위"}, M]}
          and cd["1차"].branches[0].qty == ("budget", 0.5) and cd["1차"].branches[0].when is None
          and cd["못 옮김"].skip == "데이터 없음: x" and cd["익절"].ref == "5-1",
          "cards = 규칙 카드(적힌 그대로 — 참조 안 펼침)")
    # on 은 상품만 · qty 식의 {"rule"} 은 펼친다 · 규칙 note 는 갈래까지
    g2 = TreeGateway.of(dict(data, rules=data["rules"] + [rule("A 전용 익절", SELL, W, ("held", 0.5), on=["A"], note="메모"),
                                                          rule("식 비중", BUY, None, ("cash", {"rule": "20일선 위"}))]))
    s2 = [r for r in g2.sells("A") if r.label == "A 전용 익절"]
    check(s2 and s2[0].note == "메모" and not [r for r in g2.sells("B") if r.label == "A 전용 익절"],
          "on 반영 · note 전달")
    check(TreeGateway.of(dict(data, rules=[rule("식", BUY, None, ("cash", {"rule": "w"})),
                                           {"label": "w", "value": W}])).weight("A").qty.x == dict(W, label="w"),
          "qty 식의 {rule} 펼침")
    check(g.refs() >= {"0-1"}, "refs 에 상품 ref 포함")
    # 규칙 단위 질문(구간② 검사기) — 이름 목록 · 뜻(펼침/그대로) · 측정 · why · 옛 양식 키
    check(g.labels()[:2] == ["20일선 위", "선물 양"] and g.body("없음") is None, "labels/body 없는 이름")
    b2 = g.body("선물 양")
    check(b2["products"] == ["A"] and b2["branches"][0]["do"] == BUY
          and b2["branches"][0]["when"]["all"][0] == dict(W, label="20일선 위", ref="1-1")
          and g.body("선물 양", expand=False)["branches"][0]["when"]["all"][0] == {"rule": "20일선 위"},
          "body 펼침/그대로 %r" % b2)
    check(g.value("20일선 위") == W and g.value("선물 양") is None and g.why("선물 양") is None
          and TreeGateway.of(dict(data, rules=data["rules"] + [dict(rule("w", BUY, W), why="원문 3-1")])).why("w") == "원문 3-1",
          "value/why")
    bad = dict(data, rules=data["rules"] + [rule("x", BUY, {"rule": "없는 이름"})])
    check(TreeGateway.of(bad).gate("A", BUY)["any"][-1].get("manual", "").startswith("연산 없음: 미해결 참조"),
          "없는 이름 참조는 수동(연산 없음)으로 드러낸다")
    R0 = {"label": "r", "then": [{"when": W, "do": SELL}]}
    old_sym = lambda sym: dict(data, rules=[{"label": "r", "then": [{"when": {"lt": [{"px": "close", "sym": sym}, 0]},
                                                                      "do": BLOCK}]}])
    for broken in (dict(data, version=2), dict(data, products={}), dict(data, rules=[]),
                   dict(data, rules=data["rules"] + [data["rules"][0]]),
                   dict(data, rules=data["rules"] + [rule("y", "쉰다", {"all": []})]),
                   dict(data, review={}),                                         # 옛 양식 키
                   dict(data, products={"A": {"ref": "0-1", "exit_note": "x"}}),
                   dict(data, names={"$묶음": {"syms": ["N1"]}}),                    # 폐지: 이름 심볼
                   old_sym("$s"), old_sym("$빅테크"),                                 # 폐지: $s·이름 심볼
                   dict(data, products={"A": {"index": "^NDX"}, "B": {}}),                  # $index 인데 상품 B 에 index 없음
                   dict(data, rules=[{"label": "r", "then": [{"when": {"lt": [{"px": "close"}, 0]}, "do": BLOCK}]}]),  # sym 생략
                   dict(data, rules=[{"label": "r", "then": [{"when": {"ge": [{"across": {"syms": ["N1"], "cond": UP("N1")}}, 1]},
                                                              "do": BUY}]}]),     # 폐지: across
                   dict(data, rules=[dict(R0, scale=0.5)]),                         # 규칙에 모르는 키
                   dict(data, rules=[{"label": "r", "then": [{"when": W, "do": SELL, "sell": "all"}]}]),
                   dict(data, rules=[{"label": "r", "then": [{"when": W, "do": SELL, "qty": {"of": "cash", "x": 1}}]}]),
                   dict(data, rules=[{"label": "r", "then": [{"when": W, "do": BLOCK, "qty": {"of": "held", "x": 1}}]}]),
                   dict(data, rules=[{"label": "r", "then": [{"when": W, "do": BUY, "repeat": True}]}]),
                   dict(data, rules=[dict(R0, skip="연산 없음: x")]),                  # then 과 skip 같이
                   dict(data, rules=[{"label": "r", "note": "식 없음"}]),               # then·value·skip 다 없음
                   dict(data, rules=[dict(R0, on=["Z"])]),                            # on 이 없는 종목
                   dict(data, rules=[{"then": R0["then"]}]),                         # label 없음
                   dict(data, rules=[{"label": "r", "then": [{"do": SELL}]}]),     # 판다인데 when 없음
                   dict(data, rules=[{"label": "r", "value": {"foo": 1}}])):           # 참조 안 된 이름 조건도 문법 검사
        try:
            TreeGateway.of(broken)
            FAILS.append("형식이 틀린 트리가 통과: %r" % sorted(broken))
        except CondError:
            pass


# ------------------------------------------------------------------ 3. 판때기·노드 풀
def t_board():
    P = lambda sym: {"px": "close", "sym": sym}
    UPS = lambda sym: {"gt": [P(sym), {"lag": [P(sym), 1]}]}
    only_b = dict(UPS("$self"), on=["B"], label="B 만")
    data = synthetic({"A": "^IX", "B": None},
                     rule("자기 상승", BUY, {"all": [UPS("$self"), only_b]}),
                     rule("지수 하락", BLOCK, {"lt": [P("$index"), 0]}, on=["A"]),
                     rule("엔비 상승", BUY, UPS("NVDA")),
                     rule("확인", BUY, {"manual": "눈으로 확인"}),
                     rule("비중", BUY, None, ("cash", {"sum": [P("$self"), 5]})),
                     rule("손절", SELL, {"lt": [{"pos": "ret"}, -8]}, ("held", 1)))
    g = TreeGateway.of(data)
    a, b = g.board("A"), g.board("B")
    check(g.board("A") is a, "판때기는 상품마다 한 번(같은 객체)")
    gate_a = a.gates[BUY]["any"]
    check(isinstance(a.gates[BUY], Node) and gate_a[0]["all"][0]["gt"][0] == {"px": "close", "sym": "A"},
          "판때기: $self → 상품 티커")
    check(a.gates[BLOCK]["any"][0]["lt"][0] == {"px": "close", "sym": "^IX"}, "판때기: $index → 그 상품 지수")
    check(b.gates[BLOCK] == {"any": []}, "규칙 on: 대상 밖 상품의 판때기엔 그 갈래가 없다")
    off = gate_a[0]["all"][1]
    check(off.off and off == {"all": []} and off.syms == {"A"} and not b.gates[BUY]["any"][0]["all"][1].off,
          "노드 레벨 on: 대상 밖 상품은 OFF('항상 참'), 대상 상품은 그대로")
    check(all(k not in n for n in (a.gates[BUY], gate_a[0]) for k in ("label", "ref", "allprod", "on")),
          "묶인 노드엔 메타가 없다")
    check(a.symbols == {"A", "^IX", "NVDA"} and b.symbols == {"B", "NVDA"} and g.symbols() == {"A", "^IX", "B", "NVDA"},
          "판때기 필요 심볼 = 자기 + 지수 + 구체 티커: %r %r" % (sorted(a.symbols), sorted(b.symbols)))
    check(a.warmup == 1 and g.warmup() == 1, "판때기 워밍업 = 등급 식의 가장 긴 lookback")
    check(a.weight == {"sum": [{"px": "close", "sym": "A"}, 5]} and len(a.sells) == 1 and a.tranches == [],
          "판때기: 비중 식·판다 갈래 묶음")
    # 노드 풀 — 같은 식 = 같은 노드(상품·책을 넘어), 수동·pos 를 품은 식은 상품마다
    check(gate_a[1] is b.gates[BUY]["any"][1], "같은 식(NVDA 상승)은 상품끼리 노드 하나")
    other = TreeGateway.of(synthetic(["NVDA"], rule("자기", BUY, dict(UPS("$self"), label="딴 이름"))))
    check(other.board("NVDA").gates[BUY]["any"][0] is gate_a[1], "다른 책의 $self(NVDA) 상승 = 같은 노드(라벨 무관)")
    check(gate_a[2] is not b.gates[BUY]["any"][2] and gate_a[2].mkey == "눈으로 확인",
          "수동 잎은 상품끼리 공유하지 않는다(답이 상품별)")
    check(a.sells[0] is not b.sells[0] and not a.sells[0].pure, "pos 식은 상품끼리 공유하지 않는다")
    unk = {"ge": [P("$self"), "?"]}
    concrete = bind({"ge": [P("A"), "?"]}, "A")
    check("$self" in bind(unk, "A").mkey and bind(unk, "A") is not concrete and "$self" not in concrete.mkey,
          "\"?\" 식의 답 열쇠는 적힌 식 그대로($self — 묶은 티커가 아님)")
    check(bind(unk, "A") is bind(dict(unk), "A") and bind(unk, "A") is not bind(unk, "B"), "\"?\" 식: 같은 상품끼리만 같은 노드")


def main():
    for name, fn in (("문법", t_syntax), ("트리 출입구 계약", t_gateway), ("판때기·노드 풀", t_board)):
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
        print("트리 언어 검사 실패 %d건 — 정지" % len(FAILS))
        return 1
    print("트리 언어 검사 통과 — 문법·출입구·판때기")
    return 0


if __name__ == "__main__":
    sys.exit(main())
