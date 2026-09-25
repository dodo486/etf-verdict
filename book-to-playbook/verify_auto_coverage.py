#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""구간③ 자동수집 커버리지 검사 — '자동 가능한데 ✋직접으로 샌 것'을 사람 판단 없이 잡는다.

## 왜 있나
구간③에서 `source:"manual"`(✋직접)은 사람이 자유 판단으로 찍어 왔다. 그래서 "jhts 시세수집팀에
요청하면 데이터가 나오는데 아무도 안 물어본 것"(예: 주도주 6개 방향)이 "데이터 자체가 없는 것"과
구분 없이 ✋직접으로 새어 나갔다. 판단 주체가 사람이라 실수·게으름이 통과된다.

## 무엇을 바꾸나
사람은 **무엇을 재는가(metric type)만 선언**하고, 자동 가능 여부는 `metric_registry.json`이 정한다.
  · type ∈ auto_types & impl=true   → 🤖 자동(데이터 있음 + 판정 로직 있음)
  · type ∈ auto_types & impl=false  → 🚧 미구현(데이터는 jhts 에 있는데 로직만 없음 — ✋직접 아님, 해야 할 일)
  · type ∈ no_data_types            → ✋ 직접(데이터 자체가 없음 — 정당)
  · 선언 없음 / 미등록 type          → ❌ 미결선(자동/무데이터를 시스템이 못 정함 — 선언하라)

## 판정 대상
각 책 rules.json 의 체크리스트 조건(부모·subs). 자동 바인딩 신호:
  · k(엔진 avoid 키) / ek / ik 있음        → 🤖 (엔진이 계산)
  · 그 ref 에 auto metric 인 data_spec 있음 → 🤖 (커버됨)
  · 조건에 mtype 선언 있음                   → 레지스트리로 분류
  · 위 어느 것도 없음                        → ❌ 미결선

## 사용
    python verify_auto_coverage.py [slug] [--product SOXL] [--json]
결과: 🤖/🚧/✋/❌ 개수 + ❌·🚧 목록. ❌ 있으면 exit 1(블로킹), 🚧 는 경고.
"""
import io, json, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))

def load(p):
    return json.loads(io.open(os.path.join(BASE, p), encoding="utf-8").read())

def rules_path(slug):
    return os.path.join("books", slug, "rules.json")

def spec_path(slug):
    for p in (os.path.join("books", slug, "data_spec.json"), "%s_data_spec.json" % slug):
        if os.path.exists(os.path.join(BASE, p)):
            return p
    return None

def auto_refs(spec, registry):
    """auto metric(그 자체로 자동수집 지표)인 data_spec 항목이 있는 ref 집합."""
    at = registry["auto_types"]
    out = set()
    for it in spec.get("items", []):
        m = it.get("metric") or {}
        t = m.get("type")
        if it.get("source") == "auto" and t in at:
            out.add(it.get("ref"))
    return out

def classify(cond, registry):
    """조건 하나 → (mark, 설명). cond: {t,k,ek,ik,ref,mtype}.
    ref 단위 추측은 하지 않는다(한 소절에 지표가 여럿이라 오분류) — 조건 자신이 근거를 대야 한다."""
    at, nd = registry["auto_types"], registry["no_data_types"]
    # 1) 엔진 키/자동판정 신호 = 이미 자동
    if cond.get("k") or cond.get("ek") or cond.get("ik"):
        return "auto", "엔진 키(%s)" % (cond.get("k") or cond.get("ek") or cond.get("ik"))
    # 2) 명시적 metric type 선언 → 레지스트리로 파생
    mt = cond.get("mtype")
    if mt:
        if mt in at:
            return ("auto", "mtype=%s(구현)" % mt) if at[mt]["impl"] else ("todo", "mtype=%s(데이터 O·로직 미구현)" % mt)
        if mt in nd:
            return "manual", "mtype=%s(데이터 없음)" % mt
        return "bad", "미등록 mtype=%s" % mt
    # 3) 근거 없음 → 미결선(선언 강제)
    return "unset", "자동/무데이터 미선언"

def check(slug, product=None):
    registry = load("metric_registry.json")
    rules = load(rules_path(slug))

    rows = []
    DATA = rules.get("DATA", {})
    prods = [product] if product else [p for p in DATA if isinstance(DATA[p], dict) and p != "COMMON"]
    # exit(익절·손절 사다리)은 라이브 판정 체크박스가 아니라 실행 계획이라 커버리지 대상에서 뺀다.
    for prod in prods:
        cfg = DATA.get(prod) or {}
        for g in ("filter", "entry", "avoid", "caution"):
            for r in cfg.get(g, []) or []:
                if not isinstance(r, dict):
                    continue
                conds = []
                if r.get("subs"):
                    for s in r["subs"]:
                        conds.append(dict(s, _label="%s › %s" % (r.get("t", "")[:16], s.get("t", "")[:26])))
                else:
                    conds.append(dict(r, _label=r.get("t", "")[:40]))
                for c in conds:
                    mark, why = classify(c, registry)
                    rows.append((prod, g, c.get("ref"), c.get("_label"), mark, why))
    return rows

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    slug = args[0] if args else "etf"
    product = None
    if "--product" in sys.argv:
        product = sys.argv[sys.argv.index("--product") + 1]
    as_json = "--json" in sys.argv

    rows = check(slug, product)
    ICON = {"auto": "🤖", "todo": "🚧", "manual": "✋", "unset": "❌", "bad": "❌"}
    from collections import Counter
    tally = Counter(r[4] for r in rows)

    if as_json:
        print(json.dumps({"slug": slug, "product": product,
                          "tally": dict(tally),
                          "rows": [{"prod": r[0], "grp": r[1], "ref": r[2], "label": r[3], "mark": r[4], "why": r[5]} for r in rows]},
                         ensure_ascii=False))
        return

    title = "%s%s 구간③ 자동수집 커버리지" % (slug, (" / " + product) if product else "")
    print("=" * 66)
    print(title)
    print("=" * 66)
    print("🤖 자동 %d · 🚧 미구현(데이터O·로직X) %d · ✋ 직접(데이터X) %d · ❌ 미결선 %d"
          % (tally.get("auto", 0), tally.get("todo", 0), tally.get("manual", 0), tally.get("unset", 0) + tally.get("bad", 0)))
    for want, head in (("todo", "🚧 미구현 — 데이터는 jhts 에 있으니 로직 구현(✋직접 금지)"),
                       ("unset", "❌ 미결선 — mtype 선언 필요(자동인지 무데이터인지 시스템이 판정하게)"),
                       ("bad", "❌ 미등록 mtype")):
        sub = [r for r in rows if r[4] == want]
        if sub:
            print("\n[%s]" % head)
            for r in sub:
                print("   %s [%s/%s] %s  — %s" % (ICON[r[4]], r[0], r[2], r[3], r[5]))
    blocking = tally.get("unset", 0) + tally.get("bad", 0)
    print("\n%s" % ("통과 — 미결선 0" if blocking == 0 else "미결선 %d건(블로킹) · 미구현 %d건(경고)" % (blocking, tally.get("todo", 0))))
    sys.exit(1 if blocking else 0)

if __name__ == "__main__":
    main()
