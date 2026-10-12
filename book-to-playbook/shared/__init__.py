# -*- coding: utf-8 -*-
"""shared 층 — 모든 층이 쓰는 유일한 공용 코드. 경로·인코딩·책 레지스트리, 그리고 여러 층이 함께 읽는
원문 표기 규칙(소절 키) 하나뿐이다 — 그 밖의 뜻(규칙)은 두지 않는다.

  · paths.py       경로·인코딩·책 레지스트리(books.json)
  · sections.py    소절 키 규칙 — 원문·플레이북의 장/소절 표지 정규식(authoring 원문 인덱스·web 소절 원문)

shared 는 어느 층도 import 하지 않는다(경계는 entry/verify_rules.py 가 기계로 강제한다).
"""
