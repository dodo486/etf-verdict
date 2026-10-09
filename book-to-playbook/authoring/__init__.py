# -*- coding: utf-8 -*-
"""authoring 층 — 책 원본 → 플레이북 → 조건 트리(tree.json)를 '만드는' 쪽. 저자·추출자·심판의 코드와 지침.

  · playbook/   책 원문 → 소절 인덱스(book_source·pages) + 플레이북 본문·원본 등록(PLAYBOOK.md·*.json)
  · checklist/  구간② 진행 절차·지침 문서(README·EXTRACTOR·SCENARIO·JUDGE·COND_DSL) — 트리를 쓰는 사람 참고서

경계: authoring 은 shared · market · dsl 만 import 한다(트리의 뜻은 dsl 공개 모듈로). 소비·화면·판정은 모른다.
다른 층과의 인터페이스는 코드가 아니라 산출물 파일(books/<slug>/*.json)이다.
경계는 verify/verify_code.py 가 강제한다.
"""
