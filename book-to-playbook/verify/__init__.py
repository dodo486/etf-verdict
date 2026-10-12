# -*- coding: utf-8 -*-
"""verify 층 — 코드 검사만. 엔진·화면 코드가 바뀌면 다시 돈다(가짜 트리·가짜 시세, 책 무관 · 크기 고정).

  · rules.py       코드 규칙 — 폴더 경계(층=조직도) + 주인 표(결정 하나 = 주인 하나)
  · primitives.py  원시 연산·등급 계산·트리 출입구 계약을 기준값·손계산과 대조
  · trading.py     거래 시뮬레이터·실전 경로 불변식 · --parity 신호 패리티(백테스트 == 실시간, 실제 책)
  · view.py        화면 설명 구조

책 데이터 검사는 그것을 만드는 곳에 산다(만드는 곳 = 검증하는 곳):
  원문 본문 해시 → authoring/playbook/source_integrity · 트리 채점·트리 계약 → authoring/checklist/score
  · 책 페이지 구획·UI 사본 → consumers/display/book_page
경계: verify 는 모든 층을 import 해도 된다(검사 대상이므로). 아래 층은 verify 를 모른다.
"""
