#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""판정 화면 데이터(웹 화면층, 책 무관) — 오늘 판정을 판정 JSON(#verdict-data)·알림 문장으로 빚는다.

판정은 구간③ 판정기(trading/judge.Judge — 라이브 = 달력 마지막 봉)가 내고, 이 파일은 그 Decision 과 평가 문맥을
사람과 화면이 읽는 모양으로 묶기만 한다 — 화면은 트리를 다시 해석하지 않고 이 출력만 그린다. 트리는 출입구
(checklist/tree_gateway.TreeGateway), 시세는 수집 단계(checklist.grade.history → md_feed.histories) 하나로 받는다.
books.json 의 engine.daily 가 이 모듈이다(python -m web.verdict_view <slug> — 라이브 서버·러너가 부른다).

출력 계약(알림 · 화면 · /api/verdict 가 소비):
  top     : {slug, title, ts, date, source, cash, common[], verdicts[], refs{}, missing{}, positions_note}
  common  : [{name, label, ref, v, view}]           상품 여럿이 같이 보는 판단(defs) — 화면 맨 위 한 번
  verdict : {prod, index, note, date, close, chg, key, grade, reason,
             zones{filter,avoid,entry: view[]}, opt{..}, pes{..},     조건 칸 셋의 중첩 설명 + 낙관·비관 값
             caution[{label, ref, scale, v, manual, view}], amount{factor, unspecified, unknown},
             sizing{label, ref, weight, weight_range, tranches[{label, ref, frac, note, view?}]},
             exit[{label, ref, sell, note, view}], positions[...]}    positions = 내 포지션(로컬 파일)이 있을 때만
  refs    : {원문 소절: {auto, manual, zones[], prods[], unexpressed?[{rule, reason}]}}
            플레이북 소절별 체크리스트 반영 현황 + 트리로 못 옮긴 규칙과 그 사유
view 는 노드 하나당 항목 하나 {v, op?, n?, kids?, label?, ref?, manual?, note?, hidden?} (condition_view._view)
— 수동은 '모름'으로 둔 그날 값. 화면은 사람이 체크한 수동 조건으로 같은 3값 논리를 다시 계산한다.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from shared.paths import book_log, book_meta, positions_json, write_text
from shared import md_feed
from checklist import cond
from checklist.grade import GRADES, GRADE_RULES, WARMUP_DAYS, history
from checklist.tree_gateway import TreeGateway
from trading.judge import Holding, Judge
from trading.notify import send_telegram, send_desktop
from web import condition_view as cv

SOURCE = "jhts 시세팀(일봉)"


def book_title(slug):
    """books.json 에서 이 책의 제목(알림/콘솔 헤더용). 없으면 slug.
    명단 읽기는 공용 함수(paths.book_meta) 한 곳을 쓴다 — 직접 파싱하지 않는다."""
    return book_meta(slug).get("title") or slug


def load_positions(slug):
    """books/<slug>/positions.json (커밋하지 않는 개인 파일) → {prod: [포지션]}."""
    p = positions_json(slug)
    if not os.path.exists(p):
        return {}
    out = {}
    for x in (json.load(open(p, encoding="utf-8")).get("positions") or []):
        out.setdefault(x["prod"], []).append(x)
    return out


# ------------------------------------------------------------------ 공통 조건(defs)
def common_items(gw, pe):
    """라벨 달린 정의 중 상품 둘 이상이 같이 보는 것(상품마다 값이 다른 식 제외) — 공통 칸에서 조건마다 한 번만 펼친다.

    · 다른 공통 조건 안에 들어 있는 정의는 따로 나열하지 않는다(그 펼침에 보인다).
    · 단, 공통 칸 안에서 두 번 이상 펼쳐질 정의(모드 둘이 같이 쓰는 '반도체 과열', 한 조건 안에 두 번 쓰인 점수 등)는
      따로 한 번 나열하고, 그 밖의 자리에선 folded(한 줄 — 계산엔 그대로 쓰임)로 둔다. 가장 바깥 것부터 정한다."""
    defs = gw.defs()
    users = gw.def_users()
    i = len(pe.cal) - 1
    shared = [name for name, node in defs.items()
              if isinstance(node, dict) and node.get("label")
              and len(users.get(name, ())) >= 2 and not cv.product_specific(node, defs)]

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
                    "view": cv._view(node, defs, pe.ctx[None], i, shared=True, fold=fold - {name})})
    return out


