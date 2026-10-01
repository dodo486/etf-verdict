#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""판정 엔진 (책 무관) — 구간③. 체크리스트(= 조건 트리 books/<slug>/tree.json)를 오늘 시세에 대 판정한다.

입력은 둘뿐이다: 트리(구간② 산출물)와 jhts 시세(수집 단계 tree_grade.history → md_feed.histories).
트리의 뜻(등급·금액·분할·매도)은 shared/tree_grade 한 벌이고, 이 파일은 그 결과를 사람과 화면이 읽는
모양으로 묶기만 한다 — 화면은 트리를 다시 해석하지 않고 이 출력만 그린다.

출력 계약(latest-verdict-<slug>.json · 알림 · 화면이 소비):
  top     : {slug, title, ts, date, source, cash, common[], verdicts[], refs{}, missing{}, positions_note}
  common  : [{name, label, ref, v, view}]           상품 여럿이 같이 보는 판단(defs) — 화면 맨 위 한 번
  verdict : {prod, index, note, date, close, chg, key, grade, reason,
             zones{filter,avoid,entry: view[]}, opt{..}, pes{..},     조건 칸 셋의 중첩 설명 + 낙관·비관 값
             caution[{label, ref, scale, v, manual, view}], amount{factor, unspecified, unknown},
             sizing{label, ref, weight, weight_range, tranches[{label, ref, frac, note, view?}]},
             exit[{label, ref, sell, note, view}], positions[...]}    positions = 내 포지션(로컬 파일)이 있을 때만
  refs    : {원문 소절: {auto, manual, zones[], prods[], unexpressed?[{rule, reason}]}}
            플레이북 소절별 체크리스트 반영 현황 + 트리로 못 옮긴 규칙과 그 사유
view 는 노드 하나당 항목 하나 {v, op?, n?, kids?, label?, ref?, manual?, note?, hidden?} (tree_grade._view)
— 수동은 '모름'으로 둔 그날 값. 화면은 사람이 체크한 수동 조건으로 같은 3값 논리를 다시 계산한다.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from shared.paths import BASE
from shared.notify import send_telegram, send_desktop
from shared import cond, md_feed, tree_grade

# 트리 판정에 필요한 이력 길이(가장 긴 창 + 여유). backtest.WARMUP_DAYS 와 같은 기준.
TREE_HISTORY_DAYS = 500
SOURCE = "jhts 시세팀(일봉)"


def book_title(slug):
    """books.json 에서 이 책의 제목(알림/콘솔 헤더용). 없으면 slug."""
    try:
        m = json.load(open(os.path.join(BASE, "books.json"), encoding="utf-8"))
        for b in m.get("books", []):
            if b.get("slug") == slug:
                return b.get("title") or slug
    except Exception:  # noqa: BLE001
        pass
    return slug


def load_positions(slug):
    """books/<slug>/positions.json (커밋하지 않는 개인 파일) → {prod: [포지션]}."""
    p = os.path.join(BASE, "books", slug, "positions.json")
    if not os.path.exists(p):
        return {}
    out = {}
    for x in (json.load(open(p, encoding="utf-8")).get("positions") or []):
        out.setdefault(x["prod"], []).append(x)
    return out


# ------------------------------------------------------------------ 공통 조건(defs)
def _def_users(tree):
    """{정의 이름: 그 정의를 참조하는 상품 집합} — 칸 안에서 {"def": 이름} 을 직접·간접으로 쓰는 상품."""
    defs = tree.get("defs") or {}
    users = {}

    def walk(n, p, seen):
        if isinstance(n, dict):
            if "def" in n and n["def"] in defs and n["def"] not in seen:
                users.setdefault(n["def"], set()).add(p)
                walk(defs[n["def"]], p, seen | {n["def"]})
            for k, x in n.items():
                if k not in cond.META:
                    walk(x, p, seen)
        elif isinstance(n, list):
            for x in n:
                walk(x, p, seen)

    for p, cfg in tree["products"].items():
        for _z, _l, _r, node in cond.zone_nodes(cfg):
            walk(node, p, set())
    return users


def common_items(tree, pe):
    """라벨 달린 정의 중 상품 둘 이상이 같이 보는 것(상품마다 값이 다른 식 제외)."""
    defs = tree.get("defs") or {}
    out = []
    users = _def_users(tree)
    i = len(pe.cal) - 1
    for name, node in defs.items():
        if not (isinstance(node, dict) and node.get("label")):
            continue
        if len(users.get(name, ())) < 2 or tree_grade.product_specific(node, defs):
            continue
        v = cond.series(node, pe.ctx[None])[i]
        out.append({"name": name, "label": node["label"], "ref": node.get("ref"), "v": v,
                    "view": tree_grade._view(node, defs, pe.ctx[None], i, shared=True)})
    return out


