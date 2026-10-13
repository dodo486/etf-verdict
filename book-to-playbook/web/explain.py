#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조건 설명(화면층, 책 무관) — 조건 노드 하나 → 그날 값·측정 증거가 달린 설명 항목.

계산하지 않는다 — 값은 부르는 쪽이 넘기는 값 함수 val(n)(= 그 노드의 그날 값, 판단자 ProductJudge.value)로만 얻는다.
여기는 그 값을 화면이 그리는 중첩 항목으로 빚기만 한다(식 → 낱말은 web/text).
  · view         노드 하나 → 설명 항목 하나(중첩 설명 + 그날 값 + 측정 증거)
  · static_view  값 없는 규칙 설명(시세·포지션 없이 — val 은 ProductJudge.blank_value)
  · _measure 외  '무엇을 재서 얼마였나'(측정 증거)
"""
from tree.gateway import (
    ARITH, CMP, CondError, is_manual, is_unknown, manual_key, META, _op_of, product_specific, ROLES, UNKNOWN,
    UNKNOWN_REASON)
from web import text
from web.raw_tree import e as prose

LOGICAL = ("all", "any", "atleast", "not")


# ------------------------------------------------------------------ 측정 증거(실제 값)
# 조건의 ●/○ 밑에 '무엇을 재서 그 값이 얼마였나'를 실어보낸다 — 사용자가 판정을 검증·신뢰할 수 있게.
# 판단자는 어차피 비교 양쪽 값을 계산해 참/거짓을 낸다. 그 값을 값 함수로 받아 뷰에 담는 것뿐이다.
def _meas_val(e, val):
    """값 표현식 하나를 그날 실제 숫자로 — 못 재면 None. 표시용이라 자리수만 줄인다(계산엔 안 쓴다)."""
    try:
        v = val(e)
    except Exception:
        return None
    if v is None or isinstance(v, bool):
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if v != v:                                   # NaN
        return None
    a = abs(v)
    return round(v, 1) if a >= 100 else round(v, 2) if a >= 1 else round(v, 3)


def _describe_operand(e):
    """값 표현식 → 짧은 사람 설명(없으면 '' — 그럼 숫자만 보여준다). 복합식(산술 등)은 라벨이 설명하므로 생략."""
    if not isinstance(e, dict):
        return ""                                # 상수(기준값) — 숫자 자체로
    try:
        op = _op_of(e)
    except CondError:
        return ""
    if op == "px":
        sym = e["sym"]
        base = text.px_name(e["px"])
        pre = text.intraday(e)                   # 장중 분봉 vs 확정 일봉 구분
        core = base if sym in ROLES else "%s %s" % (sym, base)   # 역할($self·$index)은 이름 없이, 구체 티커는 이름과 함께
        return pre + core
    if op in ("highest", "lowest", "sum"):
        return "%s일 %s" % (text.short_n(e[op][1]), text.WINDOW[op])
    if op == "lag":
        inner = _describe_operand(e["lag"][0])
        return ("%s " % inner if inner else "") + text.ago(text.short_n(e["lag"][1]))
    if op == "barssince":
        return "마지막 참 이후 일수"
    if op == "pos":
        return text.pos_short(e["pos"]) + (text.pos_rule(e) if e["pos"] == "filled" else "")
    if op == "valuewhen":                        # 그 조건이 마지막으로 참이던 날의 값
        return _describe_operand(e["valuewhen"][1]) + "(최근 신호일)"
    if op in ("minsince", "maxsince"):           # 신호 이후 최저/최고
        return text.SINCE[op] + " " + _describe_operand(e[op][1]) + "(신호 이후)"
    return ""                                    # add/sub/mul/div/case … 복합 → 숫자만(산술은 inputs 로 분해)


def _unit_of(e):
    """값 표현식의 단위 힌트(%·일·배) — 모르면 '' (라벨이 단위를 말하므로 비워도 된다)."""
    if not isinstance(e, dict):
        return ""
    try:
        op = _op_of(e)
    except CondError:
        return ""
    if op == "barssince":
        return text.BARSSINCE_UNIT
    if op == "div":
        return text.DIV_UNIT
    if op == "pos":
        return text.pos_unit(e["pos"])
    return ""


def _inputs_of(e, val, acc, seen, top=True):
    """파생값이 '무슨 원시 숫자로 나왔나'를 [{d, v}]로 모은다 — 사용자가 검증할 수 있게.
    · 산술(합·차·비율)은 안의 시세 잎들을 보여준다. 예: 고가 771 · 종가 770.6.
    · LHS 자체가 단일 잎(종가·20일선·연속일수)이면 분해하지 않는다 — 피연산자가 이미 값으로 보인다.
    중복 설명은 한 번만."""
    if not isinstance(e, dict):
        return

    def add(d, v):
        if d and d not in seen:
            seen.add(d)
            acc.append({"d": d, "v": v})

    try:
        op = _op_of(e)
    except CondError:
        return
    if op in ARITH:
        for sub in e[op]:
            _inputs_of(sub, val, acc, seen, top=False)
        return
    if op == "abs":
        _inputs_of(e["abs"], val, acc, seen, top=False)
        return
    # 단일 잎(px·lag·창…): 산술 안쪽이면 값으로 보여주고, LHS 통째면(top) 분해하지 않는다
    if not top and op in ("px", "lag", "barssince", "highest", "lowest", "sum", "pos"):
        add(_describe_operand(e), _meas_val(e, val))
    # case·valuewhen 등은 생략(라벨이 설명을 맡는다)


def _measure(node, val, top=True):
    """표시되는 조건 하나가 '무엇을 재서 얼마였나' — [{op, lhs, lhsd, rhs, rhsd, unit, inputs?}, …].
    하위에 라벨 달린 조건이 있으면 멈춘다(그 조건이 자기 증거를 따로 보여준다)."""
    if not isinstance(node, dict):
        return []
    if not top and (node.get("label") or is_manual(node)):
        return []
    try:
        op = _op_of(node)
    except CondError:
        return []
    if op in CMP:
        a, b = node[op]
        lhsd = _describe_operand(a)
        fact = {"op": op,
                "lhs": _meas_val(a, val), "lhsd": lhsd,
                "rhs": _meas_val(b, val),
                "rhsd": _describe_operand(b),     # "?"(저자가 안 준 기준)면 rhs None·rhsd '' — 화면이 '기준 ?'로
                "unit": _unit_of(a)}
        ins = []                           # 파생값(변화율·산술)이면 무슨 원시 숫자로 나왔는지 함께 보여준다
        _inputs_of(a, val, ins, set())
        if ins:
            fact["inputs"] = ins
        return [fact]
    if op == "not":
        kids = [node["not"]]
    elif op in ("all", "any"):
        kids = node[op]
    elif op == "atleast":
        kids = node["of"]
    else:
        return []
    facts = []
    for c in kids:
        facts += _measure(c, val, top=False)
    return facts


def view(node, val):
    """노드 하나 → 화면 항목 하나 {v, op?, n?, kids?, label?, ref?, manual?, note?, expr?}.

    · 논리 노드(all/any/atleast/not)는 op 와 자식 항목 전부를 담는다 — 화면이 사람이 체크한 수동 조건으로
      같은 3값 논리를 다시 계산할 수 있게(not 아래 수동은 극성이 뒤집힌다 — cond 와 같은 규칙).
    · 그 밖의 노드는 그날 값(v)이 고정된 잎이다. 잎은 **식 글(expr)을 항상 단다** — 라벨·수동 사유가 식을 가리지 않게
      (라벨만 보이고 무엇을 재는지 안 보이면 사람이 트리를 검증할 수 없다). 라벨 없는 잎도 숨기지 않고 식 글로 보인다.
      안쪽에 라벨 달린 노드가 있으면 참고용 kids(op 없음 — 다시 계산하지 않는다)로 붙인다.
    val(n) = 노드 n 의 그날 값(부르는 쪽이 판단자에게서 — 수동 = 모름(None)·사람이 답했으면 그 답)."""
    skip = ("of", "sym", "tf", "else")
    op = next((k for k in node if k not in META and k not in skip), None)
    item = {"v": val(node)}
    for k in ("label", "ref", "note"):
        if node.get(k):
            item[k] = node[k]
    if node.get("allprod"):                      # 공통(on 없음) 규칙 — 화면이 상품 카드에서 빼고 공통 섹션으로 모은다
        item["allprod"] = True
        # 상품에 안 기대는 공통 규칙($self·$index·pos·노드 on 안 씀)은 상품마다 값·질문이 같다 → 화면이 한 줄로 합쳐도 된다는 힌트.
        #   답 열쇠(mkey)는 지금 규칙 그대로(상품별) — 화면이 그 한 줄의 수동 답을 세 상품 열쇠에 같이 넣는다(서버 무변).
        if not product_specific(node):
            item["allsame"] = True
    if op in LOGICAL:
        # 묶음(all/any/atleast/not)은 '?' 가 안에 있어도 **항상 펼친다** — 사람이 확인할 건 묶음 자체가 아니라
        #   그 안의 sub-조건들이다(각 '?' sub 는 재귀로 자기 수동 잎이 된다). 접어서 "수동 확인" 하나로 숨기지 않는다.
        kids = node[op] if op in ("all", "any") else (node["of"] if op == "atleast" else [node["not"]])
        item["op"] = op
        if op == "atleast":
            item["n"] = node["atleast"]
            if node["atleast"] == UNKNOWN:  # 몇 개 필요한지 저자 미명시 — 묶음은 수동(사람이 개수 판단), 단 후보는 펼친다
                item["manual"] = UNKNOWN_REASON
                item["mkey"] = manual_key(node)
        item["kids"] = [view(k, val) for k in kids]
    elif is_unknown(node):
        # 저자가 숫자를 안 준 식("?") — 사람이 정하는 수동 잎. 답을 묶는 열쇠는 식(문장 아님 — 같은 식 = 같은 질문).
        item["manual"] = UNKNOWN_REASON
        item["mkey"] = manual_key(node)
    elif op == "manual":
        item["manual"] = node["manual"]
    else:
        inner = [view(k, val) for k in _labeled_inside(node)]
        if inner:
            item["kids"] = inner
    if op not in LOGICAL and op != "manual":
        item["expr"] = prose(node)               # 식 글(원시 트리 보기와 같은 문장) — "?" 수동 잎도 무엇을 정하는지 보인다
    # 측정 증거 — 화면에 보이는 조건(라벨/수동/관측)에 그날 실제 값을 붙인다. "?" 식이면 알려진 쪽 값이
    #   근거 숫자다(기준은 저자가 안 줬으니 사람이 그 숫자를 보고 참/거짓을 고른다 — 깜깜이 판단 방지).
    if node.get("label") or is_manual(node):
        facts = _measure(node, val)
        if facts:
            item["detail"] = facts
    return item


def _labeled_inside(node):
    """잎 노드 안쪽의 가장 바깥 라벨 노드들(참고 표시용)."""
    out = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("label") or "manual" in n:
                out.append(n)
                return
            for k, x in n.items():
                if k not in META:
                    walk(x)
        elif isinstance(n, list):
            for x in n:
                walk(x)
    for k, x in node.items():
        if k not in META:
            walk(x)
    return out


def static_view(node, val):
    """포지션·시세 없이 보이는 규칙 설명(값 없음) — 라벨·논리 묶음·수동 사유만(비중·분할·판다 갈래, 시세 없는 상품).
    val = 시세·포지션 없는 값 함수(ProductJudge.blank_value)."""
    if node is None:
        return None

    def strip(it):
        it = {k: x for k, x in it.items() if k != "v"}
        if "kids" in it:
            it["kids"] = [strip(k) for k in it["kids"]]
        return it
    try:
        return strip(view(node, val))
    except CondError:
        return None
