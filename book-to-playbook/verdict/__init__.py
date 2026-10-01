# -*- coding: utf-8 -*-
"""구간③ 팀 — 체크리스트(조건 트리) → 데이터 수집·판정.

입력은 둘뿐이다: 구간②가 만든 books/<slug>/tree.json 과 jhts 시세. 수집할 심볼은 트리에서 나오고
(shared/cond.symbols_of), 시세는 shared/md_feed.histories 하나로 받는다 — 없으면 jhts 에 수집 요청을 남긴다.

  · verdict_engine.py     오늘 판정(여섯 칸) → 알림 + latest-verdict-<slug>.json (화면이 그대로 그린다)
  · backtest.py           같은 트리로 과거 신호·거래 성적(책 매도·분할 규칙) → 백테스트 탭
  · verify_primitives.py  검사기 ② — 원시 연산·체결·등급 계산을 기준값·손계산과 대조

팀 경계: 다른 팀(playbook·checklist) 코드를 import 하지 않는다. 공용은 shared/ 만.
`import jhts` 는 shared/md_feed.py 에서만 허용된다. 네트워크 모듈(urllib 등)은 이 팀
전체에서 금지다 — 알림 송신은 shared/notify.py 가 맡는다. 경계는 verify_teams.py 가 기계로 강제한다.
"""
