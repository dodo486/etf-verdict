#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""라이브 판정 엔진(구간③) — slug + 관측 시각(asof) → 전 상품 판정(Decision). 시세 조달·Judge 는 여기, 화면 모양은 consumers/display 가 빚는다.

왜 signals 에 있나
  '시세를 받아 판정을 내리는' 일은 구간③(판정)의 몫이다. 예전엔 이 드라이버가 화면층(consumers/display/verdict_view)에
  섞여 있어 화면이 판정을 '계산'하는 꼴이었다 — 등급 수학은 Judge/ProductEval 이 내지만, 그 Judge 를 세우고 시세를
  조달하는 오케스트레이션이 화면층에 있었다. 그 엔진 절반을 여기로 옮겨, consumers/display 는 이 엔진이 낸 Decision 을
  '화면·알림 모양으로 빚기만' 한다(화면은 판정을 계산하지 않는다 — 서버 권위·판단/표시 분리).

  · open_history    책 열기(트리 로드+가드+시세) — 라이브·백테스트·검사가 공유하는 진입 preamble
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


def open_history(slug, extra_days=0, tree=None, hist=None):
    """책 열기 — slug → (tree, hist). tree 가 없으면 정지, hist 가 없으면 history_back(extra_days 만큼 더 과거까지).
    여러 진입점(라이브·백테스트 러너·탭·검사)이 똑같이 하던 '로드+가드+시세' preamble 한 곳.
    tree·hist 를 주면 그대로 쓴다(바깥이 이미 받아둔 걸 두 번 안 받게)."""
    tree = tree or TreeGateway.load(slug)
    if tree is None:
        raise SystemExit("books/%s/tree.json 없음 — 조건 트리가 있어야 한다" % slug)
    return tree, (hist if hist is not None else Grade.history_back(tree, extra_days))


def load_positions(slug):
    """books/<slug>/positions.json (커밋하지 않는 개인 파일) → {prod: [포지션]}."""
    p = positions_json(slug)
    if not os.path.exists(p):
        return {}
    out = {}
    for x in (json.load(open(p, encoding="utf-8")).get("positions") or []):
        out.setdefault(x["prod"], []).append(x)
    return out


def live_decisions(slug, asof=None, answers=None, tree=None, hist=None):
    """slug 의 라이브 판정 — 시세를 받아 상품마다 Judge(라이브 = 달력 마지막 봉)로 Decision 을 낸다.
    asof = 관측 시각(UTC datetime, None 이면 지금) · answers = 사람이 답한 수동 {Cond.answer_key: 참/거짓}(서버 권위).
    tree·hist 를 주면 그대로 쓴다 — 피더가 전 책 심볼을 '한 번' 조회한 공유 시세(합집합 hist)를 책마다 넣어
    주면, 이 책의 Judge 는 자기 심볼만 읽어(ProductEval) 혼자 받던 때와 같은 판정을 낸다(중복 조회 제거).

    → (tree, hist, positions, [(prod, Decision, [내 포지션])]).  트리가 없으면 (None, {}, {}, []).
    Decision 은 판정 '사실'(등급·금액 Amount·보유 규칙 상태) — 화면 모양·사유 문장은 web 이 빚는다(엔진은 화면을 모른다)."""
    tree = tree if tree is not None else TreeGateway.load(slug)
    if tree is None:
        return None, {}, {}, []
    hist = hist if hist is not None else Grade.history_back(tree)
    positions = load_positions(slug)
    out = []
    for p in tree.products():
        j = Judge(tree, p, hist, asof=asof, answers=answers)
        xs = positions.get(p, [])
        d = j.decide(holdings=[Holding.at(j.cal, str(x["entry_date"]), float(x["entry_px"]), int(x.get("filled", 1)))
                               for x in xs])
        out.append((p, d, xs))
    return tree, hist, positions, out
