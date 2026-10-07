#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""책 페이지 찾기 — 플레이북 본문 무결 검사의 단일 기준(구간① 소유).

어느 HTML 을 검사하나: books.json 에 등록된 책의 플레이북 원본(BASE/<slug>-playbook.html).
쓰는 곳은 구간① verify_source_integrity 하나다 — 어느 페이지를 볼지 한 벌로 정한다.
(정적 발행(GitHub Pages)이 폐지돼 '배포본' 개념이 없어졌다 — 늘 작업본 하나만 본다.)
"""
import os

from shared.paths import BASE, load_books


def book_pages():
    """{slug: html경로} — books.json 에 등록된 책의 플레이북 원본(있는 것만)."""
    out = {}
    for b in load_books():
        slug = b["slug"]
        cand = os.path.join(BASE, "%s-playbook.html" % slug)
        if os.path.exists(cand):
            out[slug] = cand
    return out
