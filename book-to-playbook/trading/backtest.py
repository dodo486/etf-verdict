#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""신호 백테스트 (책 무관) — 과거 N일 동안 매일 '그날 장 마감 기준' 판정을 다시 내고,
그 판정 뒤에 실제로 가격이 어떻게 갔는지 잰다.

판정은 라이브와 같은 판정기(trading/judge.Judge — 같은 트리·같은 등급 코드)가 judge.signal_series 로 낸다.
트리 연산은 전부 인과적이라(그날까지의 값만 씀 — verify_primitives 가 강제) 전체 이력을 한 번
계산해 날짜로 꺼낸다. 시세는 md_feed → jhts 시세팀에서 온다.

측정 규약(신호 검증 — 청산 규칙은 흉내내지 않는다):
  · 신호일 T 의 판정은 T 종가까지의 데이터로 낸다.
  · 진입가 = T+1 시가 (마감 후 판정 → 다음 날 매수; T 종가 진입은 미래를 본 셈이 된다).
  · H거래일 수익률 = T+H 종가 ÷ 진입가 − 1  (H = 5·10·20).
  · 같은 등급이 며칠 이어지면 한 번의 신호로 센다(연속 구간 첫날만 진입) — 겹쳐 세면
    같은 상승을 여러 번 번 것처럼 부풀려진다.
  · 비교 기준 = 같은 종목에 '아무 날이나' 진입했을 때(전체 거래일)의 같은 수익률.

거래 성적(진입 → 책 매도 규칙으로 청산)은 매도 정책(trades.exit_policy)이 "book" 일 때만 낸다 — 책에 매도 규칙이
없으면("none") 대체 매도 규칙을 지어내지 않고 위의 신호 검증(매수 신호 뒤 N거래일 보유)만 남는다.

수동(manual) 조건은 과거를 확인할 수 없다. ✅(확인 없이도 매수)와 🟡(확인되면 매수)를 따로 세고,
'✅+🟡' 줄은 수동 조건이 전부 확인됐다고 가정한 낙관치다.

사용:
    python -m trading.backtest <slug> [--days 365]   → books/<slug>/logs/backtest.json (일별 행 뺀 요약은 stdout)
(책 페이지 '백테스트' 탭 데이터는 웹 화면층 web/backtest_page.py 가 이 run() 결과로 빚는다 —
 자산곡선·MaxDD·샤프 등 계산기 지표는 web.backtest_page 가 trading.portfolio 를 직접 불러 낸다.)
