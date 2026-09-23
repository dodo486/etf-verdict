#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF 데일리 진입 환경 자동판정
- 김프로랩 『미국 돈복사 ETF 투자방법』 STEP1 정량규칙을 코드로 옮김
- 시세는 직접 수집하지 않고 전부 jhts.marketdata(md_feed.py 창구)에서 받는다.
- 최신 EOD 기준으로 다음 세션 진입 '환경'을 판정 (필터/스코어카드/회피).
  장중 패턴 3종(시초가 지지·첫 눌림 저점·30분 판별)은 자동 불가 → '장중 확인'으로 표시.

출력: 콘솔 표 + JSON(--json) + 텔레그램/ macOS 알림 푸시(가능 시)
크레덴셜(택1):
  export TELEGRAM_BOT_TOKEN=... ; export TELEGRAM_CHAT_ID=...
없으면 데스크톱 알림으로 대체(macOS osascript / Windows 풍선 / Linux notify-send).
"""
import paths  # noqa: F401  (경로·UTF-8 출력 고정. 반드시 먼저 import)
import json, os, sys, ssl, urllib.request, urllib.parse
from datetime import datetime, timezone

import md_feed  # 시세 창구 — 야후/urllib 자체수집을 대체

# 텔레그램 전송용 TLS 컨텍스트(시세와 무관, 알림 전송에만 사용)
UA = {"User-Agent": "Mozilla/5.0"}
CTX = ssl.create_default_context()


def pct(a, b):
    return (a - b) / b * 100 if (a is not None and b) else None


def ok(v):  # 유효 데이터?
    return v and "error" not in v

# ---------- 데이터 수집 (md_feed 경유) ----------
# NQ=F / ES=F = 나스닥100·S&P500 선물. 저자 2-6이 '선물'을 보라고 해서 선물을 받는다.
# (지수 ^NDX/^GSPC 는 종목 필터·판정에 계속 쓰인다)
#   · 일봉 필요(MA20/MA60·거래량·연속유지) → md_feed.series()
#   · 방향만 필요(선물·^VIX·^TNX) → 선물=quote 스냅샷, 지수=index 스냅샷
SERIES_SYMS = ["^NDX", "^GSPC", "^SOX", "TQQQ", "SOXL", "UPRO",
               "NVDA", "MSFT", "AAPL", "AMD", "AVGO"]
FUTURES_SYMS = ["NQ=F", "ES=F"]
INDEX_SNAP_SYMS = ["^VIX", "^TNX"]


def _snap_to_d(sym, snap):
    """md_feed 스냅샷({price,prev,chg,...}) → 판정 코드가 기대하는 D[sym] 형태.

    일봉 없이 방향만 쓰는 심볼(선물·^VIX·^TNX)용. 옛 load() 가 채우던 키 중
    close/prev/chg 만 채운다(이 심볼들엔 MA/거래량/hold20 을 쓰지 않는다)."""
    if not snap or snap.get("price") is None:
        return {"sym": sym, "error": "시세 조회 실패"}
    return {"sym": sym, "close": snap["price"], "prev": snap.get("prev"),
            "chg": snap.get("chg")}


D = {s: md_feed.series(s) for s in SERIES_SYMS}
_fut = md_feed.quote_snapshot(FUTURES_SYMS)
for s in FUTURES_SYMS:
    D[s] = _snap_to_d(s, _fut.get(s))
for s in INDEX_SNAP_SYMS:
    D[s] = _snap_to_d(s, md_feed.index_snapshot(s))

def above20(v): return ok(v) and v["ma20"] and v["close"] > v["ma20"]
def above60(v): return ok(v) and v["ma60"] and v["close"] > v["ma60"]
def plus(sym): return ok(D[sym]) and D[sym]["chg"] is not None and D[sym]["chg"] > 0

# ---------- 스코어카드 (5점) ----------
sc = []   # (라벨, 통과여부, 근거수치) — 근거는 시트가 항목 아래에 그대로 보여준다


def _why_dir(sym, v):
    """방향 판정의 근거: 종가 / 전일 / 등락률."""
    if not ok(v) or v.get("chg") is None:
        return "수집 실패 — 값 없음"
    return f"{sym} {v['close']:,.1f} / 전일 {v['prev']:,.1f} ({v['chg']:+.2f}%)"


# 저자 2-6: '나스닥 선물 / S&P500 선물 방향'. 선물을 못 받으면 지수로 대체하지 않고
# 실패로 표시한다(대리지표를 몰래 끼워넣지 않음).
sc.append(("나스닥 선물 방향", plus("NQ=F"), _why_dir("NQ=F 선물", D["NQ=F"])))
sc.append(("S&P500 선물 방향", plus("ES=F"), _why_dir("ES=F 선물", D["ES=F"])))

vix = D["^VIX"]
vix_ok = ok(vix) and vix["chg"] is not None and vix["chg"] < 10
sc.append(("VIX 안정(전일 +10% 미만)", vix_ok,
           (f"^VIX {vix['close']:.2f} / 전일 {vix['prev']:.2f} ({vix['chg']:+.2f}%) · 기준 +10% 미만"
            if (ok(vix) and vix["chg"] is not None) else "수집 실패 — 값 없음")))

tnx = D["^TNX"]
tnx_jump = ok(tnx) and tnx["chg"] is not None and (tnx["close"] - tnx["prev"]) >= 0.10
sc.append(("10년물 안정(+0.1%p 미만)", ok(tnx) and not tnx_jump,
           (f"^TNX {tnx['close']:.2f}% / 전일 {tnx['prev']:.2f}% ({tnx['close']-tnx['prev']:+.2f}%p) · 기준 +0.10%p 미만"
            if (ok(tnx) and tnx["chg"] is not None) else "수집 실패 — 값 없음")))

# 달러인덱스: DX-Y.NYB, 실패 시 DX=F (심볼이 불안정해 둘 다 실패할 수 있다)
dxy = D.get("DXY")
if dxy is None:
    dxy = _snap_to_d("DX-Y.NYB", md_feed.index_snapshot("DX-Y.NYB"))
    if not ok(dxy):
        dxy = _snap_to_d("DX=F", md_feed.index_snapshot("DX=F"))
    D["DXY"] = dxy
dxy_ok = ok(dxy) and dxy["chg"] is not None and dxy["chg"] < 0.5
sc.append(("달러인덱스 안정(급강세 아님)", dxy_ok,
           (f"{dxy['sym']} {dxy['close']:,.2f} / 전일 {dxy['prev']:,.2f} ({dxy['chg']:+.2f}%) · 기준 +0.5% 미만"
            if (ok(dxy) and dxy["chg"] is not None)
            else "수집 실패 — 무료 달러인덱스 심볼 불안정, 직접 확인")))

score = sum(1 for _, b, _w in sc if b)

# ---------- 섹터 폭 · 실적일 (저자 5-3 / 5-4 / 3-5) ----------
# 미국 섹터는 SPDR ETF로, 실적일은 나스닥 공개 캘린더로 받는다. 실패하면 값을
# 지어내지 않고 ok=False 로 남겨 시트가 '직접 확인'으로 표시한다.
try:
    SECTORS = md_feed.sector_snapshot()
    BREADTH = md_feed.sector_breadth(SECTORS)        # 5-4: 섹터 5개 중 20일선 위 개수
    DEFONLY = md_feed.defensive_only(SECTORS)        # 5-3: 방어주만 살아남
    CYCWEAK = md_feed.cyclical_weak(SECTORS)         # 5-3: 금융·산업재 동시 약화
except Exception as _e:  # noqa: BLE001
    SECTORS, BREADTH = {}, {"ok": False, "reason": "섹터 수집 실패: %s" % _e}
    DEFONLY = CYCWEAK = {"ok": False, "reason": "섹터 수집 실패"}
    print("[섹터 실패]", _e, file=sys.stderr)

try:
    EARN = md_feed.earnings_dday(["NVDA", "MSFT", "AAPL", "AMD", "AVGO"])
except Exception as _e:  # noqa: BLE001
    EARN = {}
    print("[실적 캘린더 실패]", _e, file=sys.stderr)


def _spx_below(ma_key):
    g = D.get("^GSPC")
    return bool(ok(g) and g.get(ma_key) and g["close"] < g[ma_key])


# 5-3 "나쁜 금리 하락" — 금리 내려가는데 주식 못 오르고 금융주 약함
def _bad_rate_drop():
    g = D.get("^GSPC")
    if not (ok(tnx) and ok(g)):
        return {"ok": False, "reason": "수집 실패"}
    rate_down = (tnx["close"] - tnx["prev"]) < 0
    spx_down = g["chg"] is not None and g["chg"] <= 0
    fin = SECTORS.get("금융", {}).get("ret5")
    fin_weak = fin is not None and fin < 0
    return {"ok": True, "flag": bool(rate_down and spx_down and fin_weak),
            "label": "10년물 %+.2f%%p · S&P500 %+.2f%% · 금융 5일 %s"
                     % (tnx["close"] - tnx["prev"], g["chg"] if g["chg"] is not None else 0,
                        ("%+.1f%%" % fin) if fin is not None else "수집 실패")}


BADRATE = _bad_rate_drop()

# 5-3 침체 신호 집계 (저자 5신호 중 자동 4개 + 수동 1개)
RECESSION = {
    "signals": [
        {"key": "def_only", "label": "방어주만 살아나고 기술·금융·산업재 약화",
         "auto": DEFONLY.get("ok", False), "on": bool(DEFONLY.get("flag")),
         "why": DEFONLY.get("label") or DEFONLY.get("reason", "")},
        {"key": "cyc_weak", "label": "금융·산업재가 전고점서 계속 밀림(5거래일 약세)",
         "auto": CYCWEAK.get("ok", False), "on": bool(CYCWEAK.get("flag")),
         "why": CYCWEAK.get("label") or CYCWEAK.get("reason", "")},
        {"key": "estimates", "label": "실적 전망 하향이 업종 전체로 퍼짐",
         "auto": False, "on": False,
         "why": "애널리스트 추정치는 무료 소스 없음 — 직접 확인"},
        {"key": "bad_rate", "label": "나쁜 금리 하락(금리↓인데 주식 못 오르고 금융 약함)",
         "auto": BADRATE.get("ok", False), "on": bool(BADRATE.get("flag")),
         "why": BADRATE.get("label") or BADRATE.get("reason", "")},
        {"key": "no_recover", "label": "S&P500이 20일선 깨고 반등해도 회복 못 함",
         "auto": ok(D.get("^GSPC")), "on": _spx_below("ma20"),
         "why": ("S&P500 %.1f / 20일선 %.1f (%s) · 60일선 %.1f (%s)" % (
             D["^GSPC"]["close"], D["^GSPC"]["ma20"],
             "아래" if _spx_below("ma20") else "위",
             D["^GSPC"]["ma60"] or 0, "아래" if _spx_below("ma60") else "위"))
             if ok(D.get("^GSPC")) and D["^GSPC"].get("ma20") else "수집 실패"},
    ],
    "spx_below_ma60": _spx_below("ma60"),
}
RECESSION["count"] = sum(1 for s in RECESSION["signals"] if s["on"])


# ---------- 회피 신호 ----------
def avoid_common():
    a = []
    if ok(vix) and vix["chg"] is not None and vix["chg"] >= 10:
        a.append(f"VIX 전일 대비 +{vix['chg']:.1f}% (추격 금지)")
    if tnx_jump:
        a.append(f"10년물 +{(tnx['close']-tnx['prev']):.2f}%p 급등 (기술주 예민)")
    return a

def wick(v):  # 윗꼬리 근사: 고가 대비 종가 하락 폭
    if ok(v) and v["high"] and v["close"]:
        return (v["high"] - v["close"]) / v["high"] * 100
    return None

prod_cfg = {
    "TQQQ": {"idx":"^NDX", "color":"🔵"},
    "SOXL": {"idx":"^SOX", "color":"🟠"},
    "UPRO": {"idx":"^GSPC","color":"🟢"},
}

def verdict(prod):
    p = D[prod]; cfg = prod_cfg[prod]; idx = D[cfg["idx"]]
    if not ok(p) or not ok(idx):
        return {"prod":prod,"grade":"데이터오류","reason":"시세 조회 실패","avoid":[],"intraday":[]}
    av = []; akeys = []
    if ok(vix) and vix["chg"] is not None and vix["chg"] >= 10:
        av.append(f"VIX 전일 대비 +{vix['chg']:.1f}% (추격 금지)"); akeys.append("vix")
    if tnx_jump:
        av.append(f"10년물 +{(tnx['close']-tnx['prev']):.2f}%p 급등 (기술주 예민)"); akeys.append("tnx")
    # 필터 — 저자 3-2·5-2: 20일선 위 '회복' 만으로는 부족하고 **이후 2거래일**을
    # 지켜야 한다(규칙 근거표: "20일선 위로 회복 + 이후 2거래일 20일선 안 깸").
    # 회복일 + 2거래일 = 연속 3거래일.
    HOLD_NEED = 3
    hold = idx.get("hold20", 0) if ok(idx) else 0
    hold_ok = hold >= HOLD_NEED
    if prod == "TQQQ":
        filt = above20(idx) and hold_ok          # 저자 3-2 "최소 2거래일 버팀"
        filt_txt = "나스닥100 20일선 위 + 2거래일 유지"
    elif prod == "SOXL":
        # 저자 4장은 "SOXL·반도체지수 모두 20일선 위"까지만 말한다. 2거래일 유지는
        # SOXL에 대해 명시된 적이 없으므로 게이트로 쓰지 않는다(참고 수치로만 노출).
        filt = above20(p) and above20(idx)
        filt_txt = "SOXL·반도체지수 모두 20일선 위(스윙)"
    else:  # UPRO
        filt = above20(idx) and hold_ok
        filt_txt = "S&P500 20일선 위 + 2거래일 유지"
    # 상품별 회피
    if prod == "SOXL":
        if ok(idx) and idx["updays10"] >= 7 and p["ret5"] is not None and p["ret5"] >= 20:
            av.append(f"과열: 반도체 10일중 {idx['updays10']}일↑ + SOXL 5일 {p['ret5']:.0f}%↑"); akeys.append("overheat")
        elif p["ret5"] is not None and p["ret5"] >= 15:
            av.append(f"SOXL 최근 5일 {p['ret5']:.0f}% 급등"); akeys.append("run5")
        w = wick(p)
        if w is not None and w >= 4:
            av.append(f"장중 고점 대비 {w:.1f}% 밀려 마감(윗꼬리)"); akeys.append("wick")
        if plus("NVDA") and not (plus("AMD") or plus("AVGO")):
            av.append("엔비디아만 강하고 AMD·브로드컴 약함"); akeys.append("nvda_only")
    if prod == "UPRO":
        # 저자 5-3: 금융·산업재 5거래일 약세 + 방어주만 버팀 → 30% 축소
        if DEFONLY.get("ok") and DEFONLY.get("flag"):
            av.append("경기침체 경계: 방어주만 살아나고 기술·금융·산업재 약화")
            akeys.append("def_only")
        if BADRATE.get("ok") and BADRATE.get("flag"):
            av.append("나쁜 금리 하락(금리↓인데 S&P500 못 오르고 금융 약함)")
            akeys.append("bad_rate")
    if prod == "TQQQ":
        # 저자 3-5: 실적 발표 전 + 5일 이상 상승 → 노출 축소
        _near = [(s, v) for s, v in EARN.items() if s in ("NVDA", "MSFT", "AAPL") and v[1] <= 5]
        if _near and p["ret5"] is not None and p["ret5"] > 0:
            _s, (_dt, _dd) = _near[0]
            av.append(f"빅테크 실적 D-{_dd} ({_s} {_dt}) + 최근 5일 {p['ret5']:+.0f}% — 노출 축소 구간")
            akeys.append("earnings")
        if p["ret5"] is not None and p["ret5"] >= 25:
            av.append(f"TQQQ 최근 5일 {p['ret5']:.0f}% 급등(추격 위험)"); akeys.append("run5")
        w = wick(p)
        if w is not None and w >= 4:
            av.append(f"전고점권 윗꼬리(고점 대비 -{w:.1f}%)"); akeys.append("wick")
    # 등급
    if not filt:
        grade, reason = "🚫 진입 금지", f"필터 미충족 — {filt_txt} 아님(추세 없음)"
    elif av:
        grade, reason = "⛔ 보류", f"회피 신호 {len(av)}개 — 과열/위험, 눌림 대기"
    elif score >= 4:
        grade, reason = "✅ 매수 후보", f"필터 통과 · 스코어 {score}/5 → 1차 분할 진입 준비"
    elif score == 3:
        grade, reason = "🟡 소액만", f"스코어 {score}/5 — 확인 매수 수준"
    else:
        grade, reason = "⚪ 관망", f"스코어 {score}/5 — 신규 진입 보류"
    # 장중 확인항목(자동 불가)
    intraday = []
    if filt and not av and score >= 3:
        if prod == "TQQQ":
            intraday = ["나스닥 시초가 위 유지","첫 눌림 저점 높임","빅테크 7종목 중 3개↑"]
        elif prod == "SOXL":
            intraday = ["엔비디아 시초가 위","AMD 전일 저점 지킴","브로드컴 안 밀림"]
        else:
            intraday = ["S&P500 20일선 종가 유지"]
            if BREADTH.get("ok"):
                intraday.append("섹터 %d/5 20일선 위" % BREADTH["count"])
            else:
                intraday.append("섹터 3개↑ 동반")
    # 거래량 신호(EOD): 전일 대비 1.5배 이상 + 종가가 당일 고점 근처(고점 대비 -1.5% 이내)
    vol_ok = False
    if ok(p) and p.get("vol") and p.get("vol20") and p["vol20"]:
        near_high = (p.get("high") and p["high"] and (p["high"]-p["close"])/p["high"] <= 0.015)
        vol_ok = (p["vol"] >= 1.5*p["vol20"]) and bool(near_high)

    # ---- 항목별 검증용 수치(metrics): 아티팩트가 작은글씨로 표시 ----
    def gap(c, m):  # 이격 %
        return (c-m)/m*100 if (c is not None and m) else None
    def mil(v):
        return f"{v/1e6:.1f}M" if v else "–"
    metrics = {}
    if ok(idx):
        metrics["hold20"]="%s 20일선 위 %d거래일 연속 (기준 %d)" % (cfg["idx"], hold, HOLD_NEED)
    # 필터
    if prod == "SOXL":
        gp=gap(p["close"],p["ma20"]); gi=gap(idx["close"],idx["ma20"])
        metrics["filter"]=f"SOXL {p['close']:.2f}/20일선 {p['ma20']:.2f} ({gp:+.1f}%), ^SOX {gi:+.1f}%"
    else:
        gi=gap(idx["close"],idx["ma20"])
        iname={"TQQQ":"나스닥100","UPRO":"S&P500"}[prod]
        metrics["filter"]=f"{iname} {idx['close']:.1f}/20일선 {idx['ma20']:.1f} ({gi:+.1f}%)"
    # 거래량
    if ok(p) and p.get("vol") and p.get("vol20"):
        ratio=p["vol"]/p["vol20"] if p["vol20"] else None
        nh=(p["high"]-p["close"])/p["high"]*100 if p.get("high") else None
        metrics["vol"]=f"거래량 {mil(p['vol'])}/20일평균 {mil(p['vol20'])} ({ratio:.2f}배), 고점比 {-nh:+.1f}%" if ratio is not None else "거래량 데이터 없음"
    # 회피 지표(모두, 걸리든 안 걸리든 현재값 표시)
    if ok(vix) and vix["chg"] is not None:
        metrics["vix"]=f"^VIX {vix['close']:.1f} (전일比 {vix['chg']:+.1f}%)"
    if ok(tnx) and tnx.get("close") is not None and tnx.get("prev") is not None:
        metrics["tnx"]=f"^TNX {tnx['close']:.2f} (전일 {tnx['prev']:.2f}, {tnx['close']-tnx['prev']:+.2f}%p)"
    if p.get("ret5") is not None:
        metrics["run5"]=f"최근 5일 {p['ret5']:+.1f}%"
    # 저자 2-7 "5일선과 얼마나 벌어졌는지" — 임계는 저자 미명시이므로 수치만 노출
    if p.get("ma5"):
        metrics["ma5_gap"]=f"5일선 {p['ma5']:.2f} 대비 이격 {pct(p['close'], p['ma5']):+.1f}%"
    # 저자 7-3 "갭상승 날" — 갭 %도 저자 미명시. 수치만 노출하고 판단은 사람이
    if p.get("open") and p.get("prev"):
        g=pct(p["open"], p["prev"])
        metrics["gap"]=f"시가 {p['open']:.2f} / 전일종가 {p['prev']:.2f} · 갭 {g:+.1f}%"
    # 저자 5-4 섹터 폭 / 5-3 침체 / 3-5 실적일
    if BREADTH.get("ok"):
        metrics["breadth"]=BREADTH["label"]
    elif BREADTH.get("reason"):
        metrics["breadth"]=BREADTH["reason"]
    if prod == "UPRO":
        if DEFONLY.get("ok"): metrics["def_only"]=DEFONLY["label"]
        if BADRATE.get("ok"): metrics["bad_rate"]=BADRATE["label"]
    if prod == "TQQQ" and EARN:
        metrics["earnings"]=" · ".join("%s %s(D-%d)"%(s,v[0],v[1]) for s,v in list(EARN.items())[:3])
    w=wick(p)
    if w is not None:
        metrics["wick"]=f"고점 대비 종가 {-w:+.1f}%"
    if prod=="SOXL" and ok(idx):
        metrics["overheat"]=f"^SOX 10일중 {idx['updays10']}일↑ · SOXL 5일 {p['ret5']:+.0f}%" if p.get("ret5") is not None else f"^SOX 10일중 {idx['updays10']}일↑"
        nv=D['NVDA']['chg'] if ok(D.get('NVDA')) else None
        am=D['AMD']['chg'] if ok(D.get('AMD')) else None
        bc=D['AVGO']['chg'] if ok(D.get('AVGO')) else None
        if nv is not None:
            metrics["nvda_only"]=f"엔비디아 {nv:+.1f}%, AMD {am:+.1f}%, 브로드컴 {bc:+.1f}%" if (am is not None and bc is not None) else f"엔비디아 {nv:+.1f}%"
    # EOD로 자동 판정되는 진입 항목(시트가 체크박스를 자동으로 켠다)
    eod_checks = {}
    if ok(idx):
        eod_checks["hold20"] = {
            "ok": bool(hold_ok),
            "label": "%s 20일선 위 %d거래일 연속 (회복일+2거래일 = %d 필요)"
                     % (cfg["idx"], hold, HOLD_NEED)}
    if prod == "UPRO" and BREADTH.get("ok"):
        eod_checks["breadth"] = {"ok": BREADTH["count"] >= 3, "label": BREADTH["label"]}

    return {"prod":prod,"color":cfg["color"],"grade":grade,"reason":reason,
            "eod_checks":eod_checks,
            "avoid":av,"avoid_keys":akeys,"filter_ok":bool(filt),"vol_ok":bool(vol_ok),"intraday":intraday,
            "metrics":metrics,
            "close":p["close"],"ma20":p["ma20"],"chg":p["chg"]}

verdicts = [verdict(pp) for pp in ("TQQQ","SOXL","UPRO")]

# ---------- 출력 텍스트 ----------
now = datetime.now(timezone.utc).astimezone()
lead = {"NVDA":"엔비디아","MSFT":"MS","AAPL":"애플","AMD":"AMD","AVGO":"브로드컴"}
lead_txt = " ".join(f"{k}{'+' if plus(s) else '−'}" for s,k in lead.items() if ok(D[s]))

def build_text():
    L = []
    L.append(f"📈 ETF 데일리 진입 환경  ({now:%Y-%m-%d %H:%M} KST)")
    L.append(f"장 시작 전 스코어카드: {score}/5  " + ("공격가능" if score>=4 else "소액" if score==3 else "관망"))
    for lab, b, why in sc:
        L.append(f"   {'🟢' if b else '🔴'} {lab}")
        if why:
            L.append(f"      └ {why}")
    L.append(f"주도주: {lead_txt}")
    L.append("─"*30)
    for v in verdicts:
        if v["grade"]=="데이터오류":
            L.append(f"{v['prod']}: 데이터오류"); continue
        L.append(f"{v['color']} {v['prod']}  {v['grade']}")
        L.append(f"   {v['reason']}")
        if v.get("close") and v.get("ma20"):
            side = "위" if v["close"]>v["ma20"] else "아래"
            L.append(f"   종가 {v['close']:.2f} / 20일선 {v['ma20']:.2f} ({side}), 당일 {v['chg']:+.1f}%")
        for a in v["avoid"]:
            L.append(f"   ⚠ {a}")
        if v["intraday"]:
            L.append(f"   👁 장중 확인(31분째): " + " · ".join(v["intraday"]))
    L.append("─"*30)
    L.append("※ 환경 판정(EOD 기준). 장중 3항목은 직접 확인 후 최종 진입. 규칙 출처=저자 명시.")
    return "\n".join(L)

text = build_text()

# ---------- 전송 ----------
def send_telegram(msg):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN"); cid = os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and cid): return False
    try:
        url = f"https://api.telegram.org/bot{tok}/sendMessage"
        body = urllib.parse.urlencode({"chat_id":cid,"text":msg}).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=body, headers=UA), timeout=20, context=CTX)
        return True
    except Exception as e:
        print("[telegram 실패]", e, file=sys.stderr); return False

def send_desktop(msg):
    """데스크톱 알림 — macOS/Windows/Linux 각각의 기본 수단으로. 실패해도 조용히 넘어간다."""
    import subprocess
    title = "ETF 진입 환경"
    first = msg.split("\n")[1] if "\n" in msg else msg
    try:
        if sys.platform == "darwin":
            subprocess.run(["osascript", "-e",
                f'display notification {json.dumps(first)} with title {json.dumps(title)}'],
                check=False)
        elif sys.platform == "win32":
            # 외부 모듈(BurntToast 등) 없이 도는 최소 풍선 알림
            ps = ("[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');"
                  "$n=New-Object System.Windows.Forms.NotifyIcon;"
                  "$n.Icon=[System.Drawing.SystemIcons]::Information;$n.Visible=$true;"
                  f"$n.ShowBalloonTip(10000,{json.dumps(title)},{json.dumps(first)},'Info');"
                  "Start-Sleep -Seconds 6;$n.Dispose()")
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           check=False, capture_output=True)
        else:
            subprocess.run(["notify-send", title, first], check=False)
        return True
    except Exception:
        return False


# 이전 이름 호환
send_macos = send_desktop

def build_html():
    grade_cls = {"✅ 매수 후보":"go","🟡 소액만":"small","⛔ 보류":"no","🚫 진입 금지":"no","⚪ 관망":"","데이터오류":""}
    sc_rows = "".join(
        f'<div class="scitem"><span class="dot {"on" if b else "off"}"></span>{l}</div>' for l,b,_w in sc)
    cards = ""
    for v in verdicts:
        if v["grade"]=="데이터오류":
            cards += f'<div class="card"><h3>{v["prod"]}</h3><p class="muted">데이터 오류</p></div>'; continue
        cls = grade_cls.get(v["grade"],"")
        av = "".join(f'<li class="warn">⚠ {a}</li>' for a in v["avoid"])
        idd = ""
        if v["intraday"]:
            idd = '<div class="intraday"><b>👁 장중 확인(31분째)</b><ul>' + \
                  "".join(f"<li>{x}</li>" for x in v["intraday"]) + "</ul></div>"
        side = "위" if (v.get("close") and v.get("ma20") and v["close"]>v["ma20"]) else "아래"
        px = ""
        if v.get("close") and v.get("ma20"):
            px = f'<div class="px">종가 <b>{v["close"]:.2f}</b> / 20일선 {v["ma20"]:.2f} <span class="{ "up" if side=="위" else "dn"}">({side})</span> · 당일 {v["chg"]:+.1f}%</div>'
        cards += f'''<div class="card pc-{v["prod"].lower()} {cls}">
          <div class="chd"><h3>{v["color"]} {v["prod"]}</h3><span class="grade {cls}">{v["grade"]}</span></div>
          <p class="reason">{v["reason"]}</p>{px}
          <ul class="flags">{av}</ul>{idd}</div>'''
    sc_verdict = "공격 가능" if score>=4 else ("소액만" if score==3 else "관망")
    lead_html = " ".join(
        f'<span class="{ "up" if plus(s) else "dn"}">{k}{"▲" if plus(s) else "▼"}</span>'
        for s,k in lead.items() if ok(D[s]))
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ETF 진입 환경 · {now:%m/%d}</title>
<style>
:root{{--ground:#12141a;--surface:#1a1e28;--s2:#20242f;--line:#2b303c;--text:#c7ccd6;--head:#eef1f6;--mute:#7a8194;--gold:#d4a24e;--tqqq:#4c8dff;--soxl:#f0883e;--upro:#3fb950;--go:#3fb950;--no:#e5484d}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--ground);color:var(--text);font-family:-apple-system,"Apple SD Gothic Neo","Pretendard",sans-serif;line-height:1.65;-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}}
.wrap{{max-width:760px;margin:0 auto;padding:28px 18px 80px}}
h1{{font-size:22px;color:var(--head);margin:0 0 2px;font-weight:800;letter-spacing:-.01em}}
.ts{{color:var(--mute);font-size:13px;margin-bottom:20px}}
.scorebox{{background:linear-gradient(180deg,var(--surface),var(--s2));border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin-bottom:16px}}
.scorebox .top{{display:flex;align-items:baseline;gap:12px;margin-bottom:12px}}
.scorebox .num{{font-size:34px;font-weight:800;color:var(--gold)}}
.scorebox .lab{{font-size:15px;font-weight:700;color:var(--head)}}
.scitem{{display:flex;align-items:center;gap:9px;padding:5px 0;font-size:13.5px}}
.dot{{width:9px;height:9px;border-radius:50%;flex:none}}
.dot.on{{background:var(--go)}}.dot.off{{background:var(--no)}}
.lead{{margin-top:10px;padding-top:10px;border-top:1px solid var(--line);font-size:13px;color:var(--mute);display:flex;gap:12px;flex-wrap:wrap}}
.up{{color:var(--go)}}.dn{{color:var(--no)}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:12px 0;border-left:4px solid var(--line)}}
.card.go{{border-left-color:var(--go)}}.card.no{{border-left-color:var(--no)}}.card.small{{border-left-color:var(--gold)}}
.chd{{display:flex;justify-content:space-between;align-items:center}}
.card h3{{margin:0;font-size:19px;font-weight:800;color:var(--head)}}
.pc-tqqq h3{{color:var(--tqqq)}}.pc-soxl h3{{color:var(--soxl)}}.pc-upro h3{{color:var(--upro)}}
.grade{{font-size:14px;font-weight:800;padding:4px 10px;border-radius:20px;background:var(--s2);color:var(--mute)}}
.grade.go{{background:rgba(63,185,80,.14);color:var(--go)}}.grade.no{{background:rgba(229,72,77,.14);color:var(--no)}}.grade.small{{background:rgba(212,162,78,.14);color:var(--gold)}}
.reason{{margin:8px 0 4px;font-size:14px;color:var(--text)}}
.px{{font-size:13px;color:var(--mute)}}.px b{{color:var(--head)}}
.flags{{list-style:none;padding:0;margin:8px 0 0}}.flags .warn{{color:#f0a3a5;font-size:13px;padding:2px 0}}
.intraday{{margin-top:10px;padding:10px 12px;background:var(--s2);border-radius:9px;font-size:13px}}
.intraday b{{color:var(--gold)}}.intraday ul{{margin:6px 0 0;padding-left:18px;color:var(--text)}}
.foot{{margin-top:24px;color:var(--mute);font-size:12px;border-top:1px solid var(--line);padding-top:14px;line-height:1.6}}
</style></head><body><div class="wrap">
<h1>📈 ETF 데일리 진입 환경</h1>
<div class="ts">{now:%Y-%m-%d %H:%M} KST · 최신 세션 종가 기준 · 규칙 출처=저자 명시</div>
<div class="scorebox">
  <div class="top"><span class="num">{score}/5</span><span class="lab">{sc_verdict}</span></div>
  {sc_rows}
  <div class="lead">주도주 {lead_html}</div>
</div>
{cards}
<div class="foot">환경 판정(EOD)입니다. 장중 3항목(시초가 지지·첫 눌림 저점·30분 판별)은 자동 계산이 안 되니 31분째 직접 확인 후 최종 진입하세요. 이 페이지는 매일 화~토 08:00 자동 갱신됩니다.</div>
</div></body></html>'''

if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps({"score":score,"scorecard":[{"label":l,"ok":b,"why":w} for l,b,w in sc],
                          "verdicts":verdicts,"ts":now.isoformat(),
                          "extras":{"sectors":SECTORS,"breadth":BREADTH,
                                    "recession":RECESSION,
                                    "earnings":{s:{"date":v[0],"dday":v[1]} for s,v in EARN.items()}}}, ensure_ascii=False, indent=2))
    else:
        print(text)
    if "--no-send" not in sys.argv:
        sent = send_telegram(text)
        if not sent:
            send_desktop(text)
    # HTML 대시보드 + 로그 저장 (경로/인코딩은 paths.py가 OS 중립으로 처리)
    from paths import BASE as _BASE, LOGS as _LOGS, write_text as _write
    try:
        _write(os.path.join(_BASE, "etf-verdict.html"), build_html())
    except Exception as e:
        print("[html 실패]", e, file=sys.stderr)
    try:
        _write(os.path.join(_LOGS, f"etf-{now:%Y%m%d}.txt"), text)
    except Exception:
        pass
