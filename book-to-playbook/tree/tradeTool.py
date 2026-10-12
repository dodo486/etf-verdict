#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조건 트리 DSL 평가 한 파일 — 문법·평가(앞 절) · 등급·금액·수집(뒤 절). 공개 이름은 모듈 수준 정의 그대로
(from tree.tradeTool import series, Ctx, RuleSeries …). 공통 직렬화: python -m tree.tradeTool fmt <파일...>

■ 조건 트리 — 규칙의 단일 문법과 그 평가기 (책 무관)

왜 있나
  옛 판정식은 type 마다 손으로 짠 계산기(16종)였다. 새 조건마다 코드가 늘었고, 이름과
  계산이 다른 계산기(전고점 '유지'가 실은 연속 신고가, '눌림 일수'에 반등일 포함)와
  한 필드의 두 뜻(op 가 방향 표시이자 비교 연산자)이 조용히 틀린 판정을 냈다.
  또 규칙 형식이 평평해서(조건 목록 + need 숫자) 원문 구조(택1·N개 중 M개·
  필수 조건)를 못 담았다. 이 파일은 둘 다를 없앤다:
    · 계산은 원시 시계열 연산 몇 개의 조합뿐 — 새 조건은 코드가 아니라 트리로 쓴다.
    · 구조는 all / any / atleast / not 로 그대로 적는다.

값
  모든 식은 '날짜별 시계열'(달력 길이의 리스트)이다. 숫자 시계열은 float|None,
  조건 시계열은 True|False|None. None = 데이터가 없어 모름 — 조용히 거짓으로 치지 않는다.
  모든 연산은 인과적이다(그날까지의 값만 쓴다) — tree.verify_primitives 가 강제한다.

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

■ 등급 — 등급의 뜻(구간② DSL) — 조건 트리(books/<slug>/tree.json) → 날짜별 등급·금액·비중 (책 무관). 트리의 '뜻'은 여기 한 벌뿐이다.

등급 (동사 둘 — 사다리는 grade_rules.json):
  안 산다 갈래 하나라도 참 → ⛔ 안 산다 · 산다 갈래 하나라도 참 → ✅ 산다 · 둘 다 아님 → ⚪ 관망
수동(manual) 조건은 '확인됨/안 됨' 두 번 평가한다:
  안 돼도 산다(비관) → ✅ · 확인돼야 산다(낙관만) → 🟡 확인 대기 · 데이터 부족으로 못 정함 → ❔ 판정 불가
  비관 = 산다의 수동은 거짓, 안 산다의 수동은 참 / 낙관 = 그 반대(BUY_SIDE).
얼마나·판다:
  weight   산다 qty cash = 총 투자금 대비 비중(%) · tranches = 산다 qty budget 분할(2차 이후는 포지션 값으로)
  sells    판다 — 보유분이 있을 때만 평가(구간③ trading)

판정은 봉이 끝난 직후(그날까지의 봉)로 낸다 — cond 연산이 전부 인과적이라 전체 이력을 한 번 계산해
날짜로 꺼내도 미래를 보지 않는다(tree.verify_primitives 가 강제).

