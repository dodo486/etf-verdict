#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""책-무관 지표 계산기 (구간③ 선언 → 값).

엔진이 종목·규칙을 if 문으로 손코딩하는 대신, 이 파일 하나가
data_spec 의 metric 선언 `{type, symbol, ...params}` 을 받아 md_feed 데이터로 평가한다.
어떤 책이든 metric type 만 등록돼 있으면 판정이 나온다 — 책별 엔진이 필요 없다.

무거운 계산(MA·N일수익률·연속유지·거래량평균)은 이미 md_feed.series() 가 해 둔다
(book-agnostic). 여기서는 그 필드를 골라 임계와 비교하고 값을 만든다.

각 계산기 → dict:
  {"value": <수치>, "pass": <bool|None>, "text": "<사람이 읽을 근거>"}
  pass=None 은 '데이터 없음/자동 불가'(계산 못 함 — 통과로 치지 않는다).

이 모듈은 라이브 엔진을 아직 대체하지 않는다. verdict_engine.py 가 이 값들을 읽어 판정을 만든다.
"""
from verdict import md_feed

# ------------------------------------------------------------------ 데이터 접근
# 심볼 종류에 따라 데이터 출처가 다르다(엔진의 SERIES/FUTURES/INDEX 분기를 여기 하나로 흡수).
#   · 일봉 지표(MA·거래량·연속)가 필요하면 series()
#   · 방향(chg)만 있으면 되는 선물/지수 스냅샷은 series 가 비므로 스냅샷으로 폴백
_SERIES_CACHE = {}
_SNAP_CACHE = {}


def _series(sym):
    if sym not in _SERIES_CACHE:
        try:
            _SERIES_CACHE[sym] = md_feed.series(sym)
        except Exception:
            _SERIES_CACHE[sym] = None
    return _SERIES_CACHE[sym]


def _snap(sym):
    """chg/close/prev 만 필요한 심볼(선물·^VIX·^TNX·달러)용 스냅샷."""
    if sym in _SNAP_CACHE:
        return _SNAP_CACHE[sym]
    snap = None
    try:
        if sym.endswith("=F"):
            snap = (md_feed.quote_snapshot([sym]) or {}).get(sym)
        else:
            snap = md_feed.index_snapshot(sym)
    except Exception:
        snap = None
    _SNAP_CACHE[sym] = snap
    return snap


def _ok(d):
    return bool(d) and "error" not in d


def _dir(sym):
    """방향(chg,close,prev) — series 가 있으면 거기서, 없으면 스냅샷."""
    d = _series(sym)
    if _ok(d) and d.get("chg") is not None:
        return {"chg": d["chg"], "close": d.get("close"), "prev": d.get("prev")}
    s = _snap(sym)
    if s and s.get("price") is not None:
        return {"chg": s.get("chg"), "close": s.get("price"), "prev": s.get("prev")}
    return None


def clear_cache():
    _SERIES_CACHE.clear()
    _SNAP_CACHE.clear()


# ------------------------------------------------------------------ 계산기들
# 규칙: 임계는 metric 선언에서 읽는다(코드에 숫자 안 박음). min 이 있으면 value>=min 이 pass.
def _pass_min(value, m):
    mn = m.get("min")
    if value is None:
        return None
    if mn is None:
        return None            # 임계 없는 관찰용(값만 노출, 판정은 사람/상위)
    return value >= mn


def pct_change(m):
    sym = m["symbol"]
    d = _dir(sym)
    if not d or d.get("chg") is None:
        return {"value": None, "pass": None, "text": "%s 수집 실패" % sym}
    v = d["chg"]
    return {"value": v, "pass": _pass_min(v, m),
            "text": "%s %+.2f%%" % (sym, v)}


def point_change(m):
    """전일 대비 절대 포인트 변화(close-prev). ^TNX 처럼 값 자체가 %인 지표의 %p 변화용.
    (pct_change 는 상대 %라 금리 %p 판정엔 못 쓴다 — 엔진 tnx_jump 공식과 동일하게 절대차.)"""
    sym = m["symbol"]
    d = _dir(sym)
    if not d or d.get("close") is None or d.get("prev") is None:
        return {"value": None, "pass": None, "text": "%s 수집 실패" % sym}
    v = d["close"] - d["prev"]
    return {"value": v, "pass": _pass_min(v, m),
            "text": "%s %.2f (전일 %.2f, %+.2f%%p)" % (sym, d["close"], d["prev"], v)}


def dxy_change(m):
    """달러인덱스 등락률 — pct_change 와 같은 계산이되, 심볼이 불안정해 fallback 을 순서대로 시도.
    (엔진: DX-Y.NYB 실패 시 DX=F). 첫 성공 심볼의 값을 쓴다."""
    syms = [m.get("symbol")] + list(m.get("fallback") or [])
    for sym in syms:
        if not sym:
            continue
        d = _dir(sym)
        if d and d.get("chg") is not None:
            mm = dict(m)
            mm["symbol"] = sym
            return pct_change(mm)
    return {"value": None, "pass": None, "text": "달러인덱스 수집 실패(심볼 불안정)"}


def _num(d, k):
    return d.get(k) if _ok(d) else None


def above_ma(m):
    sym, ma = m["symbol"], m.get("ma", 20)
    d = _series(sym)
    close, mav = _num(d, "close"), _num(d, "ma%d" % ma)
    if close is None or mav is None:
        return {"value": None, "pass": None, "text": "%s MA%d 데이터 없음" % (sym, ma)}
    gap = (close - mav) / mav * 100
    return {"value": gap, "pass": close > mav,
            "text": "%s %.2f / %d일선 %.2f (%+.1f%%)" % (sym, close, ma, mav, gap)}


def hold_above_ma(m):
    """20일선 위 연속 거래일수 (md_feed 가 hold20 로 미리 세어 둠). days 이상이면 pass."""
    sym, ma, days = m["symbol"], m.get("ma", 20), m.get("days", 2)
    d = _series(sym)
    if not _ok(d):
        return {"value": None, "pass": None, "text": "%s 데이터 없음" % sym}
    hold = d.get("hold%d" % ma)
    if hold is None:
        return {"value": None, "pass": None, "text": "%s %d일선 연속 미제공" % (sym, ma)}
    need = days + 1            # 회복일 + days 유지 = 총 연속일
    return {"value": hold, "pass": hold >= need,
            "text": "%s %d일선 위 %d거래일 연속 (기준 %d)" % (sym, ma, hold, need)}


def n_day_return(m):
    sym, n = m["symbol"], m.get("n", 5)
    d = _series(sym)
    if not _ok(d):
        return {"value": None, "pass": None, "text": "%s 데이터 없음" % sym}
    if n == 5 and d.get("ret5") is not None:
        v = d["ret5"]
    else:
        closes = d.get("closes") or []
        if len(closes) <= n or not closes[-1 - n]:
            return {"value": None, "pass": None, "text": "%s %d일 데이터 부족" % (sym, n)}
        v = (closes[-1] - closes[-1 - n]) / closes[-1 - n] * 100
    return {"value": v, "pass": _pass_min(v, m), "text": "최근 %d일 %+.1f%%" % (n, v)}


def ma_distance(m):
    sym, ma = m["symbol"], m.get("ma", 5)
    d = _series(sym)
    close, mav = _num(d, "close"), _num(d, "ma%d" % ma)
    if close is None or mav is None:
        return {"value": None, "pass": None, "text": "%s %d일선 데이터 없음" % (sym, ma)}
    gap = (close - mav) / mav * 100
    return {"value": gap, "pass": _pass_min(gap, m),
            "text": "%d일선 %.2f 대비 이격 %+.1f%%" % (ma, mav, gap)}


def upper_wick(m):
    """윗꼬리 근사: 고가 대비 종가 하락 폭(%). min 있으면 그 이상이 pass."""
    sym = m["symbol"]
    d = _series(sym)
    high, close = _num(d, "high"), _num(d, "close")
    if not high or close is None:
        return {"value": None, "pass": None, "text": "%s 고가 데이터 없음" % sym}
    w = (high - close) / high * 100
    return {"value": w, "pass": _pass_min(w, m),
            "text": "고점 대비 종가 %+.1f%%" % -w}


def volume_ratio(m):
    sym = m["symbol"]
    d = _series(sym)
    vol, vol20 = _num(d, "vol"), _num(d, "vol20")
    if not vol or not vol20:
        return {"value": None, "pass": None, "text": "%s 거래량 데이터 없음" % sym}
    r = vol / vol20
    return {"value": r, "pass": _pass_min(r, m),
            "text": "거래량 %.2f배 (당일/20일평균)" % r}


def count_up_days(m):
    """최근 n거래일 중 상승일 수 (md_feed updays10). min 이상이면 pass."""
    sym, n = m["symbol"], m.get("n", 10)
    d = _series(sym)
    if not _ok(d):
        return {"value": None, "pass": None, "text": "%s 데이터 없음" % sym}
    key = "updays%d" % n
    v = d.get(key)
    if v is None:
        return {"value": None, "pass": None, "text": "%s %d일 상승일수 미제공" % (sym, n)}
    return {"value": v, "pass": _pass_min(v, m),
            "text": "%s %d일 중 %d일 상승" % (sym, n, v)}


def gap_up(m):
    sym = m["symbol"]
    d = _series(sym)
    op, prev = _num(d, "open"), _num(d, "prev")
    if op is None or not prev:
        return {"value": None, "pass": None, "text": "%s 시가/전일 데이터 없음" % sym}
    g = (op - prev) / prev * 100
    return {"value": g, "pass": _pass_min(g, m),
            "text": "시가 %.2f / 전일종가 %.2f · 갭 %+.1f%%" % (op, prev, g)}


def count_up(m):
    """심볼 목록 중 상승 개수(사실은 시세팀 breadth_up). min 이상이면 pass."""
    up, n = md_feed.breadth_up(m.get("symbols") or [])
    if n == 0:
        return {"value": None, "pass": None, "text": "심볼 수집 실패"}
    return {"value": up, "pass": _pass_min(up, m), "text": "%d/%d개 상승" % (up, n)}


def pullback_length(m):
    """최근 고점 이후 눌림 거래일수(사실은 시세팀 days_since_high). 범위(min~max)면 favorable."""
    d = _series(m["symbol"])
    v = _num(d, "days_since_high")
    if v is None:
        return {"value": None, "pass": None, "text": "눌림 데이터 없음"}
    return {"value": v, "pass": None, "text": "최근 고점 이후 %d거래일 눌림" % v}


def breakout_hold(m):
    """전고점 위 연속 유지 거래일수(사실은 시세팀 breakout_hold). min 이상이면 지지."""
    d = _series(m["symbol"])
    v = _num(d, "breakout_hold")
    if v is None:
        return {"value": None, "pass": None, "text": "전고점 데이터 없음"}
    return {"value": v, "pass": _pass_min(v, m), "text": "전고점 위 %d거래일 유지" % v}


def prev_low_break(m):
    """전일 저점 이탈 개수(사실은 시세팀 prev_low_breaks). min 이상이면 pass(주도주 이탈)."""
    br, ck = md_feed.prev_low_breaks(m.get("symbols") or [])
    if ck == 0:
        return {"value": None, "pass": None, "text": "저가 데이터 없음"}
    return {"value": br, "pass": _pass_min(br, m), "text": "%d/%d개 전일 저점 이탈" % (br, ck)}


# 선언 type → 계산기. (여기 없는 type = 아직 미구현/장중 — 상위가 '미구현'으로 표시)
CALC = {
    "pct_change": pct_change,
    "point_change": point_change,
    "dxy_change": dxy_change,
    "above_ma": above_ma,
    "hold_above_ma": hold_above_ma,
    "n_day_return": n_day_return,
    "ma_distance": ma_distance,
    "upper_wick": upper_wick,
    "volume_ratio": volume_ratio,
    "count_up_days": count_up_days,
    "gap_up": gap_up,
    "count_up": count_up,
    "prev_low_break": prev_low_break,
    "pullback_length": pullback_length,
    "breakout_hold": breakout_hold,
}


def _decide(value, m):
    """자기완결 metric 의 방향(op)+문턱(threshold)으로 pass 를 정한다.
    못 정하면 None(→ 계산기 자체 pass 를 그대로 둔다)."""
    if value is None:
        return None
    op = m.get("op")
    th = m.get("threshold", m.get("min"))
    mx = m.get("max")
    if th is not None and mx is not None:      # 범위 판정: min ≤ v ≤ max (눌림 2~4일 등)
        return th <= value <= mx
    if op == "above":
        return value > (th if th is not None else 0)
    if op == "below":
        return value < (th if th is not None else 0)
    if th is None:
        return None
    if op in ("<=",):
        return value <= th
    if op in ("<",):
        return value < th
    return value >= th          # 기본: 이상


def evaluate(metric):
    """metric 선언 하나를 평가. 계산기 없는 type 은 pass=None + 사유.
    자기완결 metric(op/threshold)이면 방향까지 반영해 pass 를 정한다."""
    if not metric or not metric.get("type"):
        return {"value": None, "pass": None, "text": "metric type 선언 없음"}
    t = metric["type"]
    if t in ("manual",):
        return {"value": None, "pass": None, "text": "수동: %s" % metric.get("reason", "")}
    fn = CALC.get(t)
    if not fn:
        return {"value": None, "pass": None, "text": "미구현/복합 type: %s" % t}
    try:
        res = fn(metric)
    except Exception as e:  # noqa: BLE001
        return {"value": None, "pass": None, "text": "계산 오류(%s): %s" % (t, e)}
    # 방향/문턱이 선언돼 있으면 그것으로 pass 를 덮어쓴다(못 정하면 계산기 기본 유지)
    d = _decide(res.get("value"), metric)
    if d is not None:
        res["pass"] = d
    return res


if __name__ == "__main__":
    import json
    import os
    from shared.paths import BASE
    spec = json.load(open(os.path.join(BASE, "books", "trend", "data_spec.json"),
                          encoding="utf-8"))["items"]
    for it in spec:
        m = it.get("metric") or {}
        r = evaluate(m)
        print("%-6s %-14s %s" % (it.get("ref", "?"), m.get("type", "-"), r["text"]))
