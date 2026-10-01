#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조건 트리 — 규칙의 단일 문법과 그 평가기 (책 무관).

왜 있나
  옛 판정식은 type 마다 손으로 짠 계산기(16종)였다. 새 조건마다 코드가 늘었고, 이름과
  계산이 다른 계산기(전고점 '유지'가 실은 연속 신고가, '눌림 일수'에 반등일 포함)와
  한 필드의 두 뜻(op 가 방향 표시이자 비교 연산자)이 조용히 틀린 판정을 냈다.
  또 규칙 형식이 평평해서(filter/entry/avoid 목록 + need 숫자) 원문 구조(택1·N개 중 M개·
  필수 조건)를 못 담았다. 이 파일은 둘 다를 없앤다:
    · 계산은 원시 시계열 연산 몇 개의 조합뿐 — 새 조건은 코드가 아니라 트리로 쓴다.
    · 구조는 all / any / atleast / not 로 그대로 적는다.

값
  모든 식은 '날짜별 시계열'(달력 길이의 리스트)이다. 숫자 시계열은 float|None,
  조건 시계열은 True|False|None. None = 데이터가 없어 모름 — 조용히 거짓으로 치지 않는다.
  모든 연산은 인과적이다(그날까지의 값만 쓴다) — verify_primitives 가 강제한다.

3값 논리
  all : 하나라도 False → False, 아니면 하나라도 None → None, 아니면 True (빈 all = True)
  any : 하나라도 True → True, 아니면 하나라도 None → None, 아니면 False (빈 any = False)
  atleast n : True 개수 ≥ n → True, True+None < n → False, 그 외 None
  not : True↔False, None 은 None

하한(AtLeast)
  streak·barssince 가 모르는 날(또는 데이터 시작)에 닿으면 정확한 길이는 모르지만 '최소 N'은 안다.
  그 값은 AtLeast(N) 로 담기고, 비교는 하한만으로 결론이 나면 참/거짓(예: 최소 50일 ≥ 3 → 참),
  아니면 None 이다. 덧셈·뺄셈(상수)은 하한을 유지하고, 그 밖의 연산(창·곱·나눗셈)에선 None 이 된다.

수동(manual)
  {"manual": "사유"} 는 자동으로 알 수 없는 조건(장중·뉴스 등). 값은 평가 시 manual_as 로
  주어진다(엔진이 '확인되면/안 되면' 두 번 평가해 '확인 대기'를 가린다). 데이터 None 과 다르다.
  극성: not 아래의 수동은 반대 값을 받는다(manual_as=True 는 '수동이 전부 구역에 유리하게 풀림'
  이라는 뜻 — '겹치면 쉼' = not(all(.., 수동)) 에서 낙관 평가가 오히려 겹침을 가정하던 버그를 막는다).

