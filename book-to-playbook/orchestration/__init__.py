# -*- coding: utf-8 -*-
"""조립·감사층(orchestration) — 전 구간을 가로질러 '실행'하고 '검사'하는 최상위 층.

구간 팀(playbook·checklist·trading)도, 공용(shared)·화면(web)도 아니다.
파이프라인을 굴리고(run) 경계·구조를 기계로 검사(verify_*)하는, 예전에 루트에 떠 있던
'폴더 밖 코드'를 한 층으로 모은 곳이다(1폴더=1구간=1기능 원칙).

  · run.py          스케줄 러너 — 판정·백테스트 탭 데이터·검사를 순서대로(daily/verdict/watch) + 검사 목록 CHECKS 한 곳(check)
  · verify_code.py  코드 규칙 — 폴더 경계(폴더=조직도) + 주인 표(결정 하나 = 주인 하나)

진입: `python -m orchestration.run <daily|verdict|watch|check>`
어느 구간도 이 층을 import 하지 않는다 — 여기가 맨 위에서 아래(구간들)를 실행·검사만 한다.
"""
