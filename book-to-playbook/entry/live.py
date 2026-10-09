#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""라이브 2단 pub-sub 조립(진입층) — 시세→신호→소비자를 버스 두 단으로 잇는다. '책 등록 = 구독'.

feed/ 는 어느 책도 모르는 순수 부품(Bus·Poller)이고, signals/·consumers/ 는 feed 를 모른다(의존성 주입 —
평범한 함수만 내놓는다). 그 둘을 아는 유일한 자리가 여기(entry 는 전 층 import 허용) — 버스를 만들고 핸들러를
엮는 조립 뿌리다.

  시세(price_bus, 하나) ── Poller 가 interval 초마다 틱 ──▶ 전 책 심볼 '한 번' 조회(합집합 hist) ──▶
     틱 {"ts","n","trees","hist"} 를 price_bus 에 fan-out ──▶ 책마다 신호 핸들러(구독)
     신호 핸들러: 틱에 실린 공유 시세로 engine.live_decisions(slug, tree=, hist=) → 판정 사실을
                 {"slug","tree","hist","positions","decisions"} 로 그 책 verdict_bus(책마다 하나)에 publish
  판정(verdict_bus, 책마다) ──▶ 화면 소비자(구독): verdict_view._format(...) 으로 top 을 빚어 캐시에 저장

공유 시세: 틱마다 **전 live 책 트리의 심볼 합집합**을 Grade.history_back([트리들]) 으로 한 번만 조회한다
(md_feed.histories 1회) — 책들이 QQQ 를 공유해도 조회는 한 번, 각 책은 자기 심볼만 읽는다(중복 조회 제거).

책을 books.json 에 추가하면(live:true) 다음 조립(start/_sync)에서 price_bus 구독자로 등록된다 — "책 등록 =
구독". 한 번 조회(시세)·한 번 계산(신호), 두 소비자(화면·알림)가 나눠 쓴다(이중 조회·이중 계산 없음)."""
import threading

from shared.paths import live_slugs
from dsl.tradeTool import Grade, History
from dsl.tree_gateway import TreeGateway
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
        """1단 → 2단: price_bus 틱(공유 시세 실림)을 받아 그 책 판정을 계산해 verdict_bus 에 올린다
        (신호층 호출만 — feed 를 모른다). 틱의 trees[slug]·hist 를 넣어 이 책이 시세를 다시 조회하지 않게 한다."""
        bus = self.verdict_bus[slug]

        def on_tick(ev):
            tree = (ev.get("trees") or {}).get(slug)
            tree, hist, positions, decisions = engine.live_decisions(
                slug, tree=tree, hist=ev.get("hist"))
            if tree is None:
                return
            bus.publish({"slug": slug, "tree": tree, "hist": hist,
                         "positions": positions, "decisions": decisions})
        return on_tick

    def _shared_tick(self, ev):
        """price_bus 로 내보낼 틱에 '공유 시세'를 싣는다 — 전 live 책 트리의 심볼 합집합을 한 번만 조회한다
        (md_feed.histories 1회). 책들이 심볼을 공유해도 조회는 한 번, fan-out 으로 나눠 쓴다(중복 조회 제거)."""
        trees = {s: TreeGateway.load(s) for s in self._slugs_fn()}
        trees = {s: t for s, t in trees.items() if t is not None}
        hist = Grade.history_back(list(trees.values())) if trees else History({})
        return {**ev, "trees": trees, "hist": hist}

    def _display_consumer(self, slug):
        """2단 소비자(화면): verdict_bus 사실로 _format 해 top 을 캐시에 둔다 — serve.latest 가 읽는다."""
        def on_verdict(ev):
            top = _format(ev["slug"], ev["tree"], ev["hist"], ev["positions"], ev["decisions"])
            with self._lock:
                self._latest[ev["slug"]] = top
        return on_verdict

    def tick_once(self):
        """price_bus 에 틱 한 번 — 책 구독자를 다시 맞추고 공유 시세를 실어 모든 책을 한 회차 재판정(테스트·수동 트리거용)."""
        self._sync()
        Poller(self._driving_bus()).run(0, cycles=1)

    def _driving_bus(self):
        """Poller 가 미는 대상 — 틱 직전 _sync(책 추가 잡기) + 공유 시세 적재(_shared_tick) 후 price_bus 로 fan-out."""
        hub, bus = self, self.price_bus

        class _DrivingBus:
            def publish(_s, ev):
                hub._sync()
                bus.publish(hub._shared_tick(ev))
        return _DrivingBus()

    def start(self, interval, now=None, sleep=None):
        """price_bus 를 interval 초마다 모는 Poller 를 스레드로 띄운다(데몬). 틱마다 _sync·공유 시세 조회 1회."""
        self._sync()
        drive = self._driving_bus()
        p = Poller(drive, now=now, sleep=sleep) if now or sleep else Poller(drive)
        t = threading.Thread(target=lambda: p.run(interval), daemon=True)
        t.start()
        return t

    def latest(self, slug):
        """그 책의 최신 top(화면이 읽음). 아직 틱이 안 왔으면 None."""
        with self._lock:
            return self._latest.get(slug)