문법 (JSON) — 허용 키 밖은 전부 오류(조용히 무시하지 않는다):
  숫자          3, 1.5            (상수)
  시세          {"px": "close"|"open"|"high"|"low"|"volume", "sym": 심볼?, "tf": 봉?}   sym 기본 "$self",
                tf 기본 "1d". 봉 길이는 노드 속성일 뿐 — 연결된 데이터가 일봉뿐이라 지금은 "1d" 만 허용.
                {"px": "close", "sym": 심볼, "at": {"open_offset_min": m}}  저자가 말한 시각의 값 — 그 판정일
                다음 미국 정규장 개장(뉴욕 09:30) 기준 m분(음수 = 개장 전) 시각까지의 마지막 1분봉 종가.
                판정일 종가 이후 그 시각 사이의 분봉만 쓴다. 그 시각이 아직 안 왔거나 분봉이 없으면 모름(None).
  산술          {"add"|"sub"|"mul"|"div"|"max"|"min": [a, b]}   max/min = 같은 날 두 값 중 큰/작은 값
                {"abs": a}
  선택          {"case": [[c1, v1], [c2, v2], ...], "else": v}   위에서부터 처음 참인 c 의 v.
                앞의 c 가 모름(None)이면 결과도 모름(뒤 갈래로 넘어가지 않는다).
  이동/창       {"ma"|"ema"|"stdev"|"highest"|"lowest"|"sum": [s, n]}
                {"lag": [s, k]}   k 거래일 전 값
                {"pct": [s, k]}   k 거래일 전 대비 변화율(%)
                {"rsi": [s, n]}   Wilder RSI
  비교          {"gt"|"ge"|"lt"|"le": [a, b]}
  논리          {"all": [...]}, {"any": [...]}, {"atleast": n, "of": [...]}, {"not": c}
  시간          {"count": [c, n]}       최근 n거래일(오늘 포함) 중 c 가 참인 날 수
                {"streak": c}           오늘부터 거꾸로 c 가 연속 참인 날 수(오늘 거짓이면 0)
                {"barssince": c}        c 가 마지막으로 참이었던 날부터 지난 거래일(오늘 참이면 0)
                {"valuewhen": [c, s]}   c 가 마지막으로 참이었던 날의 s 값
                {"minsince"|"maxsince": [c, s]}  c 가 마지막으로 참이었던 날부터 오늘까지 s 의 최저/최고
  여러 종목     {"across": {"syms": [...], "cond": c}}   c 가 참인 종목 수(c 안에서 "$s" = 그 종목)
  수동          {"manual": "사유"}
  관측·수동     {"observe": c, "manual": "사유"}   c 를 계산할 수 있으면 그 값, 관측값이 없어 모름이면 수동처럼
                (manual_as) 푼다 — 저자가 말한 시각에 관측하는 조건(개장 전 선물 등): 그 시각이 지났고 분봉이
                있으면 자동, 과거 분봉이 없는 날·아직 그 시각 전이면 지금처럼 사람 확인.
  포지션        {"pos": "ret"|"days"|"maxret"|"minret"}   매도(exit)·2차 이후 분할 매수 규칙 안에서만.
                ret = 평균 매입가 대비 오늘 종가 수익률(%), days = 첫 매수일부터 지난 봉(첫 매수일 0),
                maxret/minret = 첫 매수일~오늘 종가 수익률의 최고/최저. 매수 전 날은 None.
  재사용        {"def": "이름"}         트리 파일 defs 의 식
  메타(아무 노드에) "label", "ref", "id", "note"

