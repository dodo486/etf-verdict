# -*- coding: utf-8 -*-
"""tree 층 — 조건 트리(tree.json)의 언어: 출입구·문법·등급의 뜻. 두 모듈 모두 공개(다른 층이 import 해도 된다).

  · gateway.py          TreeGateway — tree.json 을 읽는 유일한 출입구(형식 검사·탐색)
  · tradeTool.py        Cond(조건 트리 문법·평가기) · Grade(날짜별 등급·금액·비중·워밍업 가드·시세 조달)
                        + grade_rules.json(등급 사다리) · python -m tree.tradeTool fmt <파일> = 공통 직렬화
  · verify_primitives.py 검사 — 원시 연산·등급 계산·출입구 계약을 기준값·손계산과 대조(tree 를 바꾸면)

경계: tree 는 shared · market 만 import 한다. 트리를 '만드는' 절차 문서는 authoring/extract/ 에 있다.
경계는 entry/verify_rules.py 가 강제한다.
"""
