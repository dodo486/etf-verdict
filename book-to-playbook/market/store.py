#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""시세 칸 저장소(Store) — 심볼 × 봉 길이마다 칸 하나. 과거 봉을 한 번 받아 들고, 틱마다 최근 창만 다시 받아 합친다.

  · Store            칸 묶음 — need(필요 심볼·기간 등록) · load(최초 1회 적재) · refresh(최근 창만 다시 받아 합침 →
                     바뀐 심볼) · prices(판단자가 쓰는 {심볼: [Candle]} 스냅숏) · confirmed(봉 하나가 확정봉인가)
  · market_closes    시장 하나의 정규장 마감 {YYYYMMDD: 마감(UTC)} — 거래소 캘린더(md_feed.sessions)
  · session_closes   일봉 확정 경계 {심볼: {YYYYMMDD: 그날 정규장 마감(UTC)}} — 거래소 캘린더(md_feed.sessions)에서
  · settled_dates    확정 규칙 한 줄 — 마감이 asof 이하인 날만 확정(마감 == asof 도 확정)

'이 봉이 확정인가'의 주인은 이 파일 하나다 — 판단자(judge: 배치·백테스트에서 asof 로 장중을 재현할 때)도
저장소(Store.confirmed: 라이브 '지금')도 같은 두 함수를 쓴다. 캘린더가 없으면(미설치·조회 실패) 가리지 않는다
(없는 캘린더가 조용히 일봉을 전부 지우지 않게).

