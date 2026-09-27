#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jhts 시세수집팀(jhts.marketdata) 어댑터 — 구간③의 유일한 시세 창구.

구간③(verdict 팀)은 시세(미국 ETF·지수·선물·섹터 ETF의 일봉·현재값·분봉)를 직접
스크래핑하지 않는다. 모든 시세를 여기서 jhts.marketdata(md)로부터 받는다.
야후/KIS urllib 수집 코드는 전부 걷어내고 이 창구로 옮겼다.

  · 일봉/이동평균/거래량 → md.candles(sym) 로 받아 여기서 계산(MA창·반올림은
    레거시 로직 그대로).
  · 현재값/등락률(선물·지수·EOD 스냅샷·장중) → md.quote / md.index_rate.
  · 장중 분봉(첫 눌림 저점) → md.minute_closes.

jhts.marketdata 미설치 시 AVAILABLE=False, 함수는 빈 값/None 을 돌려준다(무크래시).

이 파일에는 네트워크 코드가 **없어야 한다** — 수집은 전부 jhts 몫이다.
(`import jhts` 가 허용되는 곳도 팀 전체에서 이 파일 하나다. verify_teams.py 가 강제.)
"""
try:
    import jhts.marketdata as md
    AVAILABLE = True
except Exception:  # noqa: BLE001
    md = None
    AVAILABLE = False


# 파생 계산(MA·수익률·연속일·눌림·거래량·폭)은 전부 jhts.marketdata.indicators 로 옮겼다
# (시세팀이 사실을 계산해 서빙 · 어느 프로젝트든 같은 함수 호출).
def series(symbol):
    """심볼의 파생 시계열 사실 — jhts.marketdata.daily_features 로 위임한다.

    계산은 시세팀(indicators)이 소유한다(어느 프로젝트든 같은 함수). 여기선 창구로서
    미설치/실패만 감싼다. 반환 키는 daily_features 와 동일(기존 키 + days_since_high·
    breakout_hold·vol_down_up·first_green_below_ma20 등 신규 사실).
    """
    if not AVAILABLE:
        return {"sym": symbol, "error": "jhts.marketdata 미설치"}
    try:
        return md.daily_features(symbol)
    except Exception as e:  # noqa: BLE001
        return {"sym": symbol, "error": "시세 조회 실패: %s" % e}


# ---------------------------------------------------------------- 여러 종목 폭(breadth)
# 교차종목 사실도 시세팀이 계산한다 — 여기선 창구로 위임(판정·문턱은 소비자).
def breadth_up(symbols):
    """상승 종목 수 → (up, checked)."""
    return md.breadth_up(symbols) if AVAILABLE else (0, 0)


def prev_low_breaks(symbols):
    """전일 저점 이탈 종목 수 → (breaks, checked)."""
    return md.prev_low_breaks(symbols) if AVAILABLE else (0, 0)


# ---------------------------------------------------------------- 현재값 / 등락률
def _rate_snapshot(symbol, is_index):
    """{price, prev, chg, sign} 또는 None.

    md.index_rate/stock_rate 는 {price, rate(부호%), sign} 를 준다. 시트/스코어카드가
    '전일' 값을 보여주므로 prev 를 등락률에서 역산한다: prev = price / (1 + rate/100).
    """
    if not AVAILABLE:
        return None
    try:
        r = md.index_rate(symbol) if is_index else md.stock_rate(symbol)
    except Exception:  # noqa: BLE001
        return None
    if not r or r.get("price") is None or r.get("rate") is None:
        return None
    price = r["price"]
    rate = r["rate"]
    prev = price / (1 + rate / 100.0) if (1 + rate / 100.0) else None
    return {"price": price, "prev": prev, "chg": rate, "sign": r.get("sign")}


def index_snapshot(symbol):
    """지수/선물의 현재값 스냅샷. code: ^NDX/^GSPC/^VIX/^TNX 등. 실패 시 None."""
    return _rate_snapshot(symbol, is_index=True)


def stock_snapshot(symbol):
    """개별종목/ETF 현재값 스냅샷. 실패 시 None."""
    return _rate_snapshot(symbol, is_index=False)


def quote_snapshot(symbols):
    """md.quote 배치 → {sym: {name, price, prev, chg, volume}}.

    선물(NQ=F/ES=F) 방향 판정용. value/mktcap 은 미국 심볼에서 대개 None 이라
    제외한다(방향 판정에 안 쓰인다). prev 는 rate 에서 역산.
    """
    if not AVAILABLE or not symbols:
        return {}
    try:
        q = md.quote(list(symbols)) or {}
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for sym, v in q.items():
        if not v:
            continue
        price = v.get("price")
        rate = v.get("rate")
        prev = None
        if price is not None and rate is not None and (1 + rate / 100.0):
            prev = price / (1 + rate / 100.0)
        out[sym] = {"name": v.get("name"), "price": price, "prev": prev,
                    "chg": rate, "volume": v.get("volume")}
    return out


# ---------------------------------------------------------------- 장중 분봉
def minute_closes(symbol):
    """분봉 종가 {YYYYMMDDHHMM: 종가}. 최근 ~7거래일. 실패 시 {}."""
    if not AVAILABLE:
        return {}
    try:
        return md.minute_closes(symbol) or {}
    except Exception:  # noqa: BLE001
        return {}


def last_minute_bars(symbol, n=30):
    """가장 최근 n개 분봉 종가 시퀀스(시간 오름차순) [(YYYYMMDDHHMM, close), ...].

    장중 '첫 눌림 저점 높임' 판정용. 분봉은 종가만 제공되므로 저점 근사는 종가로 한다.
    """
    mc = minute_closes(symbol)
    if not mc:
        return []
    keys = sorted(mc.keys())[-n:]
    return [(k, mc[k]) for k in keys]


def intraday_snapshot(symbol):
    """장중 현재값 스냅샷 {last, base, chg} — 옛 KIS overseas_price 대체.

    last=현재가, base=전일종가(등락률에서 역산), chg=전일比 %.
    시가(open)는 md 실시간 창구에 없어 제공하지 않는다(장중 판정 재설계에서 처리).
    실패 시 None.
    """
    s = stock_snapshot(symbol)
    if not s:
        return None
    return {"last": s["price"], "base": s["prev"], "chg": s["chg"]}


if __name__ == "__main__":
    print("AVAILABLE =", AVAILABLE)
    if AVAILABLE:
        print("SPY series:", {k: v for k, v in series("SPY").items() if k != "closes"})
        print("NQ=F/ES=F quote:", quote_snapshot(["NQ=F", "ES=F"]))
        print("^VIX index:", index_snapshot("^VIX"))
