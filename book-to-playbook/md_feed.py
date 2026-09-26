#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jhts 시세수집팀(jhts.marketdata) 어댑터 — etf-verdict의 유일한 시세 창구.

etf-verdict는 시세(미국 ETF·지수·선물·섹터 ETF의 일봉·현재값·분봉)를 직접
스크래핑하지 않는다. 모든 시세를 여기서 jhts.marketdata(md)로부터 받는다.
야후/KIS urllib 수집 코드는 전부 걷어내고 이 창구로 옮겼다.

  · 일봉/이동평균/거래량 → md.candles(sym) 로 받아 여기서 계산(MA창·반올림은
    옛 etf_daily_verdict.py 로직 그대로).
  · 현재값/등락률(선물·지수·EOD 스냅샷·장중) → md.quote / md.index_rate.
  · 장중 분봉(첫 눌림 저점) → md.minute_closes.

jhts.marketdata 미설치 시 AVAILABLE=False, 함수는 빈 값/None 을 돌려준다(무크래시).

주의: 여기서 다루는 것 중 '실적 캘린더'(earnings_dday)만 시세가 아니라 나스닥
공개 캘린더다. md 는 시세 전용이라 이 하나는 나스닥 공개 API(가격 엔드포인트 아님)를
그대로 호출한다 — market_extras.py 에 있던 로직을 여기로 접어 넣은 것.
"""
import io
import json
import os
import ssl
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

try:
    import jhts.marketdata as md
    AVAILABLE = True
except Exception:  # noqa: BLE001
    md = None
    AVAILABLE = False


# ---------------------------------------------------------------- 공통 계산 유틸
# 파생 계산(MA·수익률·연속일·눌림·거래량·폭)은 전부 jhts.marketdata.indicators 로 옮겼다
# (시세팀이 사실을 계산해 서빙 · 어느 프로젝트든 같은 함수 호출). 여기엔 스냅샷 등에
# 아직 쓰는 _pct 만 남긴다.
def _pct(a, b):
    return (a - b) / b * 100 if (a is not None and b) else None


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


def breadth_aligned(symbols):
    """같은 방향 최대 개수 → (aligned, up, down, checked)."""
    return md.breadth_aligned(symbols) if AVAILABLE else (0, 0, 0, 0)


def breadth_above_ma(symbols, n=20):
    """n일선 위 종목 수 → (count, checked)."""
    return md.breadth_above_ma(symbols, n) if AVAILABLE else (0, 0)


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


# ---------------------------------------------------------------- 섹터 (일봉 기반)
# 저자 5-3/5-4 매핑: 경기민감 기술 XLK·금융 XLF·산업재 XLI / 방어 필수소비재 XLP·
# 유틸리티 XLU·헬스케어 XLV. 섹터 5개(5-4) = 기술·금융·산업재·헬스케어·소비재.
SECTOR_ETF = {
    "기술": "XLK", "금융": "XLF", "산업재": "XLI",
    "헬스케어": "XLV", "소비재": "XLY",
    "필수소비재": "XLP", "유틸리티": "XLU",
}
FIVE = ["기술", "금융", "산업재", "헬스케어", "소비재"]
CYCLICAL = ["기술", "금융", "산업재"]
DEFENSIVE = ["필수소비재", "유틸리티", "헬스케어"]


def sector_snapshot():
    """섹터별 20일선 위 여부 · 5일 수익률. 실패한 섹터는 error 로 남긴다."""
    out = {}
    for name, sym in SECTOR_ETF.items():
        s = series(sym)
        if "error" in s:
            out[name] = {"sym": sym, "error": s["error"]}
            continue
        out[name] = {
            "sym": sym, "close": s["close"], "ma20": s["ma20"],
            "above": bool(s["ma20"] and s["close"] > s["ma20"]),
            "gap20": _pct(s["close"], s["ma20"]),
            "ret5": s["ret5"],
        }
    return out


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def sector_breadth(snap):
    """5-4: 섹터 5개 중 20일선 위 개수. 하나라도 실패면 count 를 신뢰하지 않는다."""
    got = [snap.get(n) for n in FIVE]
    if any((not s) or s.get("error") for s in got):
        bad = [n for n in FIVE if (not snap.get(n)) or snap[n].get("error")]
        return {"ok": False, "reason": "수집 실패: " + ", ".join(bad)}
    above = [n for n in FIVE if snap[n]["above"]]
    return {"ok": True, "count": len(above), "total": len(FIVE),
            "above": above, "below": [n for n in FIVE if n not in above],
            "label": "섹터 %d/%d 20일선 위 (%s)" % (
                len(above), len(FIVE), ", ".join(above) if above else "없음")}


def defensive_only(snap):
    """5-3 첫 신호: 방어주만 살아나고 경기민감(기술·산업재·금융)이 약한가."""
    cyc = [snap.get(n, {}).get("ret5") for n in CYCLICAL]
    dfn = [snap.get(n, {}).get("ret5") for n in DEFENSIVE]
    if any(v is None for v in cyc + dfn):
        return {"ok": False, "reason": "섹터 수집 실패"}
    c, d = _avg(cyc), _avg(dfn)
    flag = (d > 0) and (c < 0)
    return {"ok": True, "flag": flag, "cyc": c, "dfn": d,
            "label": "경기민감 5일 %+.1f%% (기술 %+.1f·금융 %+.1f·산업재 %+.1f) / 방어 5일 %+.1f%%"
                     % (c, snap["기술"]["ret5"], snap["금융"]["ret5"],
                        snap["산업재"]["ret5"], d)}


def cyclical_weak(snap):
    """5-3 실전 트리거: '금융·산업재 5거래일 이상 약함'."""
    f, i = snap.get("금융", {}), snap.get("산업재", {})
    if f.get("ret5") is None or i.get("ret5") is None:
        return {"ok": False, "reason": "섹터 수집 실패"}
    flag = f["ret5"] < 0 and i["ret5"] < 0
    return {"ok": True, "flag": flag,
            "label": "금융 5일 %+.1f%% · 산업재 5일 %+.1f%%" % (f["ret5"], i["ret5"])}


# ---------------------------------------------------------------- 실적 캘린더
# 시세가 아니라 나스닥 공개 캘린더(가격 엔드포인트 아님). md 는 시세 전용이라
# 이 하나는 여기서 직접 호출한다 — market_extras.py 에 있던 로직을 접어 넣음.
_UA = {"User-Agent": "Mozilla/5.0"}
_CTX = ssl.create_default_context()
_EARNINGS_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "earnings-dates.json")


def _nasdaq_day(day):
    u = "https://api.nasdaq.com/api/calendar/earnings?date=%s" % day.isoformat()
    h = dict(_UA)
    h.update({"Accept": "application/json", "Referer": "https://www.nasdaq.com/"})
    with urllib.request.urlopen(urllib.request.Request(u, headers=h),
                                timeout=25, context=_CTX) as f:
        d = json.loads(f.read().decode("utf-8", "replace"))
    rows = (d.get("data") or {}).get("rows") or []
    return {r.get("symbol", "").upper() for r in rows}


def _load_earn_cache():
    if os.path.exists(_EARNINGS_CACHE):
        try:
            return json.loads(io.open(_EARNINGS_CACHE, encoding="utf-8").read())
        except Exception:  # noqa: BLE001
            pass
    return {}


def _save_earn_cache(c):
    io.open(_EARNINGS_CACHE, "w", encoding="utf-8", newline="\n").write(
        json.dumps(c, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def next_earnings(symbols, horizon=110, force=False):
    """각 심볼의 다음 실적 발표일. {sym: 'YYYY-MM-DD' | None}. 소스 막히면 None."""
    symbols = [s.upper() for s in symbols]
    cache = _load_earn_cache()
    today = date.today()

    def fresh(sym):
        e = cache.get(sym)
        if not e:
            return False
        try:
            if e.get("date"):
                return date.fromisoformat(e["date"]) >= today
            if e.get("scanned_until"):
                return date.fromisoformat(e["scanned_until"]) > today
        except Exception:  # noqa: BLE001
            return False
        return False

    need = [s for s in symbols if force or not fresh(s)]
    if need:
        found, day, scanned, failed = {}, today, 0, False
        while scanned < horizon and need:
            if day.weekday() < 5:
                try:
                    syms = _nasdaq_day(day)
                except Exception as e:  # noqa: BLE001
                    cache["_error"] = "%s (%s)" % (
                        e, datetime.now().isoformat(timespec="seconds"))
                    failed = True
                    break
                for s in list(need):
                    if s in syms:
                        found[s] = day.isoformat()
                        need.remove(s)
                scanned += 1
            day += timedelta(days=1)

        stamp = datetime.now().isoformat(timespec="seconds")
        for s, dt in found.items():
            cache[s] = {"date": dt, "fetched": stamp}
        if not failed:
            for s in need:
                cache[s] = {"date": None, "fetched": stamp,
                            "scanned_until": (today + timedelta(days=horizon)).isoformat()}
            cache.pop("_error", None)
        if found or need or failed:
            _save_earn_cache(cache)

    out = {}
    for s in symbols:
        e = cache.get(s)
        out[s] = e["date"] if (e and fresh(s)) else None
    return out


def earnings_dday(symbols, horizon=110):
    """{sym: (날짜, D-n)} — 가장 가까운 것부터. 못 구한 심볼은 빠진다."""
    dates = next_earnings(symbols, horizon=horizon)
    today = date.today()
    out = {}
    for s, dt in dates.items():
        if dt:
            out[s] = (dt, (date.fromisoformat(dt) - today).days)
    return dict(sorted(out.items(), key=lambda kv: kv[1][1]))


if __name__ == "__main__":
    print("AVAILABLE =", AVAILABLE)
    if AVAILABLE:
        print("TQQQ series:", {k: v for k, v in series("TQQQ").items() if k != "closes"})
        print("NQ=F/ES=F quote:", quote_snapshot(["NQ=F", "ES=F"]))
        print("^VIX index:", index_snapshot("^VIX"))
