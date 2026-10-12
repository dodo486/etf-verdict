# -*- coding: utf-8 -*-
"""web 층 — 엔진이 낸 판정 데이터를 화면 모양으로 빚는다(판정 안 함).

  · verdict_view·book_page·backtest_page·build_home·inject_*·raw_tree · ui/ 화면 JS(SSOT)
  · explain   조건 설명(그날 값·측정 증거가 달린 중첩 항목) — 계산하지 않는다, 값은 판단자의 값 함수(ProductJudge.value)로
  · text      식 → 글 낱말(시세 필드·포지션 값·창·비교 기호·단위·"?") — explain·raw_tree 가 같이 쓰는 한 곳
  · verify_page(검사 — 책 페이지 구획·UI 사본) · verify_view(검사 — 조건 설명 구조)

경계: web 은 shared · market · tree · judge · backtest 만 import 한다. 서버(entry/serve)·알림(entry/notify)이 web 을 부른다.
"""
