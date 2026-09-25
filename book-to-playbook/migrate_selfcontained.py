#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""자기완결 규칙 구조로 이관 (레시피 한 곳).

지금: 규칙(rules.json)과 지표(data_spec, 별도 파일)가 '소절 주소(ref)'로만 느슨히
연결 → 한 소절에 여럿이 매달려 오연결·이름표오류·고아·과발화가 생긴다.

목표 구조: **규칙(과 세부조건 sub)이 자기 지표를 자기 안에 품는다.** 별도 명세 파일과
ref 매핑이 필요 없어진다(진실 하나). 지표는 방향까지 표현한다.

  규칙 = {
    "t": "라벨", "ref": "소절(추적용)", "k": "엔진키",
    "metric": {
       "type": "n_day_return",   # 무엇을 재나(레지스트리 type)
       "symbol": "SOXL",          # 어느 심볼
       "n": 5,                    # type별 파라미터(ma/n/days…)
       "op": ">=",                # 방향: >= / <= / above / below
       "threshold": 15,           # 발화/게이트 기준값(옛 min 을 대체)
       "role": "trigger",         # gate(필터 통과) / trigger(회피 발화)
       "source": "auto"           # auto / manual / intraday
    },
    "subs": [ {…자기 metric…}, … ]  # 복합이면 각 sub 가 자기 지표를 품는다
  }

