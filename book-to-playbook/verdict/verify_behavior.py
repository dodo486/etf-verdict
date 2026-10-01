#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검사기 ③ — 규칙이 원문 뜻대로 '동작'하나 (책 무관). 글자가 아니라 실행 결과로 본다.

왜 있나
  옛 검증층(창작·커버리지·규칙↔명세·의미검사·자동가능)은 원문과 규칙의 **글자**(숫자·단어·어휘)를
  대조했다. 그래서 '2'라는 글자만 있으면 2거래일 유지가 1일로 판정돼도 통과했고, 사전에 없는
  새 조건(RSI·볼린저…)은 '찾은 게 없으니 누락도 없음'으로 통과했다. 이 검사는 규칙을 실제 시세와
  원문 사례에 돌려 본다 — 조건 종류를 몰라도 같은 절차가 돈다.

무엇을 하나 (books/<slug>/ 아래)
  1. 채택 트리(tree.json) — 라이브 책은 반드시 있어야 하고, 문법 검사를 통과해야 한다.
  2. 이중 추출 일치 — 서로 독립인 두 추출(tree_candidates/a.json·b.json)을 실제 시세 수년치에서
     구역별로 날마다 평가해 비교한다. 하루라도 갈린 구역은 심판 기록(tree_review.json)이 있어야 하고,
     채택 트리는 그 구역에서 심판이 고른 쪽과 **동작이 같아야** 한다(같은 날 같은 값).
  3. 원문 사례 재현 — 원문만 보고 따로 쓴 시나리오(scenarios.json)를 합성 시세로 돌려 기대값과
     맞는지. 틀리면 실패 — 단 심판이 '시나리오가 틀렸다'고 사유를 남긴 것은 제외.
  4. 발화 통계 — 채택 트리의 라벨 노드를 실제 시세에서 날마다 평가해: 한 번도 안 뜸 · 거의 매일 ·
     항상 판정 불가 · 두 조건이 완전히 같음 · 진입이 뜨면 늘 회피도 뜸 · 매수 후보 도달 불가.
     (경고 — 이상은 재추출 대상으로 넘긴다.)

종료코드: 0 통과 · 1 정지(트리 없음/문법/미심판 불일치/채택≠승자/사례 실패) · 2 경고만.
사용:
  python -m verdict.verify_behavior [slug ...] [--years 3]
  python -m verdict.verify_behavior <slug> --dump N     판정이 갈린 날 N개씩을 logs/disagree-<slug>.json 으로(심판 입력)
  python -m verdict.verify_behavior <slug> --adopt      a + 심판 결과(tree_review.json) → tree.json
  python -m verdict.verify_behavior <slug> --dump-exits N   매도 규칙 a/b 가 다르게 청산한 거래 N개씩(심판 입력)
  python -m verdict.verify_behavior <slug> --adopt-exits    매도 규칙 심판 결과(tree_review.json exits) → tree.json
