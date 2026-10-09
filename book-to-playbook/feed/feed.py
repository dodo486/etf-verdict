#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""라이브 틱 피더 — in-process pub-sub(관찰자). 일정 간격마다 '틱'을 올리면, 구독한 소비자들
(화면 push·알림·주문·pricing)이 깨어나 각자 일한다. serve 의 SSE 루프와 watch 의 장중 재판정 루프를
여기 하나로 흡수했다 — 트리거(언제 다시 판정하나)는 버스 한 곳, 소비자는 '구독'만 한다.

소비자를 더해도 트리거·다른 소비자를 안 건드린다(관찰자 패턴). 책 N개면 신호층도 N개 — 피더 하나가 틱을
올리면 각 신호층·그 소비자가 깨어난다. 시세가 지금은 pull(md_feed→jhts)이라 '피더'는 타이머로 틱을 올린다.
진짜 스트리밍이 생기면 그 이벤트가 그대로 틱 소스가 된다(소비자 코드는 그대로 — publish 만 그쪽에서 부른다).

브로커 아님 — 로컬 단일 프로세스의 가벼운 관찰자(구독 등록 + fan-out)다. 틱마다 '무엇을 계산할지'(판정·
pricing)는 구독자(순수 함수)가 정한다 — 버스는 '언제'(트리거)만 안다. 그래서 백테스트(과거 배치)는 버스를
안 거치고 같은 신호층 코드를 직접 돌린다(구독 밖).

  · Bus/Poller  2단 pub-sub 코어(feed/bus.py) — price_bus·verdict_bus 조립은 entry/live.py
  · Feed   Bus + run(interval,now,…) — 틱 publisher+레지스트리를 한 묶음으로(watch 가 쓰는 옛 모양)
  · watch  장중 주기 재판정 루프 — Feed 에 '한 회차 실행'을 구독해 돌린다(entry.run watch 가 부른다)
"""
from datetime import datetime

from feed.bus import Bus, Poller  # noqa: F401  (2단 pub-sub 코어 — entry/live 가 조립)


class Feed(Bus):
    """Bus + run(interval, now) — 틱 publisher 와 구독자 레지스트리를 한 묶음으로. watch 가 쓰는 옛 모양.
    (새 조립은 Bus + Poller 를 따로 쓴다 — entry/live.py.)"""

    def run(self, interval, now, cycles=None, sleep=None):
        """interval 초마다 틱을 publish(틱 → sleep → 틱 …). now() = 틱 시각(ts) 함수. cycles=None 이면 무한,
        K 면 K 틱. sleep(sec) 은 주입 가능(테스트는 가짜 시계로). 실제 루프는 watch 가 이걸로 돈다."""
        Poller(self, now=now, sleep=sleep).run(interval, cycles=cycles)


def watch(argv, cycle):
    """장중 주기 재판정(백테스트 제외) — asof=지금 기준으로 N분마다 cycle(한 회차)을 다시 돌린다.
    장중(tf="1m") 조건은 asof(관측 시점) 이하 마지막 분봉을 본다 — 분봉이 연결되면 살아나고, 그 전엔 None→🟡.

    --every N 간격(분, 기본 5) · --cycles K 횟수(기본 무한). cycle(rest) = 한 회차 실행(종료코드 반환).
    한 회차가 무엇을 하는지는 호출자(entry.run watch → verdict 모드: 판정·알림·검사)가 준다. 트리거는 Feed.run —
    매 틱마다 구독한 on_tick(=cycle)을 깨운다(serve SSE 와 같은 Feed 코어)."""
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
