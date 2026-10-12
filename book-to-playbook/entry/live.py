#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""라이브 조립(진입층) — 시세 저장소 → 구독표 → 바뀐 상품만 판정 → 책마다 verdict_bus. '책 등록 = 구독'.

market(store·bus)은 어느 책도 모르는 부품이고, judge/·web/ 은 버스를 모른다(의존성 주입 — 평범한 함수만 내놓는다).
그 둘을 아는 유일한 자리가 여기(entry 는 전 층 import 허용) — 판단자·저장소·버스를 엮는 조립 뿌리다.

  [시작 · 책/트리가 바뀔 때(_sync)]  live 책마다 판단자 Judge.open(slug) — 판때기는 트리 파일이 그대로면 다시 안 만든다.
     구독표 = 심볼 → {(책, 상품)} (Judge.subscriptions — 판때기 필요 심볼 + 상품 자신). 저장소에 그 심볼들을
     워밍업 기간부터 등록(store.need)하고 한 번 적재(store.load).
  [틱]  changed = store.refresh() — 이번 틱에 봉이 바뀐 심볼 → 구독표로 깨울 상품을 모은다(책마다 상품당 한 번 —
     심볼 여럿이 같이 바뀌어도 한 번) → 책마다 깨운 상품만 Judge.decisions(prices, products=…) 로 다시 판정해
     나머지 상품의 지난 판정과 합친다 → 그 책 verdict_bus 에 이벤트 하나 {"slug","book","prices","decisions"}.
     바뀐 것이 없으면 아무것도 계산·발행하지 않는다. 새로 연 책(첫 틱·트리 변경)·내 포지션 파일이 바뀐 책은 전 상품.
  [소비자]  화면: verdict_bus → verdict_view._format → latest(slug) 캐시(serve 가 읽고, SSE 는 verdict_bus 를 구독).
  [아래에서 들어오는 입력]  사람이 답한 수동 조건 = judge_with(slug, answers) — 같은 판단자·같은 저장소 시세로 계산
     (재조회·별도 프로세스 없음). 내 포지션 = Judge.positions(decisions 안에서 읽는다 — 파일이 바뀌면 그 책을 깨운다).

