# -*- coding: utf-8 -*-
"""market 층 — 시세 창구와 틱 배달. 파이프라인의 유일한 시세 입구(jhts 는 여기서만 import 한다).

  · md_feed.py     jhts 시세수집팀 창구 — 파이프라인의 유일한 시세 입구
  · _dev_cache.py  개발용 시세 캐시(ETF_DEV_CACHE 일 때만)
  · store.py       시세 칸 저장소(Store) — (심볼, 봉) 버퍼·확정 표시(confirmed)·구독용 refresh(바뀐 심볼만 알림) · 일봉 확정 경계(session_closes)
  · bus.py         틱 배달 — Bus(구독/발행)·Poller(틱 구동). 어느 책도 시세도 모르는 순수 부품(조립은 entry/live)

경계: market 은 shared 만 import 한다. 어느 상위 층도 market 을 거쳐 시세를 받는다(자가수집 금지).
경계는 entry/verify_rules.py 가 강제한다.
"""
