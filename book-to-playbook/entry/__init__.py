# -*- coding: utf-8 -*-
"""entry 층 — 사람·스케줄러가 부르는 진입점. 아래 전 층을 가로질러 실행한다.

  · run.py     스케줄 러너 — 판정·백테스트 탭 데이터(daily/verdict) · 장중 재판정(watch — 루프는 market/feed.watch)
               + 검사 목록 CHECKS 한 곳(check — 바꿨을 때)
  · serve.py   로컬 실시간 서버(라이브 허브의 판정을 그린다 · SSE 는 판정 버스 구독)
  · live.py    라이브 조립 뿌리(LiveHub) — 시세(price_bus)→판정→화면·알림(verdict_bus) 두 단 버스를 만들고 엮는다(serve 가 씀)
  · notify.py  알림 — 오늘 판정을 문장으로 만들어 텔레그램·데스크톱으로 보낸다(books.json engine.daily)
  · verify_rules.py  검사 — 코드 규칙(폴더 경계 + 주인 표). 전 층을 보므로 entry 에

진입: `python -m entry.run <daily|verdict|watch|check>` · `python -m entry.serve` · `python -m entry.notify <slug>`
경계: entry 는 모든 층을 import 해도 된다 — 여기가 맨 위에서 아래를 실행만 한다. 아래 층은 entry 를 모른다.
경계는 entry/verify_rules.py 가 강제한다.
"""
