# -*- coding: utf-8 -*-
"""signal 층 — tree+시세 → 판정 데이터. 돈·체결은 consumers, 화면 모양은 consumers/display 가 빚는다.

  · judge.py       Judge(한 상품·한 시점 판정) · Decision · Holding(pos 주입 한 곳) · signal_series(전 점 신호 — 백테스트용) · truncate(과거 세션 재현 — 파리티용)
  · engine.py      라이브 판정 엔진 — slug·asof → 시세 조달 + 전 상품 Judge → Decision · open_history(책 열기, runner·탭·검사 공유)

경계: signal 은 shared · market · dsl 만 import 한다(트리의 뜻은 dsl 공개 모듈로). 소비층·화면층은 모른다.
경계는 verify/verify_code.py 가 강제한다.
"""
