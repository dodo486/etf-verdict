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

관측 시점(asof)
  평가는 '사용자가 보는 그 순간(asof)' 기준이다. asof = 관측 시각(UTC datetime) — 라이브는 실제 지금
  또는 지정 시각, 백테스트는 재생되는 각 시점. 각 시세 조회는 asof 로 자른다: 일봉 필드는 asof 이하
  마지막 확정 일봉(고정), 분봉/장중 필드(tf="1m")는 asof 이하 마지막 분봉(살아 있음). 데이터가 없으면
  None(모름) — 조용히 거짓으로 치지 않는다. '아침 한 시점 고정 판정'은 없다 — 조건이 요구하는 데이터를
  그 조건이 말하는 봉(일봉·분봉)으로 asof 기준 가져올 뿐이다.

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
                tf 기본 "1d"(일봉 — asof 이하 '확정(settled)' 일봉; 장중 asof 면 아직 마감 안 된 그날 일봉은
                None, 즉 전일 종가까지만 본다). tf "1m"(분봉 — asof 이하 마지막 분봉, 장중 값). tf "5m"(5분봉 —
                세션 안 1분봉을 5분 OHLC 로 집계한 뒤 asof 이하 마지막 5분봉). 분봉/5분봉 데이터가 연결되기
                전까진 늘 모름(None)이라 장중 조건은 observe 로 감싸 None→manual 로 떨어진다.
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
                (manual_as) 푼다 — 장중 관측 조건(개장 전 선물 등): asof 기준 분봉이 있으면 자동, 분봉이
                없으면(아직 연결 전·그 시각 분봉 미보관) 지금처럼 사람 확인(🟡).
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
TIMEFRAMES = ("1d", "1m", "5m")  # 봉 길이 — asof 축에서 자른다. 일봉은 확정(settled) 일봉, 분봉은 asof 이하
                           # 마지막 분봉, 5분봉은 1분봉을 세션 안에서 5분 OHLC 로 집계한 뒤 asof 이하 마지막.
                           # 분봉/5분봉 데이터가 연결되기 전까진 "1m"/"5m" 조회는 늘 None(장중 observe → manual).
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
        keys = [k for k in keys if k not in ("sym", "tf")]
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
        if "tf" in node and node["tf"] not in TIMEFRAMES:
            raise CondError("%s.tf: 모르는 봉 %r (허용 %s)" % (path, node["tf"], "/".join(TIMEFRAMES)))
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

    def __init__(self, hist, cal, self_sym, index_sym=None, defs=None, manual_as=None, pos=None, asof=None,
                 unobserved=None, session_close=None):
        """pos = (첫 매수일 인덱스, 평균 매입가 | 날짜별 평균 매입가 목록) — 매도·분할 규칙 평가 때만.
        asof = 관측 시각(UTC datetime) — 분봉(tf="1m"/"5m") 필드를 이 시각 이하로 자른다. None 이면 실제 지금.
        session_close = {심볼: {YYYYMMDD: 그날 정규장 마감(UTC datetime, tz-aware)}} — 일봉 확정(settled) 경계.
          거래소 캘린더(md_feed.sessions)에서 캐려 밖(cond)에서 넣는다(평가기는 jhts 를 모른다). 장중 asof 에서
          '마감이 asof 이후'인 일봉은 아직 미확정이므로 None 으로 가린다(look-ahead 0). asof=None 이거나 캘린더가
          비면(미설치·조회 실패) 아무것도 가리지 않는다 — 없는 캘린더가 조용히 일봉을 전부 지우지 않게."""
        self.pos = pos
        self.asof = asof          # 관측 시각(UTC datetime) — 분봉 조회를 이 시각 이하로 자른다. None 이면 실제 지금
        self.unobserved = unobserved  # None = 관측값 없는 observe 는 수동처럼 · "exclude" = 그 조건을 빼고 판단(백테스트)
        self.hist = hist
        self.cal = list(cal)
        self.self_sym = self_sym
        self.index_sym = index_sym
        self.defs = defs or {}
        self.manual_as = manual_as
        self.session_close = session_close or {}  # {심볼: {YYYYMMDD: 마감 UTC datetime}} — 일봉 확정 경계
        self._px = {}
        self._memo = {}
        self._smap = {}       # 심볼 → settled_map 캐시(일봉축 마지막 확정 index 지도)
        self._flip = None

    def flipped(self):
        """수동 가정을 뒤집은 문맥(not 아래 평가용). 시세 캐시는 공유한다."""
        if self.manual_as is None:
            return self
        if self._flip is None:
            f = Ctx(self.hist, self.cal, self.self_sym, self.index_sym, self.defs, not self.manual_as, self.pos,
                    self.asof, self.unobserved, self.session_close)
            f._px, f._smap, f._flip = self._px, self._smap, self
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

    def px(self, sym, field, tf="1d"):
        """심볼·필드의 asof 축 시계열(달력 길이). 일봉(tf="1d")은 날짜별 '확정(settled)' 일봉(장중 asof 면 아직
        마감 안 된 그날 일봉은 None 으로 가림 — look-ahead 0), 분봉(tf="1m")은 그날 asof 이하 마지막 분봉 값,
        5분봉(tf="5m")은 세션 안 1분봉→5분 OHLC 집계의 그날 asof 이하 마지막 5분봉 값
        (분봉/5분봉 데이터가 없으면 전부 None — 장중 observe → manual)."""
        key = (sym, field, tf)
        if key not in self._px:
            if tf == "1d":
                by = {c.date: getattr(c, field) for c in (self.hist.get(sym) or [])}
                settled = self._settled_dates(sym)   # None = 가리지 않음(asof 없음·캘린더 없음)
                self._px[key] = [by.get(d) if (settled is None or d in settled) else None
                                 for d in self.cal]
            else:
                mins = getattr(self.hist, "minutes", {}).get(sym) or {}
                if tf == "5m":
                    mins = aggregate_5m(mins)
                self._px[key] = minute_series(mins, self.cal, field, self.asof)
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
        (그런 확정봉이 없으면 None). 일봉-tf 식(일봉 잎·그 위 창/lag/streak…)을 평가할 때, 평가 index i 를 'asof 이하
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


