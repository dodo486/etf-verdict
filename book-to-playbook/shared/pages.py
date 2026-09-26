#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""책 페이지 찾기·신선도 — 검사기들이 공유하는 단일 기준.

어느 HTML 을 검사하나: books.json 기준, 배포본(PUBLIC/<slug>/index.html) 우선.
같은 로직이 검사기 세 곳에 복붙돼 있었다 — 사본이 갈라지면 검사기마다 서로 다른
페이지를 보게 되므로 여기 하나로 모은다.
"""
import io
import json
import os

from shared.paths import BASE, PUBLIC


def book_pages():
    """{slug: html경로} — books.json 기준, 배포본(PUBLIC/<slug>/index.html) 우선."""
    manifest = json.loads(io.open(os.path.join(BASE, "books.json"), encoding="utf-8").read())
    out = {}
    for b in manifest.get("books", []):
        slug = b["slug"]
        for cand in (os.path.join(PUBLIC, slug, "index.html"),
                     os.path.join(BASE, "%s-playbook.html" % slug)):
            if os.path.exists(cand):
                out[slug] = cand
                break
    return out


def stale_pages(pages):
    """배포본이 작업본보다 오래된 책 목록 -> [(slug, 검사대상, 작업본)]."""
    out = []
    for slug, path in sorted(pages.items()):
        src = os.path.join(BASE, "%s-playbook.html" % slug)
        if path == src or not os.path.exists(src):
            continue
        try:
            if os.path.getmtime(path) < os.path.getmtime(src):
                out.append((slug, path, src))
        except OSError:
            pass
    return out


def report_stale(pages):
    """낡은 배포본이 있으면 밝히고 True(=실패) 를 돌려준다.

    통과로 찍으면 어제 페이지를 검사하고 '이상 없음'이라고 말하는 게 된다.
    """
    bad = stale_pages(pages)
    if not bad:
        return False
    print("")
    print("낡은 배포본을 검사했습니다 — 이 결과는 지금 작업본의 상태가 아닙니다.")
    for slug, path, src in bad:
        print("  ! %-8s 검사 대상  %s" % (slug, path))
        print("           작업본이 더 최신  %s" % src)
    print("  발행하거나(python run.py publish), 작업본을 직접 보려면")
    print("  BOOK_TO_PLAYBOOK_PUBLIC 을 없는 경로로 지정해 다시 돌리세요.")
    return True
