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

from shared.paths import BASE, book_meta
from verdict.notify import send_telegram, send_desktop
from shared import cond, md_feed, tree_grade

SOURCE = "jhts 시세팀(일봉)"


def book_title(slug):
    """books.json 에서 이 책의 제목(알림/콘솔 헤더용). 없으면 slug.
    명단 읽기는 공용 함수(paths.book_meta) 한 곳을 쓴다 — 직접 파싱하지 않는다."""
    return book_meta(slug).get("title") or slug


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
    """라벨 달린 정의 중 상품 둘 이상이 같이 보는 것(상품마다 값이 다른 식 제외) — 공통 칸에서 조건마다 한 번만 펼친다.

    · 다른 공통 조건 안에 들어 있는 정의는 따로 나열하지 않는다(그 펼침에 보인다).
    · 단, 공통 칸 안에서 두 번 이상 펼쳐질 정의(모드 둘이 같이 쓰는 '반도체 과열', 한 조건 안에 두 번 쓰인 점수 등)는
      따로 한 번 나열하고, 그 밖의 자리에선 folded(한 줄 — 계산엔 그대로 쓰임)로 둔다. 가장 바깥 것부터 정한다."""
    defs = tree.get("defs") or {}
    users = _def_users(tree)
    i = len(pe.cal) - 1
    shared = [name for name, node in defs.items()
              if isinstance(node, dict) and node.get("label")
              and len(users.get(name, ())) >= 2 and not tree_grade.product_specific(node, defs)]

    def refs(n, stop, acc):
        """n 안의 정의 참조를 센다 — stop(따로 나열한 정의) 안으로는 들어가지 않는다."""
        if isinstance(n, dict):
            x = n.get("def")
            if isinstance(x, str) and x in defs:
                acc[x] = acc.get(x, 0) + 1
                if x not in stop:
                    refs(defs[x], stop, acc)
            for k, y in n.items():
                if k not in cond.META and k != "def":
                    refs(y, stop, acc)
        elif isinstance(n, list):
            for y in n:
                refs(y, stop, acc)
        return acc

    inside = set()
    for name in shared:
        inside |= set(refs(defs[name], set(), {}))
    listed = [name for name in shared if name not in inside]
    for _ in range(len(shared)):
        cnt = {}
        for name in listed:
            for x, c in refs(defs[name], set(listed), {}).items():
                cnt[x] = cnt.get(x, 0) + c
        cands = {x for x, c in cnt.items() if c >= 2 and x in shared and x not in listed}
        outer = {x for x in cands if not any(x in refs(defs[y], set(listed), {}) for y in cands if y != x)}
        if not outer:
            break
        listed = [name for name in shared if name in set(listed) | outer]   # 정의 순서 유지
    fold = frozenset(listed)
    out = []
    for name in listed:
        node = defs[name]
        v = cond.series(node, pe.ctx[None])[i]
        out.append({"name": name, "label": node["label"], "ref": node.get("ref"), "v": v,
                    "view": tree_grade._view(node, defs, pe.ctx[None], i, shared=True, fold=fold - {name})})
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
def product_verdict(tree, p, hist, positions, asof=None):
    cfg = tree["products"][p]
    cs = hist.get(p) or []
    base = {"prod": p, "index": cfg.get("index"), "note": cfg.get("note")}
    if not cs:
        req = md_feed.requested().get(p, "-")
        return dict(base, key="unknown", grade=tree_grade.GRADES["unknown"],
                    reason="%s 시세 없음(수집 요청 %s)" % (p, req)), None
    cal = [c.date for c in cs]
    pe = tree_grade.ProductEval(tree, p, hist, cal, asof=asof)
    i = len(cal) - 1
    key, top = pe.grade_key(i), pe.top(i)
    reason = tree_grade.reason_of(key, top, pe.manual_items(i))
    # 데이터 완전성 가드 — 지금 가진 확정 봉이 트리가 쓰는 가장 긴 창(필요 워밍업)보다 짧으면 등급은 ❔(불완전
    #   데이터, 판정 보류)로 떨어져 있다(grade_key). 사유를 '모르고 매매 금지'로 분명히 적는다(✅/🚫 확신 금지).
    if pe.incomplete(i):
        have = pe._confirmed[i] + 1
        reason = "불완전 데이터(판정 보류) — 확정 봉 %d개 < 필요 워밍업 %d개, 창이 덜 차 신뢰불가" % (have, pe.warmup)
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
def render(slug, asof=None):
    """asof = 관측 시각(UTC datetime). None 이면 지금 — 장중(tf="1m") 조건을 이 시점 이하로 자른다."""
    tree = tree_grade.load_tree(slug)
    now = datetime.now(timezone.utc).astimezone()
    top = {"slug": slug, "title": book_title(slug), "ts": now.isoformat(), "source": SOURCE,
           "verdicts": [], "common": [], "refs": {}, "missing": {}, "cash": None,
           # 등급 글자표(키→라벨)를 실어보낸다 — 화면이 따로 복붙하지 않고 이걸 받아 쓴다(단일 출처).
           "grades": tree_grade.GRADES,
           # 등급 판정 사다리(데이터) 도 같이 실어, 화면이 같은 표로 등급을 다시 낸다(복붙 금지).
           "grade_rules": tree_grade.GRADE_RULES,
           # 여섯 칸 키→한글 이름표(화면 머리글용) — cond.ZONE_LABELS 가 정본이다. 화면(shared-ui ZW)이
           #   복붙하지 않고 이걸 받아 쓴다. 머리글 번호 순서대로(①필터 ②회피 ③진입 …) 실어보낸다.
           "zones": {s: cond.ZONE_LABELS[s]
                     for s in ("filter", "avoid", "entry", "caution", "sizing", "exit")}}
    if tree is None:
        top["error"] = "조건 트리 없음 — books/%s/tree.json 이 있어야 판정한다" % slug
        return top
    start = (datetime.now() - timedelta(days=tree_grade.WARMUP_DAYS)).strftime("%Y%m%d")
    hist = tree_grade.history(tree, start)
    positions = load_positions(slug)
    pe0 = None
    weights, all_known = [], True
    for p in tree["products"]:
        v, pe = product_verdict(tree, p, hist, positions, asof=asof)
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
        top["positions_note"] = "내 포지션(books/%s/positions.json) 기준 — 로컬 화면에서만 쓴다" % slug
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
    L.append("※ 관측 시점(asof) 기준 판정 — 종가 조건은 마지막 확정 일봉, 장중 조건은 그 시점 분봉. "
             "🟡 는 수동(장중 분봉 미연결·저자 미명시) 조건을 직접 확인한 뒤 진입. 규칙 출처 = 저자 명시.")
    return "\n".join(L)


# 알림 발신(send_telegram/send_desktop)은 같은 팀 verdict/notify.py 가 맡는다 —
# 네트워크 코드(urllib)는 그 한 파일에만 허용된다(verify_teams.py ALLOW 의 명시 예외).
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