# ------------------------------------------------------------------ 분봉(asof 축)
def minute_series(minutes, cal, field, asof=None):
    """날짜별 'asof 이하 마지막 분봉'의 필드 값. minutes = {YYYYMMDDHHMM(UTC): {open,high,low,close,volume} 또는 종가}.
    분봉 데이터가 asof 이하 그날 범위에 없으면 None(모름 — 장중 observe 가 manual 로 떨어진다).
    분봉 다축 달력(그날의 분봉 구간)은 후속 범위다 — 데이터가 연결되면 여기만 채운다."""
    import datetime as _dt
    asof = asof or _dt.datetime.now(_dt.timezone.utc)
    hi = asof.astimezone(_dt.timezone.utc).strftime("%Y%m%d%H%M")
    keys = sorted(minutes)
    out = []
    for d in cal:
        val = None
        for k in reversed(keys):
            if k[:8] == d and k <= hi:
                bar = minutes[k]
                val = bar if not isinstance(bar, dict) else bar.get(field)
                break
        out.append(None if val is None else float(val))
    return out


def aggregate_5m(minutes):
    """1분봉 OHLCV {YYYYMMDDHHMM(UTC): {open,high,low,close,volume} 또는 종가} → 5분봉 {5분 시작키: {OHLCV}}.
    5분 버킷은 '같은 날·같은 시(HH)·분을 5로 내림'(09:30·09:35…)으로 묶어 세션 경계를 넘지 않는다
    (버킷 키가 YYYYMMDDHH 를 포함하므로 다른 날·다른 세션의 분봉은 절대 한 버킷에 섞이지 않는다).
    OHLC = 버킷 안 (첫 open, 최고 high, 최저 low, 끝 close), volume = 합. 스칼라 종가만 있으면 O=H=L=C=종가,
    volume=0. 각 필드가 모두 없는 봉은 건너뛴다(가짜로 채우지 않는다)."""
    buckets = {}                 # 5분 시작키(YYYYMMDDHHmm, mm=5의 배수) → [(분키, 봉dict), ...] 시간순
    for k in sorted(minutes):
        mm = int(k[10:12])
        bkey = k[:10] + "%02d" % (mm - mm % 5)     # 같은 날·시 + 분 5내림 (세션/날 경계 안 넘음)
        bar = minutes[k]
        if not isinstance(bar, dict):
            bar = {"open": bar, "high": bar, "low": bar, "close": bar, "volume": 0.0}
        buckets.setdefault(bkey, []).append(bar)
    out = {}
    for bkey, bars in buckets.items():
        o = next((b.get("open") for b in bars if b.get("open") is not None), None)
        c = next((b.get("close") for b in reversed(bars) if b.get("close") is not None), None)
        highs = [b.get("high") for b in bars if b.get("high") is not None]
        lows = [b.get("low") for b in bars if b.get("low") is not None]
        vols = [b.get("volume") for b in bars if b.get("volume") is not None]
        out[bkey] = {"open": o, "high": max(highs) if highs else None, "low": min(lows) if lows else None,
                     "close": c, "volume": sum(vols) if vols else None}
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


