#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""데이터 소스 어댑터 레이어 (book-to-playbook 자동판정 프레임워크)

통일 인터페이스로 시세 데이터 소스를 추상화한다. 각 어댑터는
  - capabilities()  → 처리 가능한 metric.type 집합
  - fetch(spec)     → 그 metric 값을 계산해 표준 결과 dict 반환
을 갖는다.

metric.type 카탈로그 (spec["metric"]["type"]):
  above_ma       심볼 종가가 N일 이동평균 위인가       {symbol, ma}
  above_open     심볼 현재가가 당일 시가 위인가(장중)   {symbol}
  pct_change     전일 대비 등락률(%)                    {symbol}
  n_day_return   최근 N일 수익률(%)                     {symbol, n}
  volume_ratio   거래량 / N일평균거래량 배수            {symbol, ref?=20}
  upper_wick     윗꼬리 %(고점 대비 종가 하락폭)         {symbol}
  higher_low     첫 눌림 저점 높임 여부(장중 분봉)        {symbol}
  count_up       여러 심볼 중 상승 개수                  {symbols:[...], min?}

반환 결과 dict (fetch)의 공통 키:
  ok      bool|None   판정 통과 여부(임계값 있으면), 없으면 None
  value   number|str  대표 수치(있으면)
  label   str         사람이 읽는 한 줄(수치 포함)
  status  str         "ok" | "error" | "manual"
  source  str         어댑터 식별자("yahoo"/"kis"/"manual")
  reason  str         status!=ok 일 때 사유(선택)

