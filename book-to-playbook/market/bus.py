#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""in-process pub-sub 버스(관찰자) — 구독자 레지스트리 + fan-out. 브로커 아님(로컬 단일 프로세스).

버스 하나 = 한 종류의 이벤트. publish(event) 하면 subscribe 한 콜백들이 한꺼번에 깨어난다. 한 소비자가
터져도 나머지는 받는다(격리). 틱을 '언제' 올리는지(트리거)는 Poller 가, '무엇을 계산할지'는 구독자(순수
함수)가 정한다 — 버스는 '누구에게 보내나'만 안다.

조립은 entry/live.py(bus 는 어느 책도 모르는 순수 부품이다):
  · Poller          타이머 — 틱 {"ts","n"} 마다 라이브 허브가 시세 저장소를 갱신하고 바뀐 상품만 다시 판정한다
  · verdict_bus     책마다 하나 — 허브가 그 책 판정을 틱당 한 번 올린다 → 화면(SSE)이 구독

  · Bus     subscribe/publish — 구독자 레지스트리 + fan-out(관찰자 격리)
  · Poller  interval 초마다 Bus 에 틱을 올리는 드라이버(sleep 주입 가능 — 테스트는 가짜 시계로)
"""
import threading
import time as _time


class Bus:
    """구독자 레지스트리 + fan-out. subscribe(cb) 로 콜백을 등록하고 publish(event) 가 그들을 깨운다."""

    def __init__(self):
        self._subs = []
        self._lock = threading.Lock()

    def subscribe(self, cb):
        """cb(event) 를 등록한다. 반환값(함수)을 부르면 구독 해지."""
        with self._lock:
            self._subs.append(cb)

        def _unsub():
            with self._lock:
                if cb in self._subs:
                    self._subs.remove(cb)
        return _unsub

    def publish(self, event):
        """등록된 모든 구독자에게 event 를 fan-out. 한 구독자가 터져도 나머지는 받는다(관찰자 격리)."""
        with self._lock:
            subs = list(self._subs)
        for cb in subs:
            try:
                cb(event)
            except Exception:  # noqa: BLE001 — 한 소비자의 실패가 다른 소비자를 막지 않는다
                pass


class Poller:
    """interval 초마다 bus 에 틱 {"ts","n"} 을 올리는 드라이버(틱 → sleep → 틱 …). now() = 틱 시각(ts) 함수.
    cycles=None 이면 무한, K 면 K 틱. sleep(sec) 은 주입 가능(테스트는 가짜 시계로 실제 대기 없이 돌린다)."""

    def __init__(self, bus, now=_time.time, sleep=None):
        self.bus = bus
        self.now = now
        self._sleep = sleep or _time.sleep

    def run(self, interval, cycles=None):
        n = 0
        while cycles is None or n < cycles:
            n += 1
            self.bus.publish({"ts": self.now(), "n": n})
            if cycles is not None and n >= cycles:
                break
            self._sleep(interval)
