#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""장중 재생 드라이버 (책 무관) — 구간④. **통합 스테핑 코어(operations.driver)의 '신호만' 얇은 래퍼.**

## 왜 있나

일봉만 쓰는 트리는 하루 한 점(그날 마감)에서 판정하면 끝이다 — operations.verify_signal_parity 가 하는
그대로다. 하지만 트리가 5분봉·1분봉(tf="5m"/"1m") 조건을 섞으면, '일봉 regime(어제 확정) AND 분봉
trigger(장중)'를 그 분봉 간격으로 재생해 봐야 장중 신호가 보인다.

예전엔 이 재생이 자기만의 스테핑 루프를 들고 있었고, backtest.run(일봉 하루씩)이 또 하나를 들고 있었다.
지금은 **스테핑(시간을 밟으며 매 asof 판정)을 operations.driver 한 곳으로 합쳤다**. 이 파일은 그 코어의
신호 시계열을 그대로 출력하는 '신호만' 용도 래퍼다(백테스트는 같은 코어 뒤에 계산기를 붙인다).

## 단방향(폭포수)

operations/(구간④)에 있고 driver(동일 구간)만 통해 verdict·shared 를 쓴다(downward). 상류는 이 파일을
import 하지 않는다 — verify_teams 가 강제.

## 사용

    python -m operations.replay <slug> [--prod SPY] [--limit 20]
    → 장중 등급 시계열(asof · 상품 · 등급) + 데이터 범위(세션·봉 수) 요약. 분봉 없으면 "데이터 없음" 표면화.
"""
import sys

from shared import tree_grade
from operations import driver

# 하위호환 재노출(기존 호출부·테스트가 operations.replay.finest_tf 등을 쓸 수 있게) — 정본은 driver.
finest_tf = driver.finest_tf
tree_tfs = driver.tree_tfs
asof_timeline = driver.asof_timeline


def replay(slug, hist=None, tree=None, limit=None, prod=None):
    """트리의 가장 촘촘한 tf 간격 asof 타임라인에서 판정을 재생해 장중 등급 시계열을 낸다.

    스테핑·판정은 전부 operations.driver(공통 코어)가 한다 — 이 함수는 그 신호 시계열을 재생 출력
    계약으로 묶기만 한다(백테스트는 같은 코어 뒤에 vectorbt 계산기를 붙인다 — 뒤만 다르다).

    → {slug, title, finest_tf, prods, sessions, points, timeline:[UTC iso], series:{prod:[{asof, key, grade, close}]},
       limit:{reason, sessions, bars}}  (분봉 없으면 points=0, series 빈, 한계 표면화)."""
    tree = tree or tree_grade.load_tree(slug)
    if tree is None:
        raise SystemExit("books/%s/tree.json 없음 — 조건 트리가 있어야 재생한다" % slug)
    if hist is None:
        hist = driver.load_hist(tree)
    tf = driver.finest_tf(tree)
    timeline = driver.asof_timeline(tree, hist, limit=limit)
    prods = [prod] if prod else list(tree["products"].keys())
    series = driver.step(tree, hist, timeline, prods)
    sessions = sorted({a.strftime("%Y%m%d") for a in timeline})
    return {"slug": slug, "title": (tree.get("source") or {}).get("book", slug),
            "finest_tf": tf, "prods": prods, "sessions": sessions, "points": len(timeline),
            "timeline": [a.isoformat() for a in timeline], "series": series,
            "limit": driver.limit_note(tree, hist, tf, timeline, sessions)}


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
