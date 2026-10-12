#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""책 계약 — 시세 없이 바로 갈리는 책 산출물 계약만(라이브 책마다, 실패 → 정지). entry.run 이 항상 돌린다.

  · books/<slug>/source_index.json — 원문이 소절 단위로 잘려 있다(소절 키 = 체크리스트 ref)
  · books/<slug>/tree.json — 체크리스트가 문법을 통과한다(v3 규칙·동사 셋)
  · 트리의 ref 가 전부 실제 소절 키다(없는 소절을 근거로 삼지 않는다)
  · 책 페이지(books/<slug>/playbook.html)에 #src · #verdict-data · #sheet-root 와 공유 UI 구획 전부가 있고
    사본이 consumers/display/ui/*.js 와 같다(consumers.display.inject_ui.check)

트리가 원문 뜻대로 '동작'하는지(이중 추출·사례·발화 통계)는 verify/book/tree.py 가 본다.

종료코드: 0 통과 · 1 정지.
사용: python -m verify.book.contract [slug ...]
"""
import json
import sys

from shared import paths  # noqa: F401  (UTF-8 출력)
from shared.paths import live_slugs, playbook_html, read_text, source_index_json
from dsl.tradeTool import Cond
from signals.judge import Judge


def contract(slug):
    """라이브 책 하나의 산출물 계약 위반 목록 — 소절 인덱스 · 트리 문법 · 트리 ref 가 실제 소절."""
    bad = []
    try:
        idx = json.load(open(source_index_json(slug), encoding="utf-8"))
        keys = set(idx.get("sections") or {})
        if not keys:
            bad.append("source_index.json 에 소절이 없다")
    except (OSError, ValueError) as e:
        bad.append("source_index.json 없음/깨짐: %s" % e)
        keys = set()
    try:
        tree = Judge.read(slug, "tree.json")
        if not tree:
            raise ValueError("tree.json 없음")
        tree.validate()
    except (OSError, ValueError, Cond.CondError) as e:
        bad.append("tree.json 문법: %s" % e)
        tree = None
    if tree is not None and keys:
        refs = tree.refs()
        # "2-1·2-3" 처럼 여러 소절을 함께 적은 ref 는 하나하나 본다
        parts = {p.strip() for r in refs for p in str(r).replace("·", ",").split(",") if p.strip()}
        missing = sorted(parts - keys)
        if missing:
            bad.append("tree.json 의 ref 가 없는 소절을 가리킴: %s" % ", ".join(missing))
    return bad


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
    slugs = [a for a in argv if not a.startswith("-")] or live_slugs()
    stop = []
    for slug in slugs:
        for what, bad in (("책 계약 ", contract(slug)), ("책 페이지 ", page_contract(slug))):
            print("  %s %-34s %s" % ("✅" if not bad else "❌", what + slug, "; ".join(bad)[:300] or "통과"))
            if bad:
                stop.append(what + slug)
    if stop:
        print("책 계약 정지 — %s" % ", ".join(stop))
        return 1
    print("책 계약 통과 — 소절 인덱스·트리 문법·ref·책 페이지")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
