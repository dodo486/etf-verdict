#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""책 페이지 '백테스트' 탭 데이터(웹 화면층, 책 무관) — 구간③ 백테스트(trading.backtest.run)·계산기(portfolio)
결과를 화면이 읽는 요약(일별 행 제외, 1년·3년)으로 빚는다. 백테스트를 다시 정의하지 않는다.

사용:
    python -m web.backtest_page <slug>   → backtest-<slug>.json (책 페이지 조립 web/book_page 가 탭으로 심는다)
"""
import json
import sys
from datetime import datetime

from shared.paths import backtest_path, write_text
from checklist.grade import GRADES
from checklist.tree_gateway import TreeGateway
from trading import portfolio, trades
from trading.backtest import BUY_OR_CONFIRM, HORIZONS, fetch_history, run

PAGE_PERIODS = (("1y", 365), ("3y", 1095))


def page_data(slug):
    """책 페이지 '백테스트' 탭이 읽는 요약(일별 행 제외). 시세는 가장 긴 기간으로 한 번만 받는다."""
    tree = TreeGateway.load(slug)
    if tree is None:
        raise SystemExit("books/%s/tree.json 없음" % slug)
    hist = fetch_history(tree, max(d for _, d in PAGE_PERIODS))
    out = {"slug": slug, "generated": datetime.now().isoformat(timespec="seconds"),
           "horizons": list(HORIZONS), "grades": list(GRADES.values()),
           "buy_or_confirm": BUY_OR_CONFIRM,
           # 표준 매도 규칙의 짧은 표시(예 '+9%/−5%/10일') — trading/trades.STANDARD 에서 파생(단일 출처).
           #   화면(backtest-ui)은 이 값을 받아 쓰고 숫자를 복붙하지 않는다.
           "standard_exit_label": trades.standard_label(), "periods": {}}
    for key, days in PAGE_PERIODS:
        res = run(slug, days, hist=hist, tree=tree)
        prods = {}
        for p in res["summary"]:
            d = dict(res["summary"][p], trades=res["trades"][p])
            # 계산기 지표(vectorbt) — 판정기가 낸 '그 거래'(res["trades"])를 portfolio 로 다시 굴려
            #   자산곡선·MaxDD·샤프·총수익을 옛 지표 옆에 나란히 둔다(중복 수집 없음 — 같은 hist·같은 거래).
            cs = hist.get(p) or []
            cal = [c.date for c in cs]
            closes = [c.close for c in cs]
            tl = res["trades"].get(p, {}).get("trades") or []
            d["vectorbt"] = portfolio.run_product(p, cal, closes, tl) if cal else None
            prods[p] = d
        out["periods"][key] = {
            "days": days, "period": res["period"], "trading_days": res["trading_days"],
            "missing_symbols": res["missing_symbols"], "manual": res["manual"],
            "products": prods}
    return out


def _cli():
    slug = next((a for a in sys.argv[1:] if not a.startswith("-")), None)
    if not slug:
        print("사용법: python -m web.backtest_page <slug>", file=sys.stderr)
        sys.exit(2)
    path = backtest_path(slug)
    write_text(path, json.dumps(page_data(slug), ensure_ascii=False, separators=(",", ":"), default=str))
    print("웹페이지용 백테스트 → %s" % path)


if __name__ == "__main__":
    _cli()
