# -*- coding: utf-8 -*-
"""소절 키 규칙 — 책 원문·플레이북 글에서 장/소절 표지를 알아보는 규칙의 유일한 주인.

소절 키는 `N-M`(예 7-5) 또는 특수 소절(프롤로그·에필로그)이다. 원문 인덱스(authoring.transcribe.book_source)와
화면의 소절 원문(web.book_page)이 같은 키를 봐야 체크리스트 ref 가 양쪽에서 같은 소절을 가리킨다.

    ^\\s*(Chapter\\s+\\d+)\\.   또는  ^\\s*(\\d+)\\s*장\\.   → 장 경계
    ^\\s*(\\d+-\\d+)\\.                                    → 소절
    ^\\s*(프롤로그|에필로그)[:\\s]                          → 특수 소절
    ^#{2,3}\\s*(키)\\s*[.\\s—-]                             → 플레이북 #src 마크다운의 소절 제목
"""
import re

SECTION_KEY = r"\d+-\d+"            # 소절 키 'N-M'
SPECIAL_KEY = r"프롤로그|에필로그"     # 특수 소절 키
KEY = SECTION_KEY + "|" + SPECIAL_KEY

MARK_CHAPTER = re.compile(r"^\s*(?:Chapter\s+(\d+)|(\d+)\s*장)\.")
MARK_SECTION = re.compile(r"^\s*(%s)\." % SECTION_KEY)
MARK_SPECIAL = re.compile(r"^\s*(%s)[:\s]" % SPECIAL_KEY)
PB_HEAD = re.compile(r"^#{2,3}\s*(%s)\s*[.\s—-]" % KEY)


def marks(lines):
    """표지 위치 전부. [(i, kind, key, rest)] — kind: chapter|section|special"""
    out = []
    for i, line in enumerate(lines):
        m = MARK_CHAPTER.match(line)
        if m:
            key = m.group(1) or m.group(2)
            out.append((i, "chapter", key, line[m.end():].strip()))
            continue
        m = MARK_SECTION.match(line)
        if m:
            out.append((i, "section", m.group(1), line[m.end():].strip()))
            continue
        m = MARK_SPECIAL.match(line)
        if m:
            out.append((i, "special", m.group(1), line[m.end():].strip()))
    return out