"""
import json
import statistics
import sys
from datetime import datetime, timedelta

from shared.paths import book_log, write_text
from trading import trades
from trading.judge import signal_series
from trading.commonTool import open_history

HORIZONS = (5, 10, 20)
BUY_OR_CONFIRM = "✅+🟡 (수동 확인 가정)"


# ------------------------------------------------------------------ 수익률 통계
def _fwd(cs, i, h):
    """cs[i] 가 신호일일 때 T+1 시가 진입 → T+h 종가 수익률(%). 미래 부족이면 None."""
    if i + h >= len(cs) or not cs[i + 1].open:
        return None
    return (cs[i + h].close / cs[i + 1].open - 1) * 100


def _stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "avg": statistics.mean(vals), "median": statistics.median(vals),
            "win": sum(1 for v in vals if v > 0) / len(vals) * 100}


def _bucket(prod_rows, idx, cs, pick):
    """pick(row) 가 참인 날 → {days, signals, fwd} (연속 구간 첫날 진입)."""
    days, starts, prev = 0, [], False
    for r in prod_rows:
        b = pick(r)
        if b:
            days += 1
            if not prev:
                starts.append(r["date"])
        prev = b
    ii = [idx[d] for d in starts if d in idx]
    return {"days": days, "signals": len(starts),
            "fwd": {h: _stats([_fwd(cs, i, h) for i in ii]) for h in HORIZONS}}


def _summarize(prod_rows, cs):
    idx = {c.date: i for i, c in enumerate(cs)}
    grades = {}
    for g in dict.fromkeys(r["grade"] for r in prod_rows):
        grades[g] = _bucket(prod_rows, idx, cs, lambda r, g=g: r["grade"] == g)
    grades[BUY_OR_CONFIRM] = _bucket(prod_rows, idx, cs, lambda r: r["key"] in ("buy", "confirm"))
    all_i = [idx[r["date"]] for r in prod_rows if r["date"] in idx]
    base = {h: _stats([_fwd(cs, i, h) for i in all_i]) for h in HORIZONS}
    hold = (cs[all_i[-1]].close / cs[all_i[0]].close - 1) * 100 if len(all_i) >= 2 else None
    return {"grades": grades, "baseline": base, "buy_hold": hold}


# ------------------------------------------------------------------ 실행
def run(slug, days=365, hist=None, tree=None, unobserved=None):
    """hist 를 주면 시세를 다시 받지 않는다(여러 기간을 한 번에 돌릴 때).
    unobserved="exclude" = 분봉이 없어 관측 못 한 장중 조건(asof observe — 개장 전 선물 등)을 빼고 판단한다."""
    tree, hist = open_history(slug, days, tree, hist)
    today = datetime.now()
    start = (today - timedelta(days=days)).strftime("%Y%m%d")
    missing = sorted(s for s, cs in hist.items() if not cs)

    # 신호 = judge.signal_series(일봉 벡터 1회계산 — 라이브 latest() 와 같은 Judge.grade). 백테스트는 그 신호 뒤에
    #   집계·계산기를 붙인다(판단/계산 분리 — 여기선 판정기가 낸 신호를 '받아쓰기'만 한다). judges=Judge(워밍업·수동조건).
    sig = signal_series(tree, hist, start=start, unobserved=unobserved)

    rows, summary, manual, period, trade_res, incomplete = [], {}, {}, None, {}, {}
    for p in tree.products():
        cs = hist.get(p) or []
        cal = [c.date for c in cs]
        j = sig["judges"][p]
        pts = sig["series"][p]
        prow = [{"date": pt["date"], "prod": p, "key": pt["key"], "grade": pt["grade"]} for pt in pts]
        inc_days = sum(1 for pt in pts if pt["incomplete"])   # 워밍업 부족 날 수 — ❔(불완전)로 뺀 날
        if inc_days:
            # 불완전 데이터 표면화(missing_symbols 패턴) — 필요 워밍업 대비 확정 봉이 모자란 날 수.
            #   그 날들의 1d 신호는 조용히 계산하지 않고 ❔(판정 불가)로 뺐다.
            incomplete[p] = {"required_warmup": j.warmup, "incomplete_days": inc_days}
        rows.extend(prow)
        summary[p] = _summarize(prow, cs)
        # 거래: 매수 신호(✅·🟡) 시작일 다음 날 시가 진입 → 책 매도 규칙으로 청산(보유 중 신호는 건너뜀).
        #   매도 정책(trades.exit_policy)이 "none"(책에 매도 규칙 없음)이면 거래를 만들지 않는다.
        pos_of = {d: i for i, d in enumerate(cal)}
        starts, prev = [], False
        for r in prow:
            b = r["key"] in ("buy", "confirm")
            if b and not prev:
                starts.append(pos_of[r["date"]])
            prev = b
        pol = trades.exit_policy(tree, p)
        if pol == "none":           # 책에 매도 규칙 없음 — 거래를 지어내지 않는다(매수 신호 뒤 N거래일 보유만: summary)
            trade_res[p] = {"exit_policy": pol}
        else:
            exits = tree.exit_rules(p)
            # 매수 크기 = 그날 판정의 '얼마나'(j.amount — 라이브 화면과 같은 Judge 경로)에 금액 정책(trades.size_of)
            tl = trades.build_trades(tree, p, hist, cal, starts, exits, amount=j.amount)
            st = trades._parity_stats(tl)
            trade_res[p] = {"exit_policy": pol, "unsized_note": trades.unsized_note(tree, p, exits),
                            "size_notes": trades.size_notes(st["size_counts"]), "stats": st, "trades": tl}
        manual[p] = [{"section": s, "rule": l, "ref": r} for s, l, r in j.manual_items()]
        if prow and period is None:
            period = [prow[0]["date"], prow[-1]["date"], len(prow)]
    return {"slug": slug, "title": tree.book(slug),
            "period": period[:2] if period else None, "trading_days": period[2] if period else 0,
            "horizons": list(HORIZONS), "missing_symbols": missing, "incomplete_warmup": incomplete, "manual": manual,
            "summary": summary, "trades": trade_res, "daily": rows, "generated": today.isoformat(timespec="seconds")}


# ------------------------------------------------------------------ CLI(디버그용 — JSON. 화면 데이터는 web.backtest_page 가 빚는다)
def _cli():
    argv = sys.argv[1:]
    slug = next((a for a in argv if not a.startswith("-") and not a.isdigit()), None)
    if not slug:
        print("사용법: python -m trading.backtest <slug> [--days 365]", file=sys.stderr)
        sys.exit(2)
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 365
    unobserved = "exclude" if "--exclude-unobserved" in argv else None
    res = run(slug, days, unobserved=unobserved)
    res["unobserved"] = "제외하고 판단" if "--exclude-unobserved" in argv else "수동(🟡)으로 둠"
    write_text(book_log(slug, "backtest.json"), json.dumps(res, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "daily"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _cli()
