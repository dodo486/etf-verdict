# -*- coding: utf-8 -*-
"""backtest 층 — 판정→체결(trades)→돈(portfolio)→러너(runner) · market_config.json · verify_trading(검사 — 체결 계산·실전 경로 · --parity).

경계: backtest 는 shared · market · tree · judge 만 import 한다. 판정을 다시 내지 않는다(판단자가 낸 값만 쓴다).
"""
