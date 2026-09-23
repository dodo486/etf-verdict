#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""장중 진입조건 자동 판정 (미국 개장+31분 실행)

시세는 jhts.marketdata(md_feed 창구)의 실시간 현재값·분봉으로 받는다.
KIS 를 쓰던 옛 경로는 걷어냈다(미국 시세는 KIS 크레덴셜이 더 이상 필요 없다).

자동으로 채우는 '장중 항목':
  - 빅테크/대표주 플러스: 전일종가 대비 등락%  (md.stock_rate → chg)
  - 첫 눌림 저점 높임: 분봉 종가 시퀀스        (md.minute_closes)
  - 시초가 지지(현재가 > 시가): md 실시간 창구엔 '당일 시가'가 없어 자동 불가 →
    status=error 로 정직하게 남긴다(값을 지어내지 않는다). 장중 3항목 중 이 하나는
    사람이 직접 확인한다.

출력: kis-intraday.json (아티팩트가 읽어 진입조건 체크에 반영 — 파일명·스키마는 유지)
"""
import paths  # noqa: F401  (경로·UTF-8 출력 고정. 반드시 먼저 import)
import os, json
from datetime import datetime, timezone

import md_feed

BASE = os.path.dirname(os.path.abspath(__file__))

# 종목별 주도주 매핑 (진입조건 ②에 해당)
LEADERS = {
    "TQQQ": [("NVDA", "엔비디아"), ("MSFT", "MS"), ("AAPL", "애플")],
    "SOXL": [("NVDA", "엔비디아"), ("AMD", "AMD"), ("AVGO", "브로드컴")],
    "UPRO": [],  # 섹터 데이터는 장중 무료 불가 → 수동
}


def higher_low_from_minutes(sym):
    """장 초반 첫 눌림에서 저점을 높였는가 판정(분봉 종가 근사).

    분봉은 종가만 제공되므로 저점을 종가 시퀀스로 근사한다: 전반부 최저 vs 후반부
    최저. 반환 {ok, label} 또는 {error}. (옛 KIS higher_low 의 종가판)."""
    bars = md_feed.last_minute_bars(sym, n=30)
    if not bars or len(bars) < 6:
        return {"error": "분봉 부족(장 초반 아님)"}
    lows = [c for _, c in bars if c is not None]
    if len(lows) < 6:
        return {"error": "분봉 저점 부족"}
    half = len(lows) // 2
    first_low = min(lows[:half])
    second_low = min(lows[half:])
    ok = second_low > first_low
    return {"ok": bool(ok),
            "label": f"저점 {first_low:.2f}→{second_low:.2f} ({'높임 ✓' if ok else '이탈'})"}


def snap(sym):
    """반환 (data|None, error_str|None). data = {last, base, chg}."""
    o = md_feed.intraday_snapshot(sym)
    if o and o.get("last") is not None:
        return o, None
    return None, "빈 응답(no data)"


def main():
    now = datetime.now(timezone.utc).astimezone()
    out = os.path.join(BASE, "kis-intraday.json")

    if not md_feed.AVAILABLE:
        json.dump({"ts": now.isoformat(), "status": "error",
                   "reason": "jhts.marketdata 미설치", "intraday": {}},
                  open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("jhts.marketdata 미설치 → 실패 기록"); return

    # 심볼별 현재값 조회(데이터+에러 분리)
    syms = set(["TQQQ", "SOXL", "UPRO"])
    for p in LEADERS.values():
        for s, _ in p:
            syms.add(s)
    px, err = {}, {}
    for s in syms:
        d, e = snap(s)
        px[s] = d; err[s] = e

    # 대상 ETF 3개가 전부 실패면 수집 자체 실패
    etf_errs = [err[s] for s in ("TQQQ", "SOXL", "UPRO") if err.get(s)]
    if len(etf_errs) == 3:
        json.dump({"ts": now.isoformat(), "status": "error",
                   "reason": f"시세 조회 실패: {etf_errs[0]}", "intraday": {}},
                  open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"전면 실패 → 기록: {etf_errs[0]}"); return

    result = {"ts": now.isoformat(), "status": "ok", "intraday": {}}
    for prod in ("TQQQ", "SOXL", "UPRO"):
        o = px.get(prod); e = err.get(prod)
        if not o:  # 이 종목만 실패
            result["intraday"][prod] = {"status": "error", "reason": e or "no data"}
            continue
        checks = {}
        bpct = o.get("chg")
        # 시초가 지지: md 실시간엔 당일 시가가 없어 자동 불가 → 정직하게 error.
        ol = f"현재 {o['last']:.2f}"
        if o.get("base") is not None:
            ol += f" / 전일 {o['base']:.2f}"
        if bpct is not None:
            ol += f" (전일比 {bpct:+.1f}%)"
        checks["open_hold"] = {"auto": True, "status": "error",
                               "reason": "당일 시가 미제공(직접 확인)", "label": ol}
        leaders = LEADERS.get(prod, [])
        if leaders:
            miss = [nm for s, nm in leaders if err.get(s)]
            parts = []
            for s, nm in leaders:
                if err.get(s):
                    parts.append(f"{nm} 실패"); continue
                p = px.get(s, {}).get("chg")
                parts.append(f"{nm} {p:+.1f}%" if p is not None else f"{nm} –")
            up = [nm for s, nm in leaders
                  if px.get(s) and (px[s].get("chg") or 0) > 0]
            if len(miss) == len(leaders):
                checks["leaders"] = {"auto": True, "status": "error",
                                     "reason": "주도주 조회 실패"}
            else:
                lbl = f"{len(up)}/{len(leaders)}↑ · " + ", ".join(parts)
                checks["leaders"] = {"auto": True, "ok": len(up) >= 2, "label": lbl}
        # 첫 눌림 저점 높임: 분봉 종가로 자동 판정
        hl = higher_low_from_minutes(prod)
        if hl.get("error"):
            checks["pullback"] = {"auto": True, "status": "error",
                                  "reason": f"분봉: {hl['error']}"}
        else:
            checks["pullback"] = {"auto": True, "ok": bool(hl["ok"]), "label": hl["label"]}
        result["intraday"][prod] = {
            "status": "ok", "last": o.get("last"), "open": None, "base": o.get("base"),
            "checks": checks,
        }
    json.dump(result, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"장중 판정 저장: {out}")
    for prod, v in result["intraday"].items():
        if v.get("status") == "error":
            print(f"  {prod}: ❌ {v.get('reason')}"); continue
        cs = v["checks"]
        auto_ok = [k for k, c in cs.items() if c.get("auto") and c.get("ok")]
        print(f"  {prod}: 현재 {v['last']} → 자동충족 {auto_ok}")


if __name__ == "__main__":
    main()