TLS 검증은 항상 켠 상태로 유지한다(ssl.CERT_NONE 금지). 시크릿 값은 출력하지 않는다.
"""
import json
import ssl
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0"}
# TLS 인증서 정상 검증(기본 컨텍스트). ssl.CERT_NONE 사용 금지.
_CTX = ssl.create_default_context()


# ----------------------------------------------------------------------------
# 공통 계산 유틸 (etf_daily_verdict.py 로직을 여기로 추출·재사용)
# ----------------------------------------------------------------------------
def _ma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None


def _pct(a, b):
    return (a - b) / b * 100 if (a is not None and b) else None


# ----------------------------------------------------------------------------
# YahooAdapter — 무료 EOD/일봉 (미국주식/지수/VIX/금리/달러)
# ----------------------------------------------------------------------------
class YahooAdapter:
    """야후 파이낸스 chart API(무인증). EOD·일봉 기반 metric 담당."""

    source = "yahoo"
    CADENCE = "eod"
    HANDLES = {"above_ma", "pct_change", "n_day_return", "volume_ratio",
               "upper_wick", "count_up"}

    def __init__(self):
        self._cache = {}  # symbol -> parsed series (per-process)

    def capabilities(self):
        return set(self.HANDLES)

    # --- 원천 데이터 ---
    def _fetch_raw(self, symbol, rng="3mo", interval="1d"):
        q = urllib.parse.quote(symbol)
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{q}"
               f"?range={rng}&interval={interval}")
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=20, context=_CTX) as r:
            data = json.load(r)
        res = data["chart"]["result"][0]
        q0 = res["indicators"]["quote"][0]
        closes = [c for c in q0.get("close", []) if c is not None]
        highs = [h for h in q0.get("high", []) if h is not None]
        vols = [v for v in q0.get("volume", []) if v is not None]
        return {"close": closes, "high": highs, "vol": vols,
                "meta": res.get("meta", {})}

    def _series(self, symbol):
        """심볼 시계열을 캐시 경유로 로드. 실패 시 {"error":...}."""
        if symbol in self._cache:
            return self._cache[symbol]
        try:
            d = self._fetch_raw(symbol)
            c = d["close"]
            if len(c) < 2:
                out = {"error": "시세 데이터 부족"}
            else:
                out = {
                    "sym": symbol, "close": c[-1], "prev": c[-2],
                    "closes": c, "highs": d["high"], "vols": d["vol"],
                    "high": d["high"][-1] if d["high"] else None,
                    "vol": d["vol"][-1] if d["vol"] else None,
                }
        except Exception as e:  # noqa: BLE001
            out = {"error": str(e)}
        self._cache[symbol] = out
        return out

    # --- metric 계산 ---
    def fetch(self, spec):
        m = spec.get("metric", {})
        t = m.get("type")
        if t == "count_up":
            return self._count_up(m)
        s = self._series(m.get("symbol", ""))
        if "error" in s:
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": s["error"], "label": f"{m.get('symbol')} 조회 실패"}
        if t == "above_ma":
            return self._above_ma(m, s)
        if t == "pct_change":
            return self._pct_change(m, s)
        if t == "n_day_return":
            return self._n_day_return(m, s)
        if t == "volume_ratio":
            return self._volume_ratio(m, s)
        if t == "upper_wick":
            return self._upper_wick(m, s)
        return {"status": "error", "source": self.source, "ok": None,
                "reason": f"미지원 metric.type={t}", "label": t or "?"}

    def _above_ma(self, m, s):
        n = int(m.get("ma", 20))
        mv = _ma(s["closes"], n)
        if mv is None:
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": f"{n}일 데이터 부족", "label": f"{m['symbol']} MA{n} 없음"}
        gap = _pct(s["close"], mv)
        ok = s["close"] > mv
        return {"status": "ok", "source": self.source, "ok": bool(ok),
                "value": s["close"],
                "label": f"{m['symbol']} {s['close']:.2f}/{n}일선 {mv:.2f} ({gap:+.1f}%)"}

    def _pct_change(self, m, s):
        chg = _pct(s["close"], s["prev"])
        if chg is None:
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": "등락률 계산 불가", "label": f"{m['symbol']} –"}
        thr = m.get("min")
        ok = None if thr is None else (chg > float(thr))
        return {"status": "ok", "source": self.source, "ok": ok, "value": chg,
                "label": f"{m['symbol']} 전일比 {chg:+.1f}%"}

    def _n_day_return(self, m, s):
        n = int(m.get("n", 5))
        c = s["closes"]
        if len(c) < n + 1:
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": f"{n}일 데이터 부족", "label": f"{m['symbol']} {n}일수익률 없음"}
        ret = _pct(c[-1], c[-(n + 1)])
        thr = m.get("min")
        ok = None if thr is None else (ret >= float(thr))
        return {"status": "ok", "source": self.source, "ok": ok, "value": ret,
                "label": f"{m['symbol']} 최근 {n}일 {ret:+.1f}%"}

    def _volume_ratio(self, m, s):
        ref = int(m.get("ref", 20))
        vols = s["vols"]
        avg = _ma(vols, ref) if len(vols) >= ref else None
        if not (s.get("vol") and avg):
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": "거래량 데이터 부족", "label": f"{m['symbol']} 거래량 없음"}
        ratio = s["vol"] / avg
        thr = m.get("min")
        ok = None if thr is None else (ratio >= float(thr))

        def mil(v):
            return f"{v/1e6:.1f}M" if v else "–"
        return {"status": "ok", "source": self.source, "ok": ok, "value": ratio,
                "label": f"{m['symbol']} 거래량 {mil(s['vol'])}/{ref}일평균 {mil(avg)} ({ratio:.2f}배)"}

    def _upper_wick(self, m, s):
        hi, cl = s.get("high"), s.get("close")
        if not (hi and cl):
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": "고가/종가 없음", "label": f"{m['symbol']} 윗꼬리 없음"}
        wick = (hi - cl) / hi * 100
        thr = m.get("min")
        ok = None if thr is None else (wick >= float(thr))
        return {"status": "ok", "source": self.source, "ok": ok, "value": wick,
                "label": f"{m['symbol']} 고점 대비 종가 {-wick:+.1f}%"}

    def _count_up(self, m):
        syms = m.get("symbols", [])
        parts = []
        up = 0
        n_ok = 0
        for sym in syms:
            s = self._series(sym)
            if "error" in s:
                parts.append(f"{sym} 실패")
                continue
            chg = _pct(s["close"], s["prev"])
            n_ok += 1
            if chg is not None and chg > 0:
                up += 1
            parts.append(f"{sym} {chg:+.1f}%" if chg is not None else f"{sym} –")
        if n_ok == 0:
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": "전 심볼 조회 실패", "label": "count_up 실패"}
        thr = m.get("min")
        ok = None if thr is None else (up >= int(thr))
        return {"status": "ok", "source": self.source, "ok": ok, "value": up,
                "label": f"{up}/{len(syms)}↑ · " + ", ".join(parts)}


# ----------------------------------------------------------------------------
# KisAdapter — KIS 실시간(장중) 미국주식
# ----------------------------------------------------------------------------
class KisAdapter:
    """한국투자증권 Open API. 장중(현재가/시가/고저/분봉/첫눌림) metric 담당.
    kis_intraday.py 를 import 재사용. kis.env 키 없으면 자동 skip(manual 폴백은 레지스트리가 처리)."""

    source = "kis"
    CADENCE = "intraday"
    HANDLES = {"above_open", "higher_low"}

    def __init__(self):
        self._mod = None
        self._enabled = None
        self._snap = {}  # symbol -> price dict cache

    def _load(self):
        if self._enabled is not None:
            return self._enabled
        try:
            import kis_intraday  # noqa: PLC0415
            self._mod = kis_intraday
            self._enabled = bool(kis_intraday.APP_KEY and kis_intraday.APP_SECRET)
        except Exception:  # noqa: BLE001
            self._mod = None
            self._enabled = False
        return self._enabled

    def capabilities(self):
        # 키가 없으면 아무 것도 처리 못함 → 빈 집합(레지스트리가 manual로 폴백)
        return set(self.HANDLES) if self._load() else set()

    def _price(self, symbol):
        if symbol in self._snap:
            return self._snap[symbol]
        o = self._mod.overseas_price(symbol)
        self._snap[symbol] = o
        return o

    def fetch(self, spec):
        if not self._load():
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": "KIS 키 없음(kis.env)", "label": "장중 데이터 없음"}
        m = spec.get("metric", {})
        t = m.get("type")
        if t == "above_open":
            return self._above_open(m)
        if t == "higher_low":
            return self._higher_low(m)
        return {"status": "error", "source": self.source, "ok": None,
                "reason": f"미지원 metric.type={t}", "label": t or "?"}

    def _above_open(self, m):
        sym = m.get("symbol", "")
        o = self._price(sym)
        if not o or o.get("error") or not o.get("last") or not o.get("open"):
            reason = (o or {}).get("error") or "빈 응답(no data)"
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": reason, "label": f"{sym} 장중 조회 실패"}
        opct = (o["last"] - o["open"]) / o["open"] * 100
        bpct = None
        if o.get("base"):
            bpct = (o["last"] - o["base"]) / o["base"] * 100
        lbl = f"{sym} 현재 {o['last']:.2f} / 시가 {o['open']:.2f} (시가比 {opct:+.1f}%)"
        if bpct is not None:
            lbl += f" · 전일比 {bpct:+.1f}%"
        return {"status": "ok", "source": self.source, "ok": opct > 0,
                "value": opct, "label": lbl}

    def _higher_low(self, m):
        sym = m.get("symbol", "")
        hl = self._mod.higher_low(sym)
        if hl.get("error"):
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": hl["error"], "label": f"{sym} 분봉: {hl['error']}"}
        return {"status": "ok", "source": self.source, "ok": bool(hl["ok"]),
                "label": f"{sym} {hl['label']}"}


# ----------------------------------------------------------------------------
# ManualAdapter — 폴백. 무료 데이터로 커버 안 되는 항목은 정직하게 "수동".
# ----------------------------------------------------------------------------
class ManualAdapter:
    source = "manual"
    CADENCE = "manual"

    def capabilities(self):
        return set()  # 어떤 metric도 자동 처리하지 않음(항상 폴백 대상)

    def fetch(self, spec):
        reason = spec.get("reason") or "무료 데이터 없음 — 직접 확인"
        return {"status": "manual", "source": self.source, "ok": None,
                "label": reason, "reason": reason}


# ----------------------------------------------------------------------------
# 레지스트리 + resolve
# ----------------------------------------------------------------------------
_YAHOO = YahooAdapter()
_KIS = KisAdapter()
_MANUAL = ManualAdapter()

# 우선순위: 자동 소스 먼저(야후 EOD → KIS 장중), 마지막은 항상 manual 폴백.
ADAPTERS = [_YAHOO, _KIS, _MANUAL]


def resolve(metric_spec):
    """metric_spec(= data_spec item의 metric dict)을 처리 가능한 첫 어댑터 반환.
    없으면 ManualAdapter. source=="manual"로 강제된 항목도 ManualAdapter."""
    if not isinstance(metric_spec, dict):
        return _MANUAL
    t = metric_spec.get("type")
    for a in ADAPTERS:
        if t in a.capabilities():
            return a
    return _MANUAL


def cadence_of(adapter, spec):
    """항목 cadence 추론: spec에 명시되면 그대로, 없으면 어댑터 기본."""
    return spec.get("cadence") or getattr(adapter, "CADENCE", "manual")
