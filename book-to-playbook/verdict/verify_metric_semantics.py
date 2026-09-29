#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""계산기 의미 — 지표 무관 커버리지 엔진(검증층 세 번째 다리). 모든 책 공통.

## 왜 있나 / 무엇을 하나

기존 검증층은 사람이 쓴 라벨의 숫자·출처만 봤고, 계산기가 **무슨 조건을** 계산하는지는
코드에 숨어 검사 밖이었다. 그래서 (a)저자가 안 시킨 기준으로 계산(창작), (b)저자 조건의
일부만 계산(누락)이 조용히 통과했다. 실측 사고: '거래량 전일 1.5배'인데 20일평균으로 계산,
'거래량 1.5배 + 종가 고점 아래'인데 거래량만 계산(종가 위치 누락).

이 엔진은 **지표 종류를 몰라도** 모든 규칙에 같은 절차를 돌린다:

  1. 저자 라벨을 조건 축(aspect)으로 분해   — aspect_lexicon(공용 어휘)
  2. 그 규칙의 계산기가 덮는 aspect 를 스키마에서 읽음  — auto_types[t].aspects
  3. 양방향 커버리지:
       · 저자 aspect ⊄ 계산기 aspect  → 누락 (예: 종가 위치를 안 봄)
       · 계산기 축(기준선·기간)이 저자 소절에 없음 → 창작 (예: 20일평균인데 저자는 전일)
  4. 미달 → 사람 없이 자동 처리(resolve_inplace):
       · supersede: 저자 요구를 이미 덮는 계산기로 교체(🤖)
       · compose : 그 aspect 를 계산하는 지표(aspect_metric)가 있으면 보강(수집 — ✋ 아님)
       · 임계 미명시(정성)면 advisory 로 값만 보여주고 사람이 판단(정직하게 표시)

지표를 늘려도 aspects 한 줄, 조건 축을 늘려도 aspect_lexicon 한 줄. 검사 로직은 안 늘어난다.

## 한계
정성 조건("힘있게")은 임계가 없으면 자동 판정 못 한다 → 값은 수집·표시하되 advisory.
목표: "틀리면서 조용할 수 없다" + 구할 수 있는 건 다 수집(✋로 도망 금지).

## 사용
    python -m verdict.verify_metric_semantics [slug] [--json]
