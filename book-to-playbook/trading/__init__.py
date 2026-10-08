# -*- coding: utf-8 -*-
"""구간③ 팀(trading) — 확정 트리로 판정 · 백테스트 · 장중. 돈·체결은 여기, 화면 모양은 web/ 이 빚는다.

  · judge.py            Judge(한 상품·한 시점 판정) · Decision(판정 사실) · Holding(보유 상태 — pos 주입 한 곳)
                        · signal_series(전 상품·전 시점 신호 — 백테스트용) · truncate(과거 세션 재현 — 파리티용)
  · trades.py           체결 워크 — 매도·분할 규칙 → 체결 일정(다음 봉 시가·단위 물량, 돈 없음) · 매도 정책(exit_policy — 책에 매도 규칙 없으면 매수 신호만 평가)
  · portfolio.py        계산기(모의 실행) — 체결 일정 → vectorbt 돈·지표(market_config.json)
  · backtest.py         백테스트 러너(신호 성적·거래 성적)
  · commonTool.py       진입점 공통 '책 열기'(open_history — 로드+가드+시세, backtest·탭·검사가 공유)
  · watch.py            장중 주기 재판정 루프(orchestration.run watch)
  · notify.py           알림 송신(텔레그램·데스크톱 — 네트워크 예외는 이 한 파일)
  · verify_trading.py   검사기 — 거래 시뮬레이터·실전 경로 불변식 · --parity 신호 패리티(백테스트 == 실시간)

트리의 뜻은 구간② 공개 DSL(checklist.tree_gateway·tradeTool)만 import 한다. 화면층(web)은 import 하지 않는다.
"""
