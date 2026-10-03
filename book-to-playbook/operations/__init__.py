# -*- coding: utf-8 -*-
"""구간④ 계산기(operations) — 확정된 조건 트리를 '소비'하는 돈·성적 계산기(백테스트 엔진).

단방향(폭포수): operations 는 아래(shared 의 규칙 평가 결과·verdict 산출물)만 읽는다.
머리(playbook·checklist·verdict)와 공통층(shared)은 operations 를 import 하지 않는다 — 역류 금지.
경계는 verify_teams.py 가 기계로 강제한다.

  · portfolio.py  shared.trades.build_trades 가 낸 체결 일정을 받아 vectorbt 로 돈·지표
                  (자산곡선·MaxDD·샤프·총수익)를 낸다. 비용 config 는 operations/market_config.json.
  · backtest.py   드라이버 — 같은 트리로 과거 신호·거래 성적을 내고(기본 엔진),
                  --engine vectorbt 로 포트폴리오 지표를 더한다.
"""
