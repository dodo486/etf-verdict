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
  volume_ratio   거래량 / 기준거래량 배수               {symbol, base?=1(전일), min?}
                 base=1(기본)이면 전일 대비, 2 이상이면 그 기간 평균 대비.
                 저자 7-4 "오늘 거래량이 전일보다 1.5배 이상 늘었는지" — 기본이 전일 대비인 이유.
  ma_distance    종가와 N일선의 이격도(%)               {symbol, ma?=5}
  gap_up         당일 시가의 전일종가 대비 갭(%)         {symbol}
  upper_wick     윗꼬리 %(고점 대비 종가 하락폭)         {symbol}
  higher_low     첫 눌림 저점 높임 여부(장중 분봉)        {symbol}
  count_up       여러 심볼 중 상승 개수                  {symbols:[...], min?}
  hold_above_ma  N일선 회복 후 며칠 더 지켰나            {symbol, ma, days?=2, }
                 저자 3-2·5-2 "회복 후 그다음 2거래일 동안 다시 안 깸". days=회복일 다음
                 추가로 지켜야 할 거래일 수(총 need = days+1).
  count_above_ma 여러 심볼 중 N일선 위 개수              {symbols:[...], ma?=20, min?}
                 저자 5-1 "섹터 ETF 흐름을 5개만 같이 보십시오… 3개 이상이 플러스".
  count_up_days  최근 N거래일 중 상승일 개수             {symbol, n?=10, min?}
                 저자 2-3 "최근 10거래일 중 반도체 지수가 7일 이상 올랐다면".
  defensive_only 방어(XLP·XLU·XLV) 강세 + 경기민감(XLK·XLF·XLI) 약세 동시(5일)  {}
                 저자 5-3 "방어주만 살아나고 경기민감(기술·금융·산업재) 약화".
  bad_rate_drop  나쁜 금리 하락(10년물↓ + S&P500 못오름 + XLF 5일 약세) 동시    {}
                 저자 5-3 "금리↓인데 주식 못 오르고 금융주 약함".
  earnings_dday  심볼들의 다음 실적 발표일까지 D-day     {symbols:[...], min?}
                 저자 3-5 "빅테크 실적 발표 임박". 나스닥 공개 캘린더(market_extras.py
                 재사용, NasdaqEarningsAdapter). 저자가 D-n 임계를 명시하지 않아
                 min 없으면 ok=None(수치만 노출).

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


def _n_day_pct(closes, n):
    """최근 n거래일 수익률(%). 데이터 부족하면 None."""
    if len(closes) < n + 1:
        return None
    return _pct(closes[-1], closes[-(n + 1)])