트리는 원본 dict 가 아니라 TreeGateway(tree/gateway.py — 트리를 읽는 유일한 출입구)로 받는다.
같은 뜻을 만드는 쪽(authoring.extract.verify_tree 의 사례·authoring.extract.compare 의 a/b 비교)과 읽는 쪽(구간③ 판정·백테스트)이 함께 쓴다 — 화면용 설명(view·
측정 증거)은 판단자(judge/judge·explain)가 이 평가 문맥으로 빚는다 — 화면은 그리기만.
"""
import json
import math
import os
from datetime import datetime, timedelta

from market import md_feed

# ================= 문법·평가 (옛 cond.py) =================
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
STREAK_CAP = 400          # 연속·경과일을 거꾸로 셀 때의 상한(데이터 길이보다 길면 무의미)


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


# ------------------------------------------------------------------ 평가
class Ctx:
    """평가 문맥. hist={심볼: [Candle(date,open,high,low,close,volume)]}, cal=날짜 목록."""

    def __init__(self, hist, cal, self_sym, index_sym=None, manual_as=None, pos=None, asof=None,
                 session_close=None, answers=None):
        """self_sym = 평가 중인 상품($self) · index_sym = 그 상품의 지수($index, 없으면 None).
        pos = (첫 매수일 인덱스, 평균 매입가 | 날짜별 평균 매입가 목록[, 장부]) — 판다·분할 갈래 평가 때만.
        장부 = {"filled": {규칙 이름 | None(전체): 날짜별 산 횟수}, "sold": 날짜별 판 비율} — 없으면 filled·sold 는 모름.
        asof = 관측 시각(UTC datetime) — 일봉 확정(settled) 경계를 정한다. None 이면 실제 지금.
        session_close = {심볼: {YYYYMMDD: 그날 정규장 마감(UTC datetime, tz-aware)}} — 일봉 확정(settled) 경계.
          거래소 캘린더(md_feed.sessions)에서 캐려 밖(cond)에서 넣는다(평가기는 jhts 를 모른다). 장중 asof 에서
          '마감이 asof 이후'인 일봉은 아직 미확정이므로 None 으로 가린다(look-ahead 0). asof=None 이거나 캘린더가
          비면(미설치·조회 실패) 아무것도 가리지 않는다 — 없는 캘린더가 조용히 일봉을 전부 지우지 않게.
        answers = {answer_key: True|False} — 사람이 답한 수동(없는 열쇠는 manual_as). None 이면 옛 동작 그대로."""
        self.pos = pos
        self.asof = asof          # 관측 시각(UTC datetime) — 일봉 확정 경계. None 이면 실제 지금
        self.hist = hist
        self.cal = list(cal)
        self.self_sym = self_sym
        self.index_sym = index_sym
        self.manual_as = manual_as
        self.session_close = session_close or {}  # {심볼: {YYYYMMDD: 마감 UTC datetime}} — 일봉 확정 경계
        self._px = {}
        self._memo = {}
        self._smap = {}       # 심볼 → settled_map 캐시(일봉축 마지막 확정 index 지도)
        self._flip = None
        self.answers = answers

    def flipped(self):
        """수동 가정을 뒤집은 문맥(not 아래 평가용). 시세 캐시는 공유한다. 사람의 답(answers)은 뒤집지 않는다."""
        if self.manual_as is None:
            return self
        if self._flip is None:
            f = Ctx(self.hist, self.cal, self.self_sym, self.index_sym, not self.manual_as, self.pos,
                    self.asof, self.session_close, self.answers)
            f._px, f._smap, f._flip = self._px, self._smap, self
            self._flip = f
        return self._flip

    def manual_value(self, node):
        """수동 잎 하나의 값 — 사람이 답했으면 그 답, 아니면 manual_as(극성 반영된 가정)."""
        if self.answers is not None:
            a = self.answers.get(answer_key(node, self.self_sym))
            if a is not None:
                return a
        return self.manual_as

    def bind(self, sym):
        """역할 → 실제 티커($self → 상품, $index → 그 상품의 지수). 구체 티커는 그대로."""
        if sym == "$self":
            return self.self_sym
        if sym == "$index":
            if not self.index_sym:
                raise CondError("$index 가 정의되지 않은 상품: %s (products 에 index 가 없다)" % self.self_sym)
            return self.index_sym
        return sym

    def px(self, sym, field, tf="1d"):
        """심볼·필드의 asof 축 시계열(달력 길이). 일봉(tf="1d")은 날짜별 '확정(settled)' 일봉(장중 asof 면 아직
        마감 안 된 그날 일봉은 None 으로 가림 — look-ahead 0). 일봉이 아닌 봉(1m·5m)은 시세 경로가 없어 전부 None(모름)."""
        key = (sym, field, tf)
        if key not in self._px:
            if tf == "1d":
                by = {c.date: getattr(c, field) for c in (self.hist.get(sym) or [])}
                settled = self._settled_dates(sym)   # None = 가리지 않음(asof 없음·캘린더 없음)
                self._px[key] = [by.get(d) if (settled is None or d in settled) else None
                                 for d in self.cal]
            else:
                self._px[key] = [None] * len(self.cal)
        return self._px[key]

    def _settled_dates(self, sym):
        """일봉 확정(settled) 규칙: 심볼의 거래소 세션 마감이 asof 이하인 날짜 집합(그 날 일봉은 확정 → 읽어도 됨).
        asof 가 없으면(라이브 '지금' = 늘 마지막 확정봉 계약) 또는 그 심볼의 세션 캘린더가 없으면(미설치·조회 실패)
        None 을 돌려 '아무것도 가리지 않음'으로 떨어뜨린다 — 캘린더가 없다고 조용히 일봉을 전부 지우지 않게."""
        if self.asof is None:
            return None
        closes = self.session_close.get(sym)
        if not closes:
            return None
        # 세션 마감(마감 == asof 도 확정)이 asof 이하인 날만 확정 — 마감 > asof 인 '진행 중' 봉은 뺀다.
        return {d for d, close in closes.items() if close is not None and close <= self.asof}

    def settled_map(self, sym):
        """'일봉축 마지막 확정봉' 지도 — 길이 L 리스트 m 에서 m[i] = cal[i] 이하 마지막 '확정(settled)' 일봉의 index
        (그런 확정봉이 없으면 None). 일봉-tf 식(일봉 잎·그 위 창/lag/barssince…)을 평가할 때, 평가 index i 를 'asof 이하
        마지막 확정 일봉'으로 바꾸는 데 쓴다 — 장중 asof 면 오늘 봉은 미확정이라 m[i] = 어제 index → 일봉 잎·ma20 이
        '어제까지의 실제값'(None 아님)으로 나온다. 오늘 미확정 봉은 절대 안 본다(look-ahead 0).

        계약은 _settled_dates 와 같다: asof 없음·캘린더 없음이면 None(가리지 않음 = no-op, EOD/라이브 동작 그대로).
        EOD/장후 asof 에선 오늘 봉까지 다 확정 → 모든 i 에서 m[i] = i(항등) → 일봉 파리티 그대로 유지."""
        if sym not in self._smap:
            settled = self._settled_dates(sym)
            if settled is None:
                self._smap[sym] = None      # no-op — 가리지 않는다(기존 동작 보존)
            else:
                m, last = [], None
                for i, d in enumerate(self.cal):
                    if d in settled:
                        last = i
                    m.append(last)          # cal[i] 이하 마지막 확정 index(없으면 None)
                self._smap[sym] = m
        return self._smap[sym]


def _num(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def _exact(x):
    """정확한 수(하한 아님)."""
    return _num(x) and not isinstance(x, AtLeast)


def _cmp(op, x, y):
    """3값 비교 — 하한(AtLeast)이 끼면 하한만으로 결론이 날 때만 참/거짓."""
    if not (_num(x) and _num(y)):
        return None
    lx, ly = isinstance(x, AtLeast), isinstance(y, AtLeast)
    if not lx and not ly:
        return {"gt": x > y, "ge": x >= y, "lt": x < y, "le": x <= y}[op]
    if lx and ly:
        return None
    if ly:                                   # b op AtLeast → AtLeast op' b
        op, x, y = {"gt": "lt", "ge": "le", "lt": "gt", "le": "ge"}[op], y, x
    a = float(x)                             # 참값 ≥ a
    if op == "gt":
        return True if a > y else None
    if op == "ge":
        return True if a >= y else None
    if op == "lt":
        return False if a >= y else None
    return False if a > y else None          # le


def _window(s, i, n):
    """s[i-n+1..i] — 하나라도 없으면 None(창이 덜 찼거나 결측)."""
    if i - n + 1 < 0:
        return None
    w = s[i - n + 1:i + 1]
    return w if all(_exact(x) for x in w) else None


def _and3(vals):
    if any(v is False for v in vals):
        return False
    if any(v is None for v in vals):
        return None
    return True


def _or3(vals):
    if any(v is True for v in vals):
        return True
    if any(v is None for v in vals):
        return None
    return False


# 일봉축 조회(asof 이하 마지막 확정봉) 대상이 아닌 잎 — 하나라도 있으면 그 식은 '1d-순수'가 아니다.
#   · 일봉 아닌 px(tf 1m/5m)  : 일봉 확정 경계로 당기면 안 된다(값은 지금 전부 None — 모름).
#   · manual/pos              : 일봉 봉이 아닌 값(수동·포지션).
_NON_DAILY = ("manual", "pos")


def _daily_axis(node, ctx):
    """node 가 '1d-순수'(모든 px 잎이 tf=1d 이고 분봉·수동·pos 잎이 없음)면, 그 1d 심볼들의 settled_map 을
    돌려준다(일봉축 '마지막 확정봉' 지도). 아니거나, 심볼들의 지도가 엇갈리거나, 지도가 no-op(asof 없음·캘린더 없음)이면
    None — 그 경우 gather 를 건너뛴다(기존 동작 그대로). 같은 시장 심볼은 지도가 같으므로(세션 경계가 시장별) 한 지도로
    모은다 — 서로 다른 시장이 한 1d-순수 식에 섞이면(지도 엇갈림) 당기지 않는다(조용히 잘못 당기느니 기존 masked-None)."""
    syms = set()
    for n in labeled_all(node):
        if not isinstance(n, dict):
            continue
        op = _op_of(n)
        if op == "px":
            if n.get("tf", "1d") != "1d":
                return None                 # 분봉/5분봉 잎 — 1d-순수 아님
            syms.add(ctx.bind(n["sym"]))
        elif op in _NON_DAILY or is_unknown(n):
            return None                     # 수동("?" 식 포함)·포지션 — 1d-순수 아님
    if not syms:
        return None                         # px 잎이 없는 순수 숫자/비교식 — 당길 일봉축이 없음
    maps = [ctx.settled_map(sym) for sym in syms]
    first = maps[0]
    if first is None or any(m != first for m in maps[1:]):
        return None                         # no-op(asof 없음·캘린더 없음) 또는 시장별 지도 엇갈림 → 당기지 않음
    return first


def series(node, ctx):
    """노드 → 달력 길이 시계열.

    일봉축 재해석(장중 asof): 노드가 '1d-순수'면(모든 px 잎 tf=1d·분봉/수동/pos 없음), 평가 결과의 각 index i 를
    'asof 이하 마지막 확정 일봉' 값으로 당긴다(_daily_axis·settled_map). 장중 asof 면 오늘 봉은 미확정이라 m[i]=어제 →
    일봉 잎·ma20 등이 '어제까지 실제값'(None 아님)으로 나온다. 당김은 settled index 에서만 읽으므로 오늘 미확정 종가는
    어떤 파생값에도 새지 않는다(look-ahead 0). 당김은 멱등(m[m[i]]==m[i])이라 잎·그 위 1d 노드 어디서 걸어도 결과가
    같다 — 그래서 '가장 바깥 1d 노드'를 따로 찾지 않고 모든 노드에서 한 번씩 안전하게 건다. EOD/장후 asof·asof None·캘린더
    없음에선 m[i]==i(또는 no-op)라 항등 → 일봉 파리티·기존 동작 그대로."""
    key = (repr(node), ctx.manual_as)
    if key in ctx._memo:
        return ctx._memo[key]
    # 노드 레벨 on: 평가 중 상품이 그 노드의 on 에 없으면 그 노드는 '항상 참'(제약 안 함 — all/atleast 안에서 투명).
    #   규칙은 공통으로 두고 한 상품에만 더 붙는 조건을 쪼개지 않고 단다. on 이 없거나 상품이 들어 있으면 평소대로.
    if isinstance(node, dict):
        on = node.get("on")
        if on and ctx.self_sym not in on:
            out = [True] * len(ctx.cal)
            ctx._memo[key] = out
            return out
    out = _series(node, ctx)
    m = _daily_axis(node, ctx)
    if m is not None:
        out = [out[m[i]] if m[i] is not None else None for i in range(len(out))]
    ctx._memo[key] = out
    return out


def _series(node, ctx):
    L = len(ctx.cal)
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return [float(node)] * L
    if node == UNKNOWN:
        return [None] * L                    # 모르는 숫자 — 값은 모름(판단은 그것을 품은 노드가 수동으로)
    op = _op_of(node)
    v = node[op]
    if is_unknown(node):
        return [ctx.manual_value(node)] * L  # 저자가 숫자를 안 준 판단 — 사람이 정한다(수동과 같은 규칙)
    if op in WINDOW + ("lag",) and v[1] == UNKNOWN:
        return [None] * L                    # 기간을 모름 — 값도 모름
    S = lambda n: series(n, ctx)

    if op == "px":
        return ctx.px(ctx.bind(node["sym"]), v, node.get("tf", "1d"))

    if op in ARITH:
        a, b = S(v[0]), S(v[1])
        out = []
        for x, y in zip(a, b):
            if not (_num(x) and _num(y)):
                out.append(None)
            elif isinstance(x, AtLeast) or isinstance(y, AtLeast):
                # 하한 + 상수 = 하한, 하한 − 상수 = 하한. 그 밖(하한끼리·곱·나눗셈·상수−하한)은 모름.
                if op == "add" and not (isinstance(x, AtLeast) and isinstance(y, AtLeast)):
                    out.append(AtLeast(x + y))
                elif op == "sub" and isinstance(x, AtLeast) and not isinstance(y, AtLeast):
                    out.append(AtLeast(x - y))
                else:
                    out.append(None)
            elif op == "max":
                out.append(max(x, y))
            elif op == "min":
                out.append(min(x, y))
            elif op == "add":
                out.append(x + y)
            elif op == "sub":
                out.append(x - y)
            elif op == "mul":
                out.append(x * y)
            else:
                out.append(x / y if y != 0 else None)
        return out

    if op in CMP:
        a, b = S(v[0]), S(v[1])
        return [_cmp(op, x, y) for x, y in zip(a, b)]

    if op == "abs":
        return [abs(x) if _exact(x) else None for x in S(v)]

    if op == "case":
        conds = [S(c) for c, _ in v]
        vals = [S(x) for _, x in v]
        other = S(node["else"])
        out = []
        for i in range(L):
            val = other[i]
            for c, x in zip(conds, vals):
                if c[i] is None:
                    val = None
                    break
                if c[i]:
                    val = x[i]
                    break
            out.append(val)
        return out

    if op in WINDOW:
        s, n = S(v[0]), v[1]
        agg = {"sum": sum, "highest": max, "lowest": min}[op]
        return [None if w is None else agg(w) for w in (_window(s, i, n) for i in range(L))]

    if op == "lag":
        s, k = S(v[0]), v[1]
        return [s[i - k] if i - k >= 0 else None for i in range(L)]

    if op in ("all", "any"):
        cols = [S(c) for c in v]
        f = _and3 if op == "all" else _or3
        return [f([c[i] for c in cols]) for i in range(L)]

    if op == "atleast":
        cols = [S(c) for c in node["of"]]
        out = []
        for i in range(L):
            vals = [c[i] for c in cols]
            t = sum(1 for x in vals if x is True)
            u = sum(1 for x in vals if x is None)
            out.append(True if t >= v else (False if t + u < v else None))
        return out

    if op == "not":
        return [x if x is None else (not x) for x in series(v, ctx.flipped())]

    if op == "barssince":
        c = S(v)
        out = []
        for i in range(L):
            val, j = None, i
            while j >= 0 and i - j < STREAK_CAP:
                if c[j] is None:
                    break                   # 모르는 날을 지나칠 수 없다
                if c[j]:
                    val = float(i - j)
                    break
                j -= 1
            if val is None and i - j > 0:
                val = AtLeast(i - j)        # 그 사이엔 참이 없었다 — 최소 i-j 거래일
            out.append(val)
        return out

    if op == "valuewhen":
        c, s = S(v[0]), S(v[1])
        out = []
        for i in range(L):
            val, j = None, i
            while j >= 0 and i - j < STREAK_CAP:
                if c[j] is None:
                    break
                if c[j]:
                    val = s[j] if _exact(s[j]) else None
                    break
                j -= 1
            out.append(val)
        return out

    if op in ("minsince", "maxsince"):
        c, s = S(v[0]), S(v[1])
        agg = min if op == "minsince" else max
        out = []
        for i in range(L):
            val, j, seen = None, i, []
            while j >= 0 and i - j < STREAK_CAP:
                if c[j] is None or not _exact(s[j]):
                    seen = None             # 구간 안에 모르는 날이 있으면 최저/최고도 모른다
                    break
                seen.append(s[j])
                if c[j]:
                    val = agg(seen)
                    break
                j -= 1
            out.append(val if seen is not None else None)
        return out

    if op == "manual":
        return [ctx.manual_value(node)] * L

    if op == "pos":
        if ctx.pos is None:
            raise CondError("pos 는 매도·분할 규칙 안에서만 쓴다")
        e, cost = ctx.pos[:2]                # cost = 평균 매입가(숫자) 또는 날짜별 평균 매입가 목록(분할 매수)
        if v in ("filled", "sold"):          # 장부 값 — 체결 워크(trades)가 날짜별로 넣는다. 장부가 없으면 모름
            book = ctx.pos[2] if len(ctx.pos) > 2 else None
            s = None if book is None else (book["sold"] if v == "sold" else book["filled"].get(node.get("rule"), [0] * L))
            return [float(s[i]) if (s is not None and i >= e and s[i] is not None) else None for i in range(L)]
        close = ctx.px(ctx.self_sym, "close")
        px = cost if isinstance(cost, list) else [cost] * L
        ret = [((close[i] / px[i] - 1) * 100 if (i >= e and _exact(close[i]) and px[i]) else None)
               for i in range(L)]
        if v == "ret":
            return ret
        if v == "days":
            return [float(i - e) if i >= e else None for i in range(L)]
        out, acc = [], None
        agg = max if v == "maxret" else min
        for i in range(L):
            if i < e or ret[i] is None:
                acc = None if i < e else acc
                out.append(None if i < e else acc)
                continue
            acc = ret[i] if acc is None else agg(acc, ret[i])
            out.append(acc)
        return out

    raise CondError("모르는 연산 %r" % op)


# ------------------------------------------------------------------ 동사의 뜻 · 파일 직렬화
# 트리 v3 의 규칙 갈래는 동사 셋 중 하나를 한다 — 여기 한 곳이 정본이다(화면은 판정 JSON 의 verbs 로 받는다).
# 트리 파일의 키 배치·형식 검사·탐색은 tree/gateway.py(TreeGateway) 하나가 맡는다 — 여기는 동사의 이름과 뜻만.
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
    파일을 쓴 뒤 부르는 공통 도구: python -m tree.tradeTool fmt <파일...>"""
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

