# -*- coding: utf-8 -*-
"""웹 화면층(web) — 판정·백테스트 결과를 사람이 읽는 모양으로 빚고 서빙한다(판정을 다시 내지 않는다).

  · verdict_view.py     판정 JSON(#verdict-data·/api/verdict)·알림 문장 — books.json engine.daily
  · condition_view.py   조건 → 화면 항목(view·측정 증거·사유 문장)
  · backtest_page.py    책 페이지 '백테스트' 탭 데이터(1년·3년)
  · book_page.py        책 페이지 조립(판정·UI·레일·원문·백테스트) · build_home.py 책 선택 셸 · inject_nav.py 책 레일
  · inject_ui.py        ui/<name>.js(화면 JS, 단일 진실) → 책 HTML 주입 · ui/ 화면 JS
  · serve.py            로컬 실시간 서버(매 요청 엔진을 새로 돌려 그린다)
  · verify_view.py      검사기 — 화면 설명 구조 · 책 페이지 구획·UI 사본(--pages)

구간③(trading)과 구간② 공개 DSL 을 import 한다. 시세 수집은 하지 않는다(네트워크 예외는 serve.py 의 http.server 하나).
"""
