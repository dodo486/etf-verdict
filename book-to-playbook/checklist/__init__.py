# -*- coding: utf-8 -*-
"""구간② 팀 — 플레이북 → 체크리스트(조건 트리).

체크리스트 = books/<slug>/tree.json(조건 트리). 이 팀이 트리를 만드는 유일한 곳이다:
서로 모르는 추출자 a·b 가 플레이북에서 후보를 쓰고, 원문만 보고 쓴 사례로 확인하고, 판정이 갈린 날을
심판이 원문과 대조해 채택한다. 화면(체크리스트 UI)은 트리가 아니라 구간③ 판정 결과를 그린다.

  · COND_DSL.md         조건 트리 작성 지침(여섯 칸·수동 사유 머리·숫자 지어내지 않기)
  · verify_tree.py      트리 검사·채택 — 이중 추출 비교·원문 사례·발화 통계·비중 합(--dump/--adopt)
  · inject_ui.py        ui/<name>.js → 책 HTML 주입 (UI SSOT 는 파일)
  · ui/                 체크리스트·플레이북·검수·수집 현황·라이브·백테스트 화면 JS (책 무관 공유)

팀 경계: 다른 팀(playbook·verdict) 코드를 import 하지 않는다. 공용은 shared/ 만(트리의 뜻 cond·tree_grade·
trades 와 시세 창구 md_feed 는 shared/ — 구간③과 같은 코드). 경계는 verify_teams.py 가 기계로 강제한다.
"""
