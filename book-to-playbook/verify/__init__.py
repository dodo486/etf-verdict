# -*- coding: utf-8 -*-
"""verify 층 — 코드·책 산출물·화면을 기계로 검사만 하는 최상위 층. 아래 전 층을 가로질러 본다.

  · verify_code.py             코드 규칙 — 폴더 경계(층=조직도) + 주인 표(결정 하나 = 주인 하나)
  · verify_tree.py             트리 검사 — 이중 추출 비교·원문 사례·발화 통계·비중 합 · 심판 비교 도구(--dump) · 책 계약(--contract)
  · verify_primitives.py       원시 연산·등급 계산을 기준값·손계산과 대조
  · verify_trading.py          거래 시뮬레이터·실전 경로 불변식 · --parity 신호 패리티(백테스트 == 실시간)
  · verify_view.py             화면 설명 구조 · 책 페이지 구획·UI 사본(--pages)
  · verify_source_integrity.py 플레이북 본문(#src) 불변 검사

경계: verify 는 모든 층을 import 해도 된다(검사 대상이므로). 아래 층은 verify 를 모른다.
"""
