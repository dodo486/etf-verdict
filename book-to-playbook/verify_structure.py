#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검사기 ① — 구조 게이트. 형식·구조처럼 '내용 해석 없이 기계로 참/거짓이 갈리는' 검사만 묶는다.

검증층은 셋이다(나머지 글자 대조 검사는 의미를 판정하지 못해 이 셋으로 대체했다):
  ① verify_structure          — 이 파일. 형식이 맞나
  ② verdict.verify_primitives — 계산이 맞나(원시함수 실행 검사)
  ③ verdict.verify_behavior   — 원문 뜻대로 동작하나(이중 추출·원문 사례·발화 통계)

여기 묶는 넷과 등급(각 스크립트의 종료코드를 그대로 따른다):
  verify_teams                    팀 경계·jhts 단일창구       0 통과 · 그 외 정지
  playbook.verify_source_integrity 저자 원문 불변(해시)         0 통과 · 그 외 정지
  verify_contract                 책 계약 4조 · 규칙 누출       0 통과 · 1 정지 · 2 경고
  verify_editable_auto            손으로 박은 체크박스 금지     0 통과 · 그 외 정지

종료코드: 0 통과 · 1 정지(하나라도 정지) · 2 경고만.
사용: python -m verify_structure
"""
import os
import subprocess
import sys

from shared import paths  # noqa: F401  (UTF-8 출력)
from shared.paths import BASE

CHECKS = [
    # (모듈, 경고로 치는 종료코드 집합)
    ("verify_teams", set()),
    ("playbook.verify_source_integrity", set()),
    ("verify_contract", {2}),
    ("verify_editable_auto", set()),
]


def main():
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    stop, warn = [], []
    for mod, warn_codes in CHECKS:
        p = subprocess.run([sys.executable, "-m", mod], cwd=BASE, env=env, capture_output=True)
        out = p.stdout.decode("utf-8", "replace").strip().splitlines()
        last = out[-1] if out else p.stderr.decode("utf-8", "replace").strip()[-200:]
        if p.returncode == 0:
            mark = "✅"
        elif p.returncode in warn_codes:
            mark = "⚠"
            warn.append(mod)
        else:
            mark = "❌"
            stop.append(mod)
        print("  %s %-34s %s" % (mark, mod, last[:120]))
    if stop:
        print("구조 게이트 정지 — %s" % ", ".join(stop))
        return 1
    if warn:
        print("구조 게이트 통과(경고 %s)" % ", ".join(warn))
        return 2
    print("구조 게이트 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
