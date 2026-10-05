#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""신호 백테스트 (책 무관) — 과거 N일 동안 매일 '그날 장 마감 기준' 판정을 다시 내고,
그 판정 뒤에 실제로 가격이 어떻게 갔는지 잰다.

판정은 라이브와 같은 조건 트리(books/<slug>/tree.json)와 같은 등급 코드(tree_grade)가 낸다.
트리 연산은 전부 인과적이라(그날까지의 값만 씀 — verify_primitives 가 강제) 전체 이력을 한 번
계산해 날짜로 꺼낸다. 시세는 md_feed → jhts 시세팀에서 온다.

측정 규약(신호 검증 — 청산 규칙은 흉내내지 않는다):
  · 신호일 T 의 판정은 T 종가까지의 데이터로 낸다.
  · 진입가 = T+1 시가 (마감 후 판정 → 다음 날 매수; T 종가 진입은 미래를 본 셈이 된다).
  · H거래일 수익률 = T+H 종가 ÷ 진입가 − 1  (H = 5·10·20).
  · 같은 등급이 며칠 이어지면 한 번의 신호로 센다(연속 구간 첫날만 진입) — 겹쳐 세면
    같은 상승을 여러 번 번 것처럼 부풀려진다.
  · 비교 기준 = 같은 종목에 '아무 날이나' 진입했을 때(전체 거래일)의 같은 수익률.

수동(manual) 조건은 과거를 확인할 수 없다. ✅(확인 없이도 매수)와 🟡(확인되면 매수)를 따로 세고,
'✅+🟡' 줄은 수동 조건이 전부 확인됐다고 가정한 낙관치다.

사용:
    python -m operations.backtest <slug> [--days 365] [--json]   → logs/backtest-<slug>.json
    python -m operations.backtest <slug> --page                  → backtest-<slug>.json (책 페이지 '백테스트' 탭, 1년·3년)
    python -m operations.backtest <slug> --engine vectorbt       → 계산기(operations/portfolio)로 자산곡선·MaxDD·샤프 (추가 경로)