칸 열쇠는 (심볼, 봉 길이) — 지금은 일봉 "1d" 하나뿐(분봉 "1m" 은 같은 열쇠 모양으로 나중에 md_feed.minutes 로).
스레드: refresh 는 폴러 스레드에서, prices 는 서버가 읽는다 — 상태는 잠금 안에서만 바꾸고, 내보낸 스냅숏(dict·
리스트)은 다시 고치지 않는다(바뀌면 새 dict·새 리스트 — copy-on-write). 판단자의 공유 값 기억(judge.shared_values)은
시세 묶음 객체로 캐시를 가르므로, 바뀐 게 없으면 같은 dict 를, 바뀌면 새 dict 를 돌려준다.
market 은 트리를 모른다 — 무엇이 필요한지는 위층이 need 로 알려준다.
"""
import datetime as _dt
import threading

from market import md_feed
from market.md_feed import Candle   # 봉 타입 주인은 창구(md_feed) 하나 — resample 산출 봉도 이걸 쓴다

TF_DAY = "1d"


# ================================================================ 일봉 확정 — 주인
def session_closes(symbols, cal, asof, sessions=None, market_of=None):
    """일봉 확정(settled) 경계 — {심볼: {YYYYMMDD: 그날 정규장 마감(UTC datetime)}}. 장중 asof 에서
    '마감이 asof 이후'인 일봉(아직 미확정)을 가리는 데 쓴다. 경계는 하드코딩이 아니라 거래소 캘린더
    (md_feed.sessions)에서 읽는다. asof 가 없으면(라이브 '지금' = 늘 마지막 확정봉) 가릴 것이 없으므로 빈 dict.
    캘린더가 비면(jhts 미설치·조회 실패) 해당 심볼은 빠진다 → '가리지 않음'으로 떨어진다(캘린더 없다고
    일봉을 조용히 전부 지우지 않게). 시장(US/KR)이 같은 심볼은 캘린더를 한 번만 조회해 공유한다.
    sessions·market_of = 주입(검사용) — 없으면 md_feed 것."""
    if asof is None or not cal:
        return {}
    market_of = market_of or md_feed.market_of
    start, end = min(cal), max(cal)
    by_market = {}      # market → {YYYYMMDD: 마감 UTC}
    out = {}
    for sym in sorted(set(symbols)):
        mkt = market_of(sym)
        if mkt is None:
            continue
        if mkt not in by_market:
            by_market[mkt] = market_closes(mkt, start, end, sessions)
        closes = by_market[mkt]
        if closes:
            out[sym] = closes
    return out


def market_closes(market, start, end, sessions=None):
    """시장 하나의 start~end 정규장 마감 {YYYYMMDD: 마감 UTC datetime} — 캘린더가 없으면 {}."""
    return {s.date: s.close.astimezone(_dt.timezone.utc)
            for s in (sessions or md_feed.sessions)(market, start, end) if s.close is not None}


def settled_dates(closes, asof):
    """확정 규칙 — 세션 마감이 asof 이하인 날짜 집합(마감 == asof 도 확정, 마감 > asof 인 '진행 중' 봉은 뺀다).
    closes = {YYYYMMDD: 마감 UTC}(session_closes 한 심볼 몫)."""
    return {d for d, close in closes.items() if close is not None and close <= asof}


# ================================================================ 시세 칸
class Store:
    """시세 칸 묶음 — 같은 심볼은 누가 쓰든 칸 하나. 위층이 need 로 필요 심볼·시작일을 알려주고 load 로 한 번 적재,
    틱마다 refresh 로 최근 창만 다시 받아 합친다. prices() 는 판단자가 쓰는 모양 그대로(md_feed.histories 와 같음)."""

    def __init__(self, fetch=None, sessions=None, now=None, market_of=None):
        """fetch(symbols, start) → {심볼: [Candle]} (기본 md_feed.histories) · sessions(market, start, end) → [Session]
        (기본 md_feed.sessions) · now() → 지금(UTC tz-aware) · market_of(심볼) → "US"|"KR"|None — 전부 주입 가능(검사용)."""
        self._fetch = fetch or md_feed.histories
        self._sessions = sessions or md_feed.sessions
        self._market_of = market_of or md_feed.market_of
        self._now = now or (lambda: _dt.datetime.now(_dt.timezone.utc))
        self._lock = threading.Lock()       # 상태(아래 넷) 바꾸기·읽기
        self._io = threading.Lock()         # load·refresh 한 번에 하나(받는 동안 prices 는 막지 않는다)
        self._need = {}                     # 심볼 → 필요한 시작일(YYYYMMDD, 가장 이른 것)
        self._loaded = {}                   # 심볼 → 적재한 시작일
        self._bufs = {}                     # (심볼, tf) → [Candle] 오름차순 — 내보낸 뒤엔 고치지 않는다
        self._snap = {}                     # prices() 스냅숏 — 바뀌면 새 dict
        self._cal = {}                      # 시장 → (시작, 끝, {YYYYMMDD: 마감 UTC}) — confirmed 의 캘린더 기억

    # ------------------------------------------------------------ 등록·적재
    def need(self, symbols, start):
        """symbols 를 start(YYYYMMDD)부터 필요하다고 등록 — 여러 번 불러도 같다(이미 더 이른 시작이면 그대로, 더 이르면 넓힌다).
        넓혀진 심볼·새 심볼은 다음 load 가 받는다."""
        with self._lock:
            for s in symbols:
                cur = self._need.get(s)
                if cur is None or start < cur:
                    self._need[s] = start

    def load(self):
        """등록됐지만 아직 안 받은(또는 시작일이 넓혀진) 심볼만 한 번에 받는다 — 시작일마다 fetch 1회(보통 1회)."""
        with self._io:
            with self._lock:
                todo = {}
                for s, st in self._need.items():
                    if self._loaded.get(s) is None or st < self._loaded[s]:
                        todo.setdefault(st, []).append(s)
            if not todo:
                return
            got = {st: self._fetch(sorted(syms), st) for st, syms in sorted(todo.items())}
            with self._lock:
                snap = dict(self._snap)
                for st, syms in todo.items():
                    for s in syms:
                        bars = list(got[st].get(s) or [])
                        self._bufs[(s, TF_DAY)] = bars
                        self._loaded[s] = st
                        snap[s] = bars
                self._snap = snap

    def refresh(self, recent_days=7):
        """등록·적재된 심볼 전부의 최근 recent_days 일만 다시 받아 합친다(같은 날짜 봉은 바꾸고 새 날짜는 덧붙임).
        실제로 봉이 바뀐 심볼 집합을 돌려준다. 받기에 실패한 심볼(빈 결과)은 그대로 둔다(지우지 않는다)."""
        with self._io:
            with self._lock:
                syms = sorted(self._loaded)
            if not syms:
                return set()
            start = (self._now() - _dt.timedelta(days=recent_days)).strftime("%Y%m%d")
            got = self._fetch(syms, start)
            changed = set()
            with self._lock:
                snap = None
                for s in syms:
                    new = got.get(s) or []
                    if not new:
                        continue
                    old = self._bufs.get((s, TF_DAY)) or []
                    merged = _merge(old, new)
                    if merged != old:
                        self._bufs[(s, TF_DAY)] = merged
                        if snap is None:
                            snap = dict(self._snap)
                        snap[s] = merged
                        changed.add(s)
                if snap is not None:
                    self._snap = snap
            return changed

    # ------------------------------------------------------------ 읽기
    def prices(self):
        """{심볼: [Candle]} — 판단자가 쓰는 모양(md_feed.histories 와 같음). 바뀐 게 없으면 같은 dict 객체, 바뀌면 새 객체.
        돌려준 dict·리스트는 저장소가 다시 고치지 않는다 — 받는 쪽도 고치지 않는다."""
        with self._lock:
            return self._snap

    def symbols(self):
        with self._lock:
            return set(self._need)

    def confirmed(self, sym, i):
        """sym 의 i 번째 일봉이 확정봉(그날 정규장 마감 ≤ 지금)인가 — 아니면 진행 중. 규칙은 settled_dates 하나
        (judge 가 asof 로 장중을 재현할 때와 같다). 시장·캘린더를 모르면 확정으로 본다(가리지 않음)."""
        with self._lock:
            bars = self._snap.get(sym) or []
        day = bars[i].date
        mkt = self._market_of(sym)
        if mkt is None:
            return True
        closes = self._closes(mkt, bars[0].date, bars[-1].date)
        if not closes:
            return True
        return day in settled_dates({day: closes.get(day)}, self._now())

    def _closes(self, mkt, start, end):
        """시장 하나의 {YYYYMMDD: 마감 UTC} — 봉 범위를 덮도록 넓혀 가며 기억(같은 범위면 다시 묻지 않는다)."""
        with self._lock:
            hit = self._cal.get(mkt)
        if hit is not None and hit[0] <= start and end <= hit[1]:
            return hit[2]
        if hit is not None:
            start, end = min(start, hit[0]), max(end, hit[1])
        closes = market_closes(mkt, start, end, self._sessions)
        with self._lock:
            self._cal[mkt] = (start, end, closes)
        return closes


def _merge(old, new):
    """old 일봉에 new 를 합친 새 리스트 — 같은 날짜는 new 로 바꾸고, 새 날짜는 덧붙인다(날짜 오름차순). old 는 고치지 않는다."""
    by = {c.date: c for c in old}
    by.update((c.date, c) for c in new)
    return [by[d] for d in sorted(by)]


# ================================================================ 봉 집계(resample) — 최소 단위 → 임의 tf (단위 무관)
# 봉 '길이'의 주인은 여기 한 곳(tf_seconds). 엔진(judge/eval.series)은 봉을 **개수**로만 세므로 단위를 아예 모른다 —
# 분봉이 초봉·틱으로 바뀌어도 엔진은 0줄 수정, 새 시간 단위가 생겨도 아래 _TF_UNIT_S 에 한 줄이면 끝.
_TF_UNIT_S = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}   # 봉 단위 → 초 (새 단위는 여기 한 줄)
_TS_FMT = {8: "%Y%m%d", 12: "%Y%m%d%H%M", 14: "%Y%m%d%H%M%S"}         # 봉 타임스탬프 자리수 → 형식(정밀도 — 초·ms 도 한 줄)


def tf_seconds(tf):
    """봉 길이 토큰("5m"·"30m"·"1h"·"1d"…) → 초. 끝 글자 = 단위(s·m·h·d·w), 앞 = 수. 모르는 꼴이면 None.
    최소 단위가 분봉이든 초봉이든 '얼마 간격으로 묶나'는 이 초 하나로 정해진다(resample·문법 검사가 같이 쓴다)."""
    n, u = tf[:-1], tf[-1:]
    return int(n) * _TF_UNIT_S[u] if n.isdigit() and u in _TF_UNIT_S else None


def _epoch(ts):
    """봉 타임스탬프 문자열(UTC) → 에폭 초. 자리수로 정밀도를 안다(12=분, 14=초 …)."""
    return int(_dt.datetime.strptime(ts, _TS_FMT[len(ts)]).replace(tzinfo=_dt.timezone.utc).timestamp())


def resample(bars, tf):
    """최소 단위 봉 [Candle(date=타임스탬프, o,h,l,c,v)](오름차순) → tf 봉. 구간 = tf초 격자(자정 UTC 기준)로
    타임스탬프를 내림(floor)해 묶는다 — 분봉·초봉·틱 어떤 최소 단위가 와도 같은 코드(시각만 보면 되니까).
    봉 하나 = 그 구간 원자들의 open=첫·high=최고·low=최저·close=끝·volume=합. 마지막 구간이 덜 찼으면 그대로
    (진행 중 봉 — close = 지금까지 마지막값). tf 가 원자와 같거나 더 잘거나, 분석 못 할 꼴이면 그대로 돌려준다."""
    s = tf_seconds(tf)
    if s is None or not bars:
        return list(bars)
    width = len(bars[0].date)
    out, cur, g = [], None, []
    for c in bars:
        bucket = (_epoch(c.date) // s) * s
        key = _dt.datetime.fromtimestamp(bucket, _dt.timezone.utc).strftime(_TS_FMT[width])
        if key != cur and g:
            out.append(_agg(cur, g))
            g = []
        cur = key
        g.append(c)
    if g:
        out.append(_agg(cur, g))
    return out


def _agg(key, g):
    """1분봉 묶음 g → 봉 하나(date = 구간 시작 key). open=첫·high=최고·low=최저·close=끝·volume=합(없는 값은 무시)."""
    highs = [c.high for c in g if c.high is not None]
    lows = [c.low for c in g if c.low is not None]
    vols = [c.volume for c in g if c.volume is not None]
    return Candle(key, g[0].open, max(highs) if highs else None, min(lows) if lows else None,
                  g[-1].close, sum(vols) if vols else None)
