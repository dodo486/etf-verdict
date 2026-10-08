#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""라이브 틱 피더(구간③) — in-process pub-sub(관찰자). 일정 간격마다 '틱'을 올리면, 구독한 소비자들
(화면 push·알림·주문·pricing)이 깨어나 각자 일한다.

왜 있나
  serve 의 SSE 루프와 watch 의 루프가 '일정 간격마다 다시 판정'을 각자 구현하고 있었다. 트리거(언제 다시
  판정하나)를 한 곳(Feed)에 모으고 — 소비자는 '구독'만 한다. 소비자를 더해도 트리거·다른 소비자를 안
  건드린다(관찰자 패턴). 책 N개면 신호층도 N개 — 피더 하나가 틱을 올리면 각 신호층·그 소비자가 깨어난다.

  시세가 지금은 pull(md_feed→jhts)이라 '피더'는 타이머로 틱을 올린다. 진짜 스트리밍이 생기면 그 이벤트가
  그대로 틱 소스가 된다(소비자 코드는 그대로 — publish 만 그쪽에서 부르면 된다).

브로커 아님 — 로컬 단일 프로세스의 가벼운 관찰자(구독 등록 + fan-out)다. 틱마다 '무엇을 계산할지'(판정·
pricing)는 구독자(순수 함수)가 정한다 — Feed 는 '언제'(트리거)만 안다. 그래서 백테스트(과거 배치)는 Feed 를
안 거치고 같은 신호층 코드를 직접 돌린다(구독 밖).
"""
import threading
import time as _time


class Feed:
    """틱 publisher + 구독자 레지스트리. subscribe(cb) 로 콜백을 등록하고 publish/run 이 그들을 깨운다."""

    def __init__(self):
        self._subs = []
        self._lock = threading.Lock()

    def subscribe(self, cb):
        """cb(event) 를 등록한다 — event = {"ts": ..., "n": ...}. 반환값(함수)을 부르면 구독 해지."""
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

    def run(self, interval, now, cycles=None, sleep=None):
        """interval 초마다 틱을 publish(틱 → sleep → 틱 …). now() = 틱 시각(ts) 함수. cycles=None 이면 무한,
        K 면 K 틱. sleep(sec) 은 주입 가능(테스트는 가짜 시계로). 실제 루프는 serve·watch 가 이걸로 돈다."""
        slp = sleep or _time.sleep
        n = 0
        while cycles is None or n < cycles:
            n += 1
            self.publish({"ts": now(), "n": n})
            if cycles is not None and n >= cycles:
                break
            slp(interval)
