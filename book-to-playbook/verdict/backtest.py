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
    python -m verdict.backtest <slug> [--days 365] [--json]   → logs/backtest-<slug>.json
    python -m verdict.backtest <slug> --page                  → backtest-<slug>.json (책 페이지 '백테스트' 탭, 1년·3년)
"""
import json
import os
import statistics
import sys
from datetime import datetime, timedelta

from shared.paths import BASE, LOGS, ensure_dir, write_text, backtest_path
from shared import trades as trades_mod, tree_grade

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
    unobserved="exclude" = 분봉이 없어 관측 못 한 저자 시각 조건(개장 전 선물 등)을 빼고 판단한다."""
    tree = tree or tree_grade.load_tree(slug)
    if tree is None:
        raise SystemExit("books/%s/tree.json 없음 — 조건 트리가 있어야 백테스트한다" % slug)
    today = datetime.now()
    start = (today - timedelta(days=days)).strftime("%Y%m%d")
    hist = hist if hist is not None else fetch_history(tree, days)
    missing = sorted(s for s, cs in hist.items() if not cs)

    rows, summary, manual, period, trade_res = [], {}, {}, None, {}
    for p in tree["products"]:
        cs = hist.get(p) or []
        cal = [c.date for c in cs]
        pe = tree_grade.ProductEval(tree, p, hist, cal, unobserved)
        prow = []
        for i, d in enumerate(cal):
            if d >= start:
                k = pe.grade_key(i)
                prow.append({"date": d, "prod": p, "key": k, "grade": tree_grade.GRADES[k]})
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
        tl = trades_mod.simulate(tree, p, hist, cal, starts, exits)
        trade_res[p] = {"exit_source": src, "tranche_note": trades_mod.tranche_note(tree, p),
                        "stats": trades_mod.stats(tl), "trades": tl}
        manual[p] = [{"section": s, "rule": l, "ref": r} for s, l, r in pe.manual_items()]
        if prow and period is None:
            period = [prow[0]["date"], prow[-1]["date"], len(prow)]
    return {"slug": slug, "title": (tree.get("source") or {}).get("book", slug),
            "period": period[:2] if period else None, "trading_days": period[2] if period else 0,
            "horizons": list(HORIZONS), "missing_symbols": missing, "manual": manual,
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


def _cli():
    argv = sys.argv[1:]
    slug = next((a for a in argv if not a.startswith("-") and not a.isdigit()), None)
    if not slug:
        print("사용법: python -m verdict.backtest <slug> [--days 365] [--json]", file=sys.stderr)
        sys.exit(2)
    if "--page" in argv:
        data = page_data(slug)
        path = backtest_path(slug)
        write_text(path, json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str))
        print("웹페이지용 백테스트 → %s" % path)
        return
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 365
    # --exclude-unobserved : 분봉이 없어 관측 못 한 저자 시각 조건(개장 전 선물 등)을 빼고 판단(나머지 조건으로 진입)
    res = run(slug, days, unobserved="exclude" if "--exclude-unobserved" in argv else None)
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
