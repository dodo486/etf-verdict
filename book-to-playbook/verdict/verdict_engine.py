#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""선언기반 판정엔진 (책 무관).

책마다 다른 종목·규칙·스코어카드를 코드에 if 문으로 박지 않는다. 이 파일 하나가
books/<slug>/rules.json 선언만 읽어 판정을 만든다 — 어떤 책이든 규칙만 뽑으면
자동판정이 나온다. metric 평가(값·문턱 비교)는 metric_calc(구간③ 계산기)에 위임한다.

읽는 선언(rules.json):
  · DATA{<종목>:{v,need,filter[],entry[],avoid[],caution?,exit?,note}, COMMON:{entry,avoid}}
  · PRODMETA{<종목>:{color, idx}}   — 표시색 · 필터가 보는 지수 심볼
  · SCORECARD[{t, ref, metric}]     — 장 시작 전 점수표(N지표)
  · GRADE(선택){go, small}          — 등급 문턱(없으면 지표 수에서 파생)

내는 출력 계약(아티팩트/알림이 소비):
  top     : {score, scorecard[{label,ok,why}], verdicts[], extras, ts}
  verdict : {prod,color,grade,reason,avoid[],avoid_keys[],filter_ok,
             eod_checks{ek:{ok,label}}, intraday[], metrics{k:text}, vol_ok,
             close, ma20, chg}

