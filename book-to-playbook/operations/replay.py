#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""장중 재생 드라이버 (책 무관) — 구간④. 트리의 '가장 촘촘한 tf' 봉 타임스탬프로 asof 타임라인을 만들어,
그 각 asof 에서 판정을 다시 내고 '장중 신호·등급 시계열'을 낸다.

## 왜 있나

일봉만 쓰는 트리는 하루 한 점(그날 마감)에서 판정하면 끝이다 — operations.verify_signal_parity 가 하는 그대로다.
하지만 트리가 5분봉·1분봉(tf="5m"/"1m") 조건을 섞으면, '일봉 regime(어제 확정) AND 분봉 trigger(장중)'를
그 분봉 간격으로 재생해 봐야 장중 신호가 보인다. 이 드라이버는 트리의 가장 촘촘한 tf 를 찾아(finest_tf), 그
간격의 봉 타임스탬프를 asof 타임라인으로 깔고(asof_timeline), 각 asof 에서 verdict_engine.product_verdict 를
불러(라이브 드라이버가 하는 그대로) 장중 등급 시계열을 만든다.

일봉 잎은 '장중 asof 이하 마지막 확정 일봉'(어제 확정값)으로, 분봉 잎은 'asof 이하 마지막 분봉'(장중값)으로
자동으로 자른다 — cond.py 의 settled_map·minute_series 가 각 잎을 자기 축에서 asof 로 잘라 주기 때문이다. 즉
이 드라이버는 평가 규칙을 새로 만들지 않고, asof 를 분봉 간격으로 깔아 '같은 판정 엔진'을 여러 시점에 돌릴 뿐이다.

## 정직한 한계 (가짜로 안 늘린다)

분봉은 jhts 분봉(md_feed.minutes → jhts.minute_bars, OHLCV+UTC)에서 온다. 개별주·ETF 는 Alpaca(키 있으면
깊은 히스토리), 지수·선물과 Alpaca 미연결은 최근 ~7거래일(야후 1분봉 보관 한계)만 온다.
따라서 장중 타임라인도 데이터 있는 세션·봉만 깔린다. 타임라인이 비거나 짧으면 "N세션·M봉만 재생,
그 밖은 데이터 없음"을 그대로 표면화한다 — 없는 분봉을 지어내 타임라인을 늘리지 않는다.

## 단방향(폭포수)

operations/(구간④)에 있고 verdict·shared 만 import 한다(downward). 상류(playbook·checklist·verdict·shared)는
이 파일을 import 하지 않는다 — verify_teams 가 강제.

## 사용

    python -m operations.replay <slug> [--prod SPY] [--limit 20]
    → 장중 등급 시계열(asof · 상품 · 등급) + 데이터 범위(세션·봉 수) 요약. 분봉 없으면 "데이터 없음" 표면화.
