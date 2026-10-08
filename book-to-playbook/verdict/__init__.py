# -*- coding: utf-8 -*-
"""구간③ 팀 — 체크리스트(조건 트리) → 데이터 수집·판정.

입력은 둘뿐이다: 구간②가 만든 books/<slug>/tree.json 과 jhts 시세. 트리는 출입구 TreeGateway
(checklist/tree_gateway.py — 트리를 읽는 유일한 코드)로 읽고, 수집할 심볼도 거기서 나오며(TreeGateway.symbols), 시세는 shared/md_feed.histories 하나로 받는다 — 없으면 jhts 에 수집 요청을 남긴다.

  · verdict_engine.py     오늘 판정(여섯 칸) → 알림 + latest-verdict-<slug>.json (화면이 그대로 그린다)
  · verify_primitives.py  검사기 ② — 원시 연산·체결·등급 계산을 기준값·손계산과 대조

과거 신호·거래 성적(백테스트)은 구간④ 계산기(operations/backtest.py)로 옮겼다 — 확정된 트리를
'소비'하는 돈·성적 계산기다(단방향 폭포수: operations 는 shared/verdict 산출물을 읽기만 한다).

팀 경계: 다른 팀(playbook·checklist) 코드를 import 하지 않는다 — 명시 예외 하나는 트리 출입구
checklist/tree_gateway.py. 공용은 shared/ 만.
`import jhts` 는 shared/md_feed.py 에서만 허용된다. 네트워크 모듈(urllib 등)은 이 팀에서
알림 송신 전용인 verdict/notify.py 한 파일만 허용된다(verify_teams.py ALLOW 의 명시 예외) —
시세 수집용 네트워크 코드는 여전히 금지다. 경계는 verify_teams.py 가 기계로 강제한다.
"""
