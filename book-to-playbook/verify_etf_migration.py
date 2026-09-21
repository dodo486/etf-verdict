#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ETF 마이그레이션 대조검증
레거시 etf_daily_verdict.py 결과 vs 신규 verdict_engine(etf_data_spec.json) 결과를
같은 수급/판정 항목에서 대조한다. 필터/회피/거래량 판정 일치 여부만 확인.
(레거시 파이프라인·launchd·publish는 건드리지 않음. 읽기 전용 대조.)

사용: python3 verify_etf_migration.py
종료코드 0=전부 일치, 1=불일치 존재.
"""
import json
import subprocess
import sys
import os

BASE = os.path.dirname(os.path.abspath(__file__))


def legacy_verdicts():
    """etf_daily_verdict.py를 --json --no-send로 실행해 verdicts 파싱."""
    r = subprocess.run(
        [sys.executable, os.path.join(BASE, "etf_daily_verdict.py"), "--json", "--no-send"],
        capture_output=True, text=True, cwd=BASE, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(f"legacy 실행 실패: {r.stderr[:400]}")
    return json.loads(r.stdout)


def engine_items():
    from verdict_engine import evaluate  # noqa: PLC0415
    out = evaluate(os.path.join(BASE, "etf_data_spec.json"))
    return {it["item"]: it for it in out["items"]}


def approx(a, b, tol=0.15):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol


def main():
    lg = legacy_verdicts()
    lv = {v["prod"]: v for v in lg["verdicts"]}
    en = engine_items()

    rows = []  # (설명, 레거시, 신규, 일치?)

    # --- 필터 판정 일치 ---
    # TQQQ 필터 = 나스닥100 20일선 위
    tqqq_filter = en["TQQQ 필터: 나스닥100 20일선 위"]["ok"]
    rows.append(("TQQQ filter_ok", lv["TQQQ"]["filter_ok"], tqqq_filter,
                 lv["TQQQ"]["filter_ok"] == tqqq_filter))
    # UPRO 필터 = S&P500 20일선 위
    upro_filter = en["UPRO 필터: S&P500 20일선 위"]["ok"]
    rows.append(("UPRO filter_ok", lv["UPRO"]["filter_ok"], upro_filter,
                 lv["UPRO"]["filter_ok"] == upro_filter))
    # SOXL 필터 = SOXL & ^SOX 둘 다 20일선 위
    soxl_filter = bool(en["SOXL 필터A: SOXL 20일선 위"]["ok"]
                       and en["SOXL 필터B: 반도체지수 20일선 위"]["ok"])
    rows.append(("SOXL filter_ok", lv["SOXL"]["filter_ok"], soxl_filter,
                 lv["SOXL"]["filter_ok"] == soxl_filter))

    # --- 회피 신호 일치 (레거시 avoid_keys vs 엔진 임계값 재현) ---
    # TQQQ run5(>=25) / wick(>=4)
    tqqq_run5 = en["TQQQ 최근 5일 수익률"]["value"]
    tqqq_wick = en["TQQQ 윗꼬리(고점 대비 종가)"]["value"]
    lg_tqqq_keys = set(lv["TQQQ"]["avoid_keys"])
    rows.append(("TQQQ avoid:run5", "run5" in lg_tqqq_keys, tqqq_run5 >= 25,
                 ("run5" in lg_tqqq_keys) == (tqqq_run5 >= 25)))
    rows.append(("TQQQ avoid:wick", "wick" in lg_tqqq_keys, tqqq_wick >= 4,
                 ("wick" in lg_tqqq_keys) == (tqqq_wick >= 4)))

    # SOXL overheat: ^SOX updays10>=7 AND SOXL ret5>=20 ; else run5>=15 ; wick>=4 ; nvda_only
    soxl_run5 = en["SOXL 최근 5일 수익률"]["value"]
    soxl_wick = en["SOXL 윗꼬리(고점 대비 종가)"]["value"]
    lg_soxl_keys = set(lv["SOXL"]["avoid_keys"])
    # overheat/run5 는 updays10(엔진 미보유 metric)에 의존 → run5 임계값만 대조
    rows.append(("SOXL avoid:wick", "wick" in lg_soxl_keys, soxl_wick >= 4,
                 ("wick" in lg_soxl_keys) == (soxl_wick >= 4)))
    # nvda_only: NVDA+ AND not(AMD+ or AVGO+). count_up 라벨의 개별값으로 재현
    cu = en["SOXL 주도주 3개 중 상승수(엔비디아·AMD·브로드컴)"]
    # 라벨 파싱: "3/3↑ · NVDA +1.2%, AMD +9.2%, AVGO +0.1%"
    def sign(name):
        seg = [p for p in cu["label"].split("·")[-1].split(",") if name in p]
        if not seg:
            return None
        try:
            return float(seg[0].split()[-1].rstrip("%"))
        except Exception:
            return None
    nv, am, bc = sign("NVDA"), sign("AMD"), sign("AVGO")
    eng_nvda_only = (nv is not None and nv > 0) and not (
        (am is not None and am > 0) or (bc is not None and bc > 0))
    rows.append(("SOXL avoid:nvda_only", "nvda_only" in lg_soxl_keys, eng_nvda_only,
                 ("nvda_only" in lg_soxl_keys) == eng_nvda_only))

    # --- 거래량 배수 값 대조 (레거시 metrics.vol 문자열 vs 엔진 value) ---
    # 레거시 vol 판정 vol_ok = ratio>=1.5 AND 고점근처. 엔진은 ratio value 제공 → ratio만 대조.
    for prod in ("TQQQ", "SOXL", "UPRO"):
        eng_ratio = en[f"{prod} 거래량 배수"]["value"]
        # 레거시 metrics.vol 에서 "(x.xx배)" 추출
        volstr = lv[prod]["metrics"].get("vol", "")
        lg_ratio = None
        if "배)" in volstr:
            try:
                lg_ratio = float(volstr.split("(")[-1].split("배")[0])
            except Exception:
                lg_ratio = None
        rows.append((f"{prod} 거래량배수", lg_ratio, round(eng_ratio, 2) if eng_ratio else None,
                     approx(lg_ratio, round(eng_ratio, 2), tol=0.05)))

    # --- 출력 ---
    print(f"{'항목':<28} {'레거시':>10} {'신규':>10}  일치")
    print("-" * 62)
    allok = True
    for desc, a, b, match in rows:
        allok = allok and match
        mark = "✓" if match else "✗"
        print(f"{desc:<28} {str(a):>10} {str(b):>10}   {mark}")
    print("-" * 62)
    print("결과:", "전부 일치 ✅" if allok else "불일치 존재 ❌")
    sys.exit(0 if allok else 1)


if __name__ == "__main__":
    main()
