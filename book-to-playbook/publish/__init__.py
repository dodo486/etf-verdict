# -*- coding: utf-8 -*-
"""발행·서빙층 — 세 팀의 산출물을 웹페이지로 조립해 내보내는 소비자.

팀이 아니라 조립자다. 사람은 여기서 나온 페이지로 '트레이딩 가능한지'만 본다.

  · build_home.py     books.json → 책 선택 홈 + 정적 책 조립
  · inject_nav.py     책 전환 사이드 레일 주입
  · publish_pages.py  최신 판정 병합 → PUBLIC/<slug>/index.html (GitHub Pages)
  · serve.py          로컬 실시간 서버 (정적 스냅샷 위에 살아있는 값 얹기)

조립이 역할이므로 팀 모듈(checklist 의 주입기 등)을 가져다 쓸 수 있다 —
단, 시세 수집은 여기서도 금지다(판정은 verdict 팀 산출물을 소비만 한다).
"""