# ================= 등급·금액·수집 (옛 grade.py) =================
GRADES = {
    "buy": "✅ 산다",
    "confirm": "🟡 확인 대기",
    "avoid": "⛔ 안 산다",
    "wait": "⚪ 관망",
    "unknown": "❔ 판정 불가",
}
# 등급 판정 사다리의 '뜻'은 코드가 아니라 데이터(tree/grade_rules.json)에 있다 — 규칙을 바꾸면
# 거기 한 곳만 고친다. 등급을 내는 곳은 grade_key 하나 — 화면은 판정 JSON 의 key 를 그대로 그린다(서버 권위:
# 사람이 답한 수동도 서버가 Ctx answers 로 풀어 등급을 다시 낸다).
GRADE_RULES = json.load(
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "grade_rules.json"), encoding="utf-8"))
# 판정 전에 과거 시세를 며칠치(달력일) 미리 당겨올지 — '워밍업'. 트리가 쓰는 가장 긴 창
# (예: 52주 신고가 = 252거래일 ≈ 달력 365일)이 첫날부터 제대로 서도록 넉넉히 둔다.
# ★ 여기 한 곳이 정본이다 — 매일 판정(web/verdict_view)·백테스트(backtest)·검증(authoring.extract.verify_tree)이
#   모두 이 값을 가져다 쓴다. 과거엔 세 곳에 따로(500/400/500) 박혀 백테스트만 어긋났었다.
WARMUP_DAYS = 500


