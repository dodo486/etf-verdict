# -*- coding: utf-8 -*-
"""shared 층 — 모든 층이 쓰는 유일한 공용 코드. 뜻(규칙)은 두지 않는다 — 경로·인코딩·책 레지스트리뿐이다.

  · paths.py       경로·인코딩·책 레지스트리(books.json)

시세 창구(md_feed)는 market/ 으로, 트리의 뜻(cond·grade)은 dsl/ 로, 체결 워크(trades)는 consumers/ 로 옮겼다.
shared 는 어느 층도 import 하지 않는다(경계는 verify/verify_code.py 가 기계로 강제한다).
"""
