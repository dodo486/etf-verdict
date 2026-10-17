#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""시세 칸 저장소(market/store) 검사 — 가짜 시세원·가짜 캘린더로(네트워크 없음).

  · load 는 등록된 심볼을 한 번에(시작일마다 fetch 1회) — 두 번 불러도 다시 받지 않는다
  · need 로 새 심볼·더 이른 시작일을 등록하면 다음 load 는 그 심볼만 받는다
  · refresh 는 최근 창만 받아 합친다(같은 날짜 바꿈·새 날짜 덧붙임) → 실제로 바뀐 심볼만 돌려준다
  · prices() 는 바뀐 게 없으면 같은 객체, 바뀌면 새 객체 — 내보낸 스냅숏은 고치지 않는다(copy-on-write)
  · confirmed 는 settled_dates 규칙(마감 ≤ 지금) — 캘린더·시장을 모르면 확정으로 본다
  · session_closes·settled_dates 는 판단자(judge) 계산기가 쓰는 것과 같은 함수

실행: python -m market.verify_store
"""
import datetime as _dt
import sys
from collections import namedtuple

from market.store import Store, session_closes, settled_dates, resample, tf_seconds

Candle = namedtuple("Candle", "date open high low close volume")
Session = namedtuple("Session", "date open close is_half")
UTC = _dt.timezone.utc
FAILS = []


def check(name, ok):
    print(("  ok  " if ok else "  FAIL") + " " + name)
    if not ok:
        FAILS.append(name)


def bar(d, c):
    return Candle(d, c, c, c, c, 100)


class FakeFeed:
    """심볼 → {날짜: 종가}. 부를 때마다 (심볼들, 시작일)을 적는다."""

    def __init__(self, data):
        self.data, self.calls = data, []

    def __call__(self, symbols, start):
        self.calls.append((tuple(symbols), start))
        return {s: [bar(d, c) for d, c in sorted(self.data.get(s, {}).items()) if d >= start] for s in symbols}


def fake_sessions(market, start, end):
    """US 평일 세션 — 마감 21:00 UTC. KR 은 캘린더 없음."""
    if market != "US":
        return []
    out, d = [], _dt.datetime.strptime(start, "%Y%m%d")
    while d.strftime("%Y%m%d") <= end:
        if d.weekday() < 5:
            close = _dt.datetime(d.year, d.month, d.day, 21, 0, tzinfo=UTC)
            out.append(Session(d.strftime("%Y%m%d"), close - _dt.timedelta(hours=6, minutes=30), close, False))
        d += _dt.timedelta(days=1)
    return out


MARKET = {"AAA": "US", "BBB": "US", "CCC": "US", "KKK": "KR"}


def main():
    now = [_dt.datetime(2026, 10, 9, 18, 0, tzinfo=UTC)]          # 금요일 장중(마감 21:00 UTC 전)
    data = {"AAA": {"20261005": 1, "20261006": 2, "20261007": 3, "20261008": 4, "20261009": 5},
            "BBB": {"20261007": 10, "20261008": 11, "20261009": 12},
            "CCC": {"20260901": 7, "20261009": 8},
            "KKK": {"20261009": 50}}
    feed = FakeFeed(data)
    st = Store(fetch=feed, sessions=fake_sessions, now=lambda: now[0], market_of=MARKET.get)

    print("[load]")
    st.need(["AAA", "BBB"], "20261001")
    st.need(["AAA"], "20261003")                                   # 더 늦은 시작 — 넓히지 않는다
    st.load()
    check("load 는 fetch 1회(두 심볼 함께)", feed.calls == [(("AAA", "BBB"), "20261001")])
    p1 = st.prices()
    check("prices 모양 = {심볼: [Candle]}", sorted(p1) == ["AAA", "BBB"] and [c.close for c in p1["AAA"]] == [1, 2, 3, 4, 5])
    st.load()
    check("다시 load 해도 받지 않는다", len(feed.calls) == 1)
    check("바뀐 게 없으면 prices() 는 같은 객체", st.prices() is p1)
    check("symbols()", st.symbols() == {"AAA", "BBB"})

    print("[need 넓히기]")
    st.need(["AAA", "CCC"], "20261001")                            # AAA 그대로 · CCC 새로
    st.load()
    check("새 심볼만 받는다", feed.calls[-1] == (("CCC",), "20261001") and len(feed.calls) == 2)
    p2 = st.prices()
    check("적재 뒤 새 객체", p2 is not p1 and sorted(p2) == ["AAA", "BBB", "CCC"])
    check("지난 스냅숏은 그대로", sorted(p1) == ["AAA", "BBB"])
    st.need(["CCC"], "20260801")                                   # 더 이른 시작 — 그 심볼만 다시
    st.load()
    check("시작일이 넓혀진 심볼만 다시 받는다", feed.calls[-1] == (("CCC",), "20260801"))
    check("넓힌 기간까지 들어온다", [c.date for c in st.prices()["CCC"]] == ["20260901", "20261009"])
    p3 = st.prices()

    print("[refresh]")
    ch = st.refresh(recent_days=7)
    check("변화 없으면 빈 집합 · 같은 객체", ch == set() and st.prices() is p3)
    check("refresh 는 최근 창만(시작 = 지금 - 7일)", feed.calls[-1] == (("AAA", "BBB", "CCC"), "20261002"))
    data["AAA"]["20261009"] = 6                                    # 오늘 봉 갱신
    data["BBB"]["20261012"] = 13                                   # 새 날짜
    keep_aaa = p3["AAA"]
    ch = st.refresh(recent_days=7)
    check("바뀐 심볼만 돌려준다", ch == {"AAA", "BBB"})
    p4 = st.prices()
    check("바뀌면 새 객체", p4 is not p3)
    check("같은 날짜는 바꾼다", [c.close for c in p4["AAA"]] == [1, 2, 3, 4, 6])
    check("새 날짜는 덧붙인다", [c.date for c in p4["BBB"]][-1] == "20261012" and len(p4["BBB"]) == 4)
    check("안 바뀐 심볼 리스트는 그대로 공유", p4["CCC"] is p3["CCC"])
    check("내보낸 리스트는 고치지 않는다(copy-on-write)", [c.close for c in keep_aaa] == [1, 2, 3, 4, 5])
    data.pop("BBB")                                                # 받기 실패(빈 결과)
    ch = st.refresh(recent_days=7)
    check("빈 결과는 지우지 않는다", ch == set() and len(st.prices()["BBB"]) == 4)

    print("[confirmed]")
    st.need(["KKK"], "20261001")
    st.load()
    a = st.prices()["AAA"]
    check("장중: 오늘 봉은 진행 중", st.confirmed("AAA", len(a) - 1) is False)
    check("장중: 어제 봉은 확정", st.confirmed("AAA", len(a) - 2) is True)
    check("음수 index", st.confirmed("AAA", -1) is False)
    now[0] = _dt.datetime(2026, 10, 9, 21, 0, tzinfo=UTC)          # 마감 == 지금 → 확정
    check("마감 시각 = 지금이면 확정", st.confirmed("AAA", -1) is True)
    check("캘린더 없는 시장은 확정으로 본다", st.confirmed("KKK", -1) is True)
    b = st.prices()["BBB"]
    check("캘린더 범위 밖 새 봉(월요일) — 캘린더를 넓혀 다시 보고 마감 전이면 진행 중",
          b[-1].date == "20261012" and st.confirmed("BBB", -1) is False)

    print("[봉 집계(resample) — 최소 단위 → 임의 tf, 단위 무관]")
    check("tf_seconds: 단위표 s·m·h·d·w", (tf_seconds("5m"), tf_seconds("1h"), tf_seconds("1d"), tf_seconds("30s")) == (300, 3600, 86400, 30))
    check("tf_seconds: 모르는 꼴은 None", tf_seconds("5x") is None and tf_seconds("m") is None)
    # 분봉 원자(종가 10..21, 13:00~13:11) → 5m 봉 3개: 끝값 14·19·21, open=첫·high=최고·low=최저·volume=합
    mins = [Candle("2026100213%02d" % m, 10 + m, 10 + m, 10 + m, 10 + m, 2) for m in range(12)]
    r5 = resample(mins, "5m")
    check("5m 봉 수·종가(=구간 끝 1분봉)", [c.date for c in r5] == ["202610021300", "202610021305", "202610021310"] and [c.close for c in r5] == [14, 19, 21])
    check("5m open=첫·high=최고·low=최저·volume=합", r5[0].open == 10 and r5[0].high == 14 and r5[0].low == 10 and r5[0].volume == 10)
    check("1m·1d 는 그대로(집계 안 함)", resample(mins, "1m") == mins and resample(mins, "1d") != [])
    # 초봉 원자(14자리 타임스탬프)도 같은 코드로 — 최소 단위가 더 잘아져도 안 깨진다
    secs = [Candle("202610021300%02d" % s, 10 + s, 10 + s, 10 + s, 10 + s, 1) for s in range(12)]
    r5s = resample(secs, "5s")
    check("초봉 원자 → 5s 집계(같은 코드, 단위만 다름)", [c.close for c in r5s] == [14, 19, 21])

    print("[같은 규칙 — judge 계산기와 공유]")
    asof = _dt.datetime(2026, 10, 9, 18, 0, tzinfo=UTC)
    sc = session_closes(["AAA", "KKK", "ZZZ"], ["20261005", "20261009"], asof, fake_sessions, MARKET.get)
    check("session_closes: 캘린더 있는 심볼만", sorted(sc) == ["AAA"])
    check("settled_dates: 마감 ≤ asof 만", settled_dates(sc["AAA"], asof) == {"20261005", "20261006", "20261007", "20261008"})
    check("asof 없으면 빈 경계", session_closes(["AAA"], ["20261005"], None, fake_sessions, MARKET.get) == {})

    print("\n%s" % ("시세 칸 저장소 검사 통과 — 한 번 적재 · 바뀐 심볼만 · 스냅샷 동일성 · 확정 표시 · 봉 집계(단위 무관)" if not FAILS else "시세 칸 저장소 검사 실패 %d개: %s" % (len(FAILS), ", ".join(FAILS))))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
