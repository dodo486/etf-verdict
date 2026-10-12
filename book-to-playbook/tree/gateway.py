#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조건 트리의 언어 (구간② 소유, 책 무관) — 문법(validate)·동사(VERBS)·공통 직렬화·워밍업 + 트리를 읽는 유일한 출입구
TreeGateway. 공개 이름은 모듈 수준 정의 그대로(from tree.gateway import validate, VERBS, TreeGateway …).
공통 직렬화: python -m tree.gateway fmt <파일...>
여기는 트리의 '뜻'(문법)만 안다 — 식에 시세를 넣어 계산하는 일은 judge/eval.py, 등급·시세 받기는 judge/judge.py.

■ 조건 트리 — 규칙의 단일 문법 (책 무관)

왜 있나
  옛 판정식은 type 마다 손으로 짠 계산기(16종)였다. 새 조건마다 코드가 늘었고, 이름과
  계산이 다른 계산기(전고점 '유지'가 실은 연속 신고가, '눌림 일수'에 반등일 포함)와
  한 필드의 두 뜻(op 가 방향 표시이자 비교 연산자)이 조용히 틀린 판정을 냈다.
  또 규칙 형식이 평평해서(조건 목록 + need 숫자) 원문 구조(택1·N개 중 M개·
  필수 조건)를 못 담았다. 이 문법(+ 계산기 judge/eval)이 둘 다를 없앤다:
    · 계산은 원시 시계열 연산 몇 개의 조합뿐 — 새 조건은 코드가 아니라 트리로 쓴다.
    · 구조는 all / any / atleast / not 로 그대로 적는다.

값
  모든 식은 '날짜별 시계열'(달력 길이의 리스트)이다. 숫자 시계열은 float|None,
  조건 시계열은 True|False|None. None = 데이터가 없어 모름 — 조용히 거짓으로 치지 않는다.
  모든 연산은 인과적이다(그날까지의 값만 쓴다) — judge.verify_eval 이 강제한다.

관측 시점(asof)
  평가는 '사용자가 보는 그 순간(asof)' 기준이다. asof = 관측 시각(UTC datetime) — 라이브는 실제 지금
  또는 지정 시각, 백테스트는 재생되는 각 시점. 일봉 필드는 asof 이하 마지막 확정 일봉을 본다.
  일봉 아닌 봉(tf "1m"·"5m")은 아직 시세 경로가 없어 None(모름) — 조용히 거짓으로 치지 않는다.

3값 논리
  all : 하나라도 False → False, 아니면 하나라도 None → None, 아니면 True (빈 all = True)
  any : 하나라도 True → True, 아니면 하나라도 None → None, 아니면 False (빈 any = False)
  atleast n : True 개수 ≥ n → True, True+None < n → False, 그 외 None
  not : True↔False, None 은 None

하한(AtLeast)
  barssince 가 모르는 날(또는 데이터 시작)에 닿으면 정확한 길이는 모르지만 '최소 N'은 안다.
  그 값은 AtLeast(N) 로 담기고, 비교는 하한만으로 결론이 나면 참/거짓(예: 최소 50일 ≥ 3 → 참),
  아니면 None 이다. 덧셈·뺄셈(상수)은 하한을 유지하고, 그 밖의 연산(창·곱·나눗셈)에선 None 이 된다.

수동(manual)
  {"manual": "사유"} 는 식으로 쓸 수 없는 조건(순수 주관·데이터 없음·연산 없음). 값은 평가 시 manual_as 로
  주어진다(엔진이 '확인되면/안 되면' 두 번 평가해 '확인 대기'를 가린다). 데이터 None 과 다르다.
  극성: not 아래의 수동은 반대 값을 받는다(manual_as=True 는 '수동이 전부 구역에 유리하게 풀림'
  이라는 뜻 — '겹치면 쉼' = not(all(.., 수동)) 에서 낙관 평가가 오히려 겹침을 가정하던 버그를 막는다).
  사람이 답한 수동(Ctx answers — 조건별 답 맵)은 그 답이 manual_as 보다 먼저다. 답은 잎의 참/거짓 그 자체라
  not 아래에서도 뒤집지 않는다(not 이 그 값을 뒤집을 뿐). 답 열쇠 = answer_key — 상품 + "|" + manual_key(잎).

모르는 값 "?"
  저자가 숫자(기준·기간·개수)를 안 준 조건도 식으로 적는다 — 모르는 숫자 자리만 "?" 로 둔다.
    "SOXL 이 5일선에서 너무 벌어짐" → {"ge": [(SOXL ÷ MA5(SOXL) − 1)×100, "?"]}
  "?" 를 품은 판단 노드(비교의 양쪽 식 어디든 "?", 또는 atleast 의 n 이 "?")는 수동처럼 사람이 참/거짓을 정한다
  (manual_as·극성 규칙 그대로). 화면은 비교의 알려진 쪽 값을 근거 숫자로 보여준다. 식이 조건의 신원이라
  같은 식이면 같은 조건이다(문장·이름과 무관). 수치로 정할 수 없는 순수 주관만 {"manual": "저자 미명시: …(정성)"}.

