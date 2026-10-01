# -*- coding: utf-8 -*-
"""구간① 팀 — 책 원본 → 플레이북.

책 원문을 소절 단위로 인덱싱하고, 플레이북 본문이 바뀌지 않게 지킨다. 플레이북이 원문과 어긋나면
트리가 아니라 플레이북을 고친다(원문 대조 감사 → 수정 → verify_source_integrity --accept --why).

  · book_source.py               원문 → 소절 인덱스(books/<slug>/source_index.json — 체크리스트 ref 의 기준)
  · verify_source_integrity.py   플레이북 본문(#src) 불변 검사

팀 경계: 다른 팀(checklist·verdict) 코드를 import 하지 않는다. 공용은 shared/ 만.
다른 팀과의 인터페이스는 코드가 아니라 산출물 파일(books/<slug>/*.json)이다.
경계는 verify_teams.py 가 기계로 강제한다.
"""