# ------------------------------------------------------------------ 원문 소절별 반영 현황
def ref_map(tree):
    """{소절: {auto, manual, zones[], prods[]}} — 트리에 ref 로 달린 라벨 노드·규칙을 센다."""
    defs = tree.get("defs") or {}
    out = {}

    def add(ref, zone, prod, manual):
        if not ref:
            return
        r = out.setdefault(ref, {"auto": 0, "manual": 0, "zones": [], "prods": []})
        r["manual" if manual else "auto"] += 1
        if zone not in r["zones"]:
            r["zones"].append(zone)
        if prod not in r["prods"]:
            r["prods"].append(prod)

    for p, cfg in tree["products"].items():
        for z, label, ref, node in cond.zone_nodes(cfg):
            if label:
                add(ref, z, p, bool(cond.manual_leaves(node, defs)))
            for n in cond.labeled(node, defs):
                add(n.get("ref"), z, p, bool(cond.manual_leaves(n, defs)))
        sz = cfg.get("sizing") or {}
        for t in sz.get("tranches") or []:
            if "when" not in t:
                add(t.get("ref"), "sizing", p, False)
        if sz.get("weight") is None and sz.get("ref"):
            add(sz["ref"], "sizing", p, False)
    for u in tree.get("unexpressed") or []:
        if u.get("ref"):
            r = out.setdefault(u["ref"], {"auto": 0, "manual": 0, "zones": [], "prods": []})
            r.setdefault("unexpressed", []).append({"rule": u.get("rule"), "reason": u.get("reason")})
    return out


# ------------------------------------------------------------------ 상품 하나
def product_verdict(tree, p, hist, positions):
    cfg = tree["products"][p]
    cs = hist.get(p) or []
    base = {"prod": p, "index": cfg.get("index"), "note": cfg.get("note")}
    if not cs:
        req = md_feed.requested().get(p, "-")
        return dict(base, key="unknown", grade=tree_grade.GRADES["unknown"],
                    reason="%s 시세 없음(수집 요청 %s)" % (p, req)), None
    cal = [c.date for c in cs]
    pe = tree_grade.ProductEval(tree, p, hist, cal)
    i = len(cal) - 1
    key, top = pe.grade_key(i), pe.top(i)
    reason = tree_grade.reason_of(key, top, pe.manual_items())
    f, unspec, unknown = pe.amount_factor(i)
    if key in ("buy", "confirm"):
        if f < 1:
            reason += " · 금액 ×%.2f" % f
        if unspec:
            reason += " · 금액 축소(폭 저자 미명시): " + " · ".join(unspec[:2])
        if unknown:
            reason += " · 금액 축소 확인: " + " · ".join(unknown[:2])
    w, alt = pe.weight_of(i)
    sz = cfg.get("sizing") or {}
    prev = cs[-2].close if len(cs) >= 2 else None
    v = dict(base, date=cal[i], close=cs[-1].close,
             chg=(cs[-1].close / prev - 1) * 100 if prev else None,
             key=key, grade=tree_grade.GRADES[key], reason=reason,
             zones={sec: pe.view(cfg[sec], i) for sec in cond.SECTIONS},
             opt={sec: pe.opt[sec][i] for sec in cond.SECTIONS},
             pes={sec: pe.pes[sec][i] for sec in cond.SECTIONS},
             caution=[dict(st, view=pe.view(r["when"], i), v=st["value"])
                      for st, r in zip(pe.caution_state(i), cfg["caution"])],
             amount={"factor": f, "unspecified": unspec, "unknown": unknown},
             sizing={"label": sz.get("label"), "ref": sz.get("ref"), "note": sz.get("note"),
                     "weight": w, "weight_range": alt, "weight_set": sz.get("weight") is not None,
                     "tranches": [dict({k: t[k] for k in ("label", "ref", "frac", "note") if k in t},
                                       conditional="when" in t,
                                       view=_static_view(t.get("when"), tree.get("defs") or {}, cfg.get("index")))
                                  for t in sz.get("tranches") or []]},
             exit=[{"label": r["label"], "ref": r.get("ref"), "sell": r["sell"], "note": r.get("note"),
                    "view": _static_view(r["when"], tree.get("defs") or {}, cfg.get("index"))} for r in cfg["exit"]])
    pos = []
    for x in positions.get(p, []):
        st = tree_grade.position_state(tree, p, hist, cal, str(x["entry_date"]), float(x["entry_px"]),
                                       int(x.get("filled", 1)))
        pos.append(dict(st, entry_date=x["entry_date"], entry_px=x["entry_px"], filled=x.get("filled", 1)))
    if pos:
        v["positions"] = pos
    return v, pe


def _static_view(node, defs, index=None):
    """포지션 없이 보이는 규칙 설명(값 없음) — 라벨·논리 묶음·수동 사유만."""
    if node is None:
        return None

    def strip(it):
        it = {k: x for k, x in it.items() if k != "v"}
        if "kids" in it:
            it["kids"] = [strip(k) for k in it["kids"]]
        return it
    ctx = cond.Ctx({}, ["0"], "$none", index, defs, manual_as=None, pos=(0, 1.0))
    try:
        return strip(tree_grade._view(node, defs, ctx, 0))
    except cond.CondError:
        return None