문법 (JSON) — 허용 키 밖은 전부 오류(조용히 무시하지 않는다):
  숫자          3, 1.5            (상수)   "?" = 저자가 안 준 숫자(모르는 값) — 숫자가 들어갈 자리 어디든
  시세          {"px": "close"|"open"|"high"|"low"|"volume", "sym": 티커, "tf": 봉?}   sym = 구체 티커(필수 —
                상품 자신이면 그 티커, 지수면 지수 티커. $ 심볼 없음),
                tf 기본 "1d"(일봉 — asof 이하 '확정(settled)' 일봉; 장중 asof 면 아직 마감 안 된 그날 일봉은
                None, 즉 전일 종가까지만 본다). tf "1m"·"5m"(분봉)은 적을 수 있지만 시세 경로가 없어
                값은 모름(None).
  산술          {"add"|"sub"|"mul"|"div"|"max"|"min": [a, b]}   max/min = 같은 날 두 값 중 큰/작은 값
                {"abs": a}
  선택          {"case": [[c1, v1], [c2, v2], ...], "else": v}   위에서부터 처음 참인 c 의 v.
                앞의 c 가 모름(None)이면 결과도 모름(뒤 갈래로 넘어가지 않는다).
  이동/창       {"highest"|"lowest"|"sum": [s, n]}   (평균 = sum ÷ n — 전용 지표 연산은 두지 않는다)
                {"lag": [s, k]}   k 거래일 전 값   (변화율 % = (s ÷ lag(s,k) − 1) × 100)
  비교          {"gt"|"ge"|"lt"|"le": [a, b]}
  논리          {"all": [...]}, {"any": [...]}, {"atleast": n, "of": [...]}, {"not": c}
  시간          {"barssince": c}        c 가 마지막으로 참이었던 날부터 지난 거래일(오늘 참이면 0)
                                        (연속 참 일수 = barssince(not c) · 최근 n일 중 참인 날 수 = sum(case(c,1,0), n))
                {"valuewhen": [c, s]}   c 가 마지막으로 참이었던 날의 s 값
                {"minsince"|"maxsince": [c, s]}  c 가 마지막으로 참이었던 날부터 오늘까지 s 의 최저/최고
  수동          {"manual": "사유"}
  포지션        {"pos": "ret"|"days"|"maxret"|"minret"|"filled"|"sold"}   판다·2차 이후 분할(산다) 갈래 안에서만.
                ret = 평균 매입가 대비 오늘 종가 수익률(%), days = 첫 매수일부터 지난 봉(첫 매수일 0),
                maxret/minret = 첫 매수일~오늘 종가 수익률의 최고/최저. 매수 전 날은 None.
                filled = 산 횟수({"pos": "filled", "rule": "1차"} = 그 규칙으로 산 횟수, rule 없으면 전체) ·
                sold = 지금까지 판 비율(판 물량 ÷ 산 물량). 둘은 체결 장부가 있어야 안다(없으면 모름).
  메타(아무 노드에) "label", "ref", "id", "note", "on"(노드 레벨 대상 상품 — 그 밖의 상품에선 항상 참)

종목 모델: 규칙·노드가 어느 상품에 판정을 내나 = on · 시세 잎이 읽는 티커 = sym. 둘뿐이다
  ("여러 종목 중 N개" = {"atleast": N, "of": [종목별 비교 …]}, 각 잎 sym = 그 티커).

■ TreeGateway — 조건 트리(books/<slug>/tree.json)를 읽는 유일한 출입구

왜 있나
  트리의 키 배치를 아는 코드가 판정·백테스트·검사기 곳곳에 흩어지지 않게, 원본 키를 만지는 코드는 이 파일 하나다.
  나머지(판정 엔진·백테스트·화면)는 여기에 '질문'만 한다. 직접 접근은 entry/verify_rules 주인 표가 막는다.

트리 v3 (규칙 목록)
  파일은 `rules` 목록(원문 판단 하나 = 규칙 하나, 동사 셋 안 산다·산다·판다 — 정본 VERBS(아래 '동사' 절)). 소비자는 동사로 묻는다:
    · gate(안 산다)·gate(산다) — 그 동사 갈래의 any 묶음(등급용, 포지션 쓰는 갈래 제외)
    · weight — 산다 + qty cash(비중) · tranches — 산다 + qty budget(분할) · sells — 판다
  수량은 트리의 qty {of, x} 를 그대로 Qty(of, x) 로 건넨다("?" → None). 물량 변환은 judge/judge.to_units.
  `{"rule": "이름"}` 참조는 건네기 전에 **펼친다** — 계산기(judge/eval)는 평범한 식만 본다.
  트리는 상품을 모르는 공통 로직이다. 상품마다 달라지는 것은 해석기(판단자)가 채운다:
    · 시세 잎 sym = 역할 `$self`(판정 중인 상품) · `$index`(그 상품의 지수 — products 의 index) · 또는 구체 티커(^VIX 등)
    · 규칙·노드 `on` = 저자가 상품을 이름으로 짚은 규칙의 대상 상품 필터(생략 = 전 상품)
  ($s·이름 심볼 names·across 는 폐지 — 여러 종목 중 N개는 atleast·of. 형식 검사가 거부한다.)
  `{"pos": "filled", "rule": 이름}`(그 규칙으로 산 횟수)은 그대로 건넨다 — 값은 체결 장부(trades)가 낸다.