--engine vectorbt 는 기존 경로를 건드리지 않는 '옆에 나란히' 길이다(플래그 없으면 전부 그대로).
같은 거래(머리=tree 가 낸 신호·분할·매도)를 vectorbt 로 굴려 포트폴리오 지표(자산곡선·MaxDD·샤프·총수익)를
낸다. 거래수·승률·거래당 평균(머리가 정한 거래 경계로 집계한 옛 정의)의 parity 도 나란히 보여준다.
"""
import collections
import json
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone

from shared.paths import BASE, LOGS, ensure_dir, write_text, backtest_path
from shared import trades as trades_mod, tree_grade
from operations import portfolio, driver

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
def fetch_history(tree, days):
    """트리(여섯 칸 전부)가 쓰는 심볼의 일봉 — days + 워밍업만큼. 수집은 tree_grade.history 한 곳."""
    return tree_grade.history(tree, (datetime.now() - timedelta(days=days + tree_grade.WARMUP_DAYS)).strftime("%Y%m%d"))


def run(slug, days=365, hist=None, tree=None, unobserved=None):
    """hist 를 주면 시세를 다시 받지 않는다(여러 기간을 한 번에 돌릴 때).
    unobserved="exclude" = 분봉이 없어 관측 못 한 장중 조건(asof observe — 개장 전 선물 등)을 빼고 판단한다."""
    tree = tree or tree_grade.load_tree(slug)
    if tree is None:
        raise SystemExit("books/%s/tree.json 없음 — 조건 트리가 있어야 백테스트한다" % slug)
    today = datetime.now()
    start = (today - timedelta(days=days)).strftime("%Y%m%d")
    hist = hist if hist is not None else fetch_history(tree, days)
    missing = sorted(s for s, cs in hist.items() if not cs)

    # 신호 = driver 단일 입구(일봉 벡터 1회계산 경로). 백테스트는 그 신호 뒤에 집계·계산기를 붙인다
    #   (머리=판단/계산기=계산 분리 — 여기선 머리가 낸 신호를 '받아쓰기'만 한다). evals=ProductEval(워밍업·수동조건).
    #   axis="1d" 강제 — 일봉 백테스트는 늘 일봉축이다(트리에 분봉 관측 잎이 섞여 finest_tf 가 "1m"이어도).
    sig = driver.run(tree, hist, start=start, unobserved=unobserved, axis="1d")

    rows, summary, manual, period, trade_res, incomplete = [], {}, {}, None, {}, {}
    for p in tree["products"]:
        cs = hist.get(p) or []
        cal = [c.date for c in cs]
        pe = sig["evals"][p]
        pts = sig["series"][p]
        prow = [{"date": pt["date"], "prod": p, "key": pt["key"], "grade": pt["grade"]} for pt in pts]
        inc_days = sum(1 for pt in pts if pt["incomplete"])   # 워밍업 부족 날 수 — ❔(불완전)로 뺀 날
        if inc_days:
            # 불완전 데이터 표면화(missing_symbols 패턴) — 필요 워밍업 대비 확정 봉이 모자란 날 수.
            #   그 날들의 1d 신호는 조용히 계산하지 않고 ❔(판정 불가)로 뺐다.
            incomplete[p] = {"required_warmup": pe.warmup, "incomplete_days": inc_days}
        rows.extend(prow)
        summary[p] = _summarize(prow, cs)
        # 거래: 매수 신호(✅·🟡) 시작일 다음 날 시가 진입 → 매도 규칙으로 청산(보유 중 신호는 건너뜀)
        pos_of = {d: i for i, d in enumerate(cal)}
        starts, prev = [], False
        for r in prow:
            b = r["key"] in ("buy", "confirm")
            if b and not prev:
                starts.append(pos_of[r["date"]])
            prev = b
        exits, src = trades_mod.exits_of(tree, p)
        tl = trades_mod.build_trades(tree, p, hist, cal, starts, exits)
        trade_res[p] = {"exit_source": src, "tranche_note": trades_mod.tranche_note(tree, p),
                        "stats": trades_mod._parity_stats(tl), "trades": tl}
        manual[p] = [{"section": s, "rule": l, "ref": r} for s, l, r in pe.manual_items()]
        if prow and period is None:
            period = [prow[0]["date"], prow[-1]["date"], len(prow)]
    return {"slug": slug, "title": (tree.get("source") or {}).get("book", slug),
            "period": period[:2] if period else None, "trading_days": period[2] if period else 0,
            "horizons": list(HORIZONS), "missing_symbols": missing, "incomplete_warmup": incomplete, "manual": manual,
            "summary": summary, "trades": trade_res, "daily": rows, "generated": today.isoformat(timespec="seconds")}


# ------------------------------------------------------------------ 출력
def _fmt(s):
    if not s or not s.get("n"):
        return "      -      "
    return "%+6.2f%% %3.0f%%" % (s["avg"], s["win"])


def build_text(res):
    L = ["📊 백테스트 — %s" % res["title"]]
    if not res["period"]:
        return "\n".join(L + ["데이터 없음"])
    L.append("기간 %s ~ %s (%d거래일) · 진입=신호 다음날 시가 · 값=평균수익률 승률"
             % (res["period"][0], res["period"][1], res["trading_days"]))
    head = "  %-16s %5s %4s  " % ("등급", "일수", "신호") + "  ".join("%-13s" % ("%d일 후" % h) for h in HORIZONS)
    order = list(tree_grade.GRADES.values()) + [BUY_OR_CONFIRM]
    for p, s in res["summary"].items():
        L.append("")
        L.append("■ %s  (기간 보유 %+.1f%%)" % (p, s["buy_hold"] or 0))
        L.append(head)
        for g in order:
            x = s["grades"].get(g)
            if x and (x["days"] or g == BUY_OR_CONFIRM):
                L.append("  %-16s %5d %4d  " % (g, x["days"], x["signals"])
                         + "  ".join(_fmt(x["fwd"][h]) for h in HORIZONS))
        L.append("  %-16s %5s %4s  " % ("(아무 날)", "", "")
                 + "  ".join(_fmt(s["baseline"][h]) for h in HORIZONS))
    L.append("")
    L.append("■ 거래 성적 — 매수 신호 다음날 시가 진입 · 매도 규칙으로 청산 vs 같은 진입 20거래일 보유")
    L.append("  %-5s %-14s %4s %4s  %-18s %6s  %-18s" % ("상품", "매도 기준", "거래", "미청산",
                                                      "매도규칙 승률·평균", "보유일", "20일보유 승률·평균"))
    for p, t in res["trades"].items():
        st = t["stats"]
        a = "%3.0f%% %+6.2f%%" % (st["win"], st["avg"]) if "win" in st else "      -      "
        b = "%3.0f%% %+6.2f%%" % (st["f20_win"], st["f20_avg"]) if "f20_win" in st else "      -      "
        L.append("  %-5s %-14s %4d %4d  %-18s %6s  %-18s" % (p, t["exit_source"], st["trades"], st["open"], a,
                                                         "%.1f" % st["days"] if "days" in st else "-", b))
        if st["rule_hits"]:
            L.append("        매도 발동: " + " · ".join("%s %d" % kv for kv in st["rule_hits"].items()))
    man = [(p, m) for p, ms in res["manual"].items() for m in ms]
    if man:
        L.append("")
        L.append("※ 수동 조건 %d개 — 과거를 확인할 수 없어 ✅ 는 '확인 안 됨'으로, ✅+🟡 는 '확인됨'으로 셈:" % len(man))
        for p, m in man:
            L.append("   - [%s %s] %s" % (p, m["section"], m["rule"]))
    if res["missing_symbols"]:
        L.append("※ 시세를 못 받은 심볼: %s (그 조건은 판정 불가)" % ", ".join(res["missing_symbols"]))
    if res.get("incomplete_warmup"):
        L.append("※ 워밍업 부족(불완전 데이터) — 트리가 쓰는 가장 긴 창이 덜 차 그 날들의 1d 신호는 ❔(판정 보류)로 뺐다:")
        for p, w in res["incomplete_warmup"].items():
            L.append("   - %s: 필요 워밍업 %d거래일 · 부족한 날 %d개" % (p, w["required_warmup"], w["incomplete_days"]))
    L.append("※ 과거 성적이 미래를 보장하지 않는다. 신호 수가 적으면 참고용이다.")
    return "\n".join(L)


# ------------------------------------------------------------------ 웹페이지용 요약
PAGE_PERIODS = (("1y", 365), ("3y", 1095))


def page_data(slug):
    """책 페이지 '백테스트' 탭이 읽는 요약(일별 행 제외). 시세는 가장 긴 기간으로 한 번만 받는다."""
    tree = tree_grade.load_tree(slug)
    if tree is None:
        raise SystemExit("books/%s/tree.json 없음" % slug)
    hist = fetch_history(tree, max(d for _, d in PAGE_PERIODS))
    out = {"slug": slug, "generated": datetime.now().isoformat(timespec="seconds"),
           "horizons": list(HORIZONS), "grades": list(tree_grade.GRADES.values()),
           "buy_or_confirm": BUY_OR_CONFIRM,
           # 표준 매도 규칙의 짧은 표시(예 '+9%/−5%/10일') — shared/trades.STANDARD 에서 파생(단일 출처).
           #   화면(backtest-ui)은 이 값을 받아 쓰고 숫자를 복붙하지 않는다.
           "standard_exit_label": trades_mod.standard_label(), "periods": {}}
    for key, days in PAGE_PERIODS:
        res = run(slug, days, hist=hist, tree=tree)
        out["periods"][key] = {
            "days": days, "period": res["period"], "trading_days": res["trading_days"],
            "missing_symbols": res["missing_symbols"], "manual": res["manual"],
            "products": {p: dict(res["summary"][p], trades=res["trades"][p]) for p in res["summary"]}}
    return out


# ------------------------------------------------------------------ 새 계산기 경로(--engine vectorbt · 1단계 추가)
def run_vectorbt(slug, days=365, hist=None, tree=None, unobserved=None):
    """기존 run()으로 거래(머리가 낸 신호·분할·매도)를 얻고, 그 거래를 계산기(operations/portfolio)로
    다시 굴려 포트폴리오 지표(자산곡선·MaxDD·샤프·총수익)를 더한다. 기존 경로는 그대로 두고 옆에 나란히 둔다.

    거래 경계·체결가·체결일은 run()이 쓰는 규칙 평가 워크(shared.trades.build_trades)가 정한 그대로 재사용한다
    (머리의 규약·분할/매도 규칙을 계산기가 다시 정하지 않는다 — '머리=판단/계산기=계산' 분리)."""
    tree = tree or tree_grade.load_tree(slug)
    if tree is None:
        raise SystemExit("books/%s/tree.json 없음 — 조건 트리가 있어야 백테스트한다" % slug)
    hist = hist if hist is not None else fetch_history(tree, days)
    res = run(slug, days, hist=hist, tree=tree, unobserved=unobserved)
    vbt_products = {}
    for p in tree["products"]:
        cs = hist.get(p) or []
        cal = [c.date for c in cs]
        closes = [c.close for c in cs]
        tl = res["trades"].get(p, {}).get("trades") or []
        vbt_products[p] = portfolio.run_product(p, cal, closes, tl)
    return {"slug": slug, "title": res["title"], "period": res["period"],
            "trading_days": res["trading_days"], "engine": "vectorbt",
            "old_trades": res["trades"], "vectorbt": vbt_products,
            "generated": res["generated"]}


def build_vectorbt_text(vres):
    """포트폴리오 지표(총수익·MaxDD·샤프·자산곡선 점 수)와 parity(머리가 정한 거래 경계로 센 거래수·승률·거래당 평균)를 나란히."""
    L = ["📊 백테스트 (vectorbt 계산기) — %s" % vres["title"]]
    if not vres["period"]:
        return "\n".join(L + ["데이터 없음"])
    L.append("기간 %s ~ %s (%d거래일) · 거래=머리(tree)가 낸 신호·분할·매도 · 계산=vectorbt"
             % (vres["period"][0], vres["period"][1], vres["trading_days"]))
    L.append("")
    L.append("■ 포트폴리오 지표(vectorbt) · parity(머리가 정한 거래 경계로 센 옛 정의)")
    head = ("  %-6s %-6s %9s %8s %7s %6s   | parity(옛정의)  %5s %6s %8s"
            % ("상품", "시장", "총수익", "MaxDD", "샤프", "자산점", "거래", "승률", "거래당평균"))
    L.append(head)
    for p, v in vres["vectorbt"].items():
        mk = v["market_params"]["market"]
        pa = v["parity"]
        old = vres["old_trades"].get(p, {}).get("stats", {})
        tr = "%+8.2f%%" % v["total_return"] if v["total_return"] is not None else "    -   "
        dd = "%7.2f%%" % v["max_drawdown"] if v["max_drawdown"] is not None else "   -   "
        sh = "%7.3f" % v["sharpe"] if v["sharpe"] is not None else "   -   "
        win = "%5.1f%%" % old["win"] if "win" in old else "   -  "
        avg = "%+7.2f%%" % old["avg"] if "avg" in old else "   -    "
        L.append("  %-6s %-6s %9s %8s %7s %6d   | %12s  %4d %6s %8s"
                 % (p, mk, tr, dd, sh, v["equity_points"], "", pa.get("trades", 0), win, avg))
        pf = v["position_facts"]
        if pf:
            L.append("        (열린 포지션) 진입가 %.2f · 평단 %.2f · 현재수익률 %s · 최고 %.2f · 최저 %.2f · 보유 %d일"
                     % (pf["entry_px"], pf["avg_px"],
                        ("%+.2f%%" % pf["ret"]) if pf["ret"] is not None else "-",
                        pf["high"] or 0, pf["low"] or 0, pf["days"]))
    L.append("")
    L.append("※ 거래수·승률·거래당평균은 '머리가 정한 거래 경계(한 진입→청산)'로 센 옛 정의 그대로다")
    L.append("  (글루가 낸 체결 일정을 그대로 vectorbt 에 넣으므로 거래당 수익률은 구성상 동일).")
    L.append("※ MaxDD=자산곡선 최고점 대비 최대 하락폭(양수%%) · 샤프=일별수익률 연율화(무위험0) · 총수익=(마지막자산/시작자본)−1.")
    return "\n".join(L)


# ------------------------------------------------------------------ 장중(분봉) 백테스트 — 통합 스테핑 코어 + 계산기
# 분봉 축 '봉' — build_trades·portfolio 는 .date/.open/.close 만 쓴다(일봉 Candle 과 같은 접근).
_MinuteBar = collections.namedtuple("_MinuteBar", "date open high low close volume")


def _minute_axis(hist, prod, timeline):
    """장중 백테스트용 분봉 축을 만든다 — asof 타임라인을 '달력'으로, 각 asof 의 그 상품 분봉을 '봉'으로.

    cal   = asof 키(YYYYMMDDHHMM, UTC) 오름차순 — 분봉 간격의 '거래 시점' 축(일봉 하루 대신 분 한 틱).
    mhist = 그 축의 History(그 상품 분봉 OHLCV 를 봉으로) — build_trades 가 '다음 봉 시가 진입'을 분봉에 적용한다.
    분봉 데이터가 그 asof 에 없으면 그 봉은 빠진다(가짜로 채우지 않는다 — 정직한 한계)."""
    mins = (getattr(hist, "minutes", {}) or {}).get(prod) or {}
    bars = []
    for asof in timeline:
        k = asof.astimezone(timezone.utc).strftime("%Y%m%d%H%M")
        b = mins.get(k)
        if b is None:
            continue
        if not isinstance(b, dict):
            b = {"open": b, "high": b, "low": b, "close": b, "volume": 0.0}
        bars.append(_MinuteBar(k, b.get("open"), b.get("high"), b.get("low"), b.get("close"), b.get("volume")))
    cal = [b.date for b in bars]
    mh = tree_grade.History({prod: bars})
    mh.minutes = getattr(hist, "minutes", {})
    return cal, mh


def _starts_from_series(rows, cal):
    """장중 신호 시계열(step 결과)에서 '매수 신호(✅·🟡) 연속 구간 첫 asof'의 분봉 축 인덱스 목록.
    일봉 백테스트의 starts 규칙(연속 신호는 첫 점만 진입)을 분봉 축에 그대로 적용한다 —
    보유 중 신호는 build_trades 가 건너뛴다(한 상품 포지션 하나)."""
    pos_of = {d: i for i, d in enumerate(cal)}
    starts, prev = [], False
    for r in rows:
        b = r["key"] in ("buy", "confirm")
        k = r["asof"].replace("-", "").replace(":", "").replace("T", "")[:12]  # ISO → YYYYMMDDHHMM
        if b and not prev and k in pos_of:
            starts.append(pos_of[k])
        prev = b
    return starts


def run_intraday(slug, hist=None, tree=None, limit=None):
    """장중(분봉) 백테스트 — 신호 생성 단일 입구(driver.run)로 분 단위 신호를 얻고, 그 분봉 종가 시리즈로
    vectorbt 계산기(operations.portfolio)를 돌려 '장중 백테스트' 지표를 낸다(신호만 내던 재생에 계산기를 붙임).

    머리=판단/계산기=계산 분리는 그대로다: 신호(✅·🟡)는 driver.run(분봉이면 내부에서 step=product_verdict)이 각 asof 에서 내고,
    체결 일정(분봉 다음봉 시가 진입 → 매도 규칙으로 청산)은 shared.trades.build_trades 가, 돈·지표는
    operations.portfolio 가 낸다. 일봉 백테스트와 다른 것은 '축'(일봉 하루 → 분봉 한 틱)뿐이다.

    정직한 한계: 분봉은 jhts 분봉 범위(지수·선물 ~7거래일)만 — 짧은 구간 샤프/MaxDD 는 참고용(limit 표면화)."""
    tree = tree or tree_grade.load_tree(slug)
    if tree is None:
        raise SystemExit("books/%s/tree.json 없음 — 조건 트리가 있어야 백테스트한다" % slug)
    if hist is None:
        hist = driver.load_hist(tree)
    # 신호 = driver 단일 입구(분봉 per-asof). truncate=True — 각 asof 를 그 세션일 이하로 자른 hist 로 판정한다
    #   (verify_signal_parity 가 일봉 파리티를 증명한 바로 그 방식). 과거 세션도 '그 세션 자신의 일봉 regime +
    #   그 시점 분봉'으로 충실히 재생된다(truncate 없이 full hist 면 product_verdict 가 늘 오늘 봉을 판정해 과거
    #   세션 regime 이 틀린다 — 아키텍트 확인). 신호 뒤에 체결 일정·vectorbt 계산기만 백테스트가 붙인다.
    sig = driver.run(tree, hist, limit=limit, truncate=True)
    tf, timeline, sessions, prods, series = (sig["tf"], sig["timeline"], sig["sessions"],
                                             sig["prods"], sig["series"])
    vbt_products, signal_summary = {}, {}
    for p in prods:
        rows = series.get(p) or []
        cal, mh = _minute_axis(hist, p, timeline)
        closes = [c.close for c in mh.get(p)]
        starts = _starts_from_series(rows, cal)
        exits, src = trades_mod.exits_of(tree, p)
        tl = trades_mod.build_trades(tree, p, mh, cal, starts, exits)   # 분봉 축에 체결 일정(다음봉 시가 진입)
        vbt_products[p] = portfolio.run_product(p, cal, closes, tl) if cal else None
        signal_summary[p] = {"points": len(rows), "buy_signals": len(starts),
                             "exit_source": src, "bars": len(cal)}
    return {"slug": slug, "title": (tree.get("source") or {}).get("book", slug),
            "engine": "vectorbt-intraday", "finest_tf": tf, "prods": prods,
            "sessions": sessions, "points": len(timeline), "signals": signal_summary,
            "vectorbt": vbt_products, "limit": driver.limit_note(tree, hist, tf, timeline, sessions),
            "generated": datetime.now().isoformat(timespec="seconds")}


def build_intraday_text(ires):
    """장중 백테스트 결과 — 분봉 신호 수 + vectorbt 지표(짧은 구간이면 참고용 표시)."""
    L = ["📊 장중(분봉) 백테스트 — %s  (가장 촘촘한 tf = %s · 계산=vectorbt)" % (ires["title"], ires["finest_tf"])]
    L.append("재생 점 %d개 · 세션 %s" % (ires["points"], " ".join(ires["sessions"]) or "-"))
    L.append("※ 한계: " + ires["limit"]["reason"])
    if not ires["points"]:
        return "\n".join(L)
    L.append("")
    L.append("■ 분봉 신호 + 포트폴리오 지표(vectorbt · 분봉 축) — bars=분봉 틱 수, 보유일=분봉 틱 수(일 아님)")
    head = ("  %-6s %-6s %6s %6s %9s %8s %7s   | %-14s %5s %6s %8s"
            % ("상품", "시장", "틱수", "매수", "총수익", "MaxDD", "샤프", "매도기준", "거래", "승률", "거래당평균"))
    L.append(head)
    for p, v in ires["vectorbt"].items():
        sg = ires["signals"][p]
        if v is None:
            L.append("  %-6s  (분봉 봉 없음 — 그 상품은 장중 데이터가 비어 재생 불가)" % p)
            continue
        mk = v["market_params"]["market"]
        pa = v["parity"]
        tr = "%+8.2f%%" % v["total_return"] if v["total_return"] is not None else "    -   "
        dd = "%7.2f%%" % v["max_drawdown"] if v["max_drawdown"] is not None else "   -   "
        sh = "%7.3f" % v["sharpe"] if v["sharpe"] is not None else "   -   "
        win = "%5.1f%%" % pa["win"] if "win" in pa else "   -  "
        avg = "%+7.2f%%" % pa["avg"] if "avg" in pa else "   -    "
        L.append("  %-6s %-6s %6d %6d %9s %8s %7s   | %-14s %4d %6s %8s"
                 % (p, mk, sg["bars"], sg["buy_signals"], tr, dd, sh, sg["exit_source"],
                    pa.get("trades", 0), win, avg))
    L.append("")
    L.append("※ 축이 '분봉 한 틱'이라 보유일·MaxDD·샤프는 분봉 축 기준(샤프 연율화는 봉 간격으로 맞췄다 — 짧은 구간은 참고용).")
    L.append("※ 장중 asof 의 일봉 잎 = 마지막 '확정' 일봉(= 전 세션 종가 — look-ahead 0). 그날 일봉은 세션 마감(종가 봉)에")
    L.append("   비로소 확정되므로, 장중 신호는 '전 세션 일봉 regime + 그 시점 분봉'이다. 그날 일봉 판정과의 수렴은 종가 봉")
    L.append("   asof 에서 일어나는데, jhts 분봉이 마감 1분 전(예 19:59)까지만 와 그 수렴점은 분봉 범위 밖이다(정직한 한계).")
    return "\n".join(L)


def _cli():
    argv = sys.argv[1:]
    slug = next((a for a in argv if not a.startswith("-") and not a.isdigit()), None)
    if not slug:
        print("사용법: python -m operations.backtest <slug> [--days 365] [--json]", file=sys.stderr)
        sys.exit(2)
    if "--page" in argv:
        data = page_data(slug)
        path = backtest_path(slug)
        write_text(path, json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str))
        print("웹페이지용 백테스트 → %s" % path)
        return
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 365
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    unobserved = "exclude" if "--exclude-unobserved" in argv else None
    # --intraday : 장중(분봉) 백테스트 — finest_tf 가 분봉(5m/1m)인 트리를 분 단위로 밟아 계산기까지 돌린다.
    #   --engine vectorbt 라도 트리의 finest_tf 가 분봉이면 자동으로 이 경로로 보낸다(일봉 트리는 벡터 경로 유지).
    if "--intraday" in argv or ("--engine" in argv and argv[argv.index("--engine") + 1] == "vectorbt"
                                and driver.finest_tf(tree_grade.load_tree(slug)) != "1d"):
        ires = run_intraday(slug, limit=limit)
        if "--json" in argv:
            print(json.dumps(ires, ensure_ascii=False, indent=2, default=str))
        else:
            print(build_intraday_text(ires))
        return
    # --engine vectorbt (일봉 트리) : 기존 벡터 1회계산 경로 → 계산기(추가·비파괴). 일봉 파리티·속도 그대로.
    if "--engine" in argv and argv[argv.index("--engine") + 1] == "vectorbt":
        vres = run_vectorbt(slug, days, unobserved=unobserved)
        if "--json" in argv:
            print(json.dumps(vres, ensure_ascii=False, indent=2, default=str))
        else:
            print(build_vectorbt_text(vres))
        return
    # --exclude-unobserved : 분봉이 없어 관측 못 한 장중 조건(asof observe — 개장 전 선물 등)을 빼고 판단(나머지 조건으로 진입)
    res = run(slug, days, unobserved=unobserved)
    res["unobserved"] = "제외하고 판단" if "--exclude-unobserved" in argv else "수동(🟡)으로 둠"
    ensure_dir(LOGS)
    write_text(os.path.join(LOGS, "backtest-%s.json" % slug),
               json.dumps(res, ensure_ascii=False, indent=1))
    if "--json" in argv:
        print(json.dumps({k: v for k, v in res.items() if k != "daily"}, ensure_ascii=False, indent=2))
    else:
        print(build_text(res))


if __name__ == "__main__":
    _cli()