백테스트(과거 배치)는 버스를 안 거치고 같은 판단자를 직접 돌린다(Judge.signals — 구독 밖)."""
import os
import threading

from shared.paths import live_slugs, positions_json
from judge.judge import Judge, since
from web.verdict_view import _format
from market.bus import Bus, Poller
from market.store import Store


class LiveHub:
    """판단자(책마다) + 시세 저장소(하나) + 구독표 + 책마다 verdict_bus. 화면 소비자는 최신 top 을 캐시에 둔다.
    slugs·store·judges 는 주입 가능(검사 entry/verify_live 가 합성 책·가짜 시세로 돌린다) — judges = {slug: Judge}."""

    def __init__(self, slugs=None, store=None, judges=None):
        self.verdict_bus = {}        # slug -> Bus(판정 이벤트)
        self._latest = {}            # slug -> top(최신 판정 JSON)
        self._judges = {}            # slug -> Judge(또는 None — 트리 없음·못 엶)
        self._errors = {}            # slug -> 판단자를 못 연 이유(트리 형식 오류 등)
        self._decided = {}           # slug -> {상품: (상품, Decision, ProductJudge, [내 포지션])} — 지난 판정
        self._dirty = set()          # 다음 틱에 전 상품을 판정할 책(새로 열림·트리 바뀜)
        self._pos = {}               # slug -> 내 포지션 파일 표식(바뀌면 그 책을 깨운다)
        self._subs = {}              # 심볼 -> {(slug, 상품)} — 구독표
        self._store = store if store is not None else Store()
        self._judge_of = judges.get if judges is not None else (lambda s: Judge.open(s))
        self._slugs_fn = (lambda: list(slugs)) if slugs is not None else live_slugs
        self._lock = threading.Lock()       # _latest 보호(화면 소비자 ↔ serve)
        self._tick = threading.Lock()       # 판정 계산은 한 번에 하나(틱 · 수동 답)
        self.ticked = False                 # 한 번이라도 틱을 돌았나(serve 첫 요청 데우기)

    # ------------------------------------------------------------ 책 ↔ 판단자 · 구독표
    def _sync(self):
        """books.json 의 live 책과 판단자·구독표를 맞춘다(멱등 — 틱마다 부른다). 새 책·트리가 바뀐 책만 다시 열고
        (Judge.open 이 트리 파일 표식으로 캐시) 그 책을 dirty 로 둔다. 빠진 책은 버스·캐시·구독에서 지운다."""
        want = list(self._slugs_fn())
        changed = False
        for slug in want:
            if slug not in self.verdict_bus:
                self.verdict_bus[slug] = Bus()
                self.verdict_bus[slug].subscribe(self._display_consumer(slug))
            try:
                j, err = self._judge_of(slug), None
            except Exception as ex:  # noqa: BLE001 — 한 책의 트리 오류가 다른 책을 막지 않는다
                j, err = None, "판단자 열기 실패: %s" % ex
            if slug not in self._judges or j is not self._judges[slug] or err != self._errors.get(slug):
                self._judges[slug], self._errors[slug] = j, err
                self._decided[slug] = {}
                self._dirty.add(slug)
                changed = True
        for slug in set(self._judges) - set(want):
            for d in (self._judges, self._errors, self._decided, self._pos, self.verdict_bus):
                d.pop(slug, None)
            self._dirty.discard(slug)
            with self._lock:
                self._latest.pop(slug, None)
            changed = True
        if changed:
            self._resubscribe()

    def _resubscribe(self):
        """구독표를 다시 짓고 저장소에 필요 심볼을 등록·적재한다(등록은 넓히기만 — 멱등, 적재는 안 받은 심볼만)."""
        subs = {}
        for slug, j in self._judges.items():
            if j:
                for p, syms in j.subscriptions().items():
                    for s in syms:
                        subs.setdefault(s, set()).add((slug, p))
        self._subs = subs
        if subs:
            self._store.need(set(subs), since())
            self._store.load()

    def _positions_changed(self, slug):
        """내 포지션 파일(입력)이 바뀌었나 — 파일 표식(수정 시각·크기)만 본다(읽는 건 판단자)."""
        try:
            st = os.stat(positions_json(slug))
            stamp = (st.st_mtime_ns, st.st_size)
        except OSError:
            stamp = None
        old = self._pos.get(slug, stamp)
        self._pos[slug] = stamp
        return old != stamp

    # ------------------------------------------------------------ 틱
    def tick(self, ev=None):
        """한 틱 — 저장소 갱신 → 바뀐 심볼을 구독한 상품만 깨워 책마다 한 번 판정·발행. 발행한 책 slug 집합을 돌려준다."""
        with self._tick:
            self._sync()
            changed = self._store.refresh()
            prices = self._store.prices()
            woken = {}
            for sym in changed:
                for slug, p in self._subs.get(sym, ()):
                    woken.setdefault(slug, set()).add(p)
            for slug in list(self._judges):
                if self._positions_changed(slug) or slug in self._dirty:
                    woken[slug] = None                        # 전 상품
            published = {slug for slug, prods in woken.items() if self._publish(slug, prices, prods)}
            self._dirty -= set(woken)
            self.ticked = True
            return published

    def _publish(self, slug, prices, prods):
        """책 하나 — 깨운 상품(prods, None = 전부)만 판정해 지난 판정과 합치고 verdict_bus 에 이벤트 하나."""
        j, bus = self._judges.get(slug), self.verdict_bus.get(slug)
        if bus is None:
            return False
        if not j:
            bus.publish({"slug": slug, "book": None, "prices": {}, "decisions": [], "error": self._errors.get(slug)})
            return True
        try:
            fresh = j.decisions(prices, products=prods)
        except Exception as ex:  # noqa: BLE001 — 한 책의 계산 실패가 다른 책을 막지 않는다
            bus.publish({"slug": slug, "book": None, "prices": {}, "decisions": [], "error": "판정 실패: %s" % ex})
            return True
        kept = self._decided[slug]
        kept.update((d[0], d) for d in fresh)
        decisions = [kept[p] for p in j.products() if p in kept]
        bus.publish({"slug": slug, "book": j, "prices": prices, "decisions": decisions})
        return True

    def _display_consumer(self, slug):
        """2단 소비자(화면): verdict_bus 사실로 _format 해 top 을 캐시에 둔다 — serve 가 latest 로 읽는다."""
        def on_verdict(ev):
            top = _format(ev["slug"], ev["book"], ev["prices"], ev["decisions"])
            if ev.get("error"):
                top["error"] = ev["error"]
            with self._lock:
                self._latest[ev["slug"]] = top
        return on_verdict

    # ------------------------------------------------------------ 아래에서 들어오는 입력 · 읽기
    def judge_with(self, slug, answers):
        """사람이 답한 수동 조건까지 반영한 판정 top — 허브의 판단자 + 저장소의 지금 시세로(재조회·별도 프로세스 없음).
        답마다 결과가 달라 발행·캐시하지 않는다(답 없는 판정 latest 와 섞이지 않게)."""
        if not self.ticked:
            self.tick()
        with self._tick:
            j = self._judges.get(slug)
            if not j:
                top = _format(slug, None, {}, [], answers=answers)
                if self._errors.get(slug):
                    top["error"] = self._errors[slug]
                return top
            prices = self._store.prices()
            return _format(slug, j, prices, j.decisions(prices, answers=answers), answers=answers)

    def start(self, interval, now=None, sleep=None):
        """interval 초마다 tick 을 부르는 Poller 를 스레드로 띄운다(데몬). 첫 틱은 바로."""
        hub = self

        class _Drive:                       # Poller 가 미는 대상 — 틱 이벤트를 받아 hub.tick
            def publish(_s, ev):
                try:
                    hub.tick(ev)
                except Exception:  # noqa: BLE001 — 시세 창구 한 번 실패가 라이브 루프를 죽이지 않게(다음 틱에 다시)
                    pass
        kw = {k: v for k, v in (("now", now), ("sleep", sleep)) if v}
        t = threading.Thread(target=lambda: Poller(_Drive(), **kw).run(interval), daemon=True)
        t.start()
        return t

    def latest(self, slug):
        """그 책의 최신 top(화면이 읽음). 아직 틱이 안 왔으면 None."""
        with self._lock:
            return self._latest.get(slug)
