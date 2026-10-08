# -*- coding: utf-8 -*-
"""구간③ 팀(trading) — 확정 트리로 판정 · 백테스트 · 장중. 돈·체결은 여기, 화면 모양은 web/ 이 빚는다.

  ── ① 신호 (tree+시세 → 판정 데이터)
  · signal/judge.py       Judge(한 상품·한 시점 판정) · Decision · Holding(pos 주입 한 곳) · signal_series(전 점 신호 — 백테스트용) · truncate(과거 세션 재현 — 파리티용)
  · signal/engine.py      라이브 판정 엔진 — slug·asof → 시세 조달 + 전 상품 Judge → Decision (web 이 화면으로 빚는다)
  ── ② 소비 (신호를 받아 쓴다)
  · backtest/trades.py    체결 워크 — 매도·분할 규칙 → 체결 일정(돈 없음) · 매도 정책(exit_policy) · 수량 변환(to_units) · 금액 정책(size_of)
  · backtest/portfolio.py 계산기(모의 실행) — 체결 일정 → vectorbt 돈·지표(market_config.json)
  · backtest/runner.py    백테스트 러너(신호 성적·거래 성적)
  · notify/telegram.py    텔레그램 송신(네트워크 urllib 예외는 이 한 파일) · notify/desktop.py 데스크톱 송신
  ── 공통·검사
  · commonTool.py         진입점 공통 '책 열기'(open_history — 로드+가드+시세, runner·탭·검사가 공유)
  · watch.py              장중 주기 재판정 루프(orchestration.run watch)
  · verify_trading.py     검사기 — 거래 시뮬레이터·실전 경로 불변식 · --parity 신호 패리티(백테스트 == 실시간)

트리의 뜻은 구간② 공개 DSL(checklist.tree_gateway·tradeTool)만 import 한다. 화면층(web)은 import 하지 않는다.
"""