# ------------------------------------------------------------------ 원문 소절별 반영 현황
def ref_map(gw):
    """{소절: {auto, manual, zones[], prods[]}} — 트리에 ref 로 달린 라벨 노드·규칙을 센다."""
    defs = gw.defs()
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

    for p in gw.products():
        for z, label, ref, node in gw.expressions(p):
            if label:
                add(ref, z, p, bool(cond.manual_leaves(node, defs)))
            for n in cond.labeled(node, defs):
                add(n.get("ref"), z, p, bool(cond.manual_leaves(n, defs)))
        for t in gw.tranches(p):
            if t.when is None:
                add(t.ref, "sizing", p, False)
        sz = gw.sizing(p)
        if sz.weight is None and sz.ref:
            add(sz.ref, "sizing", p, False)
    for u in gw.unexpressed():
        if u.get("ref"):
            r = out.setdefault(u["ref"], {"auto": 0, "manual": 0, "zones": [], "prods": []})
            r.setdefault("unexpressed", []).append({"rule": u.get("rule"), "reason": u.get("reason")})
    return out


# ------------------------------------------------------------------ 상품 하나
def product_verdict(gw, p, hist, positions, asof=None):
    """상품 하나의 판정 JSON — 판정은 Judge(라이브 = 달력 마지막 봉)가 내고, 여기는 그 Decision 을 화면 모양으로 빚는다."""
    base = {"prod": p, "index": gw.index(p), "note": gw.note(p)}
    j = Judge(gw, p, hist, asof=asof)
    if not j.cs:
        req = md_feed.requested().get(p, "-")
        return dict(base, key="unknown", grade=GRADES["unknown"],
                    reason="%s 시세 없음(수집 요청 %s)" % (p, req)), None
    xs = positions.get(p, [])
    d = j.decide(holdings=[Holding.at(j.cal, str(x["entry_date"]), float(x["entry_px"]), int(x.get("filled", 1)))
                           for x in xs])
    i, ctx = d.i, d.eval.ctx[None]
    reason = cv.reason_of(d.key, d.top, d.manual)
    # 데이터 완전성 가드 — 지금 가진 확정 봉이 트리가 쓰는 가장 긴 창(필요 워밍업)보다 짧으면 등급은 ❔(불완전
    #   데이터, 판정 보류)로 떨어져 있다(grade_key). 사유를 '모르고 매매 금지'로 분명히 적는다(✅/🚫 확신 금지).
    if d.incomplete:
        reason = "불완전 데이터(판정 보류) — 확정 봉 %d개 < 필요 워밍업 %d개, 창이 덜 차 신뢰불가" % (d.confirmed, d.warmup)
    f, unspec, unknown = d.amount
    if d.key in ("buy", "confirm"):
        if f < 1:
            reason += " · 금액 ×%.2f" % f
        if unspec:
            reason += " · 금액 축소(폭 저자 미명시): " + " · ".join(unspec[:2])
        if unknown:
            reason += " · 금액 축소 확인: " + " · ".join(unknown[:2])
    w, alt = d.weight
    sz, defs, index = gw.sizing(p), gw.defs(), gw.index(p)
    v = dict(base, date=d.date, close=d.close,
             chg=(d.close / d.prev_close - 1) * 100 if d.prev_close else None,
             key=d.key, grade=d.grade, reason=reason,
             zones={sec: cv._view(gw.section(p, sec), defs, ctx, i) for sec in cond.SECTIONS},
             opt=d.opt, pes=d.pes,
             caution=[dict(st, view=cv._view(r.when, defs, ctx, i), v=st["value"]) for st, r in d.caution],
             amount={"factor": f, "unspecified": unspec, "unknown": unknown},
             sizing={"label": sz.label, "ref": sz.ref, "note": sz.note,
                     "weight": w, "weight_range": alt, "weight_set": sz.weight is not None,
                     "tranches": [dict(t.shown("label", "ref", "frac", "note"), conditional=t.when is not None,
                                       view=_static_view(t.when, defs, index))
                                  for t in gw.tranches(p)]},
             exit=[{"label": r.label, "ref": r.ref, "sell": r.sell, "note": r.note,
                    "view": _static_view(r.when, defs, index)} for r in gw.exit_rules(p)])
    pos = [dict(_holding_view(hs, defs, i), entry_date=x["entry_date"], entry_px=x["entry_px"], filled=x.get("filled", 1))
           for hs, x in zip(d.holdings, xs)]
    if pos:
        v["positions"] = pos
    return v, d.eval


