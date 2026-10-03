#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""신호 패리티 검사 — "백테스트 신호 == 실시간 신호"를 **실제 드라이버로 돌려** 증명한다 (구간④).

## 왜 있나

앞 세 단계(트리거 → asof → 평가)가 백테스트와 실시간에서 **같은 시점(asof)에 같은 신호·등급**을
내지 못하면, 백테스트 성적은 실전과 무관한 숫자가 된다. 그래서 이 검사가 최우선 correctness 게이트다.
raw ProductEval 끼리 비교하는 건 두 경로가 같은 클래스를 쓰니 trivial 하다 — 여기서는 **두 드라이버의
실제 진입점**을 각각 타서, 입력(hist·cal·asof·index) 구성까지 포함해 결과가 일치하는지 본다.

## 두 경로 (실제 드라이버 진입점)

  · 백테스트 경로 : `operations.backtest.run(slug, days=N)` 의 `daily` 행 → {date, prod, key, grade}.
                    (내부에서 ProductEval(tree, p, hist, cal).grade_key(i) 를 전체 달력에 돌린다.)
  · 실시간 경로   : 각 과거일 D 에 대해 `verdict.verdict_engine.product_verdict(tree, p, hist, {}, asof)`.
                    라이브 드라이버(render)가 하는 그대로 — hist 는 tree_grade.history 로 받은 일봉,
                    asof 는 그날 마감 시점(UTC), index 는 cfg["index"] — 로 호출한다. 다만 라이브는 늘
                    "마지막 봉(len(cal)-1)"을 판정하므로, 과거일 D 를 재생하려면 그 hist 를 **D 이하로
                    잘라** 마지막 봉이 D 가 되게 한다(라이브가 D 마감 직후 봤을 그 데이터 그대로).
                    부작용(파일쓰기·알림)이 있는 render 대신, 그 안에서 상품 하나를 판정하는
                    product_verdict 를 같은 방식으로 호출한다.

## 무엇을 비교하나

trend·moneycopy 전 상품 × 창(데이터 있는 최근 WINDOW 거래일) 전부에서, 두 경로의 (key, grade) 가
**일치**하는지. 불일치가 하나라도 있으면 (상품·날짜·백테스트·실시간) 을 전부 나열한다 — 숨기지 않는다.

## 분봉(장중)에 대하여

분봉 데이터는 아직 연결 전이라(minutes 비어 있음) 장중(tf="1m") observe 조건은 두 경로 모두 None→manual
로 떨어진다(의도된 동작). 따라서 이 검사는 **일봉 신호**의 패리티를 증명한다. 분봉이 연결되면 같은 코드가
그 축도 덮는다(asof 를 분봉 범위로 주면 된다).

## 단방향(폭포수)

이 파일은 operations/(구간④)에 있고 verdict·shared·operations.backtest(전부 downward/동일)만 import
한다. 상류(playbook·checklist·verdict·shared)는 이 파일을 import 하지 않는다 — verify_teams 가 강제.

## 사용

    python -m operations.verify_signal_parity [--window 120] [--slug trend]
    → 일치율 보고. 100% 면 "신호 PARITY ✅", exit 0. 불일치 있으면 전체 목록 + exit 1.
