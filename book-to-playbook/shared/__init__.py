# -*- coding: utf-8 -*-
"""공통층(shared) — 모든 팀이 쓰는 유일한 공용 코드. 뜻(규칙)은 두지 않는다 — 시세 창구와 경로뿐이다.

  · md_feed.py     jhts 시세수집팀 창구 — 파이프라인의 유일한 시세 입구
  · _dev_cache.py  개발용 시세 캐시(ETF_DEV_CACHE 일 때만)
  · paths.py       경로·인코딩·책 레지스트리(books.json)

트리의 뜻(문법 cond·등급 grade)은 구간② checklist/ 가, 체결 워크(trades)는 구간③ trading/ 이 가진다.
공통층은 어느 팀도 import 하지 않는다(경계는 orchestration/verify_code.py 가 기계로 강제한다).
"""