"""
import json
import os
from collections import namedtuple

from shared.paths import book_file

# ================= 문법 — 트리 언어의 이름·검사 =================
ROLES = ("$self", "$index")   # 시세 잎 sym 의 역할 — 해석기가 상품마다 채운다($self = 판정 중인 상품, $index = 그 상품의 지수)
META = ("label", "ref", "id", "note", "allprod", "on")   # allprod = 화면 전용 플래그(공통 규칙 여부) — 평가기는 무시
                                                         # on = 노드 레벨 대상 상품(series 가 처리) — 평가 중 상품이 빠지면 그 노드는 '항상 참'
UNKNOWN = "?"             # 저자가 안 준 숫자 — 이 자리를 품은 판단 노드는 수동(사람이 정함)
UNKNOWN_REASON = "저자 미명시: 기준 숫자를 주지 않음(식의 ? 자리)"
PX_FIELDS = ("open", "high", "low", "close", "volume")
POS_FIELDS = ("ret", "days", "maxret", "minret", "filled", "sold")
ARITH = ("add", "sub", "mul", "div", "max", "min")
TIMEFRAMES = ("1d", "1m", "5m")  # 봉 길이(문법) — 평가하는 건 일봉(확정 settled 일봉)뿐. 1m·5m 는 트리에 적을 수 있지만
                                 # 아직 시세 경로가 없어 값은 전부 None(모름) — 시세 저장소가 생기면 거기서 채운다.
WINDOW = ("highest", "lowest", "sum")   # 창(n거래일) 집계 — 평균 등 지표는 전용 연산 없이 조합(COND_DSL 6절)
GONE_OPS = ("ma", "ema", "stdev", "rsi", "pct", "count", "streak", "across")   # 지운 전용 연산 — 조합으로 쓴다(across → atleast·of · entry.verify_rules 주인 표가 되살림을 막는다)
CMP = ("gt", "ge", "lt", "le")


class CondError(ValueError):
    pass


class AtLeast(float):
    """정확한 값은 모르지만 이 값 이상임이 확실한 수(하한)."""

    def __repr__(self):
        return "AtLeast(%g)" % float(self)


# ------------------------------------------------------------------ 검증(문법)
def _op_of(node):
    """노드의 연산 키(메타 키 제외)를 하나만 돌려준다. 0개·2개 이상이면 오류."""
    keys = [k for k in node if k not in META]
    if node.get("atleast") is not None:
        keys = [k for k in keys if k != "of"]
    if node.get("px") is not None:
        keys = [k for k in keys if k not in ("sym", "tf")]
    if node.get("case") is not None:
        keys = [k for k in keys if k != "else"]
    if node.get("pos") is not None:
        keys = [k for k in keys if k != "rule"]
    if len(keys) != 1:
        raise CondError("노드에 연산이 정확히 하나여야 한다: %r" % sorted(node))
    return keys[0]


def _has_unknown(x):
    """식 안에 "?"(저자가 안 준 숫자)가 있나."""
    if x == UNKNOWN:
        return True
    if isinstance(x, list):
        return any(_has_unknown(y) for y in x)
    if isinstance(x, dict):
        return any(_has_unknown(y) for k, y in x.items() if k not in META)
    return False


def is_unknown(node):
    """"?" 를 품은 판단 노드인가 — 비교(gt/ge/lt/le)의 양쪽 식 어디든 "?", 또는 atleast 의 n 이 "?".
    저자가 숫자를 안 줘 기계가 참/거짓을 못 정하니 수동처럼 사람이 정한다(manual_as·극성 규칙 그대로)."""
    if not isinstance(node, dict):
        return False
    try:
        op = _op_of(node)
    except CondError:
        return False
    if op in CMP:
        return _has_unknown(node[op])
    return op == "atleast" and node["atleast"] == UNKNOWN


def is_manual(node):
    """사람이 참/거짓을 정하는 잎 — 문장 수동({"manual"}) 또는 "?" 를 품은 식."""
    return isinstance(node, dict) and ("manual" in node or is_unknown(node))


def manual_text(node):
    """수동 잎의 사유 문장 — 문장 수동은 그 문장, "?" 식은 공통 사유(무엇을 재는지는 식이 말한다)."""
    return node["manual"] if "manual" in node else UNKNOWN_REASON


def strip_meta(node):
    """META 를 모든 깊이에서 뗀 식 — "?" 수동 잎의 답 열쇠(같은 식 = 같은 질문)."""
    if isinstance(node, dict):
        return {k: strip_meta(v) for k, v in node.items() if k not in META}
    if isinstance(node, list):
        return [strip_meta(x) for x in node]
    return node


def manual_key(node):
    """수동 잎의 답 열쇠 본체 — 문장 수동은 그 문장, "?" 식은 "?" + 식(META 뗀 JSON)."""
    if "manual" in node:
        return node["manual"]
    return "?" + json.dumps(strip_meta(node), ensure_ascii=False, sort_keys=True)


def answer_key(node, prod):
    """사람이 답한 수동의 열쇠 — 상품마다(상품 + "|" + 수동 열쇠)."""
    return prod + "|" + manual_key(node)


def product_specific(node):
    """$self·$index(상품마다 채워지는 역할)·pos(그 상품 보유분)·노드 레벨 on 을 쓰는 식은 상품마다 값이 달라진다 —
    여러 상품이 '같이 보는' 판단이 아니다. 구체 티커 시세만 쓰면 상품과 무관하다."""
    return any(isinstance(n, dict) and ("pos" in n or n.get("on") or n.get("sym") in ROLES) for n in labeled_all(node))


def validate(node, path="$"):
    """문법 검사. 모르는 연산·키·인자 개수·필드는 전부 CondError(위치 포함)."""
    if isinstance(node, bool):
        raise CondError("%s: 불리언 상수는 쓰지 않는다(빈 all/any 를 쓴다)" % path)
    if isinstance(node, (int, float)) or node == UNKNOWN:
        return
    if not isinstance(node, dict):
        raise CondError("%s: 노드는 숫자 또는 객체여야 한다: %r" % (path, node))
    op = _op_of(node)
    v = node[op]

    def two(name):
        if not (isinstance(v, list) and len(v) == 2):
            raise CondError("%s.%s: 인자 2개 [a, b] 여야 한다" % (path, name))

    def posint(x, what):
        if x == UNKNOWN:
            return
        if not (isinstance(x, int) and not isinstance(x, bool) and x >= 1):
            raise CondError("%s.%s: %s 은 1 이상의 정수여야 한다: %r" % (path, op, what, x))

    if op == "px":
        if v not in PX_FIELDS:
            raise CondError("%s.px: 모르는 시세 필드 %r" % (path, v))
        sym = node.get("sym")
        if not (isinstance(sym, str) and sym.strip()):
            raise CondError("%s.sym: 필요하다(생략 금지) — 역할 $self·$index 또는 구체 티커" % path)
        if sym.startswith("$") and sym not in ROLES:
            raise CondError("%s.sym: %r — 역할은 $self·$index 뿐이다($s·이름 심볼은 폐지, 여러 종목은 atleast·of)" % (path, sym))
        if "tf" in node and node["tf"] not in TIMEFRAMES:
            raise CondError("%s.tf: 모르는 봉 %r (허용 %s)" % (path, node["tf"], "/".join(TIMEFRAMES)))
    elif op == "abs":
        validate(v, path + ".abs")
    elif op == "case":
        if not (isinstance(v, list) and v and all(isinstance(b, list) and len(b) == 2 for b in v)):
            raise CondError("%s.case: [[조건, 값], ...] 목록이어야 한다" % path)
        if "else" not in node:
            raise CondError("%s.case: else 가 필요하다(모든 경우의 값을 명시)" % path)
        for i, (c, x) in enumerate(v):
            validate(c, "%s.case[%d][0]" % (path, i))
            validate(x, "%s.case[%d][1]" % (path, i))
        validate(node["else"], path + ".else")
    elif op in ARITH or op in CMP:
        two(op)
        validate(v[0], path + "." + op + "[0]")
        validate(v[1], path + "." + op + "[1]")
    elif op in WINDOW or op == "lag":
        two(op)
        validate(v[0], path + "." + op + "[0]")
        if op == "lag":
            if v[1] != UNKNOWN and not (isinstance(v[1], int) and not isinstance(v[1], bool) and v[1] >= 0):
                raise CondError("%s.lag: k 는 0 이상의 정수" % path)
        else:
            posint(v[1], "n")
    elif op in ("all", "any"):
        if not isinstance(v, list):
            raise CondError("%s.%s: 목록이어야 한다" % (path, op))
        for i, c in enumerate(v):
            validate(c, "%s.%s[%d]" % (path, op, i))
    elif op == "atleast":
        posint(v, "n")
        of = node.get("of")
        if not isinstance(of, list):
            raise CondError("%s.atleast: of 목록이 필요하다" % path)
        for i, c in enumerate(of):
            validate(c, "%s.of[%d]" % (path, i))
    elif op == "not":
        validate(v, path + ".not")
    elif op == "barssince":
        validate(v, path + "." + op)
    elif op in ("valuewhen", "minsince", "maxsince"):
        two(op)
        validate(v[0], path + ".valuewhen[0]")
        validate(v[1], path + ".valuewhen[1]")
    elif op == "manual":
        if not (isinstance(v, str) and v.strip()):
            raise CondError("%s.manual: 사유 문자열이 필요하다" % path)
    elif op == "pos":
        if v not in POS_FIELDS:
            raise CondError("%s.pos: 모르는 포지션 값 %r (허용 %s)" % (path, v, "/".join(POS_FIELDS)))
        if "rule" in node and (v != "filled" or not isinstance(node["rule"], str)):
            raise CondError("%s.pos: rule 은 filled 에만(그 규칙으로 산 횟수 — 규칙 이름 문자열)" % path)
    else:
        raise CondError("%s: 모르는 연산 %r" % (path, op))


# ------------------------------------------------------------------ 동사의 뜻 · 파일 직렬화
# 트리 v3 의 규칙 갈래는 동사 셋 중 하나를 한다 — 여기 한 곳이 정본이다(화면은 판정 JSON 의 verbs 로 받는다).
# 트리 파일의 키 배치·형식 검사·탐색은 아래 TreeGateway 가 맡는다 — 이 절은 동사의 이름과 뜻만.
BLOCK, BUY, SELL = VERBS = ("안 산다", "산다", "판다")
GATES = (BLOCK, BUY)                                    # 등급을 내는 동사(포지션 없이 그날 본다) — 판다는 보유분에만
BUY_SIDE = {BLOCK: False, BUY: True}                       # 그 동사의 갈래가 '매수 쪽'인 값 — 극성(수동 가정·빠진 묶음의 중립값)


def _uses_pos(node):
    """식이 포지션 값(pos)을 쓰나."""
    return any("pos" in n for n in labeled_all(node))


def compact_json(obj, width=100):
    """구간② 파일(후보 a·b · 사례 · 최종 트리)의 유일한 직렬화 — 사람이 검증하기 쉽게 줄 수를 늘리지 않는다.
    한 줄(width)에 들어가는 노드는 한 줄로 접고, 안 들어가면 구조만 들여쓴다. 숫자·문자열만 든 긴 목록(사례의 시세
    배열 등)은 원소마다 줄을 바꾸지 않고 width 안에서 이어 붙인다. (indent=1 은 {"px": "close"} 같은 조각까지
    줄을 쪼개 수천 줄이 된다 — 실제로 moneycopy tree.json 이 9135줄까지 부풀었다.)"""
    def one(o):
        return json.dumps(o, ensure_ascii=False, separators=(", ", ": "))

    def fmt(o, depth):
        line = one(o)
        if len(line) <= width or not isinstance(o, (dict, list)):
            return line
        pad = " " * (depth + 1)
        if isinstance(o, list) and all(not isinstance(x, (dict, list)) for x in o):
            rows, cur = [], ""
            for x in (one(x) for x in o):
                if cur and len(pad) + len(cur) + len(x) + 2 > width:
                    rows.append(cur + ",")
                    cur = x
                else:
                    cur = x if not cur else cur + ", " + x
            rows.append(cur)
            return "[\n" + "\n".join(pad + r for r in rows) + "\n" + " " * depth + "]"
        br = "\n" + pad
        if isinstance(o, dict):
            body = [one(k) + ": " + fmt(v, depth + 1) for k, v in o.items()]
            return "{" + br + ("," + br).join(body) + "\n" + " " * depth + "}"
        body = [fmt(v, depth + 1) for v in o]
        return "[" + br + ("," + br).join(body) + "\n" + " " * depth + "]"
    return fmt(obj, 0) + "\n"


def fmt_files(paths):
    """JSON 파일을 compact_json 형식으로 다시 쓴다(내용 불변 — 다시 읽어 같은지 확인). 추출자·사례 작성자·심판이
    파일을 쓴 뒤 부르는 공통 도구: python -m tree.gateway fmt <파일...>"""
    for p in paths:
        obj = json.load(open(p, encoding="utf-8"))
        text = compact_json(obj)
        if json.loads(text) != obj:
            raise CondError("%s: 직렬화가 내용을 바꿨다(버그)" % p)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("%s — %d줄" % (p, text.count("\n")))


def is_compact(path):
    """파일이 compact_json 형식 그대로인가(검사기용)."""
    raw = open(path, encoding="utf-8").read()
    return raw == compact_json(json.loads(raw))


def labeled(node, acc=None):
    """라벨 달린 노드 목록(설명·통계용)."""
    acc = [] if acc is None else acc
    if isinstance(node, dict):
        if node.get("label"):
            acc.append(node)
        for k, x in node.items():
            if k not in META:
                labeled(x, acc)
    elif isinstance(node, list):
        for x in node:
            labeled(x, acc)
    return acc


def manual_leaves(node):
    return [n for n in labeled_all(node) if is_manual(n)]


def labeled_all(node, acc=None):
    """모든 dict 노드."""
    acc = [] if acc is None else acc
    if isinstance(node, dict):
        acc.append(node)
        for k, x in node.items():
            if k not in META:
                labeled_all(x, acc)
    elif isinstance(node, list):
        for x in node:
            labeled_all(x, acc)
    return acc


# ------------------------------------------------------------------ 워밍업(필요 lookback)
def warmup_of(node):
    """node 를 평가할 때 '첫 평가 봉'이 조용히 틀린 값을 내지 않으려면 그 앞에 몇 개의 확정 봉이
    더 있어야 하는지 — 트리가 실제로 쓰는 가장 긴 lookback(거래일 수).

    왜 필요한가
      ma20·highest60·lag5 같은 창/지연 연산은 창이 덜 차면 **조용히 None** 을 내고, 그 None 은
      3값 논리로 위에 전파돼 '모름'이 된다 — 데이터가 모자란 줄 모르고 ✅/🚫 확신을 내는 길목이다.
      시세가 rate-limit 로 잘려(워밍업 부족) 들어오면 바로 이 일이 난다(실제 발견된 버그).
      이 함수가 트리에서 '필요한 확정 봉 수'를 직접 뽑아, 그보다 짧은 구간의 1d 신호를 '불완전'으로
      표면화하는 가드(RuleSeries.incomplete)의 임계값이 된다 — WARMUP_DAYS(fetch 버퍼)와 무관하다.

    어떻게 세나 (연산마다 '그날 값이 서려면 그 앞에 몇 봉이 더 있어야 하나'를 더해 가장 깊은 사슬)
      · 창(highest/lowest/sum) n             : n-1 + 안쪽
      · lag k                                : k  + 안쪽
      · barssince/valuewhen/minsince/maxsince : 안쪽만. 이들은 데이터 시작에 닿으면 조용히
        틀리지 않고 AtLeast/None(모름)으로 스스로 불확실을 드러내므로(STREAK_CAP 는 fetch 버퍼가
        아닌 역방향 상한일 뿐) 워밍업 기준에 넣지 않는다 — 넣으면 정상 데이터의 짧은 창도 오탐한다.
      · 산술·비교·abs·case·논리(all/any/atleast/not) : 자식 중 최댓값
      · px/manual/pos/상수                   : 0
    """
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return 0
    if not isinstance(node, dict):
        return 0
    op = _op_of(node)
    v = node[op]
    w = warmup_of
    if is_unknown(node):
        return 0                             # 사람이 정하는 판단 — 기계 lookback 없음
    if op in WINDOW + ("lag",) and v[1] == UNKNOWN:
        return w(v[0])                       # 기간을 모름 — 그 값은 늘 모름이라 이 창은 워밍업에 안 넣는다
    if op == "px":
        return 0
    if op in WINDOW:
        return (v[1] - 1) + w(v[0])
    if op == "lag":
        return v[1] + w(v[0])
    if op == "barssince":
        return w(v)                          # AtLeast/None 으로 스스로 불확실을 드러낸다 — 워밍업에 안 넣음
    if op in ("valuewhen", "minsince", "maxsince"):
        return max(w(v[0]), w(v[1]))
    if op in ARITH or op in CMP:
        return max(w(v[0]), w(v[1]))
    if op == "abs":
        return w(v)
    if op == "case":
        return max([w(c) for c, _ in v] + [w(x) for _, x in v] + [w(node["else"])])
    if op in ("all", "any"):
        return max([w(c) for c in v] + [0])
    if op == "atleast":
        return max([w(c) for c in node["of"]] + [0])
    if op == "not":
        return w(v)
    # manual · pos — lookback 없음
    return 0


# 판정 전에 과거 시세를 며칠치(달력일) 미리 당겨올지 — '워밍업'. 트리가 쓰는 가장 긴 창
# (예: 52주 신고가 = 252거래일 ≈ 달력 365일)이 첫날부터 제대로 서도록 넉넉히 둔다.
# ★ 여기 한 곳이 정본이다 — 매일 판정(web/verdict_view)·백테스트(backtest)·검증(authoring.extract.verify_tree)이
#   모두 이 값을 가져다 쓴다. 과거엔 세 곳에 따로(500/400/500) 박혀 백테스트만 어긋났었다.
WARMUP_DAYS = 500


# ================= 출입구 — TreeGateway =================
# 트리 v3 파일 형식(COND_DSL 1·5절) — 여기 밖의 키는 거부한다(옛 양식·오타를 조용히 무시하지 않는다).
TOP_KEYS = ("version", "products", "rules", "note")
PRODUCT_KEYS = ("index", "ref", "note")
# 책 폴더 안의 트리 파일 — 어느 트리(최종 None · 추출자 후보 "a"·"b")가 어느 파일인지는 여기 한 곳.
FILES = {None: "tree.json", "a": "tree_candidates/a.json", "b": "tree_candidates/b.json"}
RULE_KEYS = ("label", "ref", "note", "on", "value", "then", "skip", "why")
BRANCH_KEYS = ("when", "do", "qty", "repeat")
QTY_OF = {BUY: ("cash", "budget"), SELL: ("bought", "held")}   # 동사마다 쓸 수 있는 qty 종류(안 산다는 qty 없음)


def rule(label, do, when=None, qty=None, repeat=False, **meta):
    """합성 트리(검사용)의 행동 규칙 하나 — 갈래 하나짜리. qty = (of, x) 또는 None. meta = ref·note·on 등."""
    br = {"do": do}
    if when is not None:
        br["when"] = when
    if qty is not None:
        br["qty"] = {"of": qty[0], "x": qty[1]}
    if repeat:
        br["repeat"] = True
    return dict(meta, label=label, then=[br])


def synthetic(products, *rules, **top):
    """합성 트리(검사용, v3). products = 상품 티커 목록 또는 {상품: 기준지수 | None}. 규칙이 없으면 skip 하나를 둔다
    (v3 는 빈 rules 를 거부한다)."""
    items = products.items() if isinstance(products, dict) else [(p, None) for p in products]
    prods = {p: ({"index": ix} if ix else {}) for p, ix in items}
    return dict(top, version=3, products=prods,
                rules=list(rules) or [{"label": "(합성 — 규칙 없음)", "skip": "연산 없음: 합성 트리"}])


class Qty(namedtuple("Qty", "of x")):
    """'얼마나' — 정규화된 수량 (트리 v3 qty {of, x}). x = 수 · 식 · None(저자 미명시).
      of = "cash"(총 투자금의 x %) · "budget"(배정 금액의 x · 분할) · "bought"(산 물량의 x) · "held"(남은 물량의 x, 1=전량)"""
    __slots__ = ()


class Card(namedtuple("Card", "label ref note on value branches skip why")):
    """규칙 하나를 **적힌 그대로**(펼치지 않음 — {"rule"} 참조 그대로, 갈래의 "$value" 만 그 규칙 value 로) — 원시 트리 보기용.
    ref = 원문 소절 글자("·" 로 여럿) · on = 대상 상품 목록(None = 전부) · value = 이름 조건·측정(없으면 None)
    · branches = [CardBranch] · skip = 못 옮긴 사유(없으면 None) · why = 심판 기록."""
    __slots__ = ()


class CardBranch(namedtuple("CardBranch", "do when qty repeat")):
    """규칙 카드의 갈래 하나 — do = 동사 · when = 조건(적힌 그대로) · qty = Qty(of, x — x 는 적힌 그대로, "?" 포함) | None."""
    __slots__ = ()


class Branch:
    """갈래 하나(분할 차수·매도·비중)의 읽기 전용 값. 없는 필드는 None. qty = Qty(얼마나).
    repeat = 조건이 다시 맞을 때마다(판다 갈래만 — 기본은 한 번)."""
    __slots__ = ("label", "ref", "note", "when", "qty", "allprod", "repeat")

    def __init__(self, label=None, ref=None, note=None, when=None, qty=None, allprod=None, repeat=False):
        self.label, self.ref, self.note, self.when, self.qty = label, ref, note, when, qty
        self.allprod = allprod                   # 공통(on 없음) 규칙이면 True — 화면이 공통 섹션으로 모은다
        self.repeat = repeat


def _num(x):
    """'?' → None(저자 미명시), 그 외는 그대로."""
    return None if x in ("?", None) else x


def _qty(q, default=None, expand=lambda x: x):
    """트리 qty {of, x} → Qty(of, x) — x "?" 는 None, 식이면 펼친 식(expand). qty 가 없으면 default."""
    return Qty(q.get("of"), _num(expand(q.get("x")))) if q else default


class TreeGateway:
    """트리 하나(v3 규칙 목록). load/read/open/of 로 만들고 질문으로 읽는다.
    갈래를 do 동사로 골라 건네고, {"rule"} 참조는 펼쳐 건넨다."""

    def __init__(self, data):
        self._d = data or {}
        self._by_label = {r.get("label"): r for r in self._d.get("rules", []) if isinstance(r, dict)}

    def __bool__(self):
        return bool(self._d)

    # ---------------------------------------------------------------- 읽기
    @staticmethod
    def path(slug, which=None):
        """트리 파일 경로 — which = None(최종 tree.json) · "a"·"b"(추출자 후보). 모르는 이름이면 CondError."""
        if which not in FILES:
            raise CondError("모르는 트리 %r (허용 %s)" % (which, " · ".join(str(k) for k in FILES)))
        return book_file(slug, FILES[which])

    @classmethod
    def open(cls, path):
        return cls(json.load(open(path, encoding="utf-8")))

    @classmethod
    def read(cls, slug, which=None):
        p = cls.path(slug, which)
        return cls.open(p) if os.path.exists(p) else None

    @classmethod
    def load(cls, slug, which=None):
        t = cls.read(slug, which)
        if t is not None:
            t.validate()
        return t

    @classmethod
    def of(cls, data):
        t = cls(data)
        t.validate()
        return t

    # ---------------------------------------------------------------- 펼치기 ({"rule"} 참조)
    def _expand(self, node, seen=()):
        """조건식을 평가기가 바로 먹을 모양으로 — {"rule"} 펼침(pos 의 rule 은 장부 열쇠라 그대로)."""
        if isinstance(node, list):
            return [self._expand(x, seen) for x in node]
        if not isinstance(node, dict):
            return node
        if "pos" in node:                        # 포지션 값 — {"pos": "filled", "rule": 이름} 의 rule 은 참조가 아니라 장부 열쇠
            return dict(node)
        # bare {"rule": "이름"} → 그 규칙의 value(없으면 첫 갈래 when)
        if "rule" in node and set(node) - set(META) == {"rule"}:
            name = node["rule"]
            if name in seen:
                return {"manual": "연산 없음: 순환 참조 %s" % name}
            r = self._by_label.get(name)
            if not r:
                return {"manual": "연산 없음: 미해결 참조 %s" % name}
            tgt = r.get("value")
            if tgt is None and r.get("then"):
                tgt = r["then"][0].get("when")
            exp = self._expand(tgt if tgt is not None else {"all": []}, seen + (name,))
            # 참조한 규칙의 이름을 펼친 노드에 실어 화면이 "전고점 돌파" 로 보이게 한다(펼치며 이름을 떨구지 않음).
            if isinstance(exp, dict) and not exp.get("label"):
                exp = dict(exp, label=name)
                if node.get("ref") or r.get("ref"):
                    exp["ref"] = node.get("ref") or r.get("ref")
            return exp
        return {k: (v if k in META else self._expand(v, seen)) for k, v in node.items()}

    def _sub_value(self, node, val):
        """갈래의 `"$value"` 를 그 규칙의 value(이미 펼친 노드)로 치환."""
        if node == "$value":
            return val
        if isinstance(node, list):
            return [self._sub_value(x, val) for x in node]
        if isinstance(node, dict):
            return {k: (v if k in META else self._sub_value(v, val)) for k, v in node.items()}
        return node

    def _x_of(self, r):
        """규칙 r 의 qty.x 를 평가기가 먹을 모양으로 — 식이면 {"rule"} 참조를 펼치고 "$value" 를 r 의 value 로."""
        def ex(x):
            if not isinstance(x, (dict, list)):
                return x
            x = self._expand(x)
            return self._sub_value(x, self._expand(r["value"])) if "value" in r else x
        return ex

    def _on(self, r):
        """규칙의 대상 상품(생략 = None → 전부)."""
        on = r.get("on")
        return set(on) if on else None

    def _when_of(self, r, t):
        """규칙 r 의 갈래 t 의 when 을 평가기가 먹을 모양으로 — {"rule"} 펼치고 `"$value"` 를 r 의 value 로 치환."""
        w = t.get("when")
        if w is None:
            return None
        w = self._expand(w)
        if "value" in r:
            w = self._sub_value(w, self._expand(r["value"]))
        return w

    def _rules_for(self, prod):
        """이 상품에 적용되는 행동 규칙 (on 생략 = 전부)."""
        for r in self._d.get("rules", []):
            if "then" not in r:
                continue
            on = self._on(r)
            if on is None or prod in on:
                yield r

    # ---------------------------------------------------------------- 형식 검사 (v3, 느슨)
    def validate(self):
        tree = self._d
        if not isinstance(tree, dict):
            raise CondError("트리 파일은 객체여야 한다")
        if tree.get("version") != 3:
            raise CondError("version 3 트리만 읽는다 (받은 값 %r)" % tree.get("version"))
        if not isinstance(tree.get("products"), dict) or not tree["products"]:
            raise CondError("products 가 비어 있다")
        rules = tree.get("rules")
        if not isinstance(rules, list) or not rules:
            raise CondError("rules 가 비어 있다")
        self._check_shape(tree, rules)
        # 펼친 조건식의 문법만 검사({"rule"} 참조는 이미 펼쳐짐) + $index 를 쓰면 그 상품에 index 가 있어야 한다
        for prod in tree["products"]:
            for _do, label, _ref, node in self.expressions(prod):
                validate(node, "%s.%s" % (prod, label or _do))
                if not self.index(prod) and any(n.get("sym") == "$index" for n in labeled_all(node)
                                                if isinstance(n, dict) and "px" in n):
                    raise CondError("%s.%s: $index 를 쓰는데 products.%s 에 index 가 없다" % (prod, label or _do, prod))
        return True

    @staticmethod
    def _keys(obj, allowed, where):
        if not isinstance(obj, dict):
            raise CondError("%s: 객체여야 한다" % where)
        extra = sorted(set(obj) - set(allowed))
        if extra:
            raise CondError("%s: 모르는 키 %s (허용 %s)" % (where, extra, " · ".join(allowed)))

    def _check_shape(self, tree, rules):
        """파일 형식 — 맨 위·상품·규칙·갈래·qty 의 키와 값의 모양."""
        self._keys(tree, TOP_KEYS, "트리 맨 위")
        for p, v in tree["products"].items():
            self._keys(v, PRODUCT_KEYS, "products.%s" % p)
        targets = set(tree["products"])
        labels = set()
        for r in rules:
            self._keys(r, RULE_KEYS, "규칙 %r" % (r.get("label") if isinstance(r, dict) else r))
            lab = r.get("label")
            if not (isinstance(lab, str) and lab.strip()):
                raise CondError("규칙에 label(이름)이 없다: %r" % sorted(r))
            if lab in labels:
                raise CondError("규칙 label 이 책 안에서 유일하지 않다: %r" % lab)
            labels.add(lab)
            if "then" in r and "skip" in r:
                raise CondError("규칙 %r: then 과 skip 을 같이 쓸 수 없다" % lab)
            if "then" not in r and "skip" not in r and "value" not in r:
                raise CondError("규칙 %r: then(행동)·value(이름 조건)·skip(못 옮김) 중 하나가 필요하다" % lab)
            if "skip" in r and not (isinstance(r["skip"], str) and r["skip"].strip()):
                raise CondError("규칙 %r: skip 사유 문자열이 필요하다" % lab)
            bad_on = [x for x in (r.get("on") or []) if x not in targets]
            if bad_on:
                raise CondError("규칙 %r: on 의 %s 가 products 에 없다" % (lab, bad_on))
            if "then" in r and not (isinstance(r["then"], list) and r["then"]):
                raise CondError("규칙 %r: then 은 갈래 목록이어야 한다" % lab)
            if "value" in r:                       # 이름 조건은 참조되지 않아도 문법을 본다
                validate(self._expand(r["value"]), "규칙 %r value" % lab)
            for k, t in enumerate(r.get("then") or []):
                where = "규칙 %r 갈래 %d" % (lab, k)
                self._keys(t, BRANCH_KEYS, where)
                do = t.get("do")
                if do not in VERBS:
                    raise CondError("%s: 모르는 동사 %r (허용 %s)" % (where, do, " · ".join(VERBS)))
                if "when" not in t and not (do == BUY and t.get("qty")):
                    raise CondError("%s: when(조건)이 필요하다(조건 없는 갈래는 산다의 비중·1차 분할뿐)" % where)
                if "repeat" in t and (t["repeat"] is not True or do != SELL):
                    raise CondError("%s: repeat 은 판다 갈래에 true 로만(산다·안 산다의 반복은 연산 없음)" % where)
                q = t.get("qty")
                if q is not None:
                    self._keys(q, ("of", "x"), where + " qty")
                    if q.get("of") not in QTY_OF.get(do, ()):
                        raise CondError("%s: %s 갈래의 qty 종류는 %s (받은 값 %r)"
                                             % (where, do, " · ".join(QTY_OF.get(do, ())) or "없음", q.get("of")))
                    validate(self._x_of(r)(q.get("x")), where + " qty.x")

    # ---------------------------------------------------------------- 책·상품
    def _p(self, prod):
        return self._d["products"][prod]

    def products(self):
        return list(self._d["products"])

    def has(self, prod):
        return prod in self._d["products"]

    def index(self, prod):
        """상품의 기준 지수 티커 — `$index` 가 채워지는 값(없으면 None)."""
        return self._p(prod).get("index")

    def note(self, prod):
        return self._p(prod).get("note")

    def skips(self):
        """못 옮긴 규칙(skip) [{rule, ref, reason}]."""
        return [{"rule": r.get("label"), "ref": r.get("ref"), "reason": r["skip"]}
                for r in self._d.get("rules", []) if "skip" in r]

    # ---------------------------------------------------------------- 동사별 갈래
    def gate(self, prod, do):
        """등급 동사(안 산다·산다)의 갈래 any 묶음 — 갈래 하나라도 참이면 그 동사.
        등급은 포지션 독립이라 pos 쓰는 갈래(분할 2차+·보유 조건)는 뺀다 — 그것은 tranches·sells 가 본다."""
        if do not in GATES:
            raise CondError("등급 동사가 아님 %r (허용 %s)" % (do, " · ".join(GATES)))
        members = []
        for r in self._rules_for(prod):
            for t in r.get("then", []):
                if t.get("do") != do or "when" not in t:
                    continue
                w = self._when_of(r, t)
                if _uses_pos(w):                    # 포지션 조건(분할 2차+)은 등급 밖 — tranches 가 본다
                    continue
                if isinstance(w, dict):                  # 규칙 이름·소절·공통 여부를 붙여 화면이 '무슨 규칙'인지 보이게
                    w = dict(w, label=r.get("label"), ref=r.get("ref"), allprod=not r.get("on"))
                members.append(w)
        return {"any": members}

    def _qty_branches(self, prod, do, of=None):
        """이 상품의 do 갈래 [(규칙, 갈래)] — of 를 주면 qty 종류가 그것인 갈래만(qty 를 고르기만 한다 — 변환 아님)."""
        return [(r, t) for r in self._rules_for(prod) for t in r.get("then", [])
                if t.get("do") == do and (of is None or (t.get("qty") or {}).get("of") == of)]

    def weight(self, prod):
        """비중 — 산다 갈래 중 qty cash 의 첫 갈래(Qty cash). 없으면 qty.x None 인 빈 Branch."""
        for r, t in self._qty_branches(prod, BUY, "cash"):
            return Branch(r.get("label"), r.get("ref"), r.get("note"), qty=_qty(t["qty"], expand=self._x_of(r)))
        return Branch(qty=Qty("cash", None))

    def tranches(self, prod):
        """분할 차수 — 산다 갈래 중 qty budget. 1차(산횟수 조건 없는 것)는 when None."""
        return [Branch(r.get("label"), r.get("ref"), r.get("note"), when=self._when_of(r, t),
                     qty=_qty(t["qty"], expand=self._x_of(r)), allprod=not r.get("on"))
                for r, t in self._qty_branches(prod, BUY, "budget")]

    def sells(self, prod):
        """판다 갈래 [Branch(when, qty bought/held)] — qty 없으면 남은 전량. 없으면 [](judge.exit_policy 가 정책을 정한다)."""
        return [Branch(r.get("label"), r.get("ref"), r.get("note"), when=self._when_of(r, t),
                     qty=_qty(t.get("qty"), Qty("held", 1.0), self._x_of(r)), allprod=not r.get("on"),
                     repeat=bool(t.get("repeat")))
                for r, t in self._qty_branches(prod, SELL)]

    def expressions(self, prod):
        """상품 하나의 모든 식 [(동사, 라벨, ref, 식)] — 심볼·워밍업·ref 훑기용(등급 묶음은 라벨 None)."""
        out = [(do, None, None, self.gate(prod, do)) for do in GATES]
        for t in self.tranches(prod):
            if t.when is not None:
                out.append((BUY, t.label, t.ref, t.when))
        w = self.weight(prod)
        if w.qty.x is not None:
            out.append((BUY, w.label, w.ref, w.qty.x))
        for r in self.sells(prod):
            out.append((SELL, r.label, r.ref, r.when))
        return out

    # ---------------------------------------------------------------- 트리 전체 훑기
    def symbols(self, prods=None):
        """트리가 참조하는 실제 심볼 전부 — 상품 · 그 상품의 지수 · 식의 구체 티커($self·$index 는 위 둘로 채워짐)."""
        out = set()

        def walk(n):
            if isinstance(n, dict):
                if "px" in n and n.get("sym") not in ROLES:
                    out.add(n.get("sym"))
                for k, x in n.items():
                    if k not in META:
                        walk(x)
            elif isinstance(n, list):
                for x in n:
                    walk(x)

        for p in (self._d["products"] if prods is None else prods):
            out.add(p)
            if self.index(p):
                out.add(self.index(p))
            for _z, _l, _r, node in self.expressions(p):
                walk(node)
        out.discard(None)
        return out

    def warmup(self, prod=None):
        mx = 0
        for p in [prod] if prod is not None else self._d["products"]:
            for do in GATES:
                mx = max(mx, warmup_of(self.gate(p, do)))
        return mx

    def refs(self):
        """트리가 근거로 단 원문 소절 전부 — 규칙·상품의 ref("·" 로 여럿)."""
        out = set()
        items = list(self._d.get("rules", [])) + list(self._d["products"].values())
        for r in items:
            rf = r.get("ref")
            if isinstance(rf, str):
                out.update(x.strip() for x in rf.replace(",", "·").split("·") if x.strip())
            elif isinstance(rf, list):
                out.update(rf)
        return out

    # ---------------------------------------------------------------- 규칙 단위(구간② 검사기 — a·b 비교·심판 채점)
    def labels(self):
        """규칙 이름 목록(파일 순서)."""
        return [r.get("label") for r in self._d.get("rules", [])]

    def body(self, label, expand=True):
        """규칙 하나의 '뜻'(이름·출처·메모·why 를 뺀 것) — {products, value, branches[{do, when, qty}], skip}.
        expand=True 면 {"rule"} 참조를 펼친 식(a·b 가 이름을 달리 지어도 뜻이 같으면 같다), False 면 적힌 그대로
        (같은 측정을 참조 없이 두 번 쓴 '두 벌'을 가린다). 같은 뜻인지 가리는 비교용(구간② 검사기). 없는 이름이면 None."""
        r = self._by_label.get(label)
        if r is None:
            return None
        ex = self._expand if expand else (lambda n: n)
        return {"products": sorted(r.get("on") or []), "value": ex(r["value"]) if "value" in r else None,
                "branches": [{"do": t.get("do"), "when": (self._when_of(r, t) if expand else t.get("when")),
                              "qty": t.get("qty")} for t in r.get("then", [])],
                "skip": r.get("skip")}

    def value(self, label, expand=True):
        """규칙의 측정(value) — 없으면 None. expand=False 면 적힌 그대로({"rule"} 참조를 펼치지 않음)."""
        r = self._by_label.get(label) or {}
        if "value" not in r:
            return None
        return self._expand(r["value"]) if expand else r["value"]

    def why(self, label):
        """심판이 그 규칙을 a·b 중 고른 이유(최종 트리만) — 없으면 None."""
        return (self._by_label.get(label) or {}).get("why")


    def cards(self):
        """규칙 카드 [Card](파일 순서) — 판정 로직(동사별 재배치·등급·펼치기) 안 거친 트리 1:1. 원시 트리 보기(화면)용."""
        out = []
        for r in self._d.get("rules", []):
            if not isinstance(r, dict):
                continue
            val = r.get("value")
            brs = [CardBranch(t.get("do"),
                              self._sub_value(t["when"], val) if ("when" in t and val is not None) else t.get("when"),
                              Qty((t.get("qty") or {}).get("of"), (t.get("qty") or {}).get("x")) if t.get("qty") else None,
                              bool(t.get("repeat")))
                   for t in r.get("then") or [] if isinstance(t, dict)]
            out.append(Card(r.get("label"), r.get("ref"), r.get("note"), r.get("on"), val, brs, r.get("skip"), r.get("why")))
        return out

    def conditions(self):
        """트리에 적힌 조건식 전부(펼치기 전, 적힌 그대로) — 규칙의 value·갈래 when·qty 식. 검사기가 수동 잎의
        이름·사유를 훑는 용도(파일 키는 모른 채 조건 문법만 본다)."""
        out = []
        for r in self._d.get("rules", []):
            if "value" in r:
                out.append(r["value"])
            for t in r.get("then", []):
                if "when" in t:
                    out.append(t["when"])
                if isinstance((t.get("qty") or {}).get("x"), dict):
                    out.append(t["qty"]["x"])
        return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3 and sys.argv[1] == "fmt":
        fmt_files(sys.argv[2:])
    else:
        print("사용: python -m tree.gateway fmt <json 파일...>   (구간② 파일 공통 직렬화)")