def history(trees, start):
    """트리(들 — TreeGateway)가 쓰는 모든 심볼의 일봉 {심볼: 일봉} — 수집 단계(md_feed) 하나로 받는다.
    jhts 는 md_feed 에서만 만진다(팀 경계). 일봉 아닌 봉(tf 1m·5m)은 받지 않는다 — 그 조건은 모름(None)."""
    syms = set()
    for t in trees if isinstance(trees, list) else [trees]:
        syms |= t.symbols()
    return md_feed.histories(syms, start)


def history_back(trees, extra_days=0):
    """history 를 '지금부터 extra_days + 워밍업(WARMUP_DAYS)일 과거'부터 받는다 — 수집 시작일을 세는 한 곳.
    백테스트(days)·라이브/재생(0)·검사(365*년 등)가 다 이걸로 부른다(각자 날짜 계산을 복붙하지 않는다)."""
    start = (datetime.now() - timedelta(days=extra_days + WARMUP_DAYS)).strftime("%Y%m%d")
    return history(trees, start)


def session_closes(symbols, cal, asof):
    """일봉 확정(settled) 경계 — {심볼: {YYYYMMDD: 그날 정규장 마감(UTC datetime)}}. Ctx 가 장중 asof 에서
    '마감이 asof 이후'인 일봉(아직 미확정)을 가리는 데 쓴다. 경계는 하드코딩이 아니라 거래소 캘린더
    (md_feed.sessions)에서 읽는다. asof 가 없으면(라이브 '지금' = 늘 마지막 확정봉) 가릴 것이 없으므로 빈 dict.
    캘린더가 비면(jhts 미설치·조회 실패) 해당 심볼은 빠진다 → cond 가 '가리지 않음'으로 떨어진다(캘린더 없다고
    일봉을 조용히 전부 지우지 않게). 시장(US/KR)이 같은 심볼은 캘린더를 한 번만 조회해 공유한다."""
    import datetime as _dt
    if asof is None or not cal:
        return {}
    start, end = min(cal), max(cal)
    by_market = {}      # market → {YYYYMMDD: 마감 UTC}
    out = {}
    for sym in sorted(set(symbols)):
        mkt = md_feed.market_of(sym)
        if mkt is None:
            continue
        if mkt not in by_market:
            by_market[mkt] = {s.date: s.close.astimezone(_dt.timezone.utc)
                              for s in md_feed.sessions(mkt, start, end) if s.close is not None}
        closes = by_market[mkt]
        if closes:
            out[sym] = closes
    return out


