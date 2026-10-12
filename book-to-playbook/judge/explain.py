#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""판단 근거 설명(구간③ 판단자의 일부) — 조건 노드 하나 → 그날 값·측정 증거가 달린 설명 항목(책 무관).

조건을 시세로 평가하는 일이라 판단자(judge/judge)만 부른다 — 화면(web)은 판단자가 낸 설명을
그리기만 한다(표시는 판단하지 않는다). 평가 문맥(Cond.Ctx)은 판단자가 만든다.
  · view         노드 하나 → 설명 항목 하나(중첩 설명 + 그날 값 + 측정 증거)
  · static_view  값 없는 규칙 설명(시세·포지션 없이)
  · _measure 외  '무엇을 재서 얼마였나'(측정 증거)
"""
from tree.tradeTool import Cond

LOGICAL = ("all", "any", "atleast", "not")


# ------------------------------------------------------------------ 측정 증거(실제 값)
# 조건의 ●/○ 밑에 '무엇을 재서 그 값이 얼마였나'를 실어보낸다 — 사용자가 판정을 검증·신뢰할 수 있게.
# 엔진은 어차피 비교 양쪽 값을 계산해 참/거짓을 낸다(Cond.series). 그 값을 버리지 않고 뷰에 담는 것뿐이다.
_PXF = {"close": "종가", "open": "시가", "high": "고가", "low": "저가", "volume": "거래량"}


def _meas_val(e, ctx, i):
    """값 표현식 하나를 그날 실제 숫자로 — 못 재면 None. 표시용이라 자리수만 줄인다(계산엔 안 쓴다)."""
    try:
        v = Cond.series(e, ctx)[i]
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


def _n(k):
    """창 길이·lag 자리 숫자 → 글자. 저자가 안 준 숫자("?")는 그대로 "?"."""
    return "?" if k == Cond.UNKNOWN else "%d" % k


def _describe_operand(e):
    """값 표현식 → 짧은 사람 설명(없으면 '' — 그럼 숫자만 보여준다). 복합식(산술 등)은 라벨이 설명하므로 생략."""
    if not isinstance(e, dict):
        return ""                                # 상수(기준값) — 숫자 자체로
    try:
        op = Cond._op_of(e)
    except Cond.CondError:
        return ""
    if op == "px":
        sym = e["sym"]
        base = _PXF.get(e["px"], e["px"])
        pre = "장중 " if e.get("tf", "1d") in ("1m", "5m") else ""   # 장중 분봉 vs 확정 일봉 구분
        core = base if sym in Cond.ROLES else "%s %s" % (sym, base)   # 역할($self·$index)은 이름 없이, 구체 티커는 이름과 함께
        return pre + core
    if op in ("highest", "lowest", "sum"):
        m = {"highest": "최고", "lowest": "최저", "sum": "합계"}
        return "%s일 %s" % (_n(e[op][1]), m[op])
    if op == "lag":
        inner = _describe_operand(e["lag"][0])
        return ("%s " % inner if inner else "") + "%s일 전" % _n(e["lag"][1])
    if op == "barssince":
        return "마지막 참 이후 일수"
    if op == "pos":
        return {"ret": "수익률(%)", "days": "보유일", "maxret": "최고수익(%)", "minret": "최저수익(%)",
                "filled": "산 횟수" + ("(%s)" % e["rule"] if e.get("rule") else ""),
                "sold": "판 비율"}.get(e["pos"], "포지션")
    if op == "valuewhen":                        # 그 조건이 마지막으로 참이던 날의 값
        return _describe_operand(e["valuewhen"][1]) + "(최근 신호일)"
    if op in ("minsince", "maxsince"):           # 신호 이후 최저/최고
        return ("최저 " if op == "minsince" else "최고 ") + _describe_operand(e[op][1]) + "(신호 이후)"
    return ""                                    # add/sub/mul/div/case … 복합 → 숫자만(산술은 inputs 로 분해)


def _unit_of(e):
    """값 표현식의 단위 힌트(%·일·배) — 모르면 '' (라벨이 단위를 말하므로 비워도 된다)."""
    if not isinstance(e, dict):
        return ""
    try:
        op = Cond._op_of(e)
    except Cond.CondError:
        return ""
    if op == "barssince":
        return "일"
    if op == "div":
        return "배"
    if op == "pos":
        return {"days": "일", "filled": "회", "sold": ""}.get(e["pos"], "%")
    return ""


def _inputs_of(e, ctx, i, acc, seen, top=True):
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
        op = Cond._op_of(e)
    except Cond.CondError:
        return
    if op in Cond.ARITH:
        for sub in e[op]:
            _inputs_of(sub, ctx, i, acc, seen, top=False)
        return
    if op == "abs":
        _inputs_of(e["abs"], ctx, i, acc, seen, top=False)
        return
    # 단일 잎(px·lag·창…): 산술 안쪽이면 값으로 보여주고, LHS 통째면(top) 분해하지 않는다
    if not top and op in ("px", "lag", "barssince", "highest", "lowest", "sum", "pos"):
        add(_describe_operand(e), _meas_val(e, ctx, i))
    # case·valuewhen 등은 생략(라벨이 설명을 맡는다)


def _measure(node, ctx, i, top=True):
    """표시되는 조건 하나가 '무엇을 재서 얼마였나' — [{op, lhs, lhsd, rhs, rhsd, unit, inputs?}, …].
    하위에 라벨 달린 조건이 있으면 멈춘다(그 조건이 자기 증거를 따로 보여준다)."""
    if not isinstance(node, dict):
        return []
    if not top and (node.get("label") or Cond.is_manual(node)):
        return []
    try:
        op = Cond._op_of(node)
    except Cond.CondError:
        return []
    if op in Cond.CMP:
        a, b = node[op]
        lhsd = _describe_operand(a)
        fact = {"op": op,
                "lhs": _meas_val(a, ctx, i), "lhsd": lhsd,
                "rhs": _meas_val(b, ctx, i),
                "rhsd": _describe_operand(b),     # "?"(저자가 안 준 기준)면 rhs None·rhsd '' — 화면이 '기준 ?'로
                "unit": _unit_of(a)}
        ins = []                           # 파생값(변화율·산술)이면 무슨 원시 숫자로 나왔는지 함께 보여준다
        _inputs_of(a, ctx, i, ins, set())
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
        facts += _measure(c, ctx, i, top=False)
    return facts


def view(node, ctx, i):
    """노드 하나 → 화면 항목 하나 {v, op?, n?, kids?, label?, ref?, manual?, note?, hidden?}.

    · 논리 노드(all/any/atleast/not)는 op 와 자식 항목 전부를 담는다 — 화면이 사람이 체크한 수동 조건으로
      같은 3값 논리를 다시 계산할 수 있게(not 아래 수동은 극성이 뒤집힌다 — cond 와 같은 규칙).
    · 그 밖의 노드는 그날 값(v)이 고정된 잎이다. 라벨이 없으면 hidden(화면에 안 보이지만 계산엔 쓴다),
      안쪽에 라벨 달린 노드가 있으면 참고용 kids(op 없음 — 다시 계산하지 않는다)로 붙인다.
    v 는 수동 = 모름(None)으로 둔 그날 값이다."""
    skip = ("of", "sym", "tf", "else")
    op = next((k for k in node if k not in Cond.META and k not in skip), None)
    item = {"v": Cond.series(node, ctx)[i]}
    for k in ("label", "ref", "note"):
        if node.get(k):
            item[k] = node[k]
    if node.get("allprod"):                      # 공통(on 없음) 규칙 — 화면이 상품 카드에서 빼고 공통 섹션으로 모은다
        item["allprod"] = True
        # 상품에 안 기대는 공통 규칙($self·$index·pos·노드 on 안 씀)은 상품마다 값·질문이 같다 → 화면이 한 줄로 합쳐도 된다는 힌트.
        #   답 열쇠(mkey)는 지금 규칙 그대로(상품별) — 화면이 그 한 줄의 수동 답을 세 상품 열쇠에 같이 넣는다(서버 무변).
        if not Cond.product_specific(node):
            item["allsame"] = True
    if op in LOGICAL:
        # 묶음(all/any/atleast/not)은 '?' 가 안에 있어도 **항상 펼친다** — 사람이 확인할 건 묶음 자체가 아니라
        #   그 안의 sub-조건들이다(각 '?' sub 는 재귀로 자기 수동 잎이 된다). 접어서 "수동 확인" 하나로 숨기지 않는다.
        kids = node[op] if op in ("all", "any") else (node["of"] if op == "atleast" else [node["not"]])
        kctx = ctx.flipped() if op == "not" else ctx
        item["op"] = op
        if op == "atleast":
            item["n"] = node["atleast"]
            if node["atleast"] == Cond.UNKNOWN:  # 몇 개 필요한지 저자 미명시 — 묶음은 수동(사람이 개수 판단), 단 후보는 펼친다
                item["manual"] = Cond.UNKNOWN_REASON
                item["mkey"] = Cond.manual_key(node)
        item["kids"] = [view(k, kctx, i) for k in kids]
    elif Cond.is_unknown(node):
        # 저자가 숫자를 안 준 식("?") — 사람이 정하는 수동 잎. 답을 묶는 열쇠는 식(문장 아님 — 같은 식 = 같은 질문).
        item["manual"] = Cond.UNKNOWN_REASON
        item["mkey"] = Cond.manual_key(node)
    elif op == "manual":
        item["manual"] = node["manual"]
    else:
        inner = [view(k, ctx, i) for k in _labeled_inside(node)]
        if inner:
            item["kids"] = inner
        if not node.get("label"):
            item["hidden"] = True
    # 측정 증거 — 화면에 보이는 조건(라벨/수동/관측)에 그날 실제 값을 붙인다. "?" 식이면 알려진 쪽 값이
    #   근거 숫자다(기준은 저자가 안 줬으니 사람이 그 숫자를 보고 참/거짓을 고른다 — 깜깜이 판단 방지).
    if node.get("label") or Cond.is_manual(node):
        facts = _measure(node, ctx, i)
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
                if k not in Cond.META:
                    walk(x)
        elif isinstance(n, list):
            for x in n:
                walk(x)
    for k, x in node.items():
        if k not in Cond.META:
            walk(x)
    return out


def static_view(node, index=None):
    """포지션·시세 없이 보이는 규칙 설명(값 없음) — 라벨·논리 묶음·수동 사유만(비중·분할·판다 갈래, 시세 없는 상품)."""
    if node is None:
        return None

    def strip(it):
        it = {k: x for k, x in it.items() if k != "v"}
        if "kids" in it:
            it["kids"] = [strip(k) for k in it["kids"]]
        return it
    ctx = Cond.Ctx({}, ["0"], "$none", index, manual_as=None, pos=(0, 1.0))
    try:
        return strip(view(node, ctx, 0))
    except Cond.CondError:
        return None
