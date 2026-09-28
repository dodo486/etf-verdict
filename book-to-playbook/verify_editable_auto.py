#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""자동판정 체크박스가 editable 로 새는 것을 막는다 — 모든 책 공통 강제 검사.

## 왜 있나

"체크리스트 항목이 데이터로 자동판정 가능하면, 그 체크박스는 사람이 못 바꾼다(자동만
바꾼다)." 이 규칙은 SSOT(`checklist/ui/checklist-ui.js`)의 단일 함수 `isAuto()` 가
강제한다: 스코어카드·필터·진입·회피·재진입 체크박스는 전부 chk()/isAuto() 를 거쳐
자동이면 잠긴다(disabled).

문제는 **파이프라인 밖에서 체크박스를 손으로 박는 경우**다(과거 재진입 게이트가 그랬다).
그런 하드코딩 체크박스는 isAuto() 를 안 거치므로, 자동판정 데이터를 담고도 editable 로
남을 수 있다. 그러면 사람이 실데이터 판정을 잘못 눌러 뒤집는다 — 규칙이 조용히 깨진다.

그래서 이 검사가 못박는다: **책 페이지의 리터럴 체크박스는 스코어카드(data-sc)뿐이어야
한다.** 나머지 체크리스트 체크박스는 전부 런타임에 chk() 가 만든다(자동=잠금 보장).
`data-sc` 외의 하드코딩 체크박스가 있으면 = 파이프라인 우회 = 발행 정지.

`data-sc`(스코어카드)는 SSOT 가 무조건 disabled 로 잠그므로 허용한다.

## 한계 (정직하게)

정적 검사다. HTML 소스의 리터럴 체크박스만 본다(런타임 DOM 은 안 본다 — 그건 chk() 가
isAuto() 로 이미 보장). 즉 "파이프라인을 우회한 하드코딩"을 잡는 게 목적이다.

## 사용

    python verify_editable_auto.py            # 위반 있으면 exit 1
    python verify_editable_auto.py --json     # {slug: 위반수}
"""
import io
import json
import os
import re
import sys

from shared import paths  # noqa: F401  (경로·UTF-8 출력 고정)
from shared.paths import BASE, load_books, playbook_src

# 지울 블록: SSOT 주입 영역(INJECT 마커 사이) + 데이터 스크립트 블록(런타임이 읽는 JSON/MD).
#   이 안의 `<input type=checkbox` 문자열은 '페이지의 체크박스'가 아니라
#   JS 소스/데이터라 오탐이므로 검사 대상에서 뺀다.
INJECT_RE = re.compile(r"<!--\s*INJECT:[a-z-]+\s*-->.*?<!--\s*/INJECT:[a-z-]+\s*-->", re.S)
DATA_SCRIPT_RE = re.compile(
    r'<script[^>]*\bid="(?:rules|src|coverage-data|verdict-data|metric-registry)"[^>]*>.*?</script>',
    re.S)
# 인라인 <script> 전부 제거 — 체크박스는 HTML 마크업에만 리터럴로 존재해야 한다
# (JS 가 문자열로 '<input type=checkbox' 를 담는 건 chk() 템플릿이라 페이지 체크박스 아님).
SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.S)

CHECKBOX_RE = re.compile(r'<input[^>]*type="checkbox"[^>]*>', re.I)


def strip(html):
    html = INJECT_RE.sub("", html)
    html = DATA_SCRIPT_RE.sub("", html)
    html = SCRIPT_RE.sub("", html)
    return html


def line_of(full, needle_idx):
    return full.count("\n", 0, needle_idx) + 1


def check_book(slug):
    """반환: (위반 리스트[(line, snippet)], 검사했는지)."""
    src = playbook_src(slug)
    if not os.path.exists(src):
        return [], False
    full = io.open(src, encoding="utf-8").read()
    body = strip(full)
    viols = []
    for m in CHECKBOX_RE.finditer(body):
        tag = m.group(0)
        if "data-sc" in tag:
            continue   # 스코어카드 — SSOT 가 무조건 잠금(허용)
        # 원문에서의 대략 줄 위치(스트립 전 기준으로 다시 찾는다)
        idx = full.find(tag)
        ln = line_of(full, idx) if idx >= 0 else 0
        viols.append((ln, tag[:90]))
    return viols, True


def main(argv):
    json_mode = "--json" in argv
    result = {}
    bad = 0
    checked_any = False
    for b in load_books():
        slug = b.get("slug")
        if not slug:
            continue
        viols, checked = check_book(slug)
        if not checked:
            continue
        checked_any = True
        result[slug] = len(viols)
        if not json_mode:
            if viols:
                print("✗ %-10s 파이프라인 밖 하드코딩 체크박스 %d건" % (slug, len(viols)))
                for ln, snip in viols:
                    print("    · %s:%d  %s" % (os.path.basename(playbook_src(slug)), ln, snip))
            else:
                print("✓ %-10s 리터럴 체크박스는 스코어카드(data-sc)뿐 — 자동판정 우회 없음" % slug)
        bad += len(viols)

    if json_mode:
        print(json.dumps(result, ensure_ascii=False))
        return 1 if bad else 0

    print("=" * 70)
    if bad:
        print("자동판정 우회 %d건 — 발행 정지." % bad)
        print("-" * 70)
        print("체크리스트 체크박스는 rules.json → chk() 경로로만 만든다(자동이면 isAuto 가")
        print("자동 잠금). 스코어카드(data-sc)만 예외로 허용된다. 하드코딩 체크박스는")
        print("파이프라인을 우회해 '자동판정인데 editable'일 위험이 있으므로 금지한다.")
        print("수리: 그 항목을 rules.json 의 규칙(진입/회피/재진입 등)으로 옮기고,")
        print("      페이지는 컨테이너(예: <div id=\"reentryCard\">)만 두어 SSOT 가 렌더하게 한다.")
    elif checked_any:
        print("전부 통과 — 모든 책의 리터럴 체크박스가 스코어카드뿐이다(자동판정 우회 없음).")
    else:
        print("검사 대상 책 없음.")
    print("=" * 70)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
