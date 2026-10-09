#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""라이브 2단 pub-sub 조립(진입층) — 시세→신호→소비자를 버스 두 단으로 잇는다. '책 등록 = 구독'.

feed/ 는 어느 책도 모르는 순수 부품(Bus·Poller)이고, signals/·consumers/ 는 feed 를 모른다(의존성 주입 —
평범한 함수만 내놓는다). 그 둘을 아는 유일한 자리가 여기(entry 는 전 층 import 허용) — 버스를 만들고 핸들러를
엮는 조립 뿌리다.

  시세(price_bus, 하나) ── Poller 가 interval 초마다 틱 {"ts","n"} ──▶ 책마다 신호 핸들러(구독)
     신호 핸들러: engine.live_decisions(slug) 로 판정 사실을 내 → {"slug","tree","hist","positions","decisions"}
                 를 그 책 verdict_bus(책마다 하나)에 publish
  판정(verdict_bus, 책마다) ──▶ 화면 소비자(구독): verdict_view._format(...) 으로 top 을 빚어 캐시에 저장

책을 books.json 에 추가하면(live:true) 다음 조립(start/_sync)에서 price_bus 구독자로 등록된다 — "책 등록 =
구독". 한 번 계산(신호), 두 소비자(화면·알림)가 나눠 쓴다(이중 계산 없음)."""
import threading

from shared.paths import live_slugs
from signals import engine
from consumers.display.verdict_view import _format
from feed.bus import Bus, Poller


class LiveHub:
    """price_bus 하나 + 책마다 verdict_bus. 책마다 신호 핸들러를 price_bus 에 구독하고, 화면 소비자를 그 책의
    verdict_bus 에 구독해 최신 top 을 캐시에 둔다. serve 가 latest(slug) 로 읽고, SSE 는 verdict_bus 를 구독한다."""

    def __init__(self, slugs=None):
        self.price_bus = Bus()
        self.verdict_bus = {}        # slug -> Bus(판정 이벤트)
        self._latest = {}            # slug -> top(최신 판정 JSON)
        self._unsub = {}             # slug -> price_bus 구독 해지 함수(핸들러)
        self._lock = threading.Lock()
        self._slugs_fn = (lambda: list(slugs)) if slugs is not None else (lambda: live_slugs())
        self._sync()

    def _sync(self):
        """books.json 의 라이브 책과 구독자를 맞춘다 — 새 책은 price_bus 구독자로 등록(책 등록 = 구독),
        빠진 책은 구독 해지. 멱등(여러 번 불러도 안전) — serve 재시작 없이 책 추가를 잡으려고 start 와 틱이 부른다."""
        want = set(self._slugs_fn())
        with self._lock:
            have = set(self._unsub)
            for slug in want - have:
                self.verdict_bus.setdefault(slug, Bus())
                self._unsub[slug] = self.price_bus.subscribe(self._signal_handler(slug))
                self.verdict_bus[slug].subscribe(self._display_consumer(slug))
            for slug in have - want:
                self._unsub.pop(slug)()
                self.verdict_bus.pop(slug, None)
                self._latest.pop(slug, None)

    def _signal_handler(self, slug):
        """1단 → 2단: price_bus 틱을 받아 그 책 판정을 계산해 verdict_bus 에 올린다(신호층 호출만 — feed 를 모른다)."""
        bus = self.verdict_bus[slug]

        def on_tick(_ev):
            tree, hist, positions, decisions = engine.live_decisions(slug)
            bus.publish({"slug": slug, "tree": tree, "hist": hist,
                         "positions": positions, "decisions": decisions})
        return on_tick

    def _display_consumer(self, slug):
        """2단 소비자(화면): verdict_bus 사실로 _format 해 top 을 캐시에 둔다 — serve.latest 가 읽는다."""
        def on_verdict(ev):
            top = _format(ev["slug"], ev["tree"], ev["hist"], ev["positions"], ev["decisions"])
            with self._lock:
                self._latest[ev["slug"]] = top
        return on_verdict

    def tick_once(self):
        """price_bus 에 틱 한 번 — 책 구독자를 다시 맞춘 뒤 모든 책을 한 회차 재판정(테스트·수동 트리거용)."""
        self._sync()
        Poller(self.price_bus).run(0, cycles=1)

    def start(self, interval, now=None, sleep=None):
        """price_bus 를 interval 초마다 모는 Poller 를 스레드로 띄운다(데몬). 틱마다 _sync 로 책 추가를 잡는다."""
        self._sync()
        bus = self.price_bus

        class _SyncingBus:                  # 틱 직전 _sync 를 끼운다 — 책 추가를 재시작 없이 잡게
            def publish(_s, ev):
                self._sync()
                bus.publish(ev)
        p = Poller(_SyncingBus(), now=now, sleep=sleep) if now or sleep else Poller(_SyncingBus())
        t = threading.Thread(target=lambda: p.run(interval), daemon=True)
        t.start()
        return t

    def latest(self, slug):
        """그 책의 최신 top(화면이 읽음). 아직 틱이 안 왔으면 None."""
        with self._lock:
            return self._latest.get(slug)