# 일봉축 조회(asof 이하 마지막 확정봉) 대상이 아닌 잎 — 하나라도 있으면 그 식은 '1d-순수'가 아니다.
#   · 분봉/5분봉 px(tf 1m/5m) : asof 이하 '살아 있는' 축(오늘 재생) — 일봉 확정 경계로 당기면 안 된다.
#   · manual/observe/pos      : 일봉 봉이 아닌 값(수동·포지션).
#   · across                  : $s 가 across 안에서만 풀려(심볼이 확정되지 않음) — 안전하게 비-1d 로 둔다.
_NON_DAILY = ("manual", "observe", "pos", "across")


def _daily_axis(node, ctx, s_sym):
    """node 가 '1d-순수'(모든 px 잎이 tf=1d 이고 분봉·수동·pos·across 잎이 없음)면, 그 1d 심볼들의 settled_map 을
    돌려준다(일봉축 '마지막 확정봉' 지도). 아니거나, 심볼들의 지도가 엇갈리거나, 지도가 no-op(asof 없음·캘린더 없음)이면
    None — 그 경우 gather 를 건너뛴다(기존 동작 그대로). 같은 시장 심볼은 지도가 같으므로(세션 경계가 시장별) 한 지도로
    모은다 — 서로 다른 시장이 한 1d-순수 식에 섞이면(지도 엇갈림) 당기지 않는다(조용히 잘못 당기느니 기존 masked-None)."""
    syms = set()
    for n in labeled_all(node, ctx.defs):
        if not isinstance(n, dict):
            continue
        op = _op_of(n)
        if op == "px":
            if n.get("tf", "1d") != "1d":
                return None                 # 분봉/5분봉 잎 — 1d-순수 아님
            sym = n.get("sym", "$self")
            if sym == "$s":
                return None                 # across 안 — 심볼 미확정, 안전하게 당기지 않음
            syms.add(ctx.bind(sym))
        elif op in _NON_DAILY:
            return None                     # 수동·포지션·across — 1d-순수 아님
    if not syms:
        return None                         # px 잎이 없는 순수 숫자/비교식 — 당길 일봉축이 없음
    maps = [ctx.settled_map(sym) for sym in syms]
    first = maps[0]
    if first is None or any(m != first for m in maps[1:]):
        return None                         # no-op(asof 없음·캘린더 없음) 또는 시장별 지도 엇갈림 → 당기지 않음
    return first


def series(node, ctx, s_sym=None):
    """노드 → 달력 길이 시계열.

    일봉축 재해석(장중 asof): 노드가 '1d-순수'면(모든 px 잎 tf=1d·분봉/수동/pos/across 없음), 평가 결과의 각 index i 를
    'asof 이하 마지막 확정 일봉' 값으로 당긴다(_daily_axis·settled_map). 장중 asof 면 오늘 봉은 미확정이라 m[i]=어제 →
    일봉 잎·ma20 등이 '어제까지 실제값'(None 아님)으로 나온다. 당김은 settled index 에서만 읽으므로 오늘 미확정 종가는
    어떤 파생값에도 새지 않는다(look-ahead 0). 당김은 멱등(m[m[i]]==m[i])이라 잎·그 위 1d 노드 어디서 걸어도 결과가
    같다 — 그래서 '가장 바깥 1d 노드'를 따로 찾지 않고 모든 노드에서 한 번씩 안전하게 건다. EOD/장후 asof·asof None·캘린더
    없음에선 m[i]==i(또는 no-op)라 항등 → 일봉 파리티·기존 동작 그대로."""
    key = (repr(node), s_sym, ctx.manual_as)
    if key in ctx._memo:
        return ctx._memo[key]
    out = _series(node, ctx, s_sym)
    m = _daily_axis(node, ctx, s_sym)
    if m is not None:
        out = [out[m[i]] if m[i] is not None else None for i in range(len(out))]
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
        return ctx.px(ctx.bind(sym), v, node.get("tf", "1d"))

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
# 여섯 칸의 한글 이름표 — 여기 한 곳이 정본이다. 화면(shared-ui.js ZW)은 복붙하지 않고
# 판정 JSON(verdict_engine 이 VD.zones 로 실어보냄, ZONES 순서)을 받아 쓴다.
ZONE_LABELS = {"filter": "필터", "avoid": "회피", "entry": "진입",
               "caution": "조심", "sizing": "비중·분할", "exit": "매도"}
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


