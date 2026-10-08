#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""신호 패리티 검사 — "백테스트 신호 == 실시간 신호"를 **실제 진입점으로 돌려** 증명한다 (구간③).

## 왜 남아 있나

백테스트와 라이브는 이제 같은 판정기(Judge.grade)를 지난다. 그래도 둘이 **구조적으로 같을 수는 없다** —
입력이 다르기 때문이다: 백테스트는 전체 이력을 한 번 세워 과거 날 i 를 꺼내고(asof 없음), 라이브는 그날 D 마감
직후 가진 이력(D 이하로 잘린 hist)으로 마지막 봉을 asof(그날 마감 시각)에 판정한다. 이 둘이 같으려면 cond 연산이
인과적이고(미래를 안 봄) asof 확정봉 가리기(settled)가 일봉 마감과 맞아야 한다 — 그걸 실행으로 확인하는 게 이 검사다.

## 두 경로 (실제 진입점)

  · 백테스트 경로 : `trading.backtest.run(slug, days=N)` 의 `daily` 행 → {date, prod, key, grade}.
                    (내부에서 Timeline 이 Judge(tree, p, hist, cal).grade(i) 를 전체 달력에 돌린다.)
  · 실시간 경로   : 각 과거일 D 에 대해 hist 를 D 이하로 잘라(Timeline.truncate) `Judge(tree, p, hist, asof).latest()`
                    — 라이브 판정(web.verdict_view.product_verdict)이 등급을 얻는 바로 그 호출이다.
                    asof 는 그날 마감 시점(UTC).

## 무엇을 비교하나

전 상품 × 창(데이터 있는 최근 WINDOW 거래일) 전부에서, 두 경로의 (key, grade) 가 **일치**하는지. 불일치가 하나라도
있으면 (상품·날짜·백테스트·실시간) 을 전부 나열한다 — 숨기지 않는다.

## 분봉(장중)에 대하여

분봉 데이터가 없으면 장중(tf="1m") observe 조건은 두 경로 모두 None→manual 로 떨어진다(의도된 동작). 따라서 이 검사는
**일봉 신호**의 패리티를 증명한다. 분봉이 연결되면 같은 코드가 그 축도 덮는다(asof 를 분봉 범위로 주면 된다).

## 사용

    python -m trading.verify_signal_parity [--window 120] [--slug trend]
    → 일치율 보고. 100% 면 "신호 PARITY ✅", exit 0. 불일치 있으면 전체 목록 + exit 1.
"""
import sys
from datetime import datetime, timedelta, timezone

from shared.paths import live_slugs
from checklist.grade import GRADES, WARMUP_DAYS, history
from checklist.tree_gateway import TreeGateway
from trading import backtest
from trading.judge import Judge
from trading.timeline import Timeline

WINDOW = 120            # 비교할 최근 거래일 수(상품마다 데이터 있는 범위 안에서)
CLOSE_HHMM_UTC = 21     # 미 증시 마감 ≈ 21:00 UTC(서머타임 20:00·표준 21:00) — asof 를 '그날 마감 시점'으로
                        # 둘 때의 시각. 분봉이 없어 일봉 결과엔 영향 없지만, 라이브와 같은 모양의 asof 를 준다.


def _asof_of(date_str):
    """날짜(YYYYMMDD) → 그날 마감 시점(UTC datetime). 라이브 render 가 받는 asof 와 같은 모양."""
    return datetime.strptime(date_str, "%Y%m%d").replace(hour=CLOSE_HHMM_UTC, tzinfo=timezone.utc)


def compare(slug, window=WINDOW):
    """한 책의 두 경로를 실제로 돌려 (상품·날짜)별 (key, grade) 를 비교한다.
    → {total, match, mismatches:[{prod, date, bt_key, bt_grade, live_key, live_grade}], products, window}."""
    tree = TreeGateway.load(slug)
    if tree is None:
        raise SystemExit("books/%s/tree.json 없음" % slug)

    # 라이브 판정(render)과 같은 방식으로 전체 일봉을 한 번 받는다(워밍업 포함).
    # window 만큼 + 워밍업을 넉넉히 — backtest.run 의 days 도 이 창을 덮게 준다.
    full = history(tree, (datetime.now() - timedelta(days=window * 2 + WARMUP_DAYS + 30)).strftime("%Y%m%d"))

    # 백테스트 경로: 실제 드라이버 진입점. daily 행에서 (prod, date) → (key, grade).
    bt = backtest.run(slug, days=window * 2 + 30, hist=full, tree=tree)
    bt_daily = {(r["prod"], r["date"]): (r["key"], r["grade"]) for r in bt["daily"]}

    mismatches = []
    total = 0
    for p in tree.products():
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
            # 실시간 경로: 라이브가 D 마감 직후 봤을 입력(D 이하 이력·그날 마감 asof)으로 Judge.latest.
            key, _close = Judge(tree, p, Timeline.truncate(full, d), asof=_asof_of(d)).latest()
            live_row = (key, GRADES[key])
            total += 1
            if live_row != bt_row:
                mismatches.append({"prod": p, "date": d, "bt_key": bt_row[0], "bt_grade": bt_row[1],
                                   "live_key": live_row[0], "live_grade": live_row[1]})
    return {"slug": slug, "total": total, "match": total - len(mismatches),
            "mismatches": mismatches, "products": tree.products(), "window": window}


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
    slugs = [argv[argv.index("--slug") + 1]] if "--slug" in argv else live_slugs()
    if not slugs:
        print("live 책이 없습니다(books.json 의 live:true). --slug <책> 으로 지정하세요.", file=sys.stderr)
        return 2
    reports = [compare(s, window) for s in slugs]
    print(build_text(reports))
    ok = all(r["total"] and not r["mismatches"] for r in reports) and any(r["total"] for r in reports)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
