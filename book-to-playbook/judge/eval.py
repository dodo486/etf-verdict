#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""계산기 — 판때기(트리 식)에 시세 값을 넣어 계산. 부르는 곳은 judge(판단자)뿐.

식의 뜻(값·관측 시점 asof·3값 논리·하한 AtLeast·수동·모르는 값 "?"·문법)은 tree/gateway.py docstring 이 정본이다.
  · Ctx     평가 문맥(시세·달력·상품·수동 가정·asof 일봉 확정 경계·사람의 답·공유 값 기억)
  · series  묶인 식(tree.gateway.Node — 판때기의 노드) → 달력 길이 시계열(모든 연산은 인과적 — judge.verify_eval 이 강제).
            적힌(안 묶인) 식을 받으면 그 문맥의 상품으로 묶어(gateway.bind) 계산한다.
값 기억: 문맥마다 노드 일련번호(nid)로 한 번만 계산한다. 수동·pos 가 없는 노드(Node.pure)의 값은 시세·달력·asof 로만
정해지므로, 판단자가 같은 시세·달력·asof 의 문맥들에 같은 공유 기억(shared)을 주면 상품끼리(수동 가정 셋끼리도) 한 번만 계산한다.
"""
import math

from tree.gateway import ARITH, AtLeast, bind, CMP, CondError, Node, _op_of, ROLES, UNKNOWN, WINDOW

STREAK_CAP = 400          # 연속·경과일을 거꾸로 셀 때의 상한(데이터 길이보다 길면 무의미)


class Ctx:
    """평가 문맥. hist={심볼: [Candle(date,open,high,low,close,volume)]}, cal=날짜 목록."""

    def __init__(self, hist, cal, self_sym, index_sym=None, manual_as=None, pos=None, asof=None,
                 session_close=None, answers=None, shared=None, scope=None):
        """self_sym = 평가 중인 상품($self) · index_sym = 그 상품의 지수($index, 없으면 None).
        pos = (첫 매수일 인덱스, 평균 매입가 | 날짜별 평균 매입가 목록[, 장부]) — 판다·분할 갈래 평가 때만.
        장부 = {"filled": {규칙 이름 | None(전체): 날짜별 산 횟수}, "sold": 날짜별 판 비율} — 없으면 filled·sold 는 모름.
        asof = 관측 시각(UTC datetime) — 일봉 확정(settled) 경계를 정한다. None 이면 실제 지금.
        session_close = {심볼: {YYYYMMDD: 그날 정규장 마감(UTC datetime, tz-aware)}} — 일봉 확정(settled) 경계.
          거래소 캘린더(md_feed.sessions)에서 캐려 밖(cond)에서 넣는다(평가기는 jhts 를 모른다). 장중 asof 에서
          '마감이 asof 이후'인 일봉은 아직 미확정이므로 None 으로 가린다(look-ahead 0). asof=None 이거나 캘린더가
          비면(미설치·조회 실패) 아무것도 가리지 않는다 — 없는 캘린더가 조용히 일봉을 전부 지우지 않게.
        answers = {answer_key: True|False} — 사람이 답한 수동(없는 열쇠는 manual_as). None 이면 옛 동작 그대로.
        shared = 공유 값 기억 {nid: 시계열} — 같은 시세·달력·asof 의 문맥끼리만 준다(판단자 몫). pure 노드만 넣고 꺼낸다.
        scope = 이 문맥의 확정 경계(session_close)가 덮는 상품 심볼 집합 — 경계가 있으면 식의 심볼이 그 안일 때만 공유
        (상품마다 경계가 그 상품 심볼로만 만들어지므로). None = 제한 없음."""
        self.pos = pos
        self.asof = asof          # 관측 시각(UTC datetime) — 일봉 확정 경계. None 이면 실제 지금
        self.hist = hist
        self.cal = list(cal)
        self.self_sym = self_sym
        self.index_sym = index_sym
        self.manual_as = manual_as
        self.session_close = session_close or {}  # {심볼: {YYYYMMDD: 마감 UTC datetime}} — 일봉 확정 경계
        self._px = {}
        self._memo = {}       # nid → 시계열(이 문맥에서 계산한 값)
        self._bound = {}      # 적힌 식 → 묶인 식 캐시(gateway.bind 의 cache — 뒤집은 문맥과 공유)
        self._smap = {}       # 심볼 → settled_map 캐시(일봉축 마지막 확정 index 지도)
        self._flip = None
        self.answers = answers
        self.shared, self.scope = shared, scope

    def flipped(self):
        """수동 가정을 뒤집은 문맥(not 아래 평가용). 시세 캐시는 공유한다. 사람의 답(answers)은 뒤집지 않는다."""
        if self.manual_as is None:
            return self
        if self._flip is None:
            f = Ctx(self.hist, self.cal, self.self_sym, self.index_sym, not self.manual_as, self.pos,
                    self.asof, self.session_close, self.answers, self.shared, self.scope)
            f._px, f._smap, f._bound, f._flip = self._px, self._smap, self._bound, self
            self._flip = f
        return self._flip

    def manual_value(self, node):
        """수동 잎 하나의 값 — 사람이 답했으면 그 답, 아니면 manual_as(극성 반영된 가정)."""
        if self.answers is not None:
            a = self.answers.get(self.self_sym + "|" + node.mkey)   # = gateway.answer_key(적힌 잎, 상품)
            if a is not None:
                return a
        return self.manual_as

    def _role(self, sym):
        """묶이지 않은 역할이 남은 잎 — $index 인데 상품에 지수가 없을 때뿐(묶기가 그대로 둔다). 계산하는 순간 오류."""
        if sym in ROLES:
            raise CondError("$index 가 정의되지 않은 상품: %s (products 에 index 가 없다)" % self.self_sym)
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


def _daily_axis(node, ctx):
    """node 가 '1d-순수'(모든 px 잎이 tf=1d 이고 분봉·수동·pos 잎이 없음 — 묶을 때 정한 Node.axis)면, 그 1d 심볼들의
    settled_map 을 돌려준다(일봉축 '마지막 확정봉' 지도). 아니거나(axis None·빈 집합), 심볼들의 지도가 엇갈리거나, 지도가
    no-op(asof 없음·캘린더 없음)이면 None — 그 경우 gather 를 건너뛴다(기존 동작 그대로). 같은 시장 심볼은 지도가 같으므로
    (세션 경계가 시장별) 한 지도로 모은다 — 서로 다른 시장이 한 1d-순수 식에 섞이면(지도 엇갈림) 당기지 않는다(조용히 잘못
    당기느니 기존 masked-None). OFF 자식(노드 레벨 on 에 빠진 상품)도 적힌 식의 잎으로 센다(Node.axis 계약)."""
    if not node.axis:
        return None                         # 1d-순수 아님, 또는 px 잎이 없는 순수 숫자/비교식 — 당길 일봉축이 없음
    maps = [ctx.settled_map(ctx._role(sym)) for sym in node.axis]
    first = maps[0]
    if first is None or any(m != first for m in maps[1:]):
        return None                         # no-op(asof 없음·캘린더 없음) 또는 시장별 지도 엇갈림 → 당기지 않음
    return first


def series(node, ctx):
    """노드 → 달력 길이 시계열. node = 묶인 식(Node) — 적힌 식이면 문맥의 상품으로 묶는다(gateway.bind).

    노드 레벨 on: 묶을 때 평가 중 상품이 그 노드의 on 에 없으면 OFF 노드(값 '항상 참' — all/atleast 안에서 투명).
    규칙은 공통으로 두고 한 상품에만 더 붙는 조건을 쪼개지 않고 단다. OFF 노드는 일봉축 당김을 하지 않는다.

    일봉축 재해석(장중 asof): 노드가 '1d-순수'면(모든 px 잎 tf=1d·분봉/수동/pos 없음), 평가 결과의 각 index i 를
    'asof 이하 마지막 확정 일봉' 값으로 당긴다(_daily_axis·settled_map). 장중 asof 면 오늘 봉은 미확정이라 m[i]=어제 →
    일봉 잎·ma20 등이 '어제까지 실제값'(None 아님)으로 나온다. 당김은 settled index 에서만 읽으므로 오늘 미확정 종가는
    어떤 파생값에도 새지 않는다(look-ahead 0). 당김은 멱등(m[m[i]]==m[i])이라 잎·그 위 1d 노드 어디서 걸어도 결과가
    같다 — 그래서 '가장 바깥 1d 노드'를 따로 찾지 않고 모든 노드에서 한 번씩 안전하게 건다. EOD/장후 asof·asof None·캘린더
    없음에선 m[i]==i(또는 no-op)라 항등 → 일봉 파리티·기존 동작 그대로."""
    if not isinstance(node, Node):
        if not isinstance(node, dict):
            return _series(node, ctx)       # 상수·"?" — 기억할 것 없음
        node = bind(node, ctx.self_sym, ctx.index_sym, ctx._bound)
    out = ctx._memo.get(node.nid)
    if out is not None:
        return out
    shared = ctx.shared if (ctx.shared is not None and node.pure
                            and (ctx.scope is None or node.syms <= ctx.scope)) else None
    if shared is not None:
        out = shared.get(node.nid)
    if out is None:
        if node.off:
            out = [True] * len(ctx.cal)
        else:
            out = _series(node, ctx)
            m = _daily_axis(node, ctx)
            if m is not None:
                out = [out[m[i]] if m[i] is not None else None for i in range(len(out))]
        if shared is not None:
            shared[node.nid] = out
    ctx._memo[node.nid] = out
    return out


def _series(node, ctx):
    L = len(ctx.cal)
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return [float(node)] * L
    if node == UNKNOWN:
        return [None] * L                    # 모르는 숫자 — 값은 모름(판단은 그것을 품은 노드가 수동으로)
    op = _op_of(node)
    v = node[op]
    if node.mkey is not None:
        return [ctx.manual_value(node)] * L  # 수동 잎 — 문장 수동·저자가 숫자를 안 준 판단("?") 모두 사람이 정한다
    if op in WINDOW + ("lag",) and v[1] == UNKNOWN:
        return [None] * L                    # 기간을 모름 — 값도 모름
    S = lambda n: series(n, ctx)

    if op == "px":
        return ctx.px(ctx._role(node["sym"]), v, node.get("tf", "1d"))

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
