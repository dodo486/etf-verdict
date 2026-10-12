# -*- coding: utf-8 -*-
"""authoring 층 — 책 → 전사(플레이북) → 조건 트리(tree.json)를 '만드는' 쪽. 저자·추출자·심판의 코드와 지침. 두 단계는 서로 import 하지 않는다.

  · transcribe/  ① 책 → 전사: 원문 → 소절 인덱스(book_source·pages) + 플레이북 본문·원본 등록(PLAYBOOK.md·*.json)
  · extract/     ② 전사 → 트리: 진행 절차·지침 문서(README·EXTRACTOR·SCENARIO·JUDGE·COND_DSL)
                 + 심판 비교 도구(compare.py — a·b 덤프와 '같은 뜻' 잣대) · 트리 채점(verify_tree.py)
만드는 곳 = 검증하는 곳 — 원문 검사(transcribe/verify_source)·트리 검사(extract/verify_tree)도 여기 산다.

경계: authoring 은 shared · market · tree · judge 만 import 한다(트리의 뜻은 tree 공개 모듈로, 심판 비교 도구가 후보 트리를
평가할 때는 판단자 judge/judge 로). 백테스트·화면은 모른다.
다른 층과의 인터페이스는 코드가 아니라 산출물 파일(books/<slug>/*.json)이다.
경계는 entry/verify_rules.py 가 강제한다.
"""