"""
import sys
from datetime import datetime, timezone

from shared import cond, tree_grade
from verdict import verdict_engine

# tf 촘촘함 순서 — 초로 환산(작을수록 촘촘). cond.TIMEFRAMES 와 짝(그 밖 tf 는 들어올 수 없다, 문법이 막는다).
TF_SECONDS = {"1m": 60, "5m": 300, "1d": 86400}


def tree_tfs(tree):
    """트리가 실제로 쓰는 tf 집합(모든 px 잎). defs 펼침. 늘 최소 {"1d"}(기본값)를 포함할 수 있다."""
    defs = tree.get("defs") or {}
    tfs = set()
    nodes = list(defs.values())
    for cfg in tree["products"].values():
        nodes.extend(n for _z, _l, _r, n in cond.zone_nodes(cfg))
    for node in nodes:
        for n in cond.labeled_all(node, defs):
            if isinstance(n, dict) and "px" in n:
                tfs.add(n.get("tf", "1d"))
    return tfs


def finest_tf(tree):
    """트리의 '가장 촘촘한 tf'(1m < 5m < 1d). px 잎이 없으면(순수 수동 트리) 기본 "1d"."""
    tfs = tree_tfs(tree)
    if not tfs:
        return "1d"
    return min(tfs, key=lambda tf: TF_SECONDS.get(tf, TF_SECONDS["1d"]))


def _minute_keys(hist, syms):
    """hist.minutes 에서 syms 심볼들의 분봉 키(UTC YYYYMMDDHHMM) 합집합, 오름차순.
    (타임라인 asof 는 '데이터가 실제로 있는' 분봉 시각으로만 깐다 — 없는 봉을 지어내지 않는다.)"""
    mins = getattr(hist, "minutes", {}) or {}
    keys = set()
    for s in syms:
        keys.update((mins.get(s) or {}).keys())
    return sorted(keys)


def _key_to_asof(key):
    """분봉 키(UTC YYYYMMDDHHMM) → asof(UTC datetime, tz-aware)."""
    return datetime.strptime(key, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)


def asof_timeline(tree, hist, limit=None):
    """트리의 가장 촘촘한 tf 봉 타임스탬프로 asof 타임라인(UTC datetime 오름차순)을 만든다.

    · finest=1d : 일봉 축 — 하루 한 점(그날 마지막 확정 일봉 마감 시각)이 기존 동작이다. 분봉 데이터가 없어도
      일봉 판정은 되므로, 일봉 트리는 '분봉 재생' 대상이 아니다 → 빈 타임라인(이 드라이버는 장중 재생 전용).
    · finest=5m/1m : 그 심볼들의 분봉 키(데이터 있는 범위)를 asof 로 깐다. 5m 는 1분봉을 5분 버킷으로 접은
      '각 5분 봉의 종료(=다음 버킷 직전 마지막 분봉)' 시각을, 1m 는 분봉 키 그대로를 asof 로 쓴다.
    limit 을 주면 뒤(가장 최근)에서 limit 개만 — 긴 분봉도 꼬리만 빠르게 재생."""
    tf = finest_tf(tree)
    if tf == "1d":
        return []                               # 일봉 전용 트리 — 장중 재생할 분봉 축이 없다(빈 타임라인)
    syms = cond.minute_symbols_of(tree)
    keys = _minute_keys(hist, syms)
    if not keys:
        return []                               # 분봉 데이터 없음 — 타임라인도 없음(가짜로 안 늘림)
    if tf == "5m":
        # 5분봉 축 — 1분봉을 5분 버킷으로 접은 뒤, 각 버킷 안의 '마지막 분봉' 시각을 asof 로. 그 asof 에서 minute_series
        # 가 그 버킷을 asof 이하 마지막 5분봉으로 집계한다(한 심볼 기준 버킷 — 심볼마다 분봉 범위가 조금 달라도
        # 합집합 키로 세션 경계 안에서 접으므로 각 asof 에서 심볼별로 자기 마지막 버킷을 본다).
        buckets = {}
        for k in keys:
            mm = int(k[10:12])
            bkey = k[:10] + "%02d" % (mm - mm % 5)
            if bkey not in buckets or k > buckets[bkey]:
                buckets[bkey] = k              # 그 5분 버킷의 마지막(가장 늦은) 분봉 키
        stamps = sorted(buckets.values())
    else:                                       # 1m — 분봉 키 그대로
        stamps = keys
    if limit is not None:
        stamps = stamps[-limit:]
    return [_key_to_asof(k) for k in stamps]


def replay(slug, hist=None, tree=None, limit=None, prod=None):
    """트리의 가장 촘촘한 tf 간격 asof 타임라인에서 판정을 재생해 장중 등급 시계열을 낸다.

    각 asof 에서 verdict_engine.product_verdict(tree, p, hist, {}, asof) 를 불러(라이브가 하는 그대로, 부작용 없는
    진입점) 그 시점 (key, grade, close) 를 모은다. 일봉 잎은 asof 이하 마지막 확정 일봉(어제값), 분봉 잎은 asof
    이하 마지막 분봉 — 둘 다 cond 가 asof 로 자른다.

    → {slug, title, finest_tf, prods, sessions, points, timeline:[UTC iso], series:{prod:[{asof, key, grade, close}]},
       limit:{reason, sessions, bars}}  (분봉 없으면 points=0, series 빈, 한계 표면화)."""
    tree = tree or tree_grade.load_tree(slug)
    if tree is None:
        raise SystemExit("books/%s/tree.json 없음 — 조건 트리가 있어야 재생한다" % slug)
    if hist is None:
        from datetime import timedelta
        start = (datetime.now() - timedelta(days=tree_grade.WARMUP_DAYS)).strftime("%Y%m%d")
        hist = tree_grade.history(tree, start)
    tf = finest_tf(tree)
    timeline = asof_timeline(tree, hist, limit=limit)
    prods = [prod] if prod else list(tree["products"].keys())
    series = {p: [] for p in prods}
    for asof in timeline:
        for p in prods:
            v, _pe = verdict_engine.product_verdict(tree, p, hist, {}, asof=asof)
            series[p].append({"asof": asof.isoformat(), "key": v["key"],
                              "grade": v["grade"], "close": v.get("close")})
    sessions = sorted({a.strftime("%Y%m%d") for a in timeline})
    limit_note = _limit_note(tree, hist, tf, timeline, sessions)
    return {"slug": slug, "title": (tree.get("source") or {}).get("book", slug),
            "finest_tf": tf, "prods": prods, "sessions": sessions, "points": len(timeline),
            "timeline": [a.isoformat() for a in timeline], "series": series, "limit": limit_note}


def _limit_note(tree, hist, tf, timeline, sessions):
    """정직한 한계 표면화 — 분봉 범위(세션·봉 수)와 '왜 이만큼뿐인지'."""
    if tf == "1d":
        return {"reason": "일봉 전용 트리 — 장중(분봉) 재생 대상 아님(하루 한 점은 일봉 판정과 같다). "
                          "tf:5m/1m 조건이 있어야 장중 타임라인이 깔린다.",
                "sessions": 0, "bars": 0}
    if not timeline:
        syms = sorted(cond.minute_symbols_of(tree))
        return {"reason": "분봉 데이터 없음 — jhts 분봉(md_feed.minutes)에서 %s 분봉이 비어 있다"
                          "(미설치·네트워크·그 심볼 분봉 미보관). 없는 봉을 지어내 타임라인을 늘리지 않는다." % (", ".join(syms) or "대상 심볼"),
                "sessions": 0, "bars": 0}
    return {"reason": "분봉은 jhts 분봉(지수·선물은 최근 ~7거래일 한계)만큼만 온다 — 장중 타임라인도 데이터 있는 %d세션·%d봉(tf=%s)만 "
                      "재생된다. 그 밖 기간은 분봉이 없어 재생할 수 없다(정직한 한계)." % (len(sessions), len(timeline), tf),
            "sessions": len(sessions), "bars": len(timeline)}


# ------------------------------------------------------------------ 출력
def build_text(res):
    L = ["🕒 장중 재생 — %s  (가장 촘촘한 tf = %s)" % (res["title"], res["finest_tf"])]
    L.append("상품 %s · 재생 점 %d개 · 세션 %s" % (" · ".join(res["prods"]), res["points"],
                                             " ".join(res["sessions"]) or "-"))
    L.append("※ 한계: " + res["limit"]["reason"])
    for p in res["prods"]:
        rows = res["series"].get(p) or []
        if not rows:
            continue
        L.append("")
        L.append("■ %s  (%d점)" % (p, len(rows)))
        # 등급이 바뀌는 지점만 압축해서 보여준다(같은 등급 연속은 첫 점만) — 장중 시계열이 길어도 읽히게.
        prev = None
        for r in rows:
            if r["key"] != prev:
                L.append("   %s  %s  (close=%s)" % (r["asof"], r["grade"],
                                                    ("%.2f" % r["close"]) if r["close"] is not None else "-"))
                prev = r["key"]
    return "\n".join(L)


def _cli():
    argv = sys.argv[1:]
    slug = next((a for a in argv if not a.startswith("-")), None)
    if not slug:
        print("사용법: python -m operations.replay <slug> [--prod SPY] [--limit 20]", file=sys.stderr)
        sys.exit(2)
    prod = argv[argv.index("--prod") + 1] if "--prod" in argv else None
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    res = replay(slug, limit=limit, prod=prod)
    if "--json" in argv:
        import json
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print(build_text(res))


if __name__ == "__main__":
    _cli()
