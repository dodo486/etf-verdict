# -*- coding: utf-8 -*-
"""구간③ 팀 — 체크리스트 → 데이터 수집·판정.

체크리스트의 각 항목에 필요한 데이터를 받아 자동 판정한다. 시세는 **오직**
jhts 시세수집팀(jhts.marketdata)에서만 받는다 — 이 팀의 누구도 시세를 직접
수집하지 않는다(야후·KIS·스크래핑 금지). 그 창구가 md_feed.py 하나다.

  · md_feed.py               jhts.marketdata 어댑터 — 유일한 시세 창구
  · metric_calc.py           data_spec 의 metric 선언 → 값·판정 (md_feed 데이터로)
  · verdict_engine.py        rules.json 선언 → 종목별 자동판정 (책 무관)
  · verify_rules_vs_spec.py  체크리스트 ↔ 수집요청 대조 (창작·누락 검사)
  · verify_auto_coverage.py  '자동 가능한데 ✋직접으로 샌 것' 검사

팀 경계: 다른 팀(playbook·checklist) 코드를 import 하지 않는다. 공용은 shared/ 만.
`import jhts` 는 md_feed.py 에서만 허용된다. 네트워크 모듈(urllib 등)은 이 팀
전체에서 금지다 — 알림 송신은 shared/notify.py 가 맡는다.
경계는 verify_teams.py 가 기계로 강제한다.
"""
