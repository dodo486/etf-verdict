#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""판정 틀(Board) JSON — 상품별 심볼·조건 트리를 시세 없이 정적으로 돌려준다.

/api/board?slug=<책> 이 이걸 쓴다. 판정 틀은 tree.json 이 바뀌지 않는 한 고정이며
시세와 무관하다 — 외부 시스템이 "어떤 심볼을 가져와서 어떤 조건을 평가해야 하나"를
확인하는 단 하나의 창구."""
from tree.gateway import BUY, BLOCK, GATES
from judge.judge import Judge, GRADE_RULES, GRADES
from web import explain


def _binary_mode():
    """grade_rules가 이진(규칙 1개·default=avoid)인가."""
    rules = GRADE_RULES.get("rules", [])   # noqa: tree-key — grade_rules.json, 트리 아님
    return len(rules) == 1 and GRADE_RULES.get("default") == "avoid"


def _prune_redundant_avoid(gates):
    """이진 체계에서 산다 게이트에도 있는 규칙의 안 산다 브랜치 제거.
    같은 규칙이 산다·안 산다 둘 다 있으면 안 산다는 NOT 산다의 subset —
    default=avoid로 어차피 잡히므로 중복."""
    buy_labels = {k.get("label") for k in (gates.get(BUY) or {}).get("kids", []) if k.get("label")}
    avoid = gates.get(BLOCK)
    if not avoid or not buy_labels:
        return gates
    kept = [k for k in avoid.get("kids", []) if k.get("label") not in buy_labels]
    return dict(gates, **{BLOCK: dict(avoid, kids=kept)})


def board_data(slug):
    """책 한 권의 판정 틀 — {slug, products, grade_rules}.
    grade_rules = 게이트 결과(opt/pes)를 최종 등급으로 바꾸는 사다리 — 게이트 트리와 함께 외부 시스템에 건네는 두 번째 조각."""
    j = Judge.open(slug)
    if not j:
        return {"slug": slug, "products": {}, "grade_rules": GRADE_RULES}
    out = {"slug": slug, "products": {}, "grade_rules": GRADE_RULES, "grades": GRADES}
    for prod in j.products():
        pj = j.product(prod, {}, days=["0"])
        board = j.tree.board(prod)
        gates = {do: explain.static_view(pj.gate(do), pj.blank_value, prod, pj.index)
                 for do in GATES}
        if _binary_mode():
            gates = _prune_redundant_avoid(gates)
        out["products"][prod] = {
            "index": pj.index,
            "symbols": sorted(board.symbols),
            "warmup": board.warmup,
            "gates": gates,
        }
    return out
