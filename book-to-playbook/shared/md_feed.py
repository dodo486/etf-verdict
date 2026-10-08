#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jhts 시세수집팀(jhts.marketdata) 어댑터 — 파이프라인의 유일한 시세 창구(수집 단계).

무엇을 받을지는 체크리스트(조건 트리)가 정한다: TreeGateway.symbols()(checklist/tree_gateway.py)가 여섯 칸
전부·defs 에서 심볼을 뽑고, checklist.grade.history 가 이 파일의 histories() 하나로 받는다. 판정 엔진·백테스트·트리 검사가
모두 같은 입구를 쓴다 — 수집 요청서(data_spec)를 따로 쓰지 않는다.

시세가 없는 심볼은 지어내지 않고 jhts 수집 요청(collection_requests, requester "etf-verdict",
dataset "candles")을 남긴다. 같은 요청은 jhts 가 하나로 합치고, 채워지면 다음 실행부터 그대로 들어온다.

jhts.marketdata 미설치 시 AVAILABLE=False, 함수는 빈 값을 돌려준다(무크래시 — 판정은 ❔ 로 드러난다).
이 파일에는 네트워크 코드가 **없어야 한다** — 수집은 전부 jhts 몫이다.
(`import jhts` 가 허용되는 곳도 파이프라인 전체에서 이 파일 하나다. verify_teams.py 가 강제.)
"""
import sys

from shared import _dev_cache  # DEV 전용 시세 캐시(ETF_DEV_CACHE 꺼지면 no-op) — 반복 네트워크 제거

try:
    import jhts.marketdata as md
    AVAILABLE = True
except Exception:  # noqa: BLE001
    md = None
    AVAILABLE = False

REQUESTER = "etf-verdict"
_REQUESTED = {}     # 이번 실행에서 수집 요청을 남긴 심볼 → 요청 id(또는 실패 사유)


def history(symbol, start):
    """start(YYYYMMDD) 이후 일봉 [Candle(date, open, high, low, close, volume)] 오름차순. 실패/미설치 시 []."""
    if not AVAILABLE:
        return []
    try:
        return _dev_cache.cached(("candles", symbol, start),
                                 lambda: md.candles(symbol, start=start) or [])
    except Exception as e:  # noqa: BLE001
        # 판정은 ❔ 로 degrade 하되(무크래시), '데이터 없음'과 '어댑터가 실제로 고장'을
        # 구분할 수 있게 진짜 예외는 한 줄 남긴다(조용한 실패가 버그를 숨기지 않도록).
        sys.stderr.write("md_feed.history(%s) 예외 — %s: %s\n" % (symbol, type(e).__name__, e))
        return []


def histories(symbols, start):
    """수집 단계의 단일 입구 — 심볼들의 start 이후 일봉 {심볼: [Candle]}.
    시세가 없는 심볼은 jhts 수집 요청을 남긴다(requested() 로 본다)."""
    out = {}
    for s in sorted(set(symbols)):
        out[s] = history(s, start)
        if not out[s]:
            _REQUESTED[s] = _request(s, start)
    return out


def _request(symbol, start):
    if not AVAILABLE:
        return "요청 못 함: jhts.marketdata 미설치"
    try:
        return md.request(REQUESTER, code=symbol, dataset="candles", start=start,
                          note="조건 트리가 쓰는 심볼 — 일봉 없음")
    except Exception as e:  # noqa: BLE001
        return "요청 실패: %s" % e


def minutes(symbol):
    """1분봉 OHLCV {YYYYMMDDHHMM(UTC): {open,high,low,close,volume}} — 계약은 MIGRATION_NOTES ④.
    jhts.marketdata.minute_bars 로 받는다: 리스트 [{dt(ISO8601 UTC, 끝 Z), open,high,low,close,vol}] 오름차순.
    여기서 모양만 계약으로 바꾼다 — dt 를 YYYYMMDDHHMM(UTC 그대로) 키로, vol → volume 로.
    실패·빈결과·미설치·예외 → {} (가짜로 안 채운다 — 평가기에서 '모름' 으로 정직하게 떨어진다).
    cond.minute_series 는 이 OHLCV dict(또는 스칼라 종가)를 둘 다 받으므로 트리·평가기는 무변경."""
    if not AVAILABLE:
        return {}
    try:
        bars = _dev_cache.cached(("minute_bars", symbol),
                                 lambda: md.minute_bars(symbol) or [])
    except Exception as e:  # noqa: BLE001
        # '데이터 없음'과 '어댑터 고장'을 구분할 수 있게 진짜 예외는 한 줄 남긴다.
        sys.stderr.write("md_feed.minutes(%s) 예외 — %s: %s\n" % (symbol, type(e).__name__, e))
        return {}
    out = {}
    for b in bars:
        dt = b.get("dt")
        if not dt:
            continue
        # dt: "2026-10-02T19:59:00Z"(ISO8601 UTC) → "202610021959"(UTC 그대로, 변환 없음).
        key = dt[:4] + dt[5:7] + dt[8:10] + dt[11:13] + dt[14:16]
        out[key] = {
            "open": b.get("open"),
            "high": b.get("high"),
            "low": b.get("low"),
            "close": b.get("close"),
            "volume": b.get("vol"),
        }
    return out


def sessions(market, start, end):
    """market("US"|"KR")의 start~end(YYYYMMDD) 정규장 달력 [Session] — 업계 캘린더(거래소 휴장·반일장 반영).
    Session: .date(YYYYMMDD) · .open/.close(거래소 현지 tz-aware datetime) · .is_half(반일장). 실패/미설치 시 []."""
    if not AVAILABLE:
        return []
    try:
        return md.sessions(market, start, end) or []
    except Exception:  # noqa: BLE001
        return []


def market_of(symbol):
    """심볼이 속한 시장 "US"|"KR" — 분봉/세션 시각의 기준 시장을 정한다. 미설치/실패 시 None."""
    if not AVAILABLE:
        return None
    try:
        return md.market_of(symbol)
    except Exception:  # noqa: BLE001
        return None


def requested():
    """{심볼: 요청 id | 실패 사유} — 시세가 없어 수집을 요청한 심볼."""
    return dict(_REQUESTED)


if __name__ == "__main__":
    print("AVAILABLE =", AVAILABLE)
    if AVAILABLE:
        cs = history("SPY", "20260101")
        print("SPY 일봉 %d개, 마지막 %s" % (len(cs), cs[-1] if cs else None))
