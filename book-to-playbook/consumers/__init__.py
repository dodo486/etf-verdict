# -*- coding: utf-8 -*-
"""consumers 층 — 신호(signal)를 받아 쓰는 소비자들. 판정을 다시 내지 않는다.

  · backtest/   체결 워크(trades)→돈(portfolio)→러너(runner) · market_config.json
  · notify/     telegram(망 urllib 예외)·desktop(OS 알림)
  · display/    엔진이 낸 판정 데이터를 화면 모양으로 빚는다(계산 안 함) · ui/ 화면 JS(SSOT)

경계: consumers 는 shared · market · dsl · signal · feed 만 import 한다. entry/verify 만 consumers 를 부른다.
경계는 verify/verify_code.py 가 강제한다.
"""
