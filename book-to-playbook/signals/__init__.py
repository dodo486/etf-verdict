# -*- coding: utf-8 -*-
"""signal 층 — tree+시세 → 판정 데이터. 돈·체결은 consumers, 화면 모양은 consumers/display 가 빚는다.

  · judge.py       판단자 — Judge(책 하나: 트리·시세 원본의 유일한 사용자 · 라이브 판정·백테스트 신호·소절 반영·검사기 질문)
                   · ProductJudge(상품 하나: 등급·그날 판정·설명·보유 상태·체결용 조건 값·가격) · Holding · Decision 그릇
  · explain.py     판단 근거 설명(조건별 그날 값·측정 증거) — judge 만 부른다

경계: signal 은 shared · market · dsl 만 import 한다(트리의 뜻은 dsl 공개 모듈로). 소비층·화면층은 모른다.
경계는 verify/verify_code.py 가 강제한다.
"""
