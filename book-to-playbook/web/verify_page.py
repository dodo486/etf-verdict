#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""책 페이지 검사 — 조립(book_page.assemble)이 기대는 골격이 원본에 있나. 페이지·UI 를 바꿀 때 돈다.

라이브 책마다 books/<slug>/playbook.html 에 #src · #verdict-data · #sheet-root 와 공유 UI 구획 전부가 있고
사본이 web/ui/*.js 와 같은가(inject_ui.check), 트리의 규칙이 전부 판정 화면에 식과 함께 실리나(tree_on_screen). 실패 → 정지(exit 1).

사용: python -m web.verify_page [slug ...]
"""
import sys

from shared.paths import live_slugs, playbook_html, read_text


PAGE_IDS = ('id="src"', 'id="verdict-data"', 'id="sheet-root"')


def page_contract(slug):
    """라이브 책 하나의 페이지 구조 위반 목록."""
    bad = []
    try:
        html = read_text(playbook_html(slug))
        for pid in PAGE_IDS:
            if pid not in html:
                bad.append("책 페이지에 %s 가 없다" % pid)
        from web.inject_ui import check as ui_check
        ok, msg = ui_check(html)
        if not ok:
            bad.append("공유 UI 구획: %s" % msg.split("\n")[0])
    except OSError as e:
        bad.append("책 페이지 없음: %s" % e)
    bad += tree_on_screen(slug)
    return bad


def tree_on_screen(slug):
    """트리 ↔ 화면 — 이 책 트리의 규칙이 전부 판정 화면(칸 또는 칸 밖)에 식과 함께 실리나(web/verdict_view.uncovered).
    트리가 없거나 문법에서 멈추면 여기서는 보지 않는다(트리 계약 검사가 따로 본다)."""
    from judge.judge import Judge
    from web.verdict_view import render, uncovered
    try:
        book = Judge.open(slug)
    except Exception:  # noqa: BLE001 — 트리 문법 오류는 트리 계약 검사 몫
        return []
    if book is None:
        return []
    top = render(slug)
    if top.get("error"):
        return ["판정 화면 오류: %s" % top["error"]]
    return ["트리 ↔ 화면: %s" % x for x in uncovered(book.tree, top)]


def main(argv=()):
    stop = []
    for slug in [a for a in argv if not a.startswith("-")] or live_slugs():
        bad = page_contract(slug)
        print("  %s %-34s %s" % ("✅" if not bad else "❌", "책 페이지 " + slug, "; ".join(bad)[:300] or "통과"))
        if bad:
            stop.append("책 페이지 " + slug)
    if stop:
        print("책 페이지 정지 — %s" % ", ".join(stop))
        return 1
    print("책 페이지 통과 — 구획·UI 사본·트리 ↔ 화면")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