"""
import json
import os
import sys
from collections import namedtuple
from datetime import datetime, timedelta

from shared import paths  # noqa: F401  (UTF-8 출력)
from shared.paths import BASE, LOGS, ensure_dir, live_slugs, write_text
from verdict import cond, md_feed, trades as trades_mod, tree_grade

Candle = namedtuple("Candle", "date open high low close volume")
WARMUP_DAYS = 500


def _load(slug, name):
    p = os.path.join(BASE, "books", slug, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


# ------------------------------------------------------------------ 실제 시세 평가
def _history(trees, years):
    syms = set()
    for t in trees:
        syms |= cond.symbols_of(t)
    start = (datetime.now() - timedelta(days=int(365 * years) + WARMUP_DAYS)).strftime("%Y%m%d")
    return {s: md_feed.history(s, start) for s in sorted(syms)}


def _eval_sections(tree, prod, hist, cal):
    """수동 = 모름(None) 으로 구역별 시계열 + 등급 키 시계열."""
    cfg, defs = tree["products"][prod], tree.get("defs") or {}
    ctx = cond.Ctx(hist, cal, prod, cfg.get("index"), defs, manual_as=None)
    out = {sec: cond.series(cfg[sec], ctx) for sec in cond.SECTIONS}
    pe = tree_grade.ProductEval(tree, prod, hist, cal)
    out["grade"] = [pe.grade_key(i) for i in range(len(cal))]
    return out, ctx


def _window(cal, years):
    start = (datetime.now() - timedelta(days=int(365 * years))).strftime("%Y%m%d")
    return [i for i, d in enumerate(cal) if d >= start]


def compare(ta, tb, hist, years):
    """두 트리를 상품·구역별로 날마다 비교 → {prod: {sec: {agree, n, days:[i...]}}}."""
    res = {}
    for p in ta["products"]:
        if p not in tb["products"]:
            res[p] = {"missing_in_b": True}
            continue
        cal = [c.date for c in hist.get(p) or []]
        ea, _ = _eval_sections(ta, p, hist, cal)
        eb, _ = _eval_sections(tb, p, hist, cal)
        idx = _window(cal, years)
        res[p] = {}
        for sec in cond.SECTIONS + ("grade",):
            diff = [i for i in idx if ea[sec][i] != eb[sec][i]]
            res[p][sec] = {"n": len(idx), "agree": 1 - len(diff) / max(1, len(idx)),
                           "days": [cal[i] for i in diff], "_ia": ea, "_ib": eb, "_cal": cal}
    for p in tb["products"]:
        if p not in ta["products"]:
            res[p] = {"missing_in_a": True}
    return res


# ------------------------------------------------------------------ 원문 사례
def _synthetic(sc, symbols):
    days = int(sc.get("days") or 60)
    cal = ["2000%04d" % i for i in range(days)]
    series = sc.get("series") or {}

    def fit(xs, fill):
        xs = list(xs or [])
        if len(xs) >= days:
            return xs[-days:]
        return [xs[0] if xs else fill] * (days - len(xs)) + xs

    hist = {}
    for s in set(symbols) | set(series):
        sp = series.get(s)
        if sp:
            cl = fit(sp.get("close"), 100.0)
            hi = fit(sp.get("high"), None) if sp.get("high") else cl
            lo = fit(sp.get("low"), None) if sp.get("low") else cl
            op = fit(sp.get("open"), None) if sp.get("open") else cl
            vo = fit(sp.get("volume"), 1_000_000) if sp.get("volume") else [1_000_000] * days
        else:                           # 배경: 완만한 상승 · 저변동 · 거래량 일정
            cl = [100.0 * (1.001 ** i) for i in range(days)]
            hi = [c * 1.002 for c in cl]
            lo = [c * 0.998 for c in cl]
            op = cl
            vo = [1_000_000] * days
        hist[s] = [Candle(d, float(o), float(h), float(l), float(c), v)
                   for d, o, h, l, c, v in zip(cal, op, hi, lo, cl, vo)]
    return hist, cal


def run_scenarios(tree, scen, overrides):
    out = []
    syms = cond.symbols_of(tree)
    for sc in (scen or {}).get("scenarios", []):
        name, p, sec = sc.get("name"), sc.get("prod"), sc.get("section")
        if p not in tree["products"] or sec not in cond.SECTIONS:
            out.append((sc, "형식오류", None))
            continue
        hist, cal = _synthetic(sc, syms)
        cfg = tree["products"][p]
        ctx = cond.Ctx(hist, cal, p, cfg.get("index"), tree.get("defs") or {}, manual_as=None)
        try:
            got = cond.series(cfg[sec], ctx)[-1]
        except Exception as e:  # noqa: BLE001
            out.append((sc, "평가오류 %s" % e, None))
            continue
        if got is None:
            # 수동 조건 때문에 모름이면 '확인됨/안 됨' 두 경우로 다시 본다 — 어느 쪽으로도 기대값이
            # 안 나오면 수동과 무관하게 틀린 것이다(재현불가로 덮지 않는다).
            alt = set()
            for m in (True, False):
                c2 = cond.Ctx(hist, cal, p, cfg.get("index"), tree.get("defs") or {}, manual_as=m)
                alt.add(cond.series(cfg[sec], c2)[-1])
            if None in alt:
                st = "재현불가"
            elif bool(sc.get("expect")) in alt:
                st = "수동 확인 시 일치"
            elif name in overrides:
                st = "불일치(시나리오 오류로 심판)"
            else:
                st, got = "불일치", sorted(alt)
        elif got == bool(sc.get("expect")):
            st = "일치"
        elif name in overrides:
            st = "불일치(시나리오 오류로 심판)"
        else:
            st = "불일치"
        out.append((sc, st, got))
    return out


# ------------------------------------------------------------------ 발화 통계
def _has_manual(n, defs):
    return bool(cond.manual_leaves(n, defs))


def fire_stats(tree, hist, years, ack=None):
    """ack = {경고문: 사유} — 심판이 '원문 그대로라 정상'이라 사유를 남긴 경고는 확인됨으로 센다."""
    ack = ack or {}
    warns, table = [], []
    defs = tree.get("defs") or {}
    for p, cfg in tree["products"].items():
        cal = [c.date for c in hist.get(p) or []]
        ev, ctx = _eval_sections(tree, p, hist, cal)
        idx = _window(cal, years)
        N = max(1, len(idx))
        nodes = []
        top_avoid = {repr(n) for n in tree_grade._top_labeled(cfg["avoid"], defs)}
        for sec in cond.SECTIONS:
            for n in cond.labeled(cfg[sec], defs):
                if _has_manual(n, defs):
                    continue                         # 수동이 섞이면 '안 뜸/모름'이 정상이다
                s = cond.series(n, ctx)
                v = [s[i] for i in idx]
                if not all(x is None or isinstance(x, bool) for x in v):
                    continue                         # 숫자 노드는 통계 대상 아님
                on, na = sum(1 for x in v if x is True), sum(1 for x in v if x is None)
                nodes.append((sec, n.get("label"), v, repr(n)))
                flag = ""
                if na == len(v):
                    flag = "항상 판정 불가"
                elif on == 0:
                    flag = "한 번도 안 뜸"
                elif on / N > 0.95:
                    flag = "거의 매일(>95%)"
                elif na / N > 0.05:
                    flag = "판정 불가 %d일" % na
                table.append((p, sec, n.get("label"), on / N * 100, flag))
                if flag:
                    warns.append("%s %s '%s': %s" % (p, sec, n.get("label"), flag))
        for a in range(len(nodes)):
            for b in range(a + 1, len(nodes)):
                sa, la, va, ra = nodes[a]
                sb, lb, vb, rb = nodes[b]
                if la == lb or sum(1 for x in va if x is True) < 10:
                    continue
                if sa == sb and (ra in rb or rb in ra):
                    continue                         # 감싸는 노드와 그 안의 노드 — 같은 게 정상
                if va == vb:
                    warns.append("%s 완전히 같은 조건: [%s] %s == [%s] %s" % (p, sa, la, sb, lb))
                # 진입 ⇒ 회피: 회피는 맨 위 노드만(회피 안쪽 하위 조건이 진입과 겹치는 건 정상)
                for (s1, l1, v1, r1), (s2, l2, v2, r2) in (((sa, la, va, ra), (sb, lb, vb, rb)),
                                                         ((sb, lb, vb, rb), (sa, la, va, ra))):
                    if s1 == "entry" and s2 == "avoid" and r2 in top_avoid \
                            and sum(1 for x in v1 if x) >= 10 \
                            and all(v2[k] is True for k in range(len(v1)) if v1[k] is True):
                        warns.append("%s 진입⇒회피: '%s' 가 뜨면 늘 '%s' 도 뜸" % (p, l1, l2))
        g = [ev["grade"][i] for i in idx]
        nb, nc = g.count("buy"), g.count("confirm")
        table.append((p, "등급", "✅ %d일 · 🟡 %d일 · ❔ %d일" % (nb, nc, g.count("unknown")), None, ""))
        if nb + nc == 0:
            warns.append("%s 매수 후보 도달 불가 — %d일 중 ✅·🟡 0일" % (p, len(g)))
        if g.count("unknown") / N > 0.05:
            warns.append("%s 판정 불가 %d일(데이터 부족)" % (p, g.count("unknown")))
    acked = [w for w in warns if w in ack]
    return table, [w for w in warns if w not in ack], acked


# ------------------------------------------------------------------ 심판 입력 덤프
def dump_disagreements(slug, per, years):
    ta, tb = _load(slug, "tree_candidates/a.json"), _load(slug, "tree_candidates/b.json")
    cond.validate_tree(ta)
    cond.validate_tree(tb)
    hist = _history([ta, tb], years)
    cmp_ = compare(ta, tb, hist, years)
    out = {}
    for p, secs in cmp_.items():
        for sec, r in secs.items():
            if not isinstance(r, dict) or sec == "grade" or not r["days"]:
                continue
            cal = r["_cal"]
            step = max(1, len(r["days"]) // per)
            picks = r["days"][::step][:per]
            cases = []
            for d in picks:
                i = cal.index(d)
                pa = tree_grade.ProductEval(ta, p, hist, cal)
                pb = tree_grade.ProductEval(tb, p, hist, cal)
                prices = {}
                for s in sorted(cond.symbols_of({"products": {p: ta["products"][p]}, "defs": ta.get("defs")})
                                | cond.symbols_of({"products": {p: tb["products"][p]}, "defs": tb.get("defs")})):
                    cs = [c for c in hist.get(s) or [] if c.date <= d][-25:]
                    prices[s] = [[c.date, c.open, c.high, c.low, c.close, c.volume] for c in cs]
                cases.append({"date": d, "a": r["_ia"][sec][i], "b": r["_ib"][sec][i],
                              "a_explain": pa.explain(i)[sec], "b_explain": pb.explain(i)[sec],
                              "prices_last25[date,o,h,l,c,v]": prices})
            out["%s.%s" % (p, sec)] = {"agree": r["agree"], "diff_days": len(r["days"]),
                                       "a_tree": ta["products"][p][sec], "b_tree": tb["products"][p][sec],
                                       "cases": cases}
    ensure_dir(LOGS)
    path = os.path.join(LOGS, "disagree-%s.json" % slug)
    write_text(path, json.dumps({"defs_a": ta.get("defs"), "defs_b": tb.get("defs"), "sections": out},
                                ensure_ascii=False, indent=1, default=str))
    print("갈린 구역 %d개 → %s" % (len(out), path))


# ------------------------------------------------------------------ 채택
def _inline(node, defs):
    """def 참조를 그 정의로 펼친다(다른 추출의 defs 와 이름이 겹쳐도 섞이지 않게)."""
    if isinstance(node, dict):
        if "def" in node and len([k for k in node if k not in cond.META]) == 1:
            body = _inline(defs[node["def"]], defs)
            if isinstance(body, dict):
                body = dict(body, **{k: v for k, v in node.items() if k in cond.META})
            return body
        return {k: _inline(v, defs) for k, v in node.items()}
    if isinstance(node, list):
        return [_inline(x, defs) for x in node]
    return node


def adopt(slug):
    """a 를 바탕으로, 심판이 b/custom 을 고른 구역만 갈아 끼워 tree.json 을 쓴다."""
    ta, tb = _load(slug, "tree_candidates/a.json"), _load(slug, "tree_candidates/b.json")
    review = _load(slug, "tree_review.json") or {}
    tree = json.loads(json.dumps(ta))
    for key, d in (review.get("sections") or {}).items():
        p, sec = key.split(".")
        if d.get("winner") == "b":
            tree["products"][p][sec] = _inline(tb["products"][p][sec], tb.get("defs") or {})
        elif d.get("winner") == "custom":
            src = tb if d.get("defs_from") == "b" else ta
            tree["products"][p][sec] = _inline(d["custom_tree"], src.get("defs") or {})
    tree["source"] = {"book": slug, "extractor": "채택", "base": "a",
                      "review": {k: v.get("winner") for k, v in (review.get("sections") or {}).items()}}
    cond.validate_tree(tree)
    write_text(os.path.join(BASE, "books", slug, "tree.json"), json.dumps(tree, ensure_ascii=False, indent=1))
    print("채택 트리 → books/%s/tree.json (%s)" % (slug, tree["source"]["review"] or "전 구역 일치"))


# ------------------------------------------------------------------ 매도 규칙(exit) 이중 추출
def _exit_rules(cand, prod):
    """후보 파일의 상품 매도 규칙을 def 를 펼쳐 돌려준다."""
    defs = cand.get("defs") or {}
    return [dict(r, when=_inline(r["when"], defs)) for r in (cand.get("exits") or {}).get(prod) or []]


def _exit_symbols(cands):
    syms = set()
    for c in cands:
        for p in (c.get("exits") or {}):
            for r in _exit_rules(c, p):
                syms |= cond.symbols_of({"products": {p: {"filter": r["when"], "entry": {"all": []},
                                                          "avoid": {"any": []}}}})
    return syms


def _entry_starts(tree, prod, hist, cal, years):
    pe = tree_grade.ProductEval(tree, prod, hist, cal)
    starts, prev = [], False
    for i in _window(cal, years):
        b = pe.grade_key(i) in ("buy", "confirm")
        if b and not prev:
            starts.append(i)
        prev = b
    return starts


def _trade_key(t):
    return (t["entry"], t["exit"], tuple((x["date"], round(x["qty"], 6)) for x in t["sells"]))


def compare_exits(tree, ea, eb, hist, years):
    """같은 진입 신호에 두 매도 규칙을 돌려 진입일별로 짝지어 비교 → {prod: {n, diff:[(ta, tb)]}}."""
    out = {}
    for p in tree["products"]:
        cal = [c.date for c in hist.get(p) or []]
        starts = _entry_starts(tree, p, hist, cal, years)
        ta = {t["entry"]: t for t in trades_mod.simulate(tree, p, hist, cal, starts, _exit_rules(ea, p))}
        tb = {t["entry"]: t for t in trades_mod.simulate(tree, p, hist, cal, starts, _exit_rules(eb, p))}
        keys = sorted(set(ta) | set(tb))
        diff = [(ta.get(k), tb.get(k)) for k in keys
                if not (ta.get(k) and tb.get(k) and _trade_key(ta[k]) == _trade_key(tb[k]))]
        out[p] = {"n": len(keys), "diff": diff}
    return out


def _hist_with_exits(tree, cands, years):
    hist = _history([tree], years)
    extra = sorted(_exit_symbols(cands) - set(hist))
    if extra:
        start = (datetime.now() - timedelta(days=int(365 * years) + WARMUP_DAYS)).strftime("%Y%m%d")
        hist.update({s: md_feed.history(s, start) for s in extra})
    return hist


def dump_exit_disagreements(slug, per, years):
    tree = tree_grade.load_tree(slug)
    ea, eb = _load(slug, "tree_candidates/exit_a.json"), _load(slug, "tree_candidates/exit_b.json")
    hist = _hist_with_exits(tree, [ea, eb], years)
    cmp_ = compare_exits(tree, ea, eb, hist, years)
    out = {}
    for p, r in cmp_.items():
        cs = hist.get(p) or []
        idx = {c.date: i for i, c in enumerate(cs)}
        step = max(1, len(r["diff"]) // per)
        cases = []
        for a, b in r["diff"][::step][:per]:
            ent = (a or b)["entry"]
            ends = [x for x in ((a or {}).get("exit"), (b or {}).get("exit")) if x]
            i0 = idx[ent]
            i1 = min(len(cs) - 1, max(idx[x] for x in ends) + 1) if ends else min(len(cs) - 1, i0 + 60)
            cases.append({"entry": ent, "a": a, "b": b,
                          "bars_from_entry[date,o,h,l,c]": [[c.date, c.open, c.high, c.low, c.close]
                                                            for c in cs[i0:i1 + 1]]})
        out[p] = {"trades": r["n"], "diff": len(r["diff"]),
                  "a_rules": (ea.get("exits") or {}).get(p), "b_rules": (eb.get("exits") or {}).get(p),
                  "cases": cases}
    ensure_dir(LOGS)
    path = os.path.join(LOGS, "exit-disagree-%s.json" % slug)
    write_text(path, json.dumps({"defs_a": ea.get("defs"), "defs_b": eb.get("defs"), "products": out},
                                ensure_ascii=False, indent=1, default=str))
    for p, v in out.items():
        print("  %s 거래 %d 중 %d 갈림" % (p, v["trades"], v["diff"]))
    print("-> %s" % path)


def adopt_exits(slug):
    """심판 기록(tree_review.json exits.<상품>) -> tree.json products.<상품>.exit (def 펼침).
    심판 기록이 없는 상품 = 두 추출이 같게 청산한 상품 -> a 그대로."""
    tree = json.load(open(os.path.join(BASE, "books", slug, "tree.json"), encoding="utf-8"))
    ea, eb = _load(slug, "tree_candidates/exit_a.json"), _load(slug, "tree_candidates/exit_b.json")
    review = (_load(slug, "tree_review.json") or {}).get("exits") or {}
    for p in tree["products"]:
        d = review.get(p) or {"winner": "a"}
        if d["winner"] in ("a", "b"):
            rules = _exit_rules(ea if d["winner"] == "a" else eb, p)
        else:
            src = eb if d.get("defs_from") == "b" else ea
            rules = [dict(r, when=_inline(r["when"], src.get("defs") or {})) for r in d["custom_rules"]]
        tree["products"][p]["exit"] = rules
    tree.setdefault("source", {})["exit_review"] = {p: (review.get(p) or {}).get("winner", "a(일치)")
                                                    for p in tree["products"]}
    cond.validate_tree(tree)
    write_text(os.path.join(BASE, "books", slug, "tree.json"), json.dumps(tree, ensure_ascii=False, indent=1))
    print("매도 규칙 채택 -> books/%s/tree.json %s" % (slug, tree["source"]["exit_review"]))


def check_exits(slug, tree, years, review):
    """exit_a/b 가 있으면: 거래별 비교 -> 갈린 상품은 심판 기록 필수 + 채택 규칙이 승자와 같은 거래를 내야 한다."""
    ea, eb = _load(slug, "tree_candidates/exit_a.json"), _load(slug, "tree_candidates/exit_b.json")
    if not (ea or eb):
        return []
    if not (ea and eb):
        print("  ❌ 매도 규칙 독립 추출 exit_a/exit_b 중 하나 없음")
        return ["%s 매도 규칙 a/b 중 하나 없음" % slug]
    stop = []
    for c in (ea, eb):
        for p, rules in (c.get("exits") or {}).items():
            cond.validate_exits(rules, c.get("defs") or {}, "%s.exit" % p)
    hist = _hist_with_exits(tree, [ea, eb], years)
    decided = review.get("exits") or {}
    for p, r in compare_exits(tree, ea, eb, hist, years).items():
        line = "  %s %-13s 거래 %d 중 %d 갈림" % ("✅" if not r["diff"] else "≠", p + ".exit", r["n"], len(r["diff"]))
        d = decided.get(p)
        if r["diff"]:
            if not d or d.get("winner") not in ("a", "b", "custom") or not d.get("why"):
                stop.append("%s.exit 미심판 불일치" % p)
                line += "  ❌ 심판 기록 없음"
            else:
                line += "  -> 심판: %s" % d["winner"]
        # 채택 규칙은 승자(일치한 상품은 a)와 같은 거래를 내야 한다
        win_name = (d or {}).get("winner", "a") if r["diff"] else "a"
        if win_name in ("a", "b"):
            win = ea if win_name == "a" else eb
            cal = [c.date for c in hist.get(p) or []]
            starts = _entry_starts(tree, p, hist, cal, years)
            mine = trades_mod.simulate(tree, p, hist, cal, starts, tree["products"][p].get("exit") or [])
            theirs = trades_mod.simulate(tree, p, hist, cal, starts, _exit_rules(win, p))
            if [_trade_key(t) for t in mine] != [_trade_key(t) for t in theirs]:
                stop.append("%s.exit 채택 규칙이 %s 와 다르게 동작" % (p, win_name))
                line += "  ❌ 채택 != %s" % win_name
        print(line)
    return stop


# ------------------------------------------------------------------ 책 하나
def check_book(slug, years):
    stop, warn = [], []
    print("== %s" % slug)
    try:
        tree = tree_grade.load_tree(slug)
    except cond.CondError as e:
        print("  ❌ tree.json 문법 오류: %s" % e)
        return ["%s 트리 문법" % slug], []
    if tree is None:
        print("  ❌ tree.json 없음 — 라이브 책은 조건 트리로만 등급을 낸다")
        return ["%s 트리 없음" % slug], []
    review = _load(slug, "tree_review.json") or {}
    ta, tb = _load(slug, "tree_candidates/a.json"), _load(slug, "tree_candidates/b.json")
    trees = [tree] + [t for t in (ta, tb) if t]
    for t in (ta, tb):
        if t:
            cond.validate_tree(t)
    hist = _history(trees, years)
    missing = sorted(s for s, cs in hist.items() if not cs)
    if missing:
        stop.append("%s 시세 없는 심볼 %s" % (slug, missing))
        print("  ❌ 시세 없는 심볼: %s" % missing)

    # 2. 이중 추출
    if not (ta and tb):
        stop.append("%s 독립 추출 a/b 없음" % slug)
        print("  ❌ tree_candidates/a.json·b.json 이 둘 다 있어야 한다(이중 추출)")
    else:
        cmp_ = compare(ta, tb, hist, years)
        decided = review.get("sections") or {}
        for p, secs in cmp_.items():
            if any(k.startswith("missing") for k in secs):
                stop.append("%s %s 상품이 한쪽 추출에만 있음" % (slug, p))
                continue
            for sec in cond.SECTIONS:
                r = secs[sec]
                key = "%s.%s" % (p, sec)
                mark = "✅" if not r["days"] else "≠"
                line = "  %s %-13s 일치 %5.1f%% (%d일 중 %d일 갈림)" % (mark, key, r["agree"] * 100, r["n"], len(r["days"]))
                if r["days"]:
                    d = decided.get(key)
                    if not d or d.get("winner") not in ("a", "b", "custom") or not d.get("why"):
                        stop.append("%s 미심판 불일치" % key)
                        line += "  ❌ 심판 기록 없음"
                    else:
                        line += "  → 심판: %s" % d["winner"]
                        if d["winner"] in ("a", "b"):
                            win = ta if d["winner"] == "a" else tb
                            same = compare({"products": {p: tree["products"][p]}, "defs": tree.get("defs")},
                                           {"products": {p: win["products"][p]}, "defs": win.get("defs")},
                                           hist, years)[p][sec]
                            if same["days"]:
                                stop.append("%s 채택 트리가 승자와 다르게 동작" % key)
                                line += " ❌ 채택≠승자(%d일)" % len(same["days"])
                print(line)

    # 2b. 매도 규칙 이중 추출
    stop.extend(check_exits(slug, tree, years, review))

    # 3. 원문 사례
    scen = _load(slug, "scenarios.json")
    if not scen:
        warn.append("%s 원문 사례 시나리오 없음" % slug)
        print("  ⚠ scenarios.json 없음")
    else:
        res = run_scenarios(tree, scen, review.get("scenario_overrides") or {})
        cnt = {}
        for sc, st, got in res:
            cnt[st] = cnt.get(st, 0) + 1
            if st in ("불일치", "형식오류") or st.startswith("평가오류"):
                stop.append("%s 사례 %s: %s" % (slug, st, sc.get("name")))
                print("  ❌ 사례 %s: %s [%s.%s 기대 %s, 결과 %s] (%s)"
                      % (st, sc.get("name"), sc.get("prod"), sc.get("section"), sc.get("expect"), got, sc.get("ref")))
            elif st == "재현불가":
                warn.append("%s 사례 재현불가: %s" % (slug, sc.get("name")))
        print("  사례 %d개: %s" % (len(res), " · ".join("%s %d" % kv for kv in cnt.items())))

    # 4. 발화 통계
    table, fw, acked = fire_stats(tree, hist, years, review.get("fire_ack") or {})
    for p, sec, label, rate, flag in table:
        if rate is None:
            print("  %-5s %s" % (p, label))
    for w in fw:
        print("  ⚠ " + w)
    for w in acked:
        print("  ☑ %s — 확인됨: %s" % (w, review["fire_ack"][w]))
    warn.extend(fw)
    return stop, warn


def main():
    argv = sys.argv[1:]
    years = float(argv[argv.index("--years") + 1]) if "--years" in argv else 3
    if "--dump" in argv:
        dump_disagreements(argv[0], int(argv[argv.index("--dump") + 1]), years)
        return 0
    if "--adopt" in argv:
        adopt(argv[0])
        return 0
    if "--dump-exits" in argv:
        dump_exit_disagreements(argv[0], int(argv[argv.index("--dump-exits") + 1]), years)
        return 0
    if "--adopt-exits" in argv:
        adopt_exits(argv[0])
        return 0
    slugs = [a for a in argv if not a.startswith("-") and not a.replace(".", "").isdigit()] or live_slugs()
    stop, warn = [], []
    for s in slugs:
        a, b = check_book(s, years)
        stop += a
        warn += b
    if stop:
        print("동작 검사 정지 %d건" % len(stop))
        return 1
    if warn:
        print("동작 검사 통과(경고 %d건 — 재추출 대상)" % len(warn))
        return 2
    print("동작 검사 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
