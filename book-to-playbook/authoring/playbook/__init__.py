# -*- coding: utf-8 -*-
"""책 원본 → 플레이북 — 원문을 소절 단위로 인덱싱하고 플레이북 본문이 바뀌지 않게 지킨다.

  · book_source.py   원문 → 소절 인덱스(books/<slug>/source_index.json — 체크리스트 ref 의 기준)
  · pages.py         플레이북 소절 페이지 모음
  · PLAYBOOK.md      플레이북 작성 지침 · book_sources.json 원본 등록 · source_baseline.json 본문 해시 기준

플레이북이 원문과 어긋나면 트리가 아니라 플레이북을 고친다(verify/verify_source_integrity --accept --why).
"""
