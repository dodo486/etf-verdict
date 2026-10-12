#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""책 페이지 검사 — 조립(book_page.assemble)이 기대는 골격이 원본에 있나. 페이지·UI 를 바꿀 때 돈다.

라이브 책마다 books/<slug>/playbook.html 에 #src · #verdict-data · #sheet-root 와 공유 UI 구획 전부가 있고
사본이 consumers/display/ui/*.js 와 같은가(inject_ui.check). 실패 → 정지(exit 1).

사용: python -m consumers.display.verify_page [slug ...]
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
        from consumers.display.inject_ui import check as ui_check
        ok, msg = ui_check(html)
        if not ok:
            bad.append("공유 UI 구획: %s" % msg.split("\n")[0])
    except OSError as e:
        bad.append("책 페이지 없음: %s" % e)
    return bad


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
    print("책 페이지 통과 — 구획·UI 사본")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