심볼: "$self"(그 상품) · "$index"(상품의 기준 지수) · "$s"(across 안의 종목) · 그 외 문자 그대로.
"""
import json
import math

META = ("label", "ref", "id", "note")
PX_FIELDS = ("open", "high", "low", "close", "volume")
POS_FIELDS = ("ret", "days", "maxret", "minret")
ARITH = ("add", "sub", "mul", "div", "max", "min")
TIMEFRAMES = ("1d",)      # 연결된 봉 길이 — 분봉이 연결되면 여기만 늘린다(문법은 그대로)
AT_KEYS = ("open_offset_min",)
US_OPEN_ET = (9, 30)      # 미국 정규장 개장 — 뉴욕 시각
WINDOW = ("ma", "ema", "stdev", "highest", "lowest", "sum")
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
        keys = [k for k in keys if k not in ("sym", "tf", "at")]
    if node.get("case") is not None:
        keys = [k for k in keys if k != "else"]
    if node.get("observe") is not None:
        keys = [k for k in keys if k != "manual"]
    if len(keys) != 1:
        raise CondError("노드에 연산이 정확히 하나여야 한다: %r" % sorted(node))
    return keys[0]


def validate(node, defs=None, path="$"):
    """문법 검사. 모르는 연산·키·인자 개수·필드는 전부 CondError(위치 포함)."""
    defs = defs or {}
    if isinstance(node, bool):
        raise CondError("%s: 불리언 상수는 쓰지 않는다(빈 all/any 를 쓴다)" % path)
    if isinstance(node, (int, float)):
        return
    if not isinstance(node, dict):
        raise CondError("%s: 노드는 숫자 또는 객체여야 한다: %r" % (path, node))
    op = _op_of(node)
    v = node[op]

    def two(name):
        if not (isinstance(v, list) and len(v) == 2):
            raise CondError("%s.%s: 인자 2개 [a, b] 여야 한다" % (path, name))

    def posint(x, what):
        if not (isinstance(x, int) and not isinstance(x, bool) and x >= 1):
            raise CondError("%s.%s: %s 은 1 이상의 정수여야 한다: %r" % (path, op, what, x))

    if op == "px":
        if v not in PX_FIELDS:
            raise CondError("%s.px: 모르는 시세 필드 %r" % (path, v))
        if "sym" in node and not isinstance(node["sym"], str):
            raise CondError("%s.sym: 문자열이어야 한다" % path)
        if "at" in node:
            at = node["at"]
            if v != "close" or not (isinstance(at, dict) and set(at) == set(AT_KEYS)
                                    and isinstance(at["open_offset_min"], int)
                                    and not isinstance(at["open_offset_min"], bool)
                                    and -720 <= at["open_offset_min"] <= 390):
                raise CondError("%s.at: {\"open_offset_min\": 정수(-720~390)} 이고 px 는 close 여야 한다" % path)
        if "tf" in node and node["tf"] not in TIMEFRAMES:
            raise CondError("%s.tf: 연결되지 않은 봉 %r (연결된 봉 %s) — 그 데이터가 연결될 때까지 manual "
                            "(\"데이터 없음: ...\") 로 둔다" % (path, node["tf"], "/".join(TIMEFRAMES)))
    elif op == "abs":
        validate(v, defs, path + ".abs")
    elif op == "case":
        if not (isinstance(v, list) and v and all(isinstance(b, list) and len(b) == 2 for b in v)):
            raise CondError("%s.case: [[조건, 값], ...] 목록이어야 한다" % path)
        if "else" not in node:
            raise CondError("%s.case: else 가 필요하다(모든 경우의 값을 명시)" % path)
        for i, (c, x) in enumerate(v):
            validate(c, defs, "%s.case[%d][0]" % (path, i))
            validate(x, defs, "%s.case[%d][1]" % (path, i))
        validate(node["else"], defs, path + ".else")
    elif op in ARITH or op in CMP:
        two(op)
        validate(v[0], defs, path + "." + op + "[0]")
        validate(v[1], defs, path + "." + op + "[1]")
    elif op in WINDOW or op in ("lag", "pct", "rsi"):
        two(op)
        validate(v[0], defs, path + "." + op + "[0]")
        if op == "lag":
            if not (isinstance(v[1], int) and not isinstance(v[1], bool) and v[1] >= 0):
                raise CondError("%s.lag: k 는 0 이상의 정수" % path)
        else:
            posint(v[1], "n")
    elif op in ("all", "any"):
        if not isinstance(v, list):
            raise CondError("%s.%s: 목록이어야 한다" % (path, op))
        for i, c in enumerate(v):
            validate(c, defs, "%s.%s[%d]" % (path, op, i))
    elif op == "atleast":
        posint(v, "n")
        of = node.get("of")
        if not isinstance(of, list):
            raise CondError("%s.atleast: of 목록이 필요하다" % path)
        for i, c in enumerate(of):
            validate(c, defs, "%s.of[%d]" % (path, i))
    elif op == "not":
        validate(v, defs, path + ".not")
    elif op == "count":
        two(op)
        validate(v[0], defs, path + ".count[0]")
        posint(v[1], "n")
    elif op in ("streak", "barssince"):
        validate(v, defs, path + "." + op)
    elif op in ("valuewhen", "minsince", "maxsince"):
        two(op)
        validate(v[0], defs, path + ".valuewhen[0]")
        validate(v[1], defs, path + ".valuewhen[1]")
    elif op == "across":
        if not (isinstance(v, dict) and set(v) == {"syms", "cond"}
                and isinstance(v["syms"], list) and v["syms"]
                and all(isinstance(s, str) for s in v["syms"])):
            raise CondError("%s.across: {syms:[...], cond:...} 형식이어야 한다" % path)
        validate(v["cond"], defs, path + ".across.cond")
    elif op == "manual":
        if not (isinstance(v, str) and v.strip()):
            raise CondError("%s.manual: 사유 문자열이 필요하다" % path)
    elif op == "observe":
        validate(v, defs, path + ".observe")
        if not (isinstance(node.get("manual"), str) and node["manual"].strip()):
            raise CondError("%s.observe: 관측값이 없을 때의 수동 사유(manual)가 필요하다" % path)
    elif op == "pos":
        if v not in POS_FIELDS:
            raise CondError("%s.pos: 모르는 포지션 값 %r (허용 %s)" % (path, v, "/".join(POS_FIELDS)))
    elif op == "def":
        if v not in defs:
            raise CondError("%s.def: 정의되지 않은 이름 %r" % (path, v))
    else:
        raise CondError("%s: 모르는 연산 %r" % (path, op))


# ------------------------------------------------------------------ 평가
class Ctx:
    """평가 문맥. hist={심볼: [Candle(date,open,high,low,close,volume)]}, cal=날짜 목록."""

    def __init__(self, hist, cal, self_sym, index_sym=None, defs=None, manual_as=None, pos=None, now=None,
                 unobserved=None):
        """pos = (첫 매수일 인덱스, 평균 매입가 | 날짜별 평균 매입가 목록) — 매도·분할 규칙 평가 때만."""
        self.pos = pos
        self.now = now            # 저자 시각 값의 '지금'(UTC datetime) — None 이면 실제 지금
        self.unobserved = unobserved  # None = 관측값 없는 observe 는 수동처럼 · "exclude" = 그 조건을 빼고 판단(백테스트)
        self.hist = hist
        self.cal = list(cal)
        self.self_sym = self_sym
        self.index_sym = index_sym
        self.defs = defs or {}
        self.manual_as = manual_as
        self._px = {}
        self._memo = {}
        self._flip = None

    def flipped(self):
        """수동 가정을 뒤집은 문맥(not 아래 평가용). 시세 캐시는 공유한다."""
        if self.manual_as is None:
            return self
        if self._flip is None:
            f = Ctx(self.hist, self.cal, self.self_sym, self.index_sym, self.defs, not self.manual_as, self.pos,
                    self.now, self.unobserved)
            f._px, f._flip = self._px, self
            self._flip = f
        return self._flip

    def bind(self, sym):
        if sym == "$self":
            return self.self_sym
        if sym == "$index":
            if not self.index_sym:
                raise CondError("$index 가 정의되지 않은 상품: %s" % self.self_sym)
            return self.index_sym
        return sym

    def px(self, sym, field, at=None):
        key = (sym, field, None if at is None else at["open_offset_min"])
        if key not in self._px:
            if at is None:
                by = {c.date: getattr(c, field) for c in (self.hist.get(sym) or [])}
                self._px[key] = [by.get(d) for d in self.cal]
            else:
                self._px[key] = at_series(getattr(self.hist, "minutes", {}).get(sym) or {}, self.cal,
                                          at["open_offset_min"], self.now)
        return self._px[key]


# ------------------------------------------------------------------ 저자 시각(분봉)
def _nth_sunday(y, m, n):
    import datetime as _dt
    d = _dt.date(y, m, 1)
    d += _dt.timedelta(days=(6 - d.weekday()) % 7)
    return d + _dt.timedelta(days=7 * (n - 1))


def et_to_utc(day, hh, mm):
    """뉴욕 시각(YYYYMMDD, 시, 분) → UTC datetime. 미국 서머타임 규칙(3월 둘째 일요일 ~ 11월 첫째 일요일)."""
    import datetime as _dt
    d = _dt.date(int(day[:4]), int(day[4:6]), int(day[6:8]))
    dst = _nth_sunday(d.year, 3, 2) <= d < _nth_sunday(d.year, 11, 1)
    local = _dt.datetime(d.year, d.month, d.day, hh, mm)
    return (local + _dt.timedelta(hours=4 if dst else 5)).replace(tzinfo=_dt.timezone.utc)


def _next_session(cal, i):
    """판정일 cal[i] 다음 정규장 날 — 달력에 다음 날이 있으면 그날(휴장 반영), 마지막 날이면 다음 평일."""
    import datetime as _dt
    if i + 1 < len(cal):
        return cal[i + 1]
    d = _dt.date(int(cal[i][:4]), int(cal[i][4:6]), int(cal[i][6:8])) + _dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += _dt.timedelta(days=1)
    return d.strftime("%Y%m%d")


def at_series(minutes, cal, offset, now=None):
    """판정일마다 '다음 정규장 개장 + offset 분' 시각까지의 마지막 1분봉 종가(판정일 종가 이후 분봉만).
    minutes = {YYYYMMDDHHMM(UTC): 종가}. 그 시각이 아직 안 왔거나 구간에 분봉이 없으면 None."""
    import datetime as _dt
    now = now or _dt.datetime.now(_dt.timezone.utc)
    keys = sorted(minutes)
    out = []
    for i, d in enumerate(cal):
        nxt = _next_session(cal, i)
        oh, om = US_OPEN_ET
        target = et_to_utc(nxt, oh, om) + _dt.timedelta(minutes=offset)
        start = et_to_utc(d, 16, 0)                       # 판정일 정규장 마감 이후
        if target > now or not keys:
            out.append(None)
            continue
        lo, hi = start.strftime("%Y%m%d%H%M"), target.strftime("%Y%m%d%H%M")
        val = None
        for k in reversed(keys):
            if k <= hi:
                if k > lo:
                    val = float(minutes[k])
                break
        out.append(val)
    return out


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


class _Excluded:
    """'이 조건은 빼고 판단' 표지 — unobserved="exclude" 문맥에서 관측값이 없는 observe 가 낸다. 논리 묶음은 이 값을
    후보에서 빼고 계산한다(all·any 는 그 칸만, atleast 는 N 을 그대로 두고 후보에서만). 그 밖의 연산에는 모름(None)으로 간다."""

    def __repr__(self):
        return "EXCLUDED"


EXCLUDED = _Excluded()


def series(node, ctx, s_sym=None):
    """노드 → 달력 길이 시계열."""
    key = (repr(node), s_sym, ctx.manual_as)
    if key in ctx._memo:
        return ctx._memo[key]
    out = _series(node, ctx, s_sym)
    ctx._memo[key] = out
    return out


def _series(node, ctx, s_sym):
    L = len(ctx.cal)
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return [float(node)] * L
    op = _op_of(node)
    v = node[op]
    R = lambda n: series(n, ctx, s_sym)                                   # 논리 묶음용(제외 표지 그대로)
    S = lambda n: [None if x is EXCLUDED else x for x in series(n, ctx, s_sym)]   # 그 밖의 연산용

    if op == "px":
        sym = node.get("sym", "$self")
        if sym == "$s":
            if s_sym is None:
                raise CondError("$s 는 across 안에서만 쓴다")
            sym = s_sym
        return ctx.px(ctx.bind(sym), v, node.get("at"))

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
        out = []
        if op == "ema":
            k = 2.0 / (n + 1)
            prev = None
            for i in range(L):
                x = s[i]
                if not _exact(x):
                    prev = None              # 결측이 끼면 다시 쌓는다(조용히 건너뛰지 않는다)
                    out.append(None)
                    continue
                if prev is None:
                    w = _window(s, i, n)
                    prev = sum(w) / n if w else None
                    out.append(prev)
                    continue
                prev = x * k + prev * (1 - k)
                out.append(prev)
            return out
        for i in range(L):
            w = _window(s, i, n)
            if w is None:
                out.append(None)
            elif op == "ma":
                out.append(sum(w) / n)
            elif op == "sum":
                out.append(sum(w))
            elif op == "highest":
                out.append(max(w))
            elif op == "lowest":
                out.append(min(w))
            else:                         # stdev(모집단) — 볼린저밴드 관례
                m = sum(w) / n
                out.append(math.sqrt(sum((x - m) ** 2 for x in w) / n))
        return out

    if op == "lag":
        s, k = S(v[0]), v[1]
        return [s[i - k] if i - k >= 0 else None for i in range(L)]

    if op == "pct":
        s, k = S(v[0]), v[1]
        out = []
        for i in range(L):
            a = s[i]
            b = s[i - k] if i - k >= 0 else None
            out.append((a / b - 1) * 100 if (_exact(a) and _exact(b) and b != 0) else None)
        return out

    if op == "rsi":
        # Wilder: 첫 평균 = 처음 n개 변화의 단순평균, 이후 (prev*(n-1)+x)/n. 결측이 끼면 다시 쌓는다.
        s, n = S(v[0]), v[1]
        out = [None] * L
        gs, ls, ag, al = [], [], None, None
        for i in range(1, L):
            if not (_exact(s[i]) and _exact(s[i - 1])):
                gs, ls, ag, al = [], [], None, None
                continue
            ch = s[i] - s[i - 1]
            g, lo = max(ch, 0.0), max(-ch, 0.0)
            if ag is None:
                gs.append(g)
                ls.append(lo)
                if len(gs) < n:
                    continue
                ag, al = sum(gs) / n, sum(ls) / n
            else:
                ag = (ag * (n - 1) + g) / n
                al = (al * (n - 1) + lo) / n
            out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
        return out

    if op in ("all", "any"):
        cols = [R(c) for c in v]
        f = _and3 if op == "all" else _or3
        out = []
        for i in range(L):
            vals = [c[i] for c in cols if c[i] is not EXCLUDED]
            out.append(EXCLUDED if cols and not vals else f(vals))
        return out

    if op == "atleast":
        cols = [R(c) for c in node["of"]]
        out = []
        for i in range(L):
            vals = [c[i] for c in cols if c[i] is not EXCLUDED]
            if cols and not vals:
                out.append(EXCLUDED)
                continue
            t = sum(1 for x in vals if x is True)
            u = sum(1 for x in vals if x is None)
            out.append(True if t >= v else (False if t + u < v else None))
        return out

    if op == "not":
        return [x if x is None or x is EXCLUDED else (not x) for x in series(v, ctx.flipped(), s_sym)]

    if op == "count":
        c, n = S(v[0]), v[1]
        out = []
        for i in range(L):
            if i - n + 1 < 0:
                out.append(None)
                continue
            w = c[i - n + 1:i + 1]
            out.append(None if any(x is None for x in w) else float(sum(1 for x in w if x)))
        return out

    if op == "streak":
        c = S(v)
        out = []
        for i in range(L):
            cnt, j, val = 0, i, None
            while j >= 0 and cnt < STREAK_CAP:
                if c[j] is None or not c[j]:
                    break
                cnt += 1
                j -= 1
            if j >= 0 and cnt < STREAK_CAP and c[j] is False:
                val = float(cnt)            # 거짓에서 끊김 — 정확한 길이
            elif cnt > 0:
                val = AtLeast(cnt)          # 모르는 날·데이터 시작·상한에 닿음 — 최소 cnt
            out.append(val)
        return out

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

    if op == "across":
        cols = [series(v["cond"], ctx, sym) for sym in v["syms"]]
        out = []
        for i in range(L):
            vals = [c[i] for c in cols]
            out.append(None if any(x is None for x in vals) else float(sum(1 for x in vals if x)))
        return out

    if op == "manual":
        return [ctx.manual_as] * L

    if op == "observe":
        miss = EXCLUDED if ctx.unobserved == "exclude" else ctx.manual_as
        return [miss if x is None else x for x in S(v)]

    if op == "pos":
        if ctx.pos is None:
            raise CondError("pos 는 매도·분할 규칙 안에서만 쓴다")
        e, cost = ctx.pos                    # cost = 평균 매입가(숫자) 또는 날짜별 평균 매입가 목록(분할 매수)
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

    if op == "def":
        return S(ctx.defs[v])

    raise CondError("모르는 연산 %r" % op)


# ------------------------------------------------------------------ 트리 파일
# 상품 한 개의 여섯 칸 (COND_DSL.md 1절). 조건 칸 셋은 등급을, 규칙 칸 셋은 금액·분할·매도를 낸다.
SECTIONS = ("filter", "entry", "avoid")                 # 조건 칸(등급)
ZONES = SECTIONS + ("caution", "sizing", "exit")        # 반드시 다 적는 여섯 칸
TREE_TOP = ("version", "defs", "products", "source", "note", "unexpressed")
PRODUCT_KEYS = ("index", "note", "exit_note") + ZONES
EXIT_KEYS = ("label", "ref", "note", "when", "sell")
CAUTION_KEYS = ("label", "ref", "note", "when", "scale")
SIZING_KEYS = ("label", "ref", "note", "weight", "tranches")
TRANCHE_KEYS = ("label", "ref", "note", "frac", "when")
EMPTY_ZONE = {"filter": {"all": []}, "entry": {"all": []}, "avoid": {"any": []},
              "caution": [], "sizing": {"weight": None, "tranches": []}, "exit": []}


def _uses_pos(node, defs):
    return any("pos" in n for n in labeled_all(node, defs))


def _rule_list(rules, keys, path, need):
    """규칙 목록 형식 검사 — (경로, 규칙) 을 차례로 돌려준다."""
    if not isinstance(rules, list):
        raise CondError("%s: 목록이어야 한다" % path)
    out = []
    for k, r in enumerate(rules):
        pp = "%s[%d]" % (path, k)
        if not isinstance(r, dict):
            raise CondError("%s: 객체여야 한다" % pp)
        bad = set(r) - set(keys)
        if bad:
            raise CondError("%s: 모르는 키 %s" % (pp, sorted(bad)))
        if any(x not in r or r[x] in (None, "") for x in need):
            raise CondError("%s: %s 이 필요하다" % (pp, "·".join(need)))
        out.append((pp, r))
    return out


def validate_exits(rules, defs, path):
    """매도 규칙 목록: [{label, ref, when, sell}] — sell = "all" | {"initial": f} | {"remaining": f}."""
    for pp, r in _rule_list(rules, EXIT_KEYS, path, ("label", "when", "sell")):
        validate(r["when"], defs, pp + ".when")
        sell = r["sell"]
        ok = sell == "all" or (isinstance(sell, dict) and len(sell) == 1
                               and next(iter(sell)) in ("initial", "remaining")
                               and isinstance(next(iter(sell.values())), (int, float))
                               and 0 < next(iter(sell.values())) <= 1)
        if not ok:
            raise CondError("%s.sell: \"all\" 또는 {\"initial\"|\"remaining\": 0~1} 이어야 한다" % pp)


def validate_caution(rules, defs, path):
    """조심 규칙 목록: [{label, ref, when, scale}] — scale = 0<f<=1(그날 금액에 곱함) | null(저자 미명시)."""
    for pp, r in _rule_list(rules, CAUTION_KEYS, path, ("label", "when")):
        validate(r["when"], defs, pp + ".when")
        if _uses_pos(r["when"], defs):
            raise CondError("%s.when: pos 는 매도·분할 규칙 안에서만 쓴다" % pp)
        if "scale" not in r:
            raise CondError("%s: scale 을 명시한다(폭을 저자가 안 줬으면 null)" % pp)
        sc = r["scale"]
        if sc is not None and not (isinstance(sc, (int, float)) and not isinstance(sc, bool) and 0 < sc <= 1):
            raise CondError("%s.scale: 0 초과 1 이하의 수 또는 null" % pp)


def validate_sizing(sz, defs, path):
    """비중·분할: {weight: 숫자식|null, tranches: [{label, frac, when?}]} — 1차는 when 없음, frac 합 1."""
    if not isinstance(sz, dict):
        raise CondError("%s: 객체여야 한다" % path)
    bad = set(sz) - set(SIZING_KEYS)
    if bad:
        raise CondError("%s: 모르는 키 %s" % (path, sorted(bad)))
    if "weight" not in sz or "tranches" not in sz:
        raise CondError("%s: weight·tranches 를 명시한다(저자가 안 줬으면 null·[])" % path)
    if sz["weight"] is not None:
        validate(sz["weight"], defs, path + ".weight")
        if _uses_pos(sz["weight"], defs):
            raise CondError("%s.weight: pos 를 쓸 수 없다" % path)
    trs = _rule_list(sz["tranches"], TRANCHE_KEYS, path + ".tranches", ("label",))
    if trs and len({t.get("frac") is None for _, t in trs}) > 1:
        raise CondError("%s.tranches: frac 은 전부 숫자이거나 전부 null(저자 미명시)이어야 한다" % path)
    for k, (pp, t) in enumerate(trs):
        if "frac" not in t:
            raise CondError("%s: frac 을 명시한다(저자가 비율을 안 줬으면 null)" % pp)
        f = t["frac"]
        if f is not None and not (isinstance(f, (int, float)) and not isinstance(f, bool) and 0 < f <= 1):
            raise CondError("%s.frac: 0 초과 1 이하 또는 null" % pp)
        if k == 0 and "when" in t:
            raise CondError("%s: 1차는 when 없이 매수 신호 날 산다" % pp)
        if k > 0:
            if "when" not in t:
                raise CondError("%s: 2차 이후는 when 이 필요하다" % pp)
            validate(t["when"], defs, pp + ".when")
    if trs and trs[0][1]["frac"] is not None and abs(sum(t["frac"] for _, t in trs) - 1) > 1e-6:
        raise CondError("%s.tranches: frac 합이 1 이어야 한다(%g)" % (path, sum(t["frac"] for _, t in trs)))


def validate_tree(tree):
    """트리 파일 전체 검사. 상품마다 여섯 칸을 다 명시해야 한다
    (빠진 칸을 조용히 기본값으로 채우지 않는다)."""
    if not isinstance(tree, dict):
        raise CondError("트리 파일은 객체여야 한다")
    bad = set(tree) - set(TREE_TOP)
    if bad:
        raise CondError("모르는 최상위 키: %s" % sorted(bad))
    defs = tree.get("defs") or {}
    for name, d in defs.items():
        validate(d, defs, "defs.%s" % name)
        if _uses_pos(d, defs):
            raise CondError("defs.%s: pos 는 정의에 쓰지 않는다(매도·분할 규칙 안에 직접)" % name)
    prods = tree.get("products")
    if not isinstance(prods, dict) or not prods:
        raise CondError("products 가 비어 있다")
    for p, cfg in prods.items():
        if not isinstance(cfg, dict):
            raise CondError("products.%s: 객체여야 한다" % p)
        bad = set(cfg) - set(PRODUCT_KEYS)
        if bad:
            raise CondError("products.%s: 모르는 키 %s" % (p, sorted(bad)))
        for z in ZONES:
            if z not in cfg:
                raise CondError("products.%s.%s: 칸이 없다(조건이 없으면 %s 로 명시)"
                                % (p, z, json.dumps(EMPTY_ZONE[z], ensure_ascii=False)))
        for sec in SECTIONS:
            validate(cfg[sec], defs, "products.%s.%s" % (p, sec))
            if _uses_pos(cfg[sec], defs):
                raise CondError("products.%s.%s: pos 는 매도·분할 규칙 안에서만 쓴다" % (p, sec))
        validate_caution(cfg["caution"], defs, "products.%s.caution" % p)
        validate_sizing(cfg["sizing"], defs, "products.%s.sizing" % p)
        validate_exits(cfg["exit"], defs, "products.%s.exit" % p)
    return True


def zone_nodes(cfg):
    """상품 하나의 모든 식 [(칸, 라벨, ref, 식)] — 조건 칸은 칸 전체, 규칙 칸은 규칙마다."""
    out = [(sec, None, None, cfg[sec]) for sec in SECTIONS if sec in cfg]
    for r in cfg.get("caution") or []:
        out.append(("caution", r.get("label"), r.get("ref"), r["when"]))
    sz = cfg.get("sizing") or {}
    if sz.get("weight") is not None:
        out.append(("sizing", sz.get("label"), sz.get("ref"), sz["weight"]))
    for t in sz.get("tranches") or []:
        if "when" in t:
            out.append(("sizing", t.get("label"), t.get("ref"), t["when"]))
    for r in cfg.get("exit") or []:
        out.append(("exit", r.get("label"), r.get("ref"), r["when"]))
    return out


def _at_nodes(tree):
    """저자 시각(at) 시세 노드 전부."""
    nodes = list((tree.get("defs") or {}).values())
    for cfg in tree["products"].values():
        nodes.extend(n for _z, _l, _r, n in zone_nodes(cfg))
    return [n for node in nodes for n in labeled_all(node, tree.get("defs") or {}) if "px" in n and "at" in n]


def minute_symbols_of(tree):
    """저자 시각(at) 값을 쓰는 심볼 — 수집 단계가 이 심볼들의 1분봉을 같이 받는다."""
    out = set()
    for n in _at_nodes(tree):
        s = n.get("sym", "$self")
        if s.startswith("$"):
            out.update(cfg.get("index") if s == "$index" else p for p, cfg in tree["products"].items())
        else:
            out.add(s)
    out.discard(None)
    return out


def at_offsets(tree):
    """트리가 쓰는 저자 시각(개장 기준 분) — 이 시각마다 판정해야 그 값이 들어간다(run.py watch)."""
    return sorted({n["at"]["open_offset_min"] for n in _at_nodes(tree)})


def symbols_of(tree):
    """트리가 참조하는 실제 심볼 전부(상품·지수·defs·여섯 칸 전부). 수집 단계의 단일 입력."""
    out = set()

    def walk(n):
        if isinstance(n, dict):
            if "px" in n:
                s = n.get("sym", "$self")
                if not s.startswith("$"):
                    out.add(s)
            if "across" in n and isinstance(n["across"], dict):
                out.update(n["across"].get("syms") or [])
            for k, x in n.items():
                if k not in META:
                    walk(x)
        elif isinstance(n, list):
            for x in n:
                walk(x)

    walk(tree.get("defs") or {})
    for p, cfg in tree["products"].items():
        out.add(p)
        if cfg.get("index"):
            out.add(cfg["index"])
        for _z, _l, _r, node in zone_nodes(cfg):
            walk(node)
    return out


def labeled(node, defs=None, acc=None):
    """라벨 달린 노드 목록(설명·통계용) — def 를 펼쳐 따라간다."""
    acc = [] if acc is None else acc
    defs = defs or {}
    if isinstance(node, dict):
        if node.get("label"):
            acc.append(node)
        for k, x in node.items():
            if k == "def" and x in defs:
                labeled(defs[x], defs, acc)
            elif k not in META:
                labeled(x, defs, acc)
    elif isinstance(node, list):
        for x in node:
            labeled(x, defs, acc)
    return acc


def manual_leaves(node, defs=None):
    return [n for n in labeled_all(node, defs) if isinstance(n, dict) and "manual" in n]


def labeled_all(node, defs=None, acc=None):
    """모든 dict 노드(def 펼침)."""
    acc = [] if acc is None else acc
    defs = defs or {}
    if isinstance(node, dict):
        acc.append(node)
        for k, x in node.items():
            if k == "def" and x in defs:
                labeled_all(defs[x], defs, acc)
            elif k not in META:
                labeled_all(x, defs, acc)
    elif isinstance(node, list):
        for x in node:
            labeled_all(x, defs, acc)
    return acc