# ----------------------------------------------------------------------------
# YahooAdapter — 무료 EOD/일봉 (미국주식/지수/VIX/금리/달러)
# ----------------------------------------------------------------------------
class YahooAdapter:
    """야후 파이낸스 chart API(무인증). EOD·일봉 기반 metric 담당."""

    source = "yahoo"
    CADENCE = "eod"
    HANDLES = {"above_ma", "pct_change", "n_day_return", "volume_ratio",
               "upper_wick", "count_up", "ma_distance", "gap_up",
               "hold_above_ma", "count_above_ma", "defensive_only", "bad_rate_drop",
               "count_up_days"}

    # 저자 5-3 매핑: 경기민감(기술·금융·산업재) vs 방어(필수소비재·유틸리티·헬스케어)
    CYCLICAL_ETF = ["XLK", "XLF", "XLI"]
    DEFENSIVE_ETF = ["XLP", "XLU", "XLV"]

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
        opens = [o for o in q0.get("open", []) if o is not None]
        return {"close": closes, "high": highs, "vol": vols, "open": opens,
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
                    "opens": d.get("open", []),
                    "high": d["high"][-1] if d["high"] else None,
                    "vol": d["vol"][-1] if d["vol"] else None,
                    "open": d["open"][-1] if d.get("open") else None,
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
        if t == "count_above_ma":
            return self._count_above_ma(m)
        if t == "defensive_only":
            return self._defensive_only(m)
        if t == "bad_rate_drop":
            return self._bad_rate_drop(m)
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
        if t == "ma_distance":
            return self._ma_distance(m, s)
        if t == "gap_up":
            return self._gap_up(m, s)
        if t == "hold_above_ma":
            return self._hold_above_ma(m, s)
        if t == "count_up_days":
            return self._count_up_days(m, s)
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

    def _ma_distance(self, m, s):
        """종가가 N일선에서 얼마나 벌어졌나(%). 저자 2-7 "5일선과 얼마나 벌어졌는지".

        저자가 임계 %를 명시하지 않았으므로 min 이 없으면 ok=None(수치만 노출).
        """
        n = int(m.get("ma", 5))
        mv = _ma(s["closes"], n)
        if mv is None:
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": f"{n}일 데이터 부족", "label": f"{m['symbol']} MA{n} 없음"}
        dist = _pct(s["close"], mv)
        thr = m.get("min")
        ok = None if thr is None else (dist >= float(thr))
        return {"status": "ok", "source": self.source, "ok": ok, "value": dist,
                "label": f"{m['symbol']} 종가 {s['close']:.2f} / {n}일선 {mv:.2f} · 이격 {dist:+.1f}%"}

    def _gap_up(self, m, s):
        """당일 시가가 전일 종가 대비 얼마나 떴나(%). 저자 7-3 "갭상승 날".

        저자가 갭 몇 %부터인지 명시하지 않았으므로 min 없으면 ok=None.
        """
        o, prev = s.get("open"), s.get("prev")
        if not (o and prev):
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": "시가/전일종가 없음", "label": f"{m['symbol']} 갭 계산 불가"}
        gap = _pct(o, prev)
        thr = m.get("min")
        ok = None if thr is None else (gap >= float(thr))
        return {"status": "ok", "source": self.source, "ok": ok, "value": gap,
                "label": f"{m['symbol']} 시가 {o:.2f} / 전일종가 {prev:.2f} · 갭 {gap:+.1f}%"}

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
        """거래량 배수. base=1(기본)이면 전일 대비, 2 이상이면 그 기간 평균 대비.

        저자 7-4 "오늘 거래량이 전일보다 1.5배 이상 늘었는지"(같은 소절에 두 번 나옴) —
        20일 평균은 원문 어디에도 없다. 그래서 기본값을 전일 대비(base=1)로 둔다.
        `ref`는 옛 필드명 호환용으로만 남긴다(신규 항목은 `base`를 쓴다).
        """
        vols = s["vols"]
        base = int(m.get("base", m.get("ref", 1)))
        if base <= 1:
            denom = vols[-2] if len(vols) >= 2 else None
            base_txt = "전일"
        else:
            denom = _ma(vols[:-1], base) if len(vols) >= base + 1 else None
            base_txt = f"{base}일평균"
        if not (s.get("vol") and denom):
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": "거래량 데이터 부족", "label": f"{m['symbol']} 거래량 없음"}
        ratio = s["vol"] / denom
        thr = m.get("min")
        ok = None if thr is None else (ratio >= float(thr))

        def mil(v):
            return f"{v/1e6:.1f}M" if v else "–"
        return {"status": "ok", "source": self.source, "ok": ok, "value": ratio,
                "label": f"{m['symbol']} 거래량 {mil(s['vol'])}/{base_txt} {mil(denom)} ({ratio:.2f}배)"}

    def _hold_above_ma(self, m, s):
        """N일선을 회복한 뒤 며칠을 더 지켰나(연속). 저자 3-2·5-2
        "20일선 위로 회복 + 그다음 2거래일 동안 20일선을 다시 깨지 않는 것".

        need = days(추가 거래일) + 1(회복일 자체). 종가 기준으로 오늘부터 거꾸로 센다
        (etf_daily_verdict.py의 hold_above_ma()/HOLD_NEED 로직과 동일).
        """
        n = int(m.get("ma", 20))
        days = int(m.get("days", 2))
        need = days + 1
        closes = s["closes"]
        cnt = 0
        look = need + 20
        for k in range(look):
            i = len(closes) - 1 - k
            if i < n - 1:
                break
            mv = sum(closes[i - n + 1:i + 1]) / n
            if closes[i] > mv:
                cnt += 1
            else:
                break
        ok = cnt >= need
        return {"status": "ok", "source": self.source, "ok": bool(ok), "value": cnt,
                "label": f"{m['symbol']} {n}일선 위 {cnt}거래일 연속 "
                         f"(회복일+{days}거래일={need} 필요)"}

    def _count_up_days(self, m, s):
        """최근 n거래일 중 상승일(전일比 플러스) 개수. 저자 2-3
        "최근 10거래일 중 반도체 지수가 7일 이상 올랐다면" — etf_daily_verdict.py
        up_days() 와 같은 정의(당일 포함 최근 n개 캔들 중 전일 대비 상승한 날 수)."""
        n = int(m.get("n", 10))
        closes = s["closes"][-(n + 1):]
        if len(closes) < 2:
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": f"{n}일 데이터 부족", "label": f"{m['symbol']} 상승일수 없음"}
        up = sum(1 for i in range(1, len(closes)) if closes[i] > closes[i - 1])
        thr = m.get("min")
        ok = None if thr is None else (up >= int(thr))
        return {"status": "ok", "source": self.source, "ok": ok, "value": up,
                "label": f"{m['symbol']} 최근 {n}거래일 중 {up}일 상승"}

    def _count_above_ma(self, m):
        """여러 심볼 중 N일선 위 개수. 저자 5-1 섹터 폭(기술·금융·산업재·헬스케어·소비재)."""
        syms = m.get("symbols", [])
        n = int(m.get("ma", 20))
        parts = []
        above = 0
        n_ok = 0
        for sym in syms:
            s = self._series(sym)
            if "error" in s:
                parts.append(f"{sym} 실패")
                continue
            mv = _ma(s["closes"], n)
            if mv is None:
                parts.append(f"{sym} {n}일 데이터 부족")
                continue
            n_ok += 1
            up = s["close"] > mv
            if up:
                above += 1
            parts.append(f"{sym} {'위' if up else '아래'}")
        if n_ok == 0:
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": "전 심볼 조회 실패", "label": "count_above_ma 실패"}
        thr = m.get("min")
        ok = None if thr is None else (above >= int(thr))
        return {"status": "ok", "source": self.source, "ok": ok, "value": above,
                "label": f"{above}/{len(syms)} {n}일선 위 · " + ", ".join(parts)}

    def _defensive_only(self, m):
        """방어(XLP·XLU·XLV) 5일 수익률 평균 > 0 AND 경기민감(XLK·XLF·XLI) 평균 < 0.

        저자 5-3 "방어주만 살아나고 경기민감(기술·금융·산업재) 약화"."""
        cyc = [_n_day_pct(self._series(sym).get("closes", []), 5)
               if "error" not in self._series(sym) else None
               for sym in self.CYCLICAL_ETF]
        dfn = [_n_day_pct(self._series(sym).get("closes", []), 5)
               if "error" not in self._series(sym) else None
               for sym in self.DEFENSIVE_ETF]
        if any(v is None for v in cyc + dfn):
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": "섹터 ETF 조회 실패", "label": "방어주 판정 불가"}
        c = sum(cyc) / len(cyc)
        d = sum(dfn) / len(dfn)
        flag = (d > 0) and (c < 0)
        return {"status": "ok", "source": self.source, "ok": bool(flag), "value": d - c,
                "label": "경기민감(XLK·XLF·XLI) 5일 %+.1f%% / 방어(XLP·XLU·XLV) 5일 %+.1f%%"
                         % (c, d)}

    def _bad_rate_drop(self, m):
        """나쁜 금리 하락 — 10년물↓ + S&P500 못오름 + 금융주(XLF) 5일 약세 동시.

        저자 5-3 "금리↓인데 주식 못 오르고 금융주 약함". etf_daily_verdict.py
        _bad_rate_drop() 과 같은 정의."""
        tnx = self._series("^TNX")
        gspc = self._series("^GSPC")
        xlf = self._series("XLF")
        if "error" in tnx or "error" in gspc or "error" in xlf:
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": "금리/지수/금융주 조회 실패", "label": "나쁜 금리 하락 판정 불가"}
        rate_chg = tnx["close"] - tnx["prev"]
        spx_chg = _pct(gspc["close"], gspc["prev"])
        fin5 = _n_day_pct(xlf["closes"], 5)
        if spx_chg is None or fin5 is None:
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": "데이터 부족", "label": "나쁜 금리 하락 판정 불가"}
        flag = (rate_chg < 0) and (spx_chg <= 0) and (fin5 < 0)
        return {"status": "ok", "source": self.source, "ok": bool(flag), "value": rate_chg,
                "label": "^TNX %+.2f%%p · S&P500 %+.1f%% · XLF 5일 %+.1f%%"
                         % (rate_chg, spx_chg, fin5)}

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
    HANDLES = {"above_open", "higher_low", "gap_up"}

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
        if t == "gap_up":
            return self._gap_up(m)
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

    def _gap_up(self, m):
        """장중 갭 — 당일 시가 vs 전일 종가(base). 저자 7-3."""
        sym = m.get("symbol", "")
        o = self._price(sym)
        if not o or o.get("error") or not o.get("open") or not o.get("base"):
            reason = (o or {}).get("error") or "빈 응답(no data)"
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": reason, "label": f"{sym} 갭 조회 실패"}
        gap = (o["open"] - o["base"]) / o["base"] * 100
        thr = m.get("min")
        ok = None if thr is None else (gap >= float(thr))
        lbl = f"{sym} 시가 {o['open']:.2f} / 전일종가 {o['base']:.2f} · 갭 {gap:+.1f}%"
        if o.get("last"):
            hold = (o["last"] - o["open"]) / o["open"] * 100
            lbl += f" · 현재가 시가比 {hold:+.1f}%"
        return {"status": "ok", "source": self.source, "ok": ok, "value": gap, "label": lbl}

    def _higher_low(self, m):
        sym = m.get("symbol", "")
        hl = self._mod.higher_low(sym)
        if hl.get("error"):
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": hl["error"], "label": f"{sym} 분봉: {hl['error']}"}
        return {"status": "ok", "source": self.source, "ok": bool(hl["ok"]),
                "label": f"{sym} {hl['label']}"}


# ----------------------------------------------------------------------------
# NasdaqEarningsAdapter — 나스닥 공개 실적 캘린더(market_extras.py 재사용)
# ----------------------------------------------------------------------------
class NasdaqEarningsAdapter:
    """빅테크 다음 실적 발표일 D-day. 저자 3-5 "빅테크 실적 발표 임박".

    market_extras.py(이미 이 리포에 있는 무료 나스닥 캘린더 수집기)를 그대로
    재사용한다 — 새로 만들지 않는다. 실패(네트워크·모듈 없음)하면 error 로
    정직하게 남긴다."""

    source = "nasdaq"
    CADENCE = "eod"
    HANDLES = {"earnings_dday"}

    def capabilities(self):
        return set(self.HANDLES)

    def fetch(self, spec):
        m = spec.get("metric", {})
        if m.get("type") != "earnings_dday":
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": f"미지원 metric.type={m.get('type')}", "label": "?"}
        try:
            import market_extras  # noqa: PLC0415
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": f"market_extras 로드 실패: {e}", "label": "실적 캘린더 불가"}
        syms = m.get("symbols", [])
        try:
            dd = market_extras.earnings_dday(syms)
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "source": self.source, "ok": None,
                    "reason": f"실적 캘린더 조회 실패: {e}", "label": "실적 캘린더 실패"}
        if not dd:
            return {"status": "ok", "source": self.source, "ok": None, "value": None,
                    "label": "조회 범위 내 예정 실적 없음"}
        near = sorted(dd.items(), key=lambda kv: kv[1][1])
        _s0, (_dt0, d0) = near[0]
        thr = m.get("min")  # 저자가 D-n 임계를 명시하지 않아 min 없으면 ok=None
        ok = None if thr is None else (d0 <= int(thr))
        label = " · ".join(f"{s} {dt}(D-{d})" for s, (dt, d) in near[:3])
        return {"status": "ok", "source": self.source, "ok": ok, "value": d0, "label": label}


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
_NASDAQ = NasdaqEarningsAdapter()
_MANUAL = ManualAdapter()

# 우선순위: 자동 소스 먼저(야후 EOD → KIS 장중 → 나스닥 캘린더), 마지막은 항상 manual 폴백.
ADAPTERS = [_YAHOO, _KIS, _NASDAQ, _MANUAL]


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
