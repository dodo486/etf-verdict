#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jhts 시세수집팀(jhts.marketdata) 어댑터 — 파이프라인의 유일한 시세 창구(수집 단계).

무엇을 받을지는 체크리스트(조건 트리)가 정한다: cond.symbols_of(tree) 가 여섯 칸 전부·defs 에서
심볼을 뽑고, tree_grade.history 가 이 파일의 histories() 하나로 받는다. 판정 엔진·백테스트·트리 검사가
모두 같은 입구를 쓴다 — 수집 요청서(data_spec)를 따로 쓰지 않는다.

시세가 없는 심볼은 지어내지 않고 jhts 수집 요청(collection_requests, requester "etf-verdict",
dataset "candles")을 남긴다. 같은 요청은 jhts 가 하나로 합치고, 채워지면 다음 실행부터 그대로 들어온다.

jhts.marketdata 미설치 시 AVAILABLE=False, 함수는 빈 값을 돌려준다(무크래시 — 판정은 ❔ 로 드러난다).
이 파일에는 네트워크 코드가 **없어야 한다** — 수집은 전부 jhts 몫이다.
(`import jhts` 가 허용되는 곳도 파이프라인 전체에서 이 파일 하나다. verify_teams.py 가 강제.)
"""
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
        return md.candles(symbol, start=start) or []
    except Exception:  # noqa: BLE001
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
    """1분봉 종가 {YYYYMMDDHHMM(UTC): 종가} — jhts 가 주는 최근 구간(미국 심볼 약 7거래일). 실패/미설치 시 {}."""
    if not AVAILABLE:
        return {}
    try:
        return md.minute_closes(symbol) or {}
    except Exception:  # noqa: BLE001
        return {}


def requested():
    """{심볼: 요청 id | 실패 사유} — 시세가 없어 수집을 요청한 심볼."""
    return dict(_REQUESTED)


if __name__ == "__main__":
    print("AVAILABLE =", AVAILABLE)
    if AVAILABLE:
        cs = history("SPY", "20260101")
        print("SPY 일봉 %d개, 마지막 %s" % (len(cs), cs[-1] if cs else None))
