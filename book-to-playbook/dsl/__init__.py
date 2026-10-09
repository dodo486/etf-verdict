# -*- coding: utf-8 -*-
"""dsl 층 — 조건 트리(tree.json)의 언어: 출입구·문법·등급의 뜻. 두 모듈 모두 공개(다른 층이 import 해도 된다).

  · tree_gateway.py     TreeGateway — tree.json 을 읽는 유일한 출입구(형식 검사·탐색)
  · tradeTool.py        Cond(조건 트리 문법·평가기) · Grade(날짜별 등급·금액·비중·워밍업 가드·시세 조달)
                        + grade_rules.json(등급 사다리) · python -m dsl.tradeTool fmt <파일> = 공통 직렬화

경계: dsl 은 shared · market 만 import 한다. 트리를 '만드는' 절차 문서는 authoring/checklist/ 에 있다.
경계는 verify/verify_code.py 가 강제한다.
"""