값은 전부 md_feed(시세 창구) 사실을 metric_calc 캐시로 받는다 — 여기서 시세를 새로
치지 않는다. 규칙마다 metric.source 가 'manual'/'intraday' 면 자동 판정에서 제외한다.
"""
import json
import os
import sys
from datetime import datetime, timezone

from shared.paths import BASE
from shared.notify import send_telegram, send_desktop
from shared.rules_io import load_rules
from verdict import metric_calc


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


# ------------------------------------------------------------------ 스코어카드
def scorecard(rules):
    """SCORECARD 선언 → (score, rows). rows = [{label, ok, why}].
    각 항목은 자기 metric(op/threshold)으로 pass 를 정한다. 계산 불가(데이터 실패)는
    ok=False (통과로 치지 않는다). score = ok 개수."""
    rows = []
    for item in rules.get("SCORECARD", []):
        res = metric_calc.evaluate(item.get("metric") or {})
        rows.append({"label": item.get("t", ""),
                     "ok": res.get("pass") is True,
                     "why": res.get("text", "")})
    return sum(1 for r in rows if r["ok"]), rows


# ------------------------------------------------------------------ 선언 평가(순수)
# 규칙(부모/leaf)의 발화·세분키를 자기 metric(과 subs)으로만 판단 — ref 조회 없음.
def _auto(m):
    return bool(m) and m.get("source") not in ("manual", "intraday") and m.get("type") not in (None, "manual")


def _fires(rule):
    """이 규칙이 발화하나 — 자기 metric(과 subs, combine=any)으로만. 자동 대상 아니면 None."""
    subs = rule.get("subs")
    if subs:
        vals = [_fires(s) for s in subs]
        vals = [v for v in vals if v is not None]
        return any(vals) if vals else None
    m = rule.get("metric")
    if not _auto(m):
        return None
    return metric_calc.evaluate(m)["pass"]


def _fired_keys(rule):
    """발화한 leaf(또는 sub)의 자기 세분키(부모키 아님). 복합키 'a|b'→분해."""
    subs = rule.get("subs")
    if subs:
        out = []
        for s in subs:
            out.extend(_fired_keys(s))
        return out
    if _fires(rule) is True:
        k = rule.get("k") or ""
        return k.split("|") if k else []
    return []


def _grade_thresholds(rules, total):
    """등급 문턱: 선언(GRADE)이 있으면 그것, 없으면 지표 수에서 파생(go=total-1, small=total-2)."""
    g = rules.get("GRADE") or {}
    go = g.get("go", max(1, total - 1))
    small = g.get("small", max(1, total - 2))
    return go, small


def grade_of(filter_ok, avoid_fired, score, go, small):
    """등급·사유 — filter → avoid → score 순."""
    if filter_ok is not True:
        return "🚫 진입 금지", "필터 미충족 — 추세 없음"
    if avoid_fired:
        return "⛔ 보류", "회피 신호 — 눌림 대기"
    if score >= go:
        return "✅ 매수 후보", "필터 통과 · 스코어 %d → 1차 분할 진입 준비" % score
    if score >= small:
        return "🟡 소액만", "스코어 %d — 확인 매수 수준" % score
    return "⚪ 관망", "스코어 %d — 신규 진입 보류" % score


# ------------------------------------------------------------------ 데이터 접근(얇게)
def _series(sym):
    return metric_calc._series(sym)


def _dir(sym):
    return metric_calc._dir(sym)


def _ok(d):
    return metric_calc._ok(d)


def _num(d, k):
    return d.get(k) if _ok(d) else None


# ------------------------------------------------------------------ 표현층(책 무관)
# 사람이 읽을 회피 문장·metrics{} 는 전부 규칙 라벨(t) + metric_calc 근거 텍스트에서 만든다.
def _leaf_text(rule):
    """leaf 규칙의 사람 문장: 라벨(t) + metric 근거 텍스트."""
    t = rule.get("t", "")
    res = metric_calc.evaluate(rule.get("metric") or {})
    return "%s — %s" % (t, res["text"]) if res.get("text") else t


def _avoid_sentence(rule):
    """발화한 회피 규칙 한 줄. subs 면 발화한 하위조건들을 묶어 보인다."""
    subs = rule.get("subs")
    if subs:
        fired = [_leaf_text(s) for s in subs if _fires(s) is True]
        detail = "; ".join(x for x in fired if x)
        return rule.get("t", "") + (" (%s)" % detail if detail else "")
    return _leaf_text(rule)


def _collect_metrics(rules_list, out):
    """규칙 목록의 leaf metric 근거 텍스트를 out[k] 에 모은다(자동 대상만). subs 재귀."""
    for r in rules_list:
        subs = r.get("subs")
        if subs:
            _collect_metrics(subs, out)
            continue
        m = r.get("metric")
        if not _auto(m):
            continue
        res = metric_calc.evaluate(m)
        txt = res.get("text") or ""
        # 미구현/미선언 type 은 값이 없고 안내문만 나온다 — 수치가 아니므로 노출 안 함.
        if res.get("value") is None and txt.startswith(("미구현", "metric type")):
            continue
        if not txt:
            continue
        k = r.get("k")
        if k:
            for kk in k.split("|"):
                out[kk] = txt


# ------------------------------------------------------------------ 종목별 전체 계약
def full_verdict(rules, prod, score, go, small):
    cfg = rules["DATA"][prod]
    meta = (rules.get("PRODMETA") or {}).get(prod, {})
    color = meta.get("color", "")
    p = _series(prod)
    close, ma20, chg = _num(p, "close"), _num(p, "ma20"), _num(p, "chg")

    # ── 필터: 게이트는 선언(_fires)이 판정
    filt_vals = [x for x in (_fires(r) for r in cfg.get("filter", [])) if x is not None]
    filter_ok = bool(filt_vals) and all(filt_vals)

    # ── 회피(종목별 + 시장공통 COMMON): 발화한 규칙의 세분키·사람 문장
    common = rules.get("DATA", {}).get("COMMON", {})
    avoid_rules = list(cfg.get("avoid", [])) + list(common.get("avoid", []))
    av, akeys = [], []
    for r in avoid_rules:
        keys = _fired_keys(r)
        if keys:
            av.append(_avoid_sentence(r))
            akeys.extend(keys)
    akeys = list(dict.fromkeys(akeys))   # 순서 유지 dedup

    # ── metrics{}: 항목별 근거 수치(아티팩트가 작은 글씨로). 규칙 k → 텍스트
    metrics = {}
    _collect_metrics(cfg.get("filter", []), metrics)
    _collect_metrics(avoid_rules, metrics)
    _collect_metrics(cfg.get("entry", []), metrics)
    # 필터 요약(UI 의 mt.filter) — 첫 자동 필터 규칙의 근거 텍스트
    for r in cfg.get("filter", []):
        if _auto(r.get("metric")):
            metrics.setdefault("filter", metric_calc.evaluate(r["metric"])["text"])
            break

    # ── 거래량(COMMON.entry[0]) → vol_ok · metrics['vol']
    vol_ok = False
    ce = (common.get("entry") or [])
    if ce:
        vm = ce[0].get("metric") or (ce[0].get("metric_candidates") or [{}])[0]
        if _auto(vm):
            vres = metric_calc.evaluate(vm)
            vol_ok = vres.get("pass") is True
            if vres.get("text"):
                metrics["vol"] = vres["text"]

    # ── eod_checks{ek:{ok,label}}: ek 를 단 자동 필터/진입 규칙만
    eod_checks = {}
    for r in list(cfg.get("filter", [])) + list(cfg.get("entry", [])):
        ek = r.get("ek")
        if ek and _auto(r.get("metric")):
            res = metric_calc.evaluate(r["metric"])
            eod_checks[ek] = {"ok": res.get("pass") is True, "label": res.get("text", "")}

    # ── 등급·사유
    if not filter_ok:
        grade, reason = "🚫 진입 금지", "필터 미충족 — 추세 없음"
    elif av:
        grade, reason = "⛔ 보류", "회피 신호 %d개 — 눌림 대기" % len(av)
    else:
        grade, reason = grade_of(True, [], score, go, small)

    # ── 장중 확인(자동 불가) — 필터 통과 & 회피 0 & 스코어 하한 이상일 때만 노출.
    #    intraday 로 표시할 규칙 = metric.source == 'intraday' (진입/공통 entry 안).
    intraday = []
    if filter_ok and not av and score >= small:
        for r in list(cfg.get("entry", [])) + list(common.get("entry", [])):
            if (r.get("metric") or {}).get("source") == "intraday":
                intraday.append(r.get("t", ""))

    return {"prod": prod, "color": color, "grade": grade, "reason": reason,
            "eod_checks": eod_checks, "avoid": av, "avoid_keys": akeys,
            "filter_ok": bool(filter_ok), "vol_ok": bool(vol_ok), "intraday": intraday,
            "metrics": metrics, "close": close, "ma20": ma20, "chg": chg}


def interpret(rules):
    """선언만으로 낸 결정 dict {prod: {filter_ok, avoid_fired, grade, ...}} — 순수 선언 트랙."""
    score, _rows = scorecard(rules)
    total = len(rules.get("SCORECARD", []))
    go, small = _grade_thresholds(rules, total)
    out = {}
    for prod, cfg in rules.get("DATA", {}).items():
        if not isinstance(cfg, dict) or prod == "COMMON":
            continue
        v = full_verdict(rules, prod, score, go, small)
        out[prod] = v
    return out


def render(slug):
    """top 계약을 만든다: {score, scorecard, verdicts, extras, ts}."""
    metric_calc.clear_cache()
    rules = load_rules(slug)
    score, rows = scorecard(rules)
    total = len(rows)
    go, small = _grade_thresholds(rules, total)
    verdicts = [full_verdict(rules, prod, score, go, small)
                for prod, cfg in rules.get("DATA", {}).items()
                if isinstance(cfg, dict) and prod != "COMMON"]
    now = datetime.now(timezone.utc).astimezone()
    return {"score": score,
            "scorecard": [{"label": r["label"], "ok": r["ok"], "why": r["why"]} for r in rows],
            "verdicts": verdicts, "ts": now.isoformat(), "extras": {}}


# ------------------------------------------------------------------ 출력 텍스트 / 알림
def build_text(top, title=""):
    now = datetime.fromisoformat(top["ts"])
    score = top["score"]
    total = len(top["scorecard"])
    head = "📈 %s  (%s KST)" % (title or "데일리 진입 환경", now.strftime("%Y-%m-%d %H:%M"))
    L = [head, "장 시작 전 스코어카드: %d/%d" % (score, total)]
    for r in top["scorecard"]:
        L.append("   %s %s" % ("🟢" if r["ok"] else "🔴", r["label"]))
        if r["why"]:
            L.append("      └ %s" % r["why"])
    L.append("─" * 30)
    for v in top["verdicts"]:
        if v["grade"] == "데이터오류":
            L.append("%s: 데이터오류" % v["prod"]); continue
        L.append("%s %s  %s" % (v.get("color", ""), v["prod"], v["grade"]))
        L.append("   %s" % v["reason"])
        if v.get("close") and v.get("ma20"):
            side = "위" if v["close"] > v["ma20"] else "아래"
            L.append("   종가 %.2f / 20일선 %.2f (%s), 당일 %+.1f%%"
                     % (v["close"], v["ma20"], side, v.get("chg") or 0))
        for a in v.get("avoid", []):
            L.append("   ⚠ %s" % a)
        if v.get("intraday"):
            L.append("   👁 장중 확인: " + " · ".join(v["intraday"]))
    L.append("─" * 30)
    L.append("※ 환경 판정(EOD 기준). 장중 항목은 직접 확인 후 최종 진입. 규칙 출처=저자 명시.")
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
    title = book_title(slug)
    text = build_text(top, title)
    if "--json" in argv:
        print(json.dumps(top, ensure_ascii=False, indent=2))
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