# ------------------------------------------------------------------ 책 하나
def render(slug):
    tree = tree_grade.load_tree(slug)
    now = datetime.now(timezone.utc).astimezone()
    top = {"slug": slug, "title": book_title(slug), "ts": now.isoformat(), "source": SOURCE,
           "verdicts": [], "common": [], "refs": {}, "missing": {}, "cash": None}
    if tree is None:
        top["error"] = "조건 트리 없음 — books/%s/tree.json 이 있어야 판정한다" % slug
        return top
    start = (datetime.now() - timedelta(days=TREE_HISTORY_DAYS)).strftime("%Y%m%d")
    hist = tree_grade.history(tree, start)
    positions = load_positions(slug)
    pe0 = None
    weights, all_known = [], True
    for p in tree["products"]:
        v, pe = product_verdict(tree, p, hist, positions)
        top["verdicts"].append(v)
        pe0 = pe0 or pe
        sz = v.get("sizing") or {}
        if sz.get("weight_set"):
            if sz.get("weight") is None:
                all_known = False
            else:
                weights.append(sz["weight"])
    if weights and all_known:
        top["cash"] = max(0.0, 100.0 - sum(weights))
    top["date"] = max((v.get("date") or "" for v in top["verdicts"]), default=None)
    if pe0 is not None:
        top["common"] = common_items(tree, pe0)
    top["refs"] = ref_map(tree)
    top["missing"] = {s: md_feed.requested().get(s, "-") for s, cs in hist.items() if not cs}
    if positions:
        top["positions_note"] = "내 포지션(books/%s/positions.json) 기준 — 공개 페이지에는 실리지 않는다" % slug
    return top


# ------------------------------------------------------------------ 출력 텍스트 / 알림
def _mark(v):
    return {True: "🟢", False: "🔴"}.get(v, "❔")


def build_text(top):
    now = datetime.fromisoformat(top["ts"])
    L = ["📈 %s  (%s KST · %s 종가 기준)" % (top.get("title") or top["slug"], now.strftime("%Y-%m-%d %H:%M"),
                                         top.get("date") or "-")]
    if top.get("error"):
        L.append("❔ " + top["error"])
        return "\n".join(L)
    if top["common"]:
        L.append("공통 조건:")
        for c in top["common"]:
            L.append("   %s %s" % (_mark(c["v"]), c["label"]))
    L.append("─" * 30)
    for v in top["verdicts"]:
        L.append("%s  %s" % (v["prod"], v["grade"]))
        L.append("   %s" % v["reason"])
        sz = v.get("sizing") or {}
        if sz.get("weight") is not None:
            L.append("   비중 %.0f%%%s" % (sz["weight"], "" if v["amount"]["factor"] >= 1
                                          else " × 금액 %.2f" % v["amount"]["factor"]))
        elif sz.get("weight_range"):
            L.append("   비중 확인 필요: %s%%" % " / ".join("%.0f" % x for x in sz["weight_range"]))
        for ps in v.get("positions") or []:
            hit = [e["label"] for e in ps.get("exit", []) if e.get("v") is True]
            L.append("   보유(%s, %+.1f%%) 매도 신호: %s" % (ps.get("entry_date"), ps.get("ret") or 0,
                                                     " · ".join(hit) if hit else "없음"))
    if top.get("cash") is not None:
        L.append("현금 %.0f%%" % top["cash"])
    if top.get("missing"):
        L.append("⚠ 시세 없음(수집 요청): " + ", ".join("%s #%s" % kv for kv in top["missing"].items()))
    L.append("─" * 30)
    L.append("※ 종가 기준 판정. 🟡 는 수동(장중·저자 미명시) 조건을 직접 확인한 뒤 진입. 규칙 출처 = 저자 명시.")
    return "\n".join(L)


# 알림 발신(send_telegram/send_desktop)은 shared/notify.py 로 나갔다 —
# 이 팀에는 네트워크 코드를 두지 않는다(verify_teams.py 가 강제).
def _cli():
    argv = sys.argv[1:]
    slug = next((a for a in argv if not a.startswith("-")), None)
    if not slug:
        print("사용법: python -m verdict.verdict_engine <slug> [--json] [--no-send]", file=sys.stderr)
        sys.exit(2)
    top = render(slug)
    text = build_text(top)
    if "--json" in argv:
        print(json.dumps(top, ensure_ascii=False, indent=1))
    else:
        print(text)
    if "--no-send" not in argv:
        if not send_telegram(text):
            send_desktop(text)
    try:
        from shared.paths import LOGS as _LOGS, ensure_dir as _ensure, write_text as _write
        _ensure(_LOGS)
        now = datetime.fromisoformat(top["ts"])
        _write(os.path.join(_LOGS, "%s-%s.txt" % (slug, now.strftime("%Y%m%d"))), text)
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    _cli()