이 스크립트는 라이브 rules.json 을 건드리지 않는다. data_spec 을 규칙 안으로 접어넣은
'초안'을 만들고, 자동으로 못 묶은(모호/누락) 규칙을 정확히 목록으로 뽑는다 —
그게 다음에 사람이 채울 콘텐츠 worklist 다.
"""
import io, json, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
GATE_TYPES = {"above_ma", "hold_above_ma"}   # 필터 게이트(문턱 없이 '위/유지')
INTRADAY_TYPES = {"above_open", "higher_low", "minute_high_hold"}  # 장중 — EOD 엔진엔 수동
COMPOSITE_TYPES = {"defensive_only", "bad_rate_drop", "count_above_ma"}  # 복합(전용 계산기)

IDX = {"TQQQ": "^NDX", "SOXL": "^SOX", "UPRO": "^GSPC"}   # 종목 → 대표 지수
# 회피 규칙의 엔진키(k) → 지표 type. "이 규칙은 이 지표로 판정한다"의 사람 판단.
K2TYPE = {"run5": "n_day_return", "wick": "upper_wick", "tnx": "pct_change",
          "usd_str": "dxy_change", "vol_sell": "volume_ratio",
          "gap": "gap_up", "vix": "pct_change", "earnings": "earnings_dday",
          "overheat": "count_up_days"}
# 강도/개수 지표 = 진입·게이트용(많을수록 좋음). 회피 트리거로 쓰면 방향이 거꾸로다.
# (예: nvda_only '주도주 약화'는 count_up>=2 발화가 아니라 그 반대 — 전용 divergence 지표 필요)
STRENGTH_TYPES = GATE_TYPES | {"count_up", "count_above_ma"}


def _label_symbol(t, prod):
    """규칙 라벨에서 심볼을 읽는다(반도체지수→^SOX 등). 없으면 종목 자신/지수."""
    if "반도체지수" in t or "^SOX" in t:
        return "^SOX"
    if "S&P500" in t or "S&P 500" in t:
        return "^GSPC"
    if "나스닥100" in t or "나스닥 100" in t:
        return "^NDX"
    return None


def _match_symbol(cands, want):
    for m in cands:
        if m.get("symbol") == want:
            return m
    return None


def load(p):
    return json.loads(io.open(os.path.join(BASE, p), encoding="utf-8").read())


def build_spec_index(items):
    by_ref = {}
    for it in items:
        by_ref.setdefault(it.get("ref"), []).append(it.get("metric") or {})
    return by_ref


def to_inline(metric, group):
    """data_spec 의 metric(type/symbol/min…) → 자기완결 metric(op/threshold/role)."""
    t = metric.get("type")
    role = "gate" if (group in ("filter", "entry") and t in GATE_TYPES) else \
           ("trigger" if group == "avoid" else "gate")
    op = "above" if t in GATE_TYPES and role == "gate" else ">="
    threshold = metric.get("min")
    out = {"type": t, "role": role, "op": op, "source": "auto"}
    for k in ("symbol", "symbols", "ma", "n", "days"):
        if k in metric:
            out[k] = metric[k]
    if threshold is not None:
        out["threshold"] = threshold
    elif role == "trigger":
        out["_todo"] = "문턱(threshold) 미선언 — 저자 숫자 확인 필요"
    return out


def resolve(rule, group, prod, cands):
    """규칙 하나 → 그 규칙의 지표 하나를 고른다(사람 판단을 규칙으로 encode).
    반환: (metric_or_list, how) — how 는 리포트용 설명. None 이면 못 고름."""
    t = rule.get("t") or ""
    k = rule.get("k")

    # 0) 복합/특수 지표는 라벨 키워드로 지목(k 없음)
    for kw, typ, how in (("방어주", "defensive_only", "라벨 '방어주'"),
                         ("금리", "bad_rate_drop", "라벨 '나쁜금리'"),
                         ("섹터", "count_above_ma", "라벨 '섹터'")):
        if kw in t:
            hit = next((m for m in cands if m.get("type") == typ), None)
            if hit:
                if typ == "bad_rate_drop" and not ("하락" in t or "↓" in t):
                    continue
                return hit, "%s→%s" % (how, typ)

    # 1) 엔진키(k)가 지표 type 을 지목한다
    if k and k in K2TYPE:
        typ = K2TYPE[k]
        same = [m for m in cands if m.get("type") == typ]
        if len(same) == 1:
            return same[0], "k=%s→%s" % (k, typ)
        if len(same) > 1:  # 같은 type 여럿 → 심볼로(종목/지수)
            want = _label_symbol(t, prod) or prod or IDX.get(prod)
            hit = _match_symbol(same, want) or _match_symbol(same, IDX.get(prod)) or _match_symbol(same, prod)
            if hit:
                return hit, "k=%s→%s @%s" % (k, typ, hit.get("symbol"))

    # 2) 게이트(필터/진입) — 라벨 키워드로 above/hold/ma 구분
    if group in ("filter", "entry"):
        want_sym = _label_symbol(t, prod) or (prod if prod in ("TQQQ", "SOXL", "UPRO") else None)
        # 장중(시초가·눌림·저점) → intraday
        if "시초가" in t or "눌림" in t or "저점" in t:
            for m in cands:
                if m.get("type") in INTRADAY_TYPES:
                    return m, "장중(intraday)"
        if "유지" in t or "연속" in t or ("2거래일" in t):
            hit = next((m for m in cands if m.get("type") == "hold_above_ma"), None)
            if hit:
                return hit, "라벨 '유지'→hold_above_ma"
        ma = 60 if "60일선" in t else (5 if "5일선" in t else 20)
        hit = next((m for m in cands if m.get("type") == "above_ma" and m.get("ma") == ma
                    and (want_sym is None or m.get("symbol") == want_sym)), None)
        if hit:
            return hit, "라벨→above_ma ma%d @%s" % (ma, hit.get("symbol"))

    # 3) 회피 — 트리거 지표(문턱 있는 것) 우선, 심볼로 좁힘
    if group == "avoid":
        want = _label_symbol(t, prod) or prod
        trig = [m for m in cands if m.get("type") not in STRENGTH_TYPES]
        cand2 = [m for m in trig if m.get("symbol") in (want, IDX.get(prod), prod)] or trig
        if len(cand2) == 1:
            return cand2[0], "회피 트리거 @%s" % cand2[0].get("symbol")
        # 방향 회피: '아래' 규칙인데 게이트 지표(above_ma)뿐 → op:below 로 전환
        if "아래" in t:
            g = [m for m in cands if m.get("type") == "above_ma"]
            g = [m for m in g if ("60일선" in t) == (m.get("ma") == 60)]
            if len(g) == 1:
                return dict(g[0], _below=True), "방향 '아래'→below @%s" % g[0].get("symbol")

    # 4) 주의(caution) — 이격(ma_distance)은 종목별로 짝. 나머지(급등·장중)는 지표 미비→수동
    if group == "caution":
        if "벌어" in t or "이격" in t:
            hit = _match_symbol([m for m in cands if m.get("type") == "ma_distance"], prod)
            if hit:
                return hit, "이격→ma_distance @%s" % prod
        return None, None   # '많이 올랐다'·'30분' 등은 전용지표 미비 → 수동

    # 5) 마지막 안전망 — 후보가 딱 하나면 그것으로. 단 회피에 강도지표(방향 반대)는 금지.
    non_empty = [m for m in cands if m.get("type")]
    if len(non_empty) == 1:
        if group == "avoid" and non_empty[0].get("type") in STRENGTH_TYPES:
            return None, None   # 회피에 강도지표는 안 됨 → 전용 divergence 지표 필요(모호로 flag)
        return non_empty[0], "단일 후보→%s" % non_empty[0].get("type")
    return None, None


def to_inline_resolved(metric, group, below=False):
    out = to_inline(metric, group)
    if below:
        out["op"] = "below"
        out["threshold"] = 0
        out.pop("_todo", None)
    if metric.get("type") in INTRADAY_TYPES:
        out["source"] = "intraday"
    if metric.get("type") in COMPOSITE_TYPES:
        out["source"] = "auto"
        out["composite"] = True
    return out


def bind(rule, group, by_ref, report, path, prod):
    """규칙/서브 하나에 metric 을 붙인다. 모호/누락은 report 에 기록."""
    subs = rule.get("subs")
    if subs:
        rule["combine"] = "any"   # subs 중 하나라도 발화하면 부모 on
        for i, s in enumerate(subs):
            bind(s, group, by_ref, report, path + [rule.get("k") or rule.get("ref"), "sub%d" % i], prod)
        return
    ref = rule.get("ref")
    cands = by_ref.get(ref, [])
    cands = [m for m in cands if m]   # 빈 {} 제거
    label = " › ".join(str(x) for x in path) + " :: " + (rule.get("t") or "")[:30]
    # resolve 를 manual 판정보다 먼저 시도한다. 데이터가 있어 자동 판정 가능한데
    # '판정엔진 미구현'이라며 manual 로 둔 규칙(예: 60일선 아래)은 자동으로 승격한다
    # — SKILL 원칙: 데이터 있는 미구현은 ✋직접이 아니라 🚧 해야 할 일.
    picked, how = resolve(rule, group, prod, cands) if ref else (None, None)
    if picked is not None:
        below = picked.pop("_below", False)
        rule["metric"] = to_inline_resolved(picked, group, below)
        note = "  (%s%s)" % (how, ", manual→auto 승격" if rule.get("source") == "manual" else "")
        report["bound"].append(label + note)
        return
    if rule.get("source") == "manual" or not ref:
        rule["metric"] = {"type": "manual", "role": "trigger" if group == "avoid" else "gate",
                          "source": "manual", "reason": rule.get("reason") or "수동/미선언"}
        report["manual"].append(label)
        return
    if not cands:
        rule["metric"] = {"type": "manual", "role": "trigger" if group == "avoid" else "gate",
                          "source": "manual", "reason": "지표 없음(장중/방향/전용지표 신규선언 필요)"}
        report["missing"].append("%s  [ref %s]" % (label, ref))
    else:
        rule["metric_candidates"] = [to_inline(m, group) for m in cands]
        report["ambiguous"].append("%s  [ref %s 후보: %s]" % (
            label, ref, ", ".join(m.get("type", "?") for m in cands)))


def main():
    rules = load("books/etf/rules.json")
    spec = load("etf_data_spec.json")["items"]
    by_ref = build_spec_index(spec)
    report = {"bound": [], "ambiguous": [], "missing": [], "manual": []}

    DATA = rules["DATA"]
    for prod, cfg in DATA.items():
        if not isinstance(cfg, dict):
            continue
        for group in ("filter", "entry", "avoid", "caution"):
            for rule in cfg.get(group, []) or []:
                if isinstance(rule, dict):
                    bind(rule, group, by_ref, report, [prod, group], prod)

    out_path = os.path.join(BASE, "books", "etf", "rules.selfcontained.draft.json")
    io.open(out_path, "w", encoding="utf-8").write(json.dumps(rules, ensure_ascii=False, indent=1))

    print("=== 자기완결 이관 초안 ===")
    print("초안 파일:", os.path.relpath(out_path, BASE))
    print()
    print("✅ 자동 바인딩 %d개 (ref 1:1 로 지표를 규칙 안에 접어넣음)" % len(report["bound"]))
    print("✋ 수동/미선언 %d개" % len(report["manual"]))
    print()
    print("⚠️  모호 %d개 — 한 규칙에 후보 지표가 여럿(사람이 골라야):" % len(report["ambiguous"]))
    for x in report["ambiguous"]:
        print("   -", x)
    print()
    print("❌ 누락 %d개 — 이 규칙 역할에 맞는 지표가 없음(방향지표 신규선언/수동표시):" % len(report["missing"]))
    for x in report["missing"]:
        print("   -", x)


if __name__ == "__main__":
    main()
