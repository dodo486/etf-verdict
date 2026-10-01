# -*- coding: utf-8 -*-
"""구간② 팀 — 플레이북 → 체크리스트 시트.

규칙(books/<slug>/rules.json)과 공유 UI 를 책 페이지에 주입해 실전 체크리스트
시트를 조립하고, '반영됐다'는 주장(커버리지 배지)이 사실인지 지킨다.

  · inject_rules.py     rules.json → 책 HTML 주입 (규칙 SSOT 는 파일)
  · inject_ui.py        ui/<name>.js → 책 HTML 주입 (UI SSOT 는 파일)
  · ui/                 체크리스트·플레이북·검수 UI JS (책 무관 공유)
  · verify_coverage.py  커버리지 배지 검증 (✅반영이 사실인가)
  · verify_tree.py      조건 트리 검사·채택 — 이중 추출 비교·원문 사례·심판 기록·채택(--dump/--adopt)
  · COND_DSL.md         조건 트리 작성 지침

팀 경계: 다른 팀(playbook·verdict) 코드를 import 하지 않는다. 공용은 shared/ 만.
다른 팀과의 인터페이스는 코드가 아니라 산출물 파일(books/<slug>/*.json)이다.
경계는 verify_teams.py 가 기계로 강제한다.
"""
