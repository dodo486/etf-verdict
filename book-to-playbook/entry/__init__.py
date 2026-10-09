# -*- coding: utf-8 -*-
"""entry 층 — 사람·스케줄러가 부르는 진입점. 아래 전 층을 가로질러 실행한다.

  · run.py     스케줄 러너 — 판정·백테스트 탭 데이터·검사를 순서대로(daily/verdict/watch) + 검사 목록 CHECKS 한 곳(check)
  · serve.py   로컬 실시간 서버(매 요청 엔진을 새로 돌려 그린다 · SSE 는 feed 구독)
  · watch.py   장중 주기 재판정 루프(feed 구독 — python -m entry.run watch)

진입: `python -m entry.run <daily|verdict|watch|check>` · `python -m entry.serve`
경계: entry 는 모든 층을 import 해도 된다 — 여기가 맨 위에서 아래를 실행만 한다. 아래 층은 entry 를 모른다.
경계는 verify/verify_code.py 가 강제한다.
"""
