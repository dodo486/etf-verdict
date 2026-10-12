# -*- coding: utf-8 -*-
"""tree 층 — 조건 트리(tree.json)의 언어: 문법·출입구. gateway 는 공개(다른 층이 import 해도 된다).

  · gateway.py          트리 언어 — 문법(validate)·동사(VERBS)·워밍업(warmup_of) + TreeGateway(tree.json 을 읽는 유일한
                        출입구 — 형식 검사·탐색) · python -m tree.gateway fmt <파일> = 공통 직렬화
                        (식 계산은 judge/eval.py, 등급·시세 받기는 judge/judge.py)
  · verify_gateway.py   검사 — 문법·출입구 계약(tree 를 바꾸면)

경계: tree 는 shared · market 만 import 한다. 트리를 '만드는' 절차 문서는 authoring/extract/ 에 있다.
경계는 entry/verify_rules.py 가 강제한다.
"""