"""
import io
import json
import os
import re
import sys

from shared import paths  # noqa: F401
from shared.paths import BASE
from shared.pages import book_pages
from shared.rules_io import load_rules, iter_rules
from shared.tokens import norm
from verdict import metric_calc

REGISTRY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metric_registry.json")


def _registry():
    return json.loads(io.open(REGISTRY, encoding="utf-8").read())


def author_sections(html):
    """책 본문(#src)을 소절(ref) → 정규화 텍스트로 자른다."""
    ms = re.search(r'<script type="text/markdown" id="src">(.*?)</script>', html, re.S)
    if not ms:
        return {}
    secs, key, buf = {}, None, []
    for line in ms.group(1).split("\n"):
        m = re.match(r"^#{2,3}\s*([0-9]+-[0-9]+|에필로그)[.\s]", line)
        if m:
            if key:
                secs[key] = "\n".join(buf)
            key, buf = m.group(1), [line]
        elif key:
            buf.append(line)
    if key:
        secs[key] = "\n".join(buf)
    return {k: norm(t) for k, t in secs.items()}


def detect_aspects(text, lexicon):
    """정규화한 텍스트에서 조건 축(aspect) 집합을 뽑는다(공용 어휘 부분일치)."""
    n = norm(text)
    out = set()
    for asp, words in lexicon.items():
        if asp.startswith("_"):
            continue
        if any(w and norm(w) in n for w in words):
            out.add(asp)
    return out


def _metric_aspects(m, at):
    return set((at.get((m or {}).get("type")) or {}).get("aspects", []))


def _rule_metric_aspects(rule, at):
    """규칙(+subs)의 모든 계산기가 덮는 aspect 합집합.
    groupNeed(‘N개 중 M개 이상’)은 개수 판정 자체가 구조로 처리되므로 breadth 를 덮는다."""
    covered = set(_metric_aspects(rule.get("metric"), at))
    for s in rule.get("subs", []) or []:
        covered |= _metric_aspects(s.get("metric"), at)
    if rule.get("groupNeed") or rule.get("groupExtra"):
        covered.add("breadth")
    return covered


def _ground_ok(reg, metric, sec):
    """계산 기준(기준선·기간)의 근거 토큰이 저자 소절에 있나. (ok, tried)."""
    ground = reg.get("ground")
    if not ground:
        return True, []
    if "by" in ground:                       # 축이 정하는 근거(baseline=prev → '전일')
        axis = ground["by"]
        spec = (reg.get("axes") or {}).get(axis) or {}
        opt = (spec.get("options") or {}).get(metric.get(axis, spec.get("default"))) or {}
        tried = [norm(t) for t in opt.get("ground", [])]
    elif "any" in ground:
        tried = [norm(t) for t in ground["any"]]
    elif "param" in ground:
        v = metric.get(ground["param"])
        if v is None:
            return None, ["(파라미터 %s 누락)" % ground["param"]]
        forms = ground["as"] if isinstance(ground["as"], list) else [ground["as"]]
        tried = [norm(f.format(v=v)) for f in forms]
    else:
        return True, []
    return (bool([t for t in tried if t and t in sec]), tried)


def _check_rule(rule, at, lexicon, secs, mustcfg):
    """규칙 하나 → 어긋남 flag 목록(누락·창작·미선언). 지표 종류로 분기하지 않는다.

    누락은 **절(clause) 단위**로 본다: 저자 라벨을 접속사로 쪼개, 한 절의 '독립 조건 축
    (must_cover)'을 계산기가 하나도 안 덮으면 그 절은 방치된 것. 수식어로 붙는 축
    (급등 후·전고점 근처 등)은 must_cover 에서 빠져 오탐을 막는다."""
    flags = []
    m = rule.get("metric") or {}
    t = m.get("type")
    lab = rule.get("t", "")
    ref = rule.get("ref")
    covered = _rule_metric_aspects(rule, at)
    # 이 규칙이 자동 대상인가 — 자동 계산기가 하나도 없으면 authored-manual/그룹 → 커버리지 대상 아님
    is_auto = (t in at) or any((s.get("metric") or {}).get("type") in at
                               for s in rule.get("subs", []) or [])
    # 미선언 가드 — 계산 가능한데 자기선언(aspects) 없는 계산기는 자동 금지
    if t and t != "manual":
        declared = at.get(t)
        if t in metric_calc.CALC and (declared is None or "aspects" not in declared):
            flags.append({"kind": "미선언", "type": t, "ref": ref, "label": lab,
                          "why": "계산기 %s 가 aspects 를 선언하지 않음(자동 금지)" % t})
    # 누락 — 절 단위. 한 절의 must-cover 축을 계산기가 하나도 안 덮으면 그 절 방치.
    if is_auto:
        must = set(mustcfg.get("list", []))
        splitters = mustcfg.get("clause_split", [])
        pat = "|".join(re.escape(s) for s in splitters) or r"\+"
        seen = set()
        for clause in re.split(pat, lab):
            casp = detect_aspects(clause, lexicon) & must
            if casp and not (casp & covered):
                for asp in sorted(casp):
                    if asp in seen:
                        continue
                    seen.add(asp)
                    flags.append({"kind": "누락", "type": t, "ref": ref, "label": lab, "aspect": asp,
                                  "why": "저자가 '%s' 조건을 말했는데 계산기가 안 덮음" % asp})
    # 창작 — 계산기 축(기준선·기간)이 저자 소절에 근거 없나 (규칙+subs 각각)
    if ref and secs.get(ref) is not None:
        sec = secs[ref]
        for mm in [m] + [s.get("metric") or {} for s in rule.get("subs", []) or []]:
            reg = at.get(mm.get("type"))
            if reg and reg.get("ground"):
                ok, tried = _ground_ok(reg, mm, sec)
                if ok is not True:
                    flags.append({"kind": "창작", "type": mm.get("type"), "ref": ref, "label": lab,
                                  "why": "계산 기준 [%s] 의 근거(%s)가 저자 %s 소절에 없음"
                                         % (reg.get("computes", mm.get("type")), " | ".join(tried), ref)})
    return flags


def audit(slug, path, registry):
    """한 책의 규칙을 훑어 어긋남 목록(감지 전용)."""
    at, lex = registry["auto_types"], registry["aspect_lexicon"]
    must = registry.get("must_cover_aspects", {})
    secs = author_sections(io.open(path, encoding="utf-8").read())
    rules = load_rules(slug)
    if rules is None:
        return None
    flags = []
    for r in iter_rules(rules):
        flags += _check_rule(r, at, lex, secs, must)
    return flags


def resolve_inplace(rules, slug):
    """런타임 자동 처리(사람 0) — 어긋난 계산기를 저자 의도대로 스스로 해소한다.
      · supersede : 저자 요구를 이미 덮는 계산기로 교체(🤖). 예 눌림→반등확인 계산기.
      · compose   : 안 덮인 aspect 를 계산하는 지표(aspect_metric)가 있으면 sub 로 보강 —
                    임계 없는 정성 조건이면 advisory(값만 표시, 사람 판단)로. 데이터는 수집한다(✋ 아님).
    반환: 조치 목록."""
    if rules is None:
        return []
    reg = _registry()
    at, lex, amap = reg["auto_types"], reg["aspect_lexicon"], reg.get("aspect_metric", {})
    must = reg.get("must_cover_aspects", {})
    path = book_pages().get(slug)
    secs = author_sections(io.open(path, encoding="utf-8").read()) if path else {}
    actions = []
    for r in iter_rules(rules):
        for flag in _check_rule(r, at, lex, secs, must):
            m = r.get("metric") or {}
            if flag["kind"] == "누락":
                asp = flag["aspect"]
                sup = (at.get(m.get("type")) or {}).get("supersede")
                sup_covers = sup and asp in (at.get(sup["type"]) or {}).get("aspects", [])
                if sup_covers:                       # 교체하면 그 aspect 가 덮인다
                    for s_p, d_p in (sup.get("param_map") or {}).items():
                        if s_p in m:
                            m[d_p] = m.pop(s_p)
                    for k in sup.get("drop", []):
                        m.pop(k, None)
                    m["type"] = sup["type"]
                    actions.append(dict(flag, action="🤖 자동교체→%s" % sup["type"]))
                elif asp in amap and m.get("type"):  # 그 aspect 를 계산하는 지표로 보강(수집)
                    # 구조는 안 건드린다(주입·무결성 불변). 보강 지표를 **주 metric 에** 달아 두면,
                    # 값을 만드는 단 한 곳(metric_calc.evaluate)이 어느 채널에서 불리든 자동으로
                    # 이어붙인다 — 그룹(filter/entry/avoid/scorecard/reentry…)별 배선이 필요 없다.
                    comp = m.setdefault("_compose", [])
                    if not any(c.get("aspect") == asp for c in comp):
                        comp.append({"aspect": asp,
                                     "metric": {"type": amap[asp], "symbol": m.get("symbol"),
                                                "source": "auto"}})
                    actions.append(dict(flag, action="🧩 보강 값→%s" % amap[asp]))
                else:                                # 그 aspect 데이터가 없음 → 격리
                    m["source"] = "manual"
                    m["_needs_data"] = flag["why"]
                    actions.append(dict(flag, action="✋ 격리(데이터 없음)"))
            # 창작(기준선 어긋남)은 계산기 자체를 고쳐야 하는 것 — authoring/코드 수정 신호(런타임 조치 없음)
    return actions


def main(argv):
    as_json = "--json" in argv
    args = [a for a in argv if not a.startswith("--")]
    pages = book_pages()
    if not pages:
        print("검사할 책 페이지를 찾지 못했습니다.", file=sys.stderr)
        return 2
    slugs = args if args else sorted(pages)
    registry = _registry()
    results, total = {}, 0
    for slug in slugs:
        path = pages.get(slug)
        if not path:
            print("그런 책이 없습니다: %s" % slug)
            return 2
        flags = audit(slug, path, registry)
        results[slug] = flags
        if flags is None:
            continue
        total += len(flags)
        if as_json:
            continue
        print("=" * 70)
        print("%s — 계산기 의미(커버리지) 검사" % slug)
        print("=" * 70)
        if not flags:
            print("✓ 어긋남 없음")
            continue
        for f in flags:
            print("✗ [%s] %-14s (%s) %s" % (f["kind"], f["type"] or "-", f["ref"], f["label"][:42]))
            print("     %s" % f["why"])
    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif total:
        print("\n계산기 %d건이 저자 사양과 어긋남 — 런타임 resolve 가 자동교체/보강/격리로 처리." % total)
    else:
        print("\n전부 통과.")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
