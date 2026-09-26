#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""해석기 ↔ 라이브 엔진 판정 일치 검증 (단계적 이관 안전장치).

책-무관 해석기(metric_calc + rules/data_spec 선언)가 만든 '판정'이 현재 손코딩
엔진(etf_daily_verdict.py --json)의 판정과 같은지 본다. 같으면 엔진을 해석기로
바꿔도 라이브 신호가 안 바뀐다는 뜻 — 그때 안전하게 교체한다.

비교 대상(드리프트에 강한 '결정'만):
  · filter_ok       — 그 종목 진입 필터 통과 여부
  · avoid 발화 집합  — 자동 판정 가능한 회피 규칙 중 켜진 것

주의: 두 프로세스가 시세를 각각 받으므로 수치는 미세하게 다를 수 있다. 그래서
값이 아니라 '결정(bool)'을 비교하고, 임계 근처(경계)라 갈릴 수 있는 건 경고로만 낸다.
"""
import json, os, subprocess, sys
import metric_calc

BASE = os.path.dirname(os.path.abspath(__file__))


def _spec_by_ref(slug):
    spec = json.load(open(os.path.join(BASE, "%s_data_spec.json" % slug), encoding="utf-8"))["items"]
    by = {}
    for it in spec:
        by.setdefault(it.get("ref"), []).append(it.get("metric") or {})
    return by


def _rules(slug):
    return json.load(open(os.path.join(BASE, "books", slug, "rules.json"), encoding="utf-8"))["DATA"]


def interpret(slug):
    """선언만으로 각 종목의 filter_ok / 켜진 avoid k 집합을 만든다(자동 가능한 것만)."""
    spec_by_ref = _spec_by_ref(slug)
    DATA = _rules(slug)
    out = {}
    for prod, cfg in DATA.items():
        if not isinstance(cfg, dict) or prod == "COMMON":
            continue
        # 필터: auto metric 이 있는 필터 규칙이 모두 pass 여야 통과(계산 불가는 제외)
        filt_results = []
        for r in cfg.get("filter", []):
            for m in spec_by_ref.get(r.get("ref"), []):
                res = metric_calc.evaluate(m)
                if res["pass"] is not None:
                    filt_results.append(res["pass"])
        filter_ok = all(filt_results) if filt_results else None
        # 회피: **트리거 지표(min 문턱이 있는 것)**가 발화하면 on.
        #   게이트 지표(above_ma 등 min 없는 것)는 필터용이지 회피 트리거가 아니다
        #   — 이걸 안 가리면 '20일선 위' 같은 필터가 회피로 오발화한다(주소 공유 문제).
        #   k 없는 avoid(전용지표 미선언·수동·장중·subs)는 아직 자동 대상이 아니라 건너뛴다.
        fired = []
        for r in cfg.get("avoid", []):
            k = r.get("k")
            if not k:
                continue
            on = False
            for m in spec_by_ref.get(r.get("ref"), []):
                if m.get("min") is None:
                    continue                       # 게이트(문턱 없음) = 필터용, 회피 트리거 아님
                if metric_calc.evaluate(m)["pass"] is True:
                    on = True
            if on:
                fired.extend(k.split("|"))          # 복합키 'a|b' → 개별 엔진키로 분해
        out[prod] = {"filter_ok": filter_ok, "avoid_fired": sorted(set(fired))}
    return out


def interpret_draft(slug):
    """자기완결 초안(규칙 안에 metric 이 박힌 것)만 읽어 판정한다 — ref 조회 없음.
    이게 '레시피 한 곳' 구조가 실제로 도는지 보는 검증이다."""
    path = os.path.join(BASE, "books", slug, "rules.selfcontained.draft.json")
    DATA = json.load(open(path, encoding="utf-8"))["DATA"]

    def fires(rule):
        """이 규칙(부모/leaf)이 발화하나 — 자기 metric(과 subs)으로만 판단."""
        subs = rule.get("subs")
        if subs:
            return any(fires(s) for s in subs)      # combine=any
        m = rule.get("metric")
        if not m or m.get("source") in ("manual", "intraday"):
            return None                              # 자동 대상 아님
        return metric_calc.evaluate(m)["pass"]

    def fired_keys(rule):
        """발화한 **leaf(또는 sub)의 자기 키**를 모은다 — 부모키가 아니라 세분키.
        (subs 는 각자 엔진과 같은 세분키를 갖는다: nvda_only·breadth6·leader_break…)"""
        subs = rule.get("subs")
        if subs:
            out = []
            for s in subs:
                out.extend(fired_keys(s))
            return out
        if fires(rule) is True:
            k = rule.get("k") or ""
            return k.split("|") if k else []
        return []

    out = {}
    for prod, cfg in DATA.items():
        if not isinstance(cfg, dict) or prod == "COMMON":
            continue
        filt = [fires(r) for r in cfg.get("filter", [])]
        filt = [x for x in filt if x is not None]
        filter_ok = all(filt) if filt else None
        fired = []
        for r in cfg.get("avoid", []):
            fired.extend(fired_keys(r))
        out[prod] = {"filter_ok": filter_ok, "avoid_fired": sorted(set(fired))}
    return out


def engine(slug):
    """라이브 엔진 --json 의 종목별 filter_ok / avoid_keys."""
    p = subprocess.run([sys.executable, os.path.join(BASE, "%s_daily_verdict.py" % slug),
                        "--json", "--no-send"], cwd=BASE, capture_output=True, timeout=120)
    data = json.loads(p.stdout.decode("utf-8"))
    return {v["prod"]: {"filter_ok": v.get("filter_ok"),
                        "avoid_keys": sorted(set(v.get("avoid_keys") or []))}
            for v in data.get("verdicts", [])}


def main(slug="etf"):
    use_draft = "--draft" in sys.argv
    interp = interpret_draft(slug) if use_draft else interpret(slug)
    eng = engine(slug)
    print("=== 판정 일치 검증: %s (%s) ===" % (slug, "자기완결 초안" if use_draft else "ref 조회"))
    bad = 0
    for prod in eng:
        e = eng[prod]; i = interp.get(prod, {})
        fo_e, fo_i = e["filter_ok"], i.get("filter_ok")
        mark = "✅" if fo_e == fo_i else ("· 경계?" if fo_i is None else "❌")
        if fo_e != fo_i and fo_i is not None:
            bad += 1
        print("  [%s] filter_ok 엔진=%s 해석기=%s  %s" % (prod, fo_e, fo_i, mark))
        # avoid: 양방향 비교 — 해석기만 켬(과발화)·엔진만 켬(미발화) 둘 다 불일치.
        e_av, i_av = set(e["avoid_keys"]), set(i.get("avoid_fired") or [])
        extra = i_av - e_av       # 해석기만 켬
        missing = e_av - i_av     # 엔진만 켬(해석기가 놓침)
        tail = ""
        if extra:
            tail += "  ❌해석기만:" + str(sorted(extra))
        if missing:
            tail += "  ❌엔진만(놓침):" + str(sorted(missing))
        print("      avoid 엔진=%s · 해석기발화=%s%s" % (sorted(e_av), sorted(i_av), tail))
        if extra or missing:
            bad += 1
    print("\n%s" % ("✅ 결정 불일치 0 — 해석기가 엔진과 같은 판정" if bad == 0
                    else "❌ 불일치 %d건 — 교체 전 조사 필요" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "etf"))