def _holding_view(hs, defs, i):
    """보유 하나(HoldingState) → {ret, days, exit:[{label, ref, sell, v, view}], next_tranche:{label, ref, frac, v, view}|None}."""
    if hs.error:
        return {"error": hs.error}
    out = {"ret": hs.ret, "days": hs.days,
           "exit": [{"label": r.label, "ref": r.ref, "sell": r.sell, "v": v, "view": cv._view(r.when, defs, hs.ctx, i)}
                    for r, v in hs.exits]}
    nt = hs.next_tranche
    out["next_tranche"] = None if nt is None else {
        "label": nt[0].label, "ref": nt[0].ref, "frac": nt[0].frac, "v": nt[1], "view": cv._view(nt[0].when, defs, hs.ctx, i)}
    return out


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
        return strip(cv._view(node, defs, ctx, 0))
    except cond.CondError:
        return None


# ------------------------------------------------------------------ 책 하나
def render(slug, asof=None):
    """asof = 관측 시각(UTC datetime). None 이면 지금 — 장중(tf="1m") 조건을 이 시점 이하로 자른다."""
    tree = TreeGateway.load(slug)
    now = datetime.now(timezone.utc).astimezone()
    top = {"slug": slug, "title": book_title(slug), "ts": now.isoformat(), "source": SOURCE,
           "verdicts": [], "common": [], "refs": {}, "missing": {}, "cash": None,
           # 등급 글자표(키→라벨)를 실어보낸다 — 화면이 따로 복붙하지 않고 이걸 받아 쓴다(단일 출처).
           "grades": GRADES,
           # 등급 판정 사다리(데이터) 도 같이 실어, 화면이 같은 표로 등급을 다시 낸다(복붙 금지).
           "grade_rules": GRADE_RULES,
           # 여섯 칸 키→한글 이름표(화면 머리글용) — cond.ZONE_LABELS 가 정본이다. 화면(shared-ui zw)이
           #   복붙하지 않고 이걸 받아 쓴다. 머리글 번호 순서대로(①필터 ②회피 ③진입 …) 실어보낸다.
           "zones": {s: cond.ZONE_LABELS[s]
                     for s in ("filter", "avoid", "entry", "caution", "sizing", "exit")}}
    if tree is None:
        top["error"] = "조건 트리 없음 — books/%s/tree.json 이 있어야 판정한다" % slug
        return top
    start = (datetime.now() - timedelta(days=WARMUP_DAYS)).strftime("%Y%m%d")
    hist = history(tree, start)
    positions = load_positions(slug)
    pe0 = None
    weights, all_known = [], True
    for p in tree.products():
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


# 알림 발신(send_telegram/send_desktop)은 구간③ trading/notify.py 가 맡는다 —
# 네트워크 코드(urllib)는 그 한 파일에만 허용된다(orchestration/verify_code.py ALLOW 의 명시 예외).
def _cli():
    argv = sys.argv[1:]
    slug = next((a for a in argv if not a.startswith("-")), None)
    if not slug:
        print("사용법: python -m web.verdict_view <slug> [--json] [--no-send]", file=sys.stderr)
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
        now = datetime.fromisoformat(top["ts"])
        write_text(book_log(slug, "verdict-%s.txt" % now.strftime("%Y%m%d")), text)
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    _cli()