"""
import sys
from datetime import datetime, timedelta, timezone

from shared.paths import live_slugs
from shared import tree_grade
from operations import backtest
from verdict import verdict_engine

WINDOW = 120            # 비교할 최근 거래일 수(상품마다 데이터 있는 범위 안에서)
CLOSE_HHMM_UTC = 21     # 미 증시 마감 ≈ 21:00 UTC(서머타임 20:00·표준 21:00) — asof 를 '그날 마감 시점'으로
                        # 둘 때의 시각. 분봉이 없어 일봉 결과엔 영향 없지만, 라이브와 같은 모양의 asof 를 준다.


def _truncate(full, upto):
    """full(History) 을 날짜 upto(YYYYMMDD) 이하로 자른 새 History. 분봉(minutes)은 그대로 넘긴다
    — 라이브가 D 마감 직후 보유했을 데이터(그날까지의 확정 일봉)를 그대로 재현한다."""
    t = tree_grade.History({s: [c for c in (cs or []) if c.date <= upto] for s, cs in full.items()})
    t.minutes = getattr(full, "minutes", {})
    return t


def _asof_of(date_str):
    """날짜(YYYYMMDD) → 그날 마감 시점(UTC datetime). 라이브 render 가 받는 asof 와 같은 모양."""
    return datetime.strptime(date_str, "%Y%m%d").replace(hour=CLOSE_HHMM_UTC, tzinfo=timezone.utc)


def compare(slug, window=WINDOW):
    """한 책의 두 경로를 실제로 돌려 (상품·날짜)별 (key, grade) 를 비교한다.
    → {total, match, mismatches:[{prod, date, bt_key, bt_grade, live_key, live_grade}], products, window}."""
    tree = tree_grade.load_tree(slug)
    if tree is None:
        raise SystemExit("books/%s/tree.json 없음" % slug)

    # 라이브 드라이버(render)와 같은 방식으로 전체 일봉을 한 번 받는다(워밍업 포함).
    # window 만큼 + 워밍업을 넉넉히 — backtest.run 의 days 도 이 창을 덮게 준다.
    full = tree_grade.history(
        tree, (datetime.now() - timedelta(days=window * 2 + tree_grade.WARMUP_DAYS + 30)).strftime("%Y%m%d"))

    # 백테스트 경로: 실제 드라이버 진입점. daily 행에서 (prod, date) → (key, grade).
    bt = backtest.run(slug, days=window * 2 + 30, hist=full, tree=tree)
    bt_daily = {(r["prod"], r["date"]): (r["key"], r["grade"]) for r in bt["daily"]}

    mismatches = []
    total = 0
    for p in tree["products"]:
        cs = full.get(p) or []
        if not cs:
            continue
        # 비교할 날짜 = 이 상품의 데이터 중 '최근 window 거래일'. 백테스트 daily 에도 있는 날만 센다
        # (양쪽 다 판정한 날끼리만 비교 — 한쪽이 범위 밖이면 비교 대상이 아니다).
        dates = [c.date for c in cs][-window:]
        for d in dates:
            bt_row = bt_daily.get((p, d))
            if bt_row is None:
                continue
            # 실시간 경로: 라이브 드라이버가 D 마감 직후 봤을 입력으로 product_verdict 호출.
            th = _truncate(full, d)
            v, _pe = verdict_engine.product_verdict(tree, p, th, {}, asof=_asof_of(d))
            live_row = (v["key"], v["grade"])
            total += 1
            if live_row != bt_row:
                mismatches.append({"prod": p, "date": d, "bt_key": bt_row[0], "bt_grade": bt_row[1],
                                   "live_key": live_row[0], "live_grade": live_row[1]})
    return {"slug": slug, "total": total, "match": total - len(mismatches),
            "mismatches": mismatches, "products": list(tree["products"].keys()), "window": window}


def build_text(reports):
    L = ["📐 신호 패리티 검사 — 백테스트 신호 == 실시간 신호 (일봉, 실제 드라이버 진입점)"]
    grand_total = sum(r["total"] for r in reports)
    grand_match = sum(r["match"] for r in reports)
    for r in reports:
        pct = (r["match"] / r["total"] * 100) if r["total"] else 0.0
        L.append("")
        L.append("■ %s  (상품 %s · 최근 %d거래일)" % (r["slug"], " · ".join(r["products"]), r["window"]))
        L.append("   비교 %d · 일치 %d · 불일치 %d  (%.2f%%)" % (r["total"], r["match"], len(r["mismatches"]), pct))
        for m in r["mismatches"]:
            L.append("   ✗ %-6s %s  백테스트=%s / 실시간=%s" % (m["prod"], m["date"], m["bt_grade"], m["live_grade"]))
    L.append("")
    L.append("─" * 50)
    if grand_total and grand_match == grand_total:
        L.append("신호 PARITY ✅  — 총 %d 비교 전부 일치 (백테스트 == 실시간, 일봉)." % grand_total)
    elif grand_total:
        L.append("신호 불일치 ❌  — 총 %d 비교 중 %d 일치 · %d 불일치."
                 % (grand_total, grand_match, grand_total - grand_match))
    else:
        L.append("비교할 데이터 없음 — 시세가 비어 있거나 창이 0이다.")
    L.append("※ 분봉(장중, tf=\"1m\")은 데이터 미연결 → 두 경로 모두 None→manual(🟡)로 떨어져 결과에 영향 없음(정상).")
    L.append("   이 검사는 일봉 신호의 패리티를 증명한다. 분봉이 연결되면 같은 코드가 asof 축으로 그 축도 덮는다.")
    return "\n".join(L)


def main():
    argv = sys.argv[1:]
    window = int(argv[argv.index("--window") + 1]) if "--window" in argv else WINDOW
    slugs = [argv[argv.index("--slug") + 1]] if "--slug" in argv else (live_slugs() or ["trend", "moneycopy"])
    reports = [compare(s, window) for s in slugs]
    print(build_text(reports))
    ok = all(r["total"] and not r["mismatches"] for r in reports) and any(r["total"] for r in reports)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
