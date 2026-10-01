# -*- coding: utf-8 -*-
"""공통층(shared) — 세 팀(playbook·checklist·verdict) 모두가 쓰는 유일한 공용 코드.

팀 규칙: 팀 폴더끼리는 서로 import 하지 않는다. 두 팀 이상이 같은 코드가 필요하면
그 코드는 여기로 온다. (경계는 verify_teams.py 가 기계로 강제한다.)

조건 트리는 구간②가 만들고(checklist.verify_tree) 구간③이 읽는다(verdict). 트리의 **뜻**이
두 곳에서 따로 구현되면 만든 쪽과 읽는 쪽의 판정이 갈라지므로, 뜻은 여기 한 벌만 둔다:
  · cond.py        조건 트리 문법·평가기
  · tree_grade.py  트리 → 날짜별 등급·사유
  · trades.py      매수 신호 + 매도 규칙 → 거래(체결 규약)
  · md_feed.py     jhts 시세수집팀 창구 — 파이프라인의 유일한 시세 입구
"""
