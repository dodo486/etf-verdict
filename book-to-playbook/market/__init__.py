# -*- coding: utf-8 -*-
"""market 층 — 시세 창구와 틱 배달. 파이프라인의 유일한 시세 입구(jhts 는 여기서만 import 한다).

  · md_feed.py     jhts 시세수집팀 창구 — 파이프라인의 유일한 시세 입구
  · _dev_cache.py  개발용 시세 캐시(ETF_DEV_CACHE 일 때만)
  · bus.py         틱 배달 — Bus(구독/발행)·Poller(틱 구동). 어느 책도 시세도 모르는 순수 부품(조립은 entry/live)
  · feed.py        옛 장중 루프(Feed·watch — run watch 가 씀)

경계: market 은 shared 만 import 한다. 어느 상위 층도 market 을 거쳐 시세를 받는다(자가수집 금지).
경계는 entry/verify_rules.py 가 강제한다.
"""
