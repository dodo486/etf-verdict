#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""구간③ 공통 도구 — 여러 진입점이 똑같이 하던 '책 열기' 한 곳.

open_history(slug) : 트리 열고(출입구) · 없으면 정지 · 시세는 Grade.history_back 로 받는다.
  backtest.run · run_vectorbt · run_intraday · replay.replay · web.backtest_page · verify_trading 이
  각자 복붙하던 preamble(로드+가드+시세)을 흡수한다. tree·hist 를 주면 그대로 쓴다(바깥이 이미 받아둔 걸 두 번 안 받게).
"""
from checklist.tradeTool import Grade
from checklist.tree_gateway import TreeGateway


def open_history(slug, extra_days=0, tree=None, hist=None):
    """slug → (tree, hist). tree 가 없으면 정지, hist 가 없으면 history_back(extra_days 만큼 더 과거까지)."""
    tree = tree or TreeGateway.load(slug)
    if tree is None:
        raise SystemExit("books/%s/tree.json 없음 — 조건 트리가 있어야 한다" % slug)
    return tree, (hist if hist is not None else Grade.history_back(tree, extra_days))