class RuleSeries:
    """한 상품의 등급 동사(안 산다·산다)·비중을 전체 달력에 대해 한 번 계산해 둔다."""

    def __init__(self, tree, product, prices, days, asof=None, answers=None):
        """tree = 트리 출입구(TreeGateway) · product = 판정할 상품 — 그 상품의 규칙을 골라 평가한다. asof = 관측 시각(UTC datetime) — 일봉은 asof 이하
        확정(settled) 봉만 본다(미확정 그날 일봉은 None). None 이면 실제 지금(일봉은 마지막 확정봉).
        answers = 사람이 답한 수동 {answer_key: 참/거짓} — 등급·금액·비중이 그 답으로 풀린다(서버 권위).
        None 이면 옛 동작 그대로."""
        self.tree, self.product, self.days, self.prices = tree, product, list(days), prices
        self.index = tree.index(product)
        sc = session_closes(tree.symbols([product]), list(days), asof)
        mk = lambda m: Ctx(prices, days, product, self.index, manual_as=m, asof=asof, session_close=sc, answers=answers)
        self.ctx = {True: mk(True), False: mk(False), None: mk(None)}
        s = lambda node, m: series(node, self.ctx[m])
        self.opt = {do: s(tree.gate(product, do), BUY_SIDE[do]) for do in GATES}
        self.pes = {do: s(tree.gate(product, do), not BUY_SIDE[do]) for do in GATES}
        w = tree.weight(product).qty.x                # 비중 식(Qty "cash") — None = 저자 미명시
        self.weight = {m: (s(w, m) if w is not None else None) for m in (None, True, False)}
        # 데이터 완전성 가드 — 이 상품 등급이 실제로 쓰는 가장 긴 워밍업(트리에서 파생, 하드코딩 아님).
        #   그보다 '확정 봉'이 적은 초기 구간의 1d 신호는 창이 덜 차 조용히 None/틀릴 수 있어 신뢰불가다
        #   → grade_key 가 '불완전 데이터(❔ 보류)'로 표시한다(✅/🚫 확신 금지). WARMUP_DAYS(fetch 버퍼)와 무관.
        self.warmup = tree.warmup(product)
        # 심볼 확정봉 지도 — asof 장중이면 오늘 미확정 봉을 뺀 '마지막 확정 index'(없으면 전부 확정 = 항등).
        #   여러 심볼을 보면 가장 적게 확정된 심볼(지연된 feed)이 기준이다 — 하나라도 모자라면 불완전.
        self._confirmed = self._confirmed_index_map()

    def _confirmed_index_map(self):
        """날짜별 '이 상품 등급이 쓰는 모든 심볼이 확정한 봉 수 − 1'(= 확정 index). 어떤 심볼이 그 index 를
        아직 확정 못 했으면(지연된 feed·asof 장중 미확정) 그 심볼 기준으로 낮춘다. 확정봉이 하나도 없으면 -1.
        캘린더가 없거나 asof 가 없으면(라이브 지금) settled_map 이 no-op(None) → 날짜 index 그대로(항등)."""
        ctx = self.ctx[None]
        syms = sorted(set(self.tree.symbols([self.product])) | {self.product})
        maps = [ctx.settled_map(s) for s in syms]
        out = []
        for day in range(len(self.days)):
            idxs = []
            for m in maps:
                idxs.append(day if m is None else m[day])   # None map = 가리지 않음(항등)
            out.append(-1 if any(x is None for x in idxs) else min(idxs))
        return out

    def incomplete(self, day):
        """그날(day) 1d 등급이 '불완전 데이터'인가 — 확정 봉이 필요 워밍업보다 적으면 True.
        확정 index(가장 늦은 심볼 기준)가 warmup 미만이면 가장 긴 창이 덜 차 신호가 신뢰불가다."""
        return self._confirmed[day] < self.warmup

    # ---------------------------------------------------------------- 등급
    def grade_key(self, day):
        # 데이터 완전성 가드 — 워밍업이 모자란 봉은 확신 판정을 내지 않고 '판정 불가(불완전 데이터)'로 둔다.
        #   (조용히 None 이 섞인 opt/pes 로 ✅/🚫 를 내면 모르고 매매하게 된다 — 정직성 원칙.)
        if self.incomplete(day):
            return "unknown"
        # grade_rules.json 을 위에서 아래로 본다 — when 의 모든 동사가 맞는 첫 규칙이 이긴다.
        # 값은 3값(True/False/None) — 'is' 로 정확히 맞춘다(None 은 True·False 어디에도 안 맞는다).
        views = {"opt": self.opt, "pes": self.pes}
        for rule in GRADE_RULES["rules"]:
            view = views[rule["view"]]
            if all(view[do][day] is want for do, want in rule["when"].items()):
                return rule["key"]
        return GRADE_RULES["default"]

    # ---------------------------------------------------------------- 비중
    def weight_of(self, day):
        """그날 비중(%) — 수동 때문에 모르면 (None, [가능한 값들]) 로 범위를 함께 돌려준다."""
        if self.weight[None] is None:
            return None, None
        v = self.weight[None][day]
        if v is not None:
            return v, None
        alt = sorted({x for x in (self.weight[True][day], self.weight[False][day]) if x is not None})
        return None, alt or None

    # ---------------------------------------------------------------- 설명
    def explain(self, day):
        """라벨 달린 노드의 그날 값 — 수동은 '모름'(None)으로 둔 평가. {동사: [(label, ref, 값)]}"""
        return {do: [(n.get("label"), n.get("ref"), series(n, self.ctx[None])[day])
                     for n in labeled(self.tree.gate(self.product, do))] for do in GATES}

    def top(self, day):
        """동사마다 맨 위 라벨 노드들의 그날 값(사유 문장용 — 안쪽 노드까지 늘어놓으면
        not 아래의 '거짓 = 정상' 노드가 '미충족'으로 읽힌다). 수동은 모름(None)."""
        return {do: [(n.get("label"), n.get("ref"), series(n, self.ctx[None])[day])
                     for n in _top_labeled(self.tree.gate(self.product, do))] for do in GATES}

    def manual_items(self, day=None):
        """사람 확인이 필요한 조건 [(동사, 라벨, ref)] — 판다(보유분)는 뺀다."""
        return [(z, n.get("label") or manual_text(n), n.get("ref"))
                for z, _l, _r, node in self.tree.expressions(self.product) if z != SELL for n in manual_leaves(node)]


def _top_labeled(node):
    """라벨 달린 가장 바깥 노드들. all/any/atleast 는 펼치고, not 아래는 들어가지 않는다."""
    if not isinstance(node, dict):
        return []
    if node.get("label"):
        return [node]
    kids = node.get("all") or node.get("any") or (node.get("of") if "atleast" in node else None) or []
    out = []
    for k in kids:
        out.extend(_top_labeled(k))
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3 and sys.argv[1] == "fmt":
        fmt_files(sys.argv[2:])
    else:
        print("사용: python -m tree.tradeTool fmt <json 파일...>   (구간② 파일 공통 직렬화)")
