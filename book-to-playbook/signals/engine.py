#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""라이브 판정 엔진(구간③) — slug + 관측 시각(asof) → 전 상품 판정(Decision). 시세 조달·Judge 는 여기, 화면 모양은 web 이 빚는다.

왜 trading 에 있나
  '시세를 받아 판정을 내리는' 일은 구간③(판정)의 몫이다. 예전엔 이 드라이버가 web/verdict_view 에 섞여 있어
  화면층이 판정을 '계산'하는 꼴이었다 — 등급 수학은 Judge/ProductEval 이 내지만, 그 Judge 를 세우고 시세를
  조달하는 오케스트레이션이 web 에 있었다. 그 엔진 절반을 여기로 옮겨, web 은 이 엔진이 낸 Decision 을
  '화면·알림 모양으로 빚기만' 한다(web 은 판정을 계산하지 않는다 — 서버 권위·판단/표시 분리).

  · load_positions  내 포지션(books/<slug>/positions.json — 커밋 안 하는 개인 파일) 읽기
  · live_decisions  시세 조달 + 상품마다 Judge(라이브 = 달력 마지막 봉) → Decision(판정 사실)

엔진은 돈·화면을 모른다 — Decision 은 등급·금액(Amount)·보유 규칙 상태 같은 '사실'만 담는다. 사유 문장·view·
비중 금액·알림은 소비층(consumers/display · consumers/notify)이 이 사실로 빚는다.
"""
import json
import os

from shared.paths import positions_json
from dsl.tradeTool import Grade
from dsl.tree_gateway import TreeGateway
from signals.judge import Holding, Judge


def load_positions(slug):
    """books/<slug>/positions.json (커밋하지 않는 개인 파일) → {prod: [포지션]}."""
    p = positions_json(slug)
    if not os.path.exists(p):
        return {}
    out = {}
    for x in (json.load(open(p, encoding="utf-8")).get("positions") or []):
        out.setdefault(x["prod"], []).append(x)
    return out


def live_decisions(slug, asof=None, answers=None):
    """slug 의 라이브 판정 — 시세를 받아 상품마다 Judge(라이브 = 달력 마지막 봉)로 Decision 을 낸다.
    asof = 관측 시각(UTC datetime, None 이면 지금) · answers = 사람이 답한 수동 {Cond.answer_key: 참/거짓}(서버 권위).

    → (tree, hist, positions, [(prod, Decision, [내 포지션])]).  트리가 없으면 (None, {}, {}, []).
    Decision 은 판정 '사실'(등급·금액 Amount·보유 규칙 상태) — 화면 모양·사유 문장은 web 이 빚는다(엔진은 화면을 모른다)."""
    tree = TreeGateway.load(slug)
    if tree is None:
        return None, {}, {}, []
    hist = Grade.history_back(tree)
    positions = load_positions(slug)
    out = []
    for p in tree.products():
        j = Judge(tree, p, hist, asof=asof, answers=answers)
        xs = positions.get(p, [])
        d = j.decide(holdings=[Holding.at(j.cal, str(x["entry_date"]), float(x["entry_px"]), int(x.get("filled", 1)))
                               for x in xs])
        out.append((p, d, xs))
    return tree, hist, positions, out
