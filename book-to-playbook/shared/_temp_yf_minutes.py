#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TEMP — jhts 분봉 OHLCV 교체 시 이 파일 통째 삭제. 다른 곳에서 import 금지.
#   yfinance 를 import 하는 파일은 파이프라인 전체에서 **이 파일 하나뿐**이다.
#   스왑 포인트는 shared/md_feed.py 의 minutes() 한 곳. 삭제 체크리스트는 MIGRATION_NOTES.md.
# =============================================================================
"""jhts 분봉이 연결되기 전까지 쓰는 임시 분봉 제공자 — yfinance 에서 실제 1분봉 OHLCV 를 당긴다.

md_feed.minutes() 계약(MIGRATION_NOTES ④)에 맞춘 형태로 돌려준다:
    { "YYYYMMDDHHMM(UTC)": {"open":f,"high":f,"low":f,"close":f,"volume":f} }
키는 **UTC** 분(YYYYMMDDHHMM). yahoo 는 tz-aware(보통 거래소 현지 tz) 인덱스를 주므로 UTC 로 변환해 키를 만든다.
cond.minute_series 가 이 dict(또는 스칼라 종가) 둘 다 받으므로, 트리·평가기 변경 없이 tf="1m" 로 읽힌다.

정직한 한계(가짜로 안 채운다):
  · yfinance 1분봉은 최근 ~7일(실측 ~5거래일)만 준다. 그 밖 기간은 받을 수 없다.
  · 실패·빈 결과·네트워크 불가 → {} (→ 평가기에서 '모름' → 장중 observe 는 manual 🟡 로 정직하게 떨어진다).
"""
import sys

try:
    import yfinance as yf          # TEMP import — 여기 말고 어디서도 import 금지
    _AVAILABLE = True
except Exception:  # noqa: BLE001
    yf = None
    _AVAILABLE = False

# yfinance 1분봉 보관 한계(야후 정책): 최근 7일. period 로 그 범위를 당긴다.
_PERIOD = "7d"
_INTERVAL = "1m"


def minutes(symbol):
    """심볼의 최근 1분봉 OHLCV {YYYYMMDDHHMM(UTC): {open,high,low,close,volume}}.
    실패·빈결과·미설치·네트워크불가 → {} (가짜로 안 채운다 — 평가기에서 '모름' 으로 정직하게 떨어진다).
    한계: yfinance 1분봉은 최근 ~7일만. 그 밖 기간은 당길 수 없다(그 부분은 비어 있는 게 정직하다)."""
    if not _AVAILABLE:
        return {}
    try:
        df = yf.download(symbol, period=_PERIOD, interval=_INTERVAL,
                         progress=False, auto_adjust=False, threads=False)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write("_temp_yf_minutes(%s) 조회 예외 — %s: %s\n" % (symbol, type(e).__name__, e))
        return {}
    if df is None or len(df) == 0:
        return {}
    # 단일 심볼 요청도 yfinance 가 MultiIndex 컬럼(('Close','SPY'))으로 줄 수 있다 — 상위 레벨만 남긴다.
    cols = df.columns
    if getattr(cols, "nlevels", 1) > 1:
        df = df.copy()
        df.columns = [c[0] for c in cols]
    import datetime as _dt
    out = {}
    for ts, row in df.iterrows():
        # ts 가 tz-naive 면 UTC 로 가정, tz-aware 면 UTC 로 변환(야후는 보통 거래소 현지 tz).
        when = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
        if when.tzinfo is None:
            when = when.replace(tzinfo=_dt.timezone.utc)
        key = when.astimezone(_dt.timezone.utc).strftime("%Y%m%d%H%M")
        bar = {}
        for src, dst in (("Open", "open"), ("High", "high"), ("Low", "low"),
                         ("Close", "close"), ("Volume", "volume")):
            v = row.get(src)
            try:
                bar[dst] = None if v is None else float(v)
            except (TypeError, ValueError):
                bar[dst] = None
        # close 조차 못 읽으면 그 분봉은 버린다(빈 봉을 넣어 '모름'을 오염시키지 않는다).
        if bar.get("close") is not None:
            out[key] = bar
    return out


if __name__ == "__main__":
    for s in sys.argv[1:] or ["SPY", "ES=F"]:
        m = minutes(s)
        ks = sorted(m)
        print("%s: 분봉 %d개 (UTC 키)" % (s, len(m)))
        for k in ks[-3:]:
            print("   %s UTC -> %r" % (k, m[k]))
