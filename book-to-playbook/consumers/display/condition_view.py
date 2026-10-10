#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조건 → 화면 항목(웹 화면층). 판정 JSON 의 view·측정 증거(detail)·사유 문장을 여기서 빚는다(책 무관).

조건의 '뜻'(등급·금액·비중)은 dsl/tradeTool.py 의 Grade 한 벌이고, 여기는 그 평가 문맥(Cond.Ctx)을 받아
사람이 읽는 모양으로 묶기만 한다 — 판정을 다시 내지 않는다.
  · _view        노드 하나 → 화면 항목 하나(중첩 설명 + 그날 값 + 측정 증거)
  · _measure 외  '무엇을 재서 얼마였나'(측정 증거)
  · reason_of    등급 사유 한 줄
"""
from dsl.tradeTool import Cond

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


def _describe_operand(e, defs):
    """값 표현식 → 짧은 사람 설명(없으면 '' — 그럼 숫자만 보여준다). 복합식(산술 등)은 라벨이 설명하므로 생략."""
    if not isinstance(e, dict):
        return ""                                # 상수(기준값) — 숫자 자체로
    if "def" in e and e["def"] in defs and len([k for k in e if k not in Cond.META]) == 1:
        return _describe_operand(defs[e["def"]], defs)
    try:
        op = Cond._op_of(e)
    except Cond.CondError:
        return ""
    if op == "px":
        sym = e.get("sym", "$self")
        base = _PXF.get(e["px"], e["px"])
        pre = "장중 " if e.get("tf", "1d") in ("1m", "5m") else ""   # 장중 분봉 vs 확정 일봉 구분
        core = base if sym in ("$self", "$index") else "%s %s" % (sym, base)
        return pre + core
    if op in ("ma", "ema"):
        return "%s일선" % _n(e[op][1]) if op == "ma" else "%s일 지수이평" % _n(e[op][1])
    if op in ("highest", "lowest", "sum", "stdev"):
        m = {"highest": "최고", "lowest": "최저", "sum": "합계", "stdev": "변동성"}
        return "%s일 %s" % (_n(e[op][1]), m[op])
    if op == "pct":
        return "전일 대비 변화율" if e["pct"][1] == 1 else "%s일 전 대비 변화율" % _n(e["pct"][1])
    if op == "lag":
        inner = _describe_operand(e["lag"][0], defs)
        return ("%s " % inner if inner else "") + "%s일 전" % _n(e["lag"][1])
    if op == "streak":
        return "연속 참 일수"
    if op == "count":
        return "최근 참 일수"
    if op == "barssince":
        return "마지막 참 이후 일수"
    if op == "rsi":
        return "RSI%s" % _n(e["rsi"][1])
    if op == "pos":
        return {"ret": "수익률(%)", "days": "보유일", "maxret": "최고수익(%)",
                "minret": "최저수익(%)"}.get(e["pos"], "포지션")
    if op == "valuewhen":                        # 그 조건이 마지막으로 참이던 날의 값
        return _describe_operand(e["valuewhen"][1], defs) + "(최근 신호일)"
    if op in ("minsince", "maxsince"):           # 신호 이후 최저/최고
        return ("최저 " if op == "minsince" else "최고 ") + _describe_operand(e[op][1], defs) + "(신호 이후)"
    return ""                                    # add/sub/mul/div/case … 복합 → 숫자만(산술은 inputs 로 분해)


def _unit_of(e, defs):
    """값 표현식의 단위 힌트(%·일·배) — 모르면 '' (라벨이 단위를 말하므로 비워도 된다)."""
    if not isinstance(e, dict):
        return ""
    if "def" in e and e["def"] in defs and len([k for k in e if k not in Cond.META]) == 1:
        return _unit_of(defs[e["def"]], defs)
    try:
        op = Cond._op_of(e)
    except Cond.CondError:
        return ""
    if op == "pct":
        return "%"
    if op in ("streak", "count", "barssince"):
        return "일"
    if op == "div":
        return "배"
    if op == "rsi":
        return ""
    if op == "pos":
        return "일" if e["pos"] == "days" else "%"
    return ""


def _inputs_of(e, ctx, i, defs, acc, seen, top=True):
    """파생값이 '무슨 원시 숫자로 나왔나'를 [{d, v}]로 모은다 — 사용자가 검증할 수 있게.
    · pct(변화율)은 두 끝점(오늘·k일 전)을 보여준다. 예: 오늘 종가 770.6 · 5일 전 765.6.
    · 산술(합·차·비율)은 안의 시세 잎들을 보여준다. 예: 고가 771 · 종가 770.6.
    · LHS 자체가 단일 잎(종가·20일선·연속일수)이면 분해하지 않는다 — 피연산자가 이미 값으로 보인다.
    중복 설명은 한 번만."""
    if not isinstance(e, dict):
        return
    if "def" in e and e["def"] in defs and len([k for k in e if k not in Cond.META]) == 1:
        return _inputs_of(defs[e["def"]], ctx, i, defs, acc, seen, top)

    def add(d, v):
        if d and d not in seen:
            seen.add(d)
            acc.append({"d": d, "v": v})

    try:
        op = Cond._op_of(e)
    except Cond.CondError:
        return
    if op == "pct":                                   # 변화율 — 두 끝점을 보여준다
        s, k = e["pct"]
        base = _describe_operand(s, defs) or "값"
        add("오늘 " + base, _meas_val(s, ctx, i))
        add("%s일 전" % _n(k), _meas_val({"lag": [s, k]}, ctx, i))
        return
    if op in Cond.ARITH:
        for sub in e[op]:
            _inputs_of(sub, ctx, i, defs, acc, seen, top=False)
        return
    if op == "abs":
        _inputs_of(e["abs"], ctx, i, defs, acc, seen, top=False)
        return
    # 단일 잎(px·ma·streak…): 산술 안쪽이면 값으로 보여주고, LHS 통째면(top) 분해하지 않는다
    if not top and op in ("px", "ma", "ema", "lag", "streak", "count", "barssince",
                          "rsi", "highest", "lowest", "sum", "stdev", "pos"):
        add(_describe_operand(e, defs), _meas_val(e, ctx, i))
    # case·valuewhen 등은 생략(라벨이 설명을 맡는다)


def _measure(node, defs, ctx, i, top=True):
    """표시되는 조건 하나가 '무엇을 재서 얼마였나' — [{op, lhs, lhsd, rhs, rhsd, unit, inputs?}, …].
    하위에 라벨 달린 조건이 있으면 멈춘다(그 조건이 자기 증거를 따로 보여준다)."""
    if not isinstance(node, dict):
        return []
    if "def" in node and node["def"] in defs and len([k for k in node if k not in Cond.META]) == 1:
        return _measure(defs[node["def"]], defs, ctx, i, top)
    if not top and (node.get("label") or Cond.is_manual(node, defs) or "observe" in node):
        return []
    try:
        op = Cond._op_of(node)
    except Cond.CondError:
        return []
    if op in Cond.CMP:
        a, b = node[op]
        lhsd = _describe_operand(a, defs)
        fact = {"op": op,
                "lhs": _meas_val(a, ctx, i), "lhsd": lhsd,
                "rhs": _meas_val(b, ctx, i),
                "rhsd": _describe_operand(b, defs),     # "?"(저자가 안 준 기준)면 rhs None·rhsd '' — 화면이 '기준 ?'로
                "unit": _unit_of(a, defs)}
        ins = []                           # 파생값(변화율·산술)이면 무슨 원시 숫자로 나왔는지 함께 보여준다
        _inputs_of(a, ctx, i, defs, ins, set())
        if ins:
            fact["inputs"] = ins
        return [fact]
    if op == "not":
        kids = [node["not"]]
    elif op in ("all", "any"):
        kids = node[op]
    elif op == "atleast":
        kids = node["of"]
    elif op == "observe":
        kids = [node["observe"]]
    else:
        return []
    facts = []
    for c in kids:
        facts += _measure(c, defs, ctx, i, top=False)
    return facts


def _view(node, defs, ctx, i, shared=False, fold=frozenset()):
    """노드 하나 → 화면 항목 하나 {v, op?, n?, kids?, label?, ref?, manual?, note?, hidden?}.

    · 논리 노드(all/any/atleast/not)는 op 와 자식 항목 전부를 담는다 — 화면이 사람이 체크한 수동 조건으로
      같은 3값 논리를 다시 계산할 수 있게(not 아래 수동은 극성이 뒤집힌다 — cond 와 같은 규칙).
    · 그 밖의 노드는 그날 값(v)이 고정된 잎이다. 라벨이 없으면 hidden(화면에 안 보이지만 계산엔 쓴다),
      안쪽에 라벨 달린 노드가 있으면 참고용 kids(op 없음 — 다시 계산하지 않는다)로 붙인다.
    · 정의 참조는 정의 본문 항목 하나로(자리 META 를 덮어) — 같은 조건을 두 줄로 그리지 않는다.
    · 상품마다 값이 같은 정의(Cond.product_specific 아님) 안의 수동 조건은 shared=True — 한 번 답하면 그 조건을 쓰는
      모든 상품에 같은 답이 들어간다(같은 시장 사실이므로). 답 열쇠 규칙은 Cond.answer_key 하나(서버가 판정).
    · fold = 화면 다른 곳에 이미 펼쳐 둔 정의 이름들 — 그 참조는 folded 표시(화면은 한 줄, 계산은 kids).
    v 는 수동 = 모름(None)으로 둔 그날 값이다."""
    if "def" in node and node["def"] in defs and not [k for k in node if k not in Cond.META and k != "def"]:
        # 정의 참조 = 정의 본문 항목 하나(자리 META label·ref·note 를 덮어서) — '자리 줄 + 본문 줄'로 같은 조건을
        #   두 번 그리지 않고, 자리의 원문 출처는 지킨다(Cond.labeled 와 같은 규칙).
        body = defs[node["def"]]
        site = {k: v for k, v in node.items() if k in ("label", "ref", "note")}
        eff = dict(body, **site) if site and isinstance(body, dict) else body
        sh = shared or not Cond.product_specific(body, defs)
        item = _view(eff, defs, ctx.shared() if sh else ctx, i, sh, fold)   # 답 열쇠 "*" 문맥(답이 없으면 그대로)
        if node["def"] in fold:
            item["folded"] = True    # 같은 화면 다른 곳에 펼쳐 둔 조건 — 계산엔 kids 를 쓰되 화면엔 한 줄로
        return item
    skip = ("of", "sym", "tf", "else") + (("manual",) if "observe" in node else ())
    op = next((k for k in node if k not in Cond.META and k not in skip), None)
    item = {"v": Cond.series(node, ctx)[i]}
    for k in ("label", "ref", "note"):
        if node.get(k):
            item[k] = node[k]
    if node.get("allprod"):                      # 공통(on 없음) 규칙 — 화면이 상품 카드에서 빼고 공통 섹션으로 모은다
        item["allprod"] = True
        # 상품에 안 기대는 공통 규칙($self/$index 안 씀)은 상품마다 값·질문이 같다 → 화면이 한 줄로 합쳐도 된다는 힌트.
        #   답 열쇠(mkey)는 지금 규칙 그대로(상품별) — 화면이 그 한 줄의 수동 답을 세 상품 열쇠에 같이 넣는다(서버 무변).
        if not Cond.product_specific(node, defs):
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
                if shared:
                    item["shared"] = True
        item["kids"] = [_view(k, defs, kctx, i, shared, fold) for k in kids]
    elif Cond.is_unknown(node, defs):
        # 저자가 숫자를 안 준 식("?") — 사람이 정하는 수동 잎. 답을 묶는 열쇠는 식(문장 아님 — 같은 식 = 같은 질문).
        item["manual"] = Cond.UNKNOWN_REASON
        item["mkey"] = Cond.manual_key(node)
        if shared:
            item["shared"] = True
    elif op in ("manual", "observe"):
        item["manual"] = node["manual"]
        if shared:
            item["shared"] = True
        if op == "observe":
            item["observed"] = True              # v 가 있으면 관측값(자동), 없으면 사람 확인
            item["kids"] = [_view(node["observe"], defs, ctx, i, shared, fold)]
    else:
        inner = [_view(k, defs, ctx, i, shared, fold) for k in _labeled_inside(node, defs)]
        if inner:
            item["kids"] = inner
        if not node.get("label"):
            item["hidden"] = True
    # 측정 증거 — 화면에 보이는 조건(라벨/수동/관측)에 그날 실제 값을 붙인다. "?" 식이면 알려진 쪽 값이
    #   근거 숫자다(기준은 저자가 안 줬으니 사람이 그 숫자를 보고 참/거짓을 고른다 — 깜깜이 판단 방지).
    if node.get("label") or Cond.is_manual(node, defs) or "observe" in node:
        facts = _measure(node, defs, ctx, i)
        if facts:
            item["detail"] = facts
    return item


def _labeled_inside(node, defs):
    """잎 노드 안쪽의 가장 바깥 라벨 노드들(참고 표시용)."""
    out = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("label") or "manual" in n:
                out.append(n)
                return
            if "def" in n and n["def"] in defs:
                walk(defs[n["def"]])
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


def reason_of(key, ex, manual):
    """등급 사유 한 줄 — 무엇이 걸렸는지 라벨로."""
    def labels(sec, val):
        return [l for l, _, v in ex.get(sec, []) if l and v is val]
    if key == "nofilter":
        bad = labels("filter", False)
        return "필터 미충족: " + (" · ".join(bad[:3]) if bad else "전제 조건 거짓")
    if key == "avoid":
        hit = labels("avoid", True)
        return "회피 신호: " + (" · ".join(hit[:3]) if hit else "회피 조건 참")
    if key == "wait":
        return "진입 조건 미충족 — 매수 자리 아님"
    if key == "confirm":
        items = [l for s, l, _ in manual if s in ("filter", "entry")] + \
                ["(회피 아님) " + l for s, l, _ in manual if s == "avoid"]
        return "수동·장중 확인 시 매수: " + " · ".join(items[:4])
    if key == "buy":
        ok = labels("entry", True)
        return "필터 통과 · 회피 없음 · 진입: " + (" · ".join(ok[:3]) if ok else "조건 충족")
    return "데이터 부족으로 판정 불가"
