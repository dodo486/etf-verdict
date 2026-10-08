# -*- coding: utf-8 -*-
"""구간③ 팀(trading) — 확정 트리로 판정·백테스트·장중.

  · trades.py           매도·분할 규칙 → 체결 일정(단위 물량, 돈 없음) · 표준 매도(exit_defaults.json)
  · verify_trading.py   검사기 — 거래 시뮬레이터·실전 경로 불변식

트리의 뜻은 구간② 공개 DSL(checklist.tree_gateway·cond·grade)만 import 한다.
"""
