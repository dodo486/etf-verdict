#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""섹터 폭 · 실적 캘린더 — 저자 5-3 / 5-4 / 3-5 구현에 필요한 추가 수집.

여기 있는 건 전부 **무료 공개 소스**다.
  - 섹터: SPDR 섹터 ETF (야후 chart API). 저자가 지목한 업종 그대로 매핑.
  - 실적일: 나스닥 공개 캘린더 API. 실패하면 값을 지어내지 않고 None 을 돌려준다.

저자 매핑 (5-2/5-3/5-4 원문)
  경기민감 : 기술 XLK · 금융 XLF · 산업재 XLI
  방어     : 필수소비재 XLP · 유틸리티 XLU · 헬스케어 XLV
  섹터 5개 : 기술·금융·산업재·헬스케어·소비재 (시트 UPRO 진입조건과 동일)
"""
import io
import json
import os
import ssl
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

import paths
from paths import BASE

UA = {"User-Agent": "Mozilla/5.0"}
CTX = ssl.create_default_context()

# 저자가 이름으로 지목한 업종 → SPDR 섹터 ETF
SECTOR_ETF = {
    "기술": "XLK", "금융": "XLF", "산업재": "XLI",
    "헬스케어": "XLV", "소비재": "XLY",
    "필수소비재": "XLP", "유틸리티": "XLU",
}
# 5-4 "섹터 5개 중 몇 개 20일선 위" — 시트 UPRO 진입조건의 5개와 동일하게 유지
FIVE = ["기술", "금융", "산업재", "헬스케어", "소비재"]
CYCLICAL = ["기술", "금융", "산업재"]      # 경기민감 (5-3)
DEFENSIVE = ["필수소비재", "유틸리티", "헬스케어"]  # 방어 (5-3)

EARNINGS_CACHE = os.path.join(BASE, "earnings-dates.json")


# ---------------------------------------------------------------- 섹터
def _chart(symbol, rng="3mo"):
    u = ("https://query1.finance.yahoo.com/v8/finance/chart/%s?range=%s&interval=1d"
         % (urllib.parse.quote(symbol), rng))
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20, context=CTX) as f:
        d = json.load(f)
    r = d["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    return [c for c in q.get("close", []) if c is not None]


def sector_snapshot():
    """섹터별 20일선 위 여부 · 5일 수익률. 실패한 섹터는 None 으로 남긴다."""
    out = {}
    for name, sym in SECTOR_ETF.items():
        try:
            c = _chart(sym)
            if len(c) < 21:
                out[name] = {"sym": sym, "error": "데이터 부족"}
                continue
            ma20 = sum(c[-20:]) / 20
            out[name] = {
                "sym": sym, "close": c[-1], "ma20": ma20,
                "above": c[-1] > ma20,
                "gap20": (c[-1] - ma20) / ma20 * 100,
                "ret5": (c[-1] - c[-6]) / c[-6] * 100,
            }
        except Exception as e:  # noqa: BLE001
            out[name] = {"sym": sym, "error": str(e)}
    return out


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def sector_breadth(snap):
    """5-4: 섹터 5개 중 20일선 위 개수. 하나라도 실패하면 count 를 신뢰하지 않는다."""
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
    # 저자: "방어주만 살아나고 기술·산업재·금융 약해지면"
    flag = (d > 0) and (c < 0)
    return {"ok": True, "flag": flag, "cyc": c, "dfn": d,
            "label": "경기민감 5일 %+.1f%% (기술 %+.1f·금융 %+.1f·산업재 %+.1f) / 방어 5일 %+.1f%%"
                     % (c, snap["기술"]["ret5"], snap["금융"]["ret5"],
                        snap["산업재"]["ret5"], d)}


def cyclical_weak(snap, days=5):
    """5-3 실전 트리거: '금융·산업재 5거래일 이상 약함'."""
    f, i = snap.get("금융", {}), snap.get("산업재", {})
    if f.get("ret5") is None or i.get("ret5") is None:
        return {"ok": False, "reason": "섹터 수집 실패"}
    flag = f["ret5"] < 0 and i["ret5"] < 0
    return {"ok": True, "flag": flag,
            "label": "금융 5일 %+.1f%% · 산업재 5일 %+.1f%%" % (f["ret5"], i["ret5"])}


# ---------------------------------------------------------------- 실적 캘린더
def _nasdaq_day(day):
    u = "https://api.nasdaq.com/api/calendar/earnings?date=%s" % day.isoformat()
    h = dict(UA); h.update({"Accept": "application/json", "Referer": "https://www.nasdaq.com/"})
    with urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=25, context=CTX) as f:
        d = json.loads(f.read().decode("utf-8", "replace"))
    rows = (d.get("data") or {}).get("rows") or []
    return {r.get("symbol", "").upper() for r in rows}


def _load_cache():
    if os.path.exists(EARNINGS_CACHE):
        try:
            return json.loads(io.open(EARNINGS_CACHE, encoding="utf-8").read())
        except Exception:  # noqa: BLE001
            pass
    return {}


def _save_cache(c):
    io.open(EARNINGS_CACHE, "w", encoding="utf-8", newline="\n").write(
        json.dumps(c, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def next_earnings(symbols, horizon=110, force=False):
    """각 심볼의 다음 실적 발표일. {sym: 'YYYY-MM-DD' | None}

    나스닥 캘린더를 하루씩 앞으로 훑는다(주말 건너뜀). 매일 수십 번 때리지 않도록
    결과를 캐시하고, 캐시된 날짜가 아직 미래면 그대로 쓴다.
    소스가 막히면 None 을 남긴다 — 값을 지어내지 않는다.
    """
    symbols = [s.upper() for s in symbols]
    cache = _load_cache()
    today = date.today()

    def fresh(sym):
        """캐시를 다시 쓸 수 있나.

        날짜를 찾았으면 그 날이 지나기 전까지, 못 찾았으면 '여기까지 훑었다'
        시점이 지나기 전까지 재사용한다. 음성 캐시가 없으면 발표일이 horizon 밖인
        종목 때문에 매일 수십 번 스캔하게 된다.
        """
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
            if day.weekday() < 5:          # 주말 제외
                try:
                    syms = _nasdaq_day(day)
                except Exception as e:      # noqa: BLE001
                    cache["_error"] = "%s (%s)" % (e, datetime.now().isoformat(timespec="seconds"))
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
            # horizon 안에 없던 종목은 '여기까지 봤다'를 남겨 매일 재스캔을 막는다
            for s in need:
                cache[s] = {"date": None, "fetched": stamp,
                            "scanned_until": (today + timedelta(days=horizon)).isoformat()}
            cache.pop("_error", None)
        if found or need or failed:
            _save_cache(cache)

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
    snap = sector_snapshot()
    print("=== 섹터 ===")
    for n, v in snap.items():
        if v.get("error"):
            print("  %-6s %-4s 실패: %s" % (n, v["sym"], v["error"]))
        else:
            print("  %-6s %-4s 종가 %8.2f / 20일선 %8.2f (%s) · 5일 %+.1f%%"
                  % (n, v["sym"], v["close"], v["ma20"], "위" if v["above"] else "아래", v["ret5"]))
    print("\n5-4 섹터 폭 :", sector_breadth(snap))
    print("5-3 방어만  :", defensive_only(snap))
    print("5-3 경기민감:", cyclical_weak(snap))
    print("\n=== 실적일 (3-5) ===")
    dd = earnings_dday(["NVDA", "MSFT", "AAPL", "AMD", "AVGO"])
    for s, (dt, n) in dd.items():
        print("  %-5s %s  D-%d" % (s, dt, n))
    missing = [s for s in ["NVDA", "MSFT", "AAPL", "AMD", "AVGO"] if s not in dd]
    if missing:
        print("  못 구함(캘린더 범위 밖 또는 미공시):", ", ".join(missing))