def _minute_nodes(tree):
    """장중 봉(tf="1m" 또는 "5m") 시세 노드 전부 — 장중 조건이 쓰는 장중 값. 5분봉도 원천은 1분봉이라(세션 안
    집계) 같은 수집 대상이다."""
    nodes = list((tree.get("defs") or {}).values())
    for cfg in tree["products"].values():
        nodes.extend(n for _z, _l, _r, n in zone_nodes(cfg))
    return [n for node in nodes for n in labeled_all(node, tree.get("defs") or {})
            if "px" in n and n.get("tf") in ("1m", "5m")]


def minute_symbols_of(tree):
    """장중 봉(tf="1m"/"5m") 값을 쓰는 심볼 — 수집 단계가 이 심볼들의 1분봉을 같이 받는다(5분봉은 세션 안 집계)."""
    out = set()
    for n in _minute_nodes(tree):
        s = n.get("sym", "$self")
        if s.startswith("$"):
            out.update(cfg.get("index") if s == "$index" else p for p, cfg in tree["products"].items())
        else:
            out.add(s)
    out.discard(None)
    return out


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


# ------------------------------------------------------------------ 워밍업(필요 lookback)
def warmup_of(node, defs=None, _seen=None):
    """node 를 평가할 때 '첫 평가 봉'이 조용히 틀린 값을 내지 않으려면 그 앞에 몇 개의 확정 봉이
    더 있어야 하는지 — 트리가 실제로 쓰는 가장 긴 lookback(거래일 수).

    왜 필요한가
      ma20·highest60·lag5 같은 창/지연 연산은 창이 덜 차면 **조용히 None** 을 내고, 그 None 은
      3값 논리로 위에 전파돼 '모름'이 된다 — 데이터가 모자란 줄 모르고 ✅/🚫 확신을 내는 길목이다.
      시세가 rate-limit 로 잘려(워밍업 부족) 들어오면 바로 이 일이 난다(실제 발견된 버그).
      이 함수가 트리에서 '필요한 확정 봉 수'를 직접 뽑아, 그보다 짧은 구간의 1d 신호를 '불완전'으로
      표면화하는 가드(tree_grade)의 임계값이 된다 — WARMUP_DAYS(fetch 버퍼)와 무관하다.

    어떻게 세나 (연산마다 '그날 값이 서려면 그 앞에 몇 봉이 더 있어야 하나'를 더해 가장 깊은 사슬)
      · 창(ma/ema/stdev/highest/lowest/sum) n : n-1 + 안쪽
      · rsi n                                : n + 안쪽(와일더 시드)
      · lag/pct k                            : k  + 안쪽
      · count n                              : n-1 + 안쪽
      · streak/barssince/valuewhen/minsince/maxsince : 안쪽만. 이들은 데이터 시작에 닿으면 조용히
        틀리지 않고 AtLeast/None(모름)으로 스스로 불확실을 드러내므로(STREAK_CAP 는 fetch 버퍼가
        아닌 역방향 상한일 뿐) 워밍업 기준에 넣지 않는다 — 넣으면 정상 데이터의 짧은 창도 오탐한다.
      · 산술·비교·abs·case·논리(all/any/atleast/not)·across : 자식 중 최댓값
      · px/manual/pos/상수                   : 0
    """
    defs = defs or {}
    _seen = _seen or set()
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return 0
    if not isinstance(node, dict):
        return 0
    op = _op_of(node)
    v = node[op]
    w = lambda n: warmup_of(n, defs, _seen)
    if op == "px":
        return 0
    if op == "def":
        if v in _seen:                       # 정의 순환(있어선 안 되지만) — 무한재귀 방지
            return 0
        return warmup_of(defs[v], defs, _seen | {v})
    if op in WINDOW:
        return (v[1] - 1) + w(v[0])
    if op == "rsi":
        return v[1] + w(v[0])
    if op in ("lag", "pct"):
        return v[1] + w(v[0])
    if op == "count":
        return (v[1] - 1) + w(v[0])
    if op in ("streak", "barssince"):
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
    if op == "across":
        return w(v["cond"])
    if op == "observe":
        return w(node["observe"])
    # manual · pos — lookback 없음
    return 0


def tree_warmup(tree, prod=None):
    """상품 하나(prod)의 등급(조건 칸 filter/entry/avoid)이 요구하는 가장 긴 워밍업(거래일 수).
    prod=None 이면 트리의 모든 상품에 걸친 최댓값. 규칙 칸(caution/sizing/exit)은 포지션이 있을 때만
    보고 등급과 무관하므로 등급 워밍업에는 넣지 않는다(가드는 등급 신호의 신뢰성만 지킨다)."""
    defs = tree.get("defs") or {}
    prods = [prod] if prod is not None else list(tree["products"])
    mx = 0
    for p in prods:
        cfg = tree["products"][p]
        for sec in SECTIONS:
            mx = max(mx, warmup_of(cfg[sec], defs))
    return mx
