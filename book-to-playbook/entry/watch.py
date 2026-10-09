#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""장중 주기 재판정(구간③) — asof=지금 기준으로 N분마다 판정을 다시 낸다(백테스트 제외).

한 회차가 무엇을 하는지는 호출자가 cycle 로 준다(entry.run watch → 러너의 verdict 모드: 판정·알림·검사).
이 파일은 '언제 다시 판정하나'(간격·횟수)만 가진다 — 그 트리거는 Feed(feed/__init__.py) 하나로, serve 의 SSE 루프와
같은 관찰자 코어를 쓴다. watch 는 그 Feed 에 '한 회차 실행'을 구독해 돌릴 뿐이다(소비자는 구독만).
"""
from datetime import datetime

from feed import Feed


def watch(argv, cycle):
    """asof=지금 기준으로 주기적으로 재판정한다. 장중(tf="1m") 조건은 asof(관측 시점) 이하 마지막 분봉을 본다 —
    분봉이 연결되면 그대로 자동으로 살아나고, 그 전엔 None→manual(🟡)로 떨어진다.

    --every N 으로 간격(분, 기본 5)을, --cycles K 로 횟수(기본 무한)를 준다. cycle(rest) = 한 회차 실행(종료코드 반환).
    트리거는 Feed.run(간격·횟수) — 매 틱마다 구독한 on_tick(= cycle)을 깨운다(serve SSE 와 같은 Feed 코어)."""
    rest = [a for a in argv if a != "watch" and a not in ("--every", "--cycles")]
    every = int(argv[argv.index("--every") + 1]) if "--every" in argv else 5
    cycles = int(argv[argv.index("--cycles") + 1]) if "--cycles" in argv else None
    state = {"code": 0}
    feed = Feed()

    def on_tick(ev):
        print("watch: asof=지금 %d회차 판정 — %s" % (ev["n"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        state["code"] = cycle(rest) or state["code"]

    feed.subscribe(on_tick)
    feed.run(interval=max(1, every) * 60, now=lambda: datetime.now().isoformat(), cycles=cycles)
    return state["code"]
