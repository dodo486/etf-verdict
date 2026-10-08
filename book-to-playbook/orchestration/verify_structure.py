#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검사기 ① — 구조 게이트. 형식·구조처럼 '내용 해석 없이 기계로 참/거짓이 갈리는' 검사만 묶는다.

검증층은 셋이다(글자 대조 검사는 의미를 판정하지 못해 이 셋으로 대체했다):
  ① verify_structure          — 이 파일. 형식이 맞나
  ② checklist.verify_primitives — 계산이 맞나(원시 연산 실행 검사)
  ③ checklist.verify_tree     — 체크리스트(조건 트리)가 원문 뜻대로 동작하나(이중 추출·원문 사례·발화 통계)

여기 묶는 것과 등급:
  orchestration.verify_teams       팀 경계·jhts 단일 창구        0 통과 · 그 외 정지
  playbook.verify_source_integrity 플레이북 본문 불변(해시)        0 통과 · 그 외 정지
  책 계약(이 파일)                  라이브 책마다:
      · books/<slug>/source_index.json — 원문이 소절 단위로 잘려 있다(소절 키 = 체크리스트 ref)
      · books/<slug>/tree.json — 체크리스트가 문법을 통과한다(여섯 칸 전부 명시)
      · 트리의 ref 가 전부 실제 소절 키다(없는 소절을 근거로 삼지 않는다)
      · 책 페이지에 #src · #verdict-data · #sheet-root 와 공유 UI 구획 전부가 있고 사본이 ui/*.js 와 같다
                                    위반 → 정지

종료코드: 0 통과 · 1 정지.
사용: python -m orchestration.verify_structure
"""
import json
import os
import subprocess
import sys

from shared import paths  # noqa: F401  (UTF-8 출력)
from shared.paths import BASE, live_slugs, playbook_src, read_text
from checklist import cond
from checklist.tree_gateway import TreeGateway

CHECKS = ["orchestration.verify_teams", "playbook.verify_source_integrity"]
PAGE_IDS = ('id="src"', 'id="verdict-data"', 'id="sheet-root"')


def book_contract(slug):
    """라이브 책 하나의 계약 위반 목록."""
    bad = []
    try:
        idx = json.load(open(paths.source_index_path(slug), encoding="utf-8"))
        keys = set(idx.get("sections") or {})
        if not keys:
            bad.append("source_index.json 에 소절이 없다")
    except (OSError, ValueError) as e:
        bad.append("source_index.json 없음/깨짐: %s" % e)
        keys = set()
    try:
        tree = TreeGateway.open(TreeGateway.path(slug))
        tree.validate()
    except (OSError, ValueError, cond.CondError) as e:
        bad.append("tree.json 문법: %s" % e)
        tree = None
    if tree is not None and keys:
        refs = tree.refs()
        # "2-1·2-3" 처럼 여러 소절을 함께 적은 ref 는 하나하나 본다
        parts = {p.strip() for r in refs for p in str(r).replace("·", ",").split(",") if p.strip()}
        missing = sorted(parts - keys)
        if missing:
            bad.append("tree.json 의 ref 가 없는 소절을 가리킴: %s" % ", ".join(missing))
    try:
        html = read_text(playbook_src(slug))
        for pid in PAGE_IDS:
            if pid not in html:
                bad.append("책 페이지에 %s 가 없다" % pid)
        from publish.inject_ui import check as ui_check
        ok, msg = ui_check(html)
        if not ok:
            bad.append("공유 UI 구획: %s" % msg.split("\n")[0])
    except OSError as e:
        bad.append("책 페이지 없음: %s" % e)
    return bad


def main():
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    stop = []
    for mod in CHECKS:
        p = subprocess.run([sys.executable, "-m", mod], cwd=BASE, env=env, capture_output=True)
        out = p.stdout.decode("utf-8", "replace").strip().splitlines()
        last = out[-1] if out else p.stderr.decode("utf-8", "replace").strip()[-200:]
        if p.returncode != 0:
            stop.append(mod)
        print("  %s %-34s %s" % ("✅" if p.returncode == 0 else "❌", mod, last[:120]))
    for slug in live_slugs():
        bad = book_contract(slug)
        print("  %s %-34s %s" % ("✅" if not bad else "❌", "책 계약 " + slug, "; ".join(bad)[:300] or "통과"))
        if bad:
            stop.append("책 계약 " + slug)
    if stop:
        print("구조 게이트 정지 — %s" % ", ".join(stop))
        return 1
    print("구조 게이트 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
