#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""팀 경계 검사 — 폴더 구조가 곧 조직도라는 약속을 기계로 강제한다.

## 왜 있나

이 파이프라인은 세 구간을 세 팀 폴더로 나눈다.
  · playbook/   구간① 책 원본 → 플레이북
  · checklist/  구간② 플레이북 → 체크리스트 시트
  · verdict/    구간③ 체크리스트 → 데이터 수집·판정
  · operations/ 구간④ 확정 트리 → 돈·성적 계산기(백테스트 엔진)
  · shared/     공통층(모든 팀이 쓰는 유일한 공용 코드)
  · publish/    발행·서빙층(팀 산출물의 소비자·조립자)

팀 사이 인터페이스는 **코드가 아니라 산출물 파일**(books/<slug>/*.json)이다.
팀 코드가 다른 팀 코드를 import 하는 순간 그 약속이 깨지고, 예전처럼
"한 검사기 안의 정의를 다른 검사기가 몰래 빌려 쓰다 갈라지는" 사고로 돌아간다.

## 무엇을 강제하나

  규칙 1  팀 폴더(playbook·checklist·verdict)의 모듈은
          stdlib + shared + **자기 팀**만 import 한다. 다른 팀 금지.
  규칙 2  `import jhts` 는 **shared/md_feed.py 하나**에서만 허용된다.
          파이프라인의 시세는 오롯이 jhts 시세수집팀 창구(md_feed)로만 들어온다.
  규칙 3  팀 폴더에서 네트워크 모듈(urllib.request·http.client·requests·socket
          ·aiohttp·httpx) import 금지 — 시세 자가수집(야후/KIS/스크래핑)이
          다시 자라나는 길목을 막는다. 알림 송신은 shared/notify.py 가,
          로컬 서빙은 publish/serve.py 가 맡는다(거기만 허용).
  규칙 4  publish/ 도 수집 금지다(규칙 3 의 네트워크 모듈 중 서버용
          http.server 만 허용) — 발행층은 판정 산출물을 소비만 한다.
  규칙 5  단방향(폭포수) — 머리(playbook·checklist·verdict)와 공통층(shared) 어느 것도 구간④
          계산기(operations, '돈·성적')를 import 하지 않는다. operations 만 아래(shared 의 규칙 평가
          결과·verdict 산출물)를 읽는다 — 머리/공통이 계산기를 부르면 흐름이 거꾸로 선다(역류).

## 사용

    python -m verify_teams        # 위반 있으면 exit 1 (run.py 발행 게이트에 포함)
"""
import ast
import os
import sys

from shared import paths  # noqa: F401  (경로·UTF-8 출력 고정)
from shared.paths import BASE

TEAMS = ("playbook", "checklist", "verdict")
LAYERS = TEAMS + ("shared", "publish", "operations")

# 시세 자가수집에 쓰이는 모듈들 — 팀 폴더에서 보이면 그 자체로 위반.
NET_MODULES = {"urllib", "http", "requests", "socket", "aiohttp", "httpx"}

# 규칙 2·3·4 의 명시적 예외 — 예외는 여기 한 곳에만 적는다(코드 곳곳에 흩지 않는다).
ALLOW = {
    ("shared", "md_feed.py"): {"jhts"},                     # 유일한 시세 창구
    ("shared", "notify.py"): {"urllib"},                    # 알림 '송신' 전용(수집 아님)
    ("publish", "serve.py"): {"http", "urllib"},            # 로컬 서버(서빙·URL 파싱)
}

# 규칙 5 — 단방향(폭포수): 머리(playbook·checklist·verdict)와 공통층(shared) 어느 것도 구간④ 계산기
#   (operations, '돈·성적')를 import 하지 않는다. operations 만 아래(shared 규칙 평가 결과·verdict 산출물)를
#   읽는다 — 머리/공통이 계산기를 부르면 흐름이 거꾸로 선다(역류). operations 폴더는 이 금지의 대상이 아니다.
UPSTREAM = set(TEAMS) | {"shared"}      # operations 를 import 해선 안 되는 '위쪽' 레이어
OPERATIONS = "operations"


def _imports(path):
    """파일의 최상위/함수내 import 전부 → {최상위 모듈명}. 파싱 불가면 None."""
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except SyntaxError as e:
        print("  ✗ 파싱 실패 %s: %s" % (path, e))
        return None
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:          # 상대 import 는 자기 팀 안이므로 통과
                continue
            if node.module:
                out.add(node.module.split(".")[0])
    return out


def check():
    bad = []
    for layer in LAYERS:
        d = os.path.join(BASE, layer)
        if not os.path.isdir(d):
            bad.append((layer, "-", "팀 폴더가 없음"))
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".py"):
                continue
            mods = _imports(os.path.join(d, fn))
            if mods is None:
                bad.append((layer, fn, "파이썬 파싱 실패"))
                continue
            allow = ALLOW.get((layer, fn), set())

            # 규칙 1 — 다른 팀 import 금지 (shared 는 모두 허용, publish 는 조립자라 팀 허용)
            if layer in TEAMS:
                others = (set(TEAMS) - {layer}) & mods
                if others:
                    bad.append((layer, fn, "다른 팀 import: %s" % ", ".join(sorted(others))))
            if layer == "shared":
                crossing = (set(TEAMS) | {"publish"}) & mods
                if crossing:
                    bad.append((layer, fn, "공통층이 팀을 import: %s (방향이 거꾸로다)"
                                % ", ".join(sorted(crossing))))

            # 규칙 2 — jhts 는 shared/md_feed.py 만
            if "jhts" in mods and "jhts" not in allow:
                bad.append((layer, fn, "jhts 직접 import — 시세 창구는 shared/md_feed.py 하나다"))

            # 규칙 3·4 — 네트워크 모듈 금지(명시 예외 제외)
            net = (NET_MODULES & mods) - allow
            if net:
                bad.append((layer, fn,
                            "네트워크 모듈 import: %s — 시세 자가수집 금지"
                            " (수집은 jhts, 알림은 shared/notify)" % ", ".join(sorted(net))))

            # 규칙 5 — 단방향(폭포수): 위쪽(머리 + 공통층)은 구간④ 계산기(operations)를 import 하지 않는다.
            #   operations 만 아래(shared 규칙 평가 결과·verdict 산출물)를 읽는다 — 위가 아래 계산기를 부르면 역류.
            if layer in UPSTREAM and OPERATIONS in mods:
                bad.append((layer, fn, "%s 가 계산기(operations) import — 단방향(폭포수) 역류" % layer))
    return bad


def main():
    bad = check()
    if bad:
        print("팀 경계 위반 %d건" % len(bad))
        for layer, fn, why in bad:
            print("  ✗ %-10s %-28s %s" % (layer + "/", fn, why))
        print("\n팀 사이는 코드가 아니라 산출물 파일(books/<slug>/*.json)로만 잇습니다.")
        print("두 팀 이상이 같은 코드가 필요하면 shared/ 로 올리세요.")
        return 1
    print("팀 경계 통과 — 팀 간 import 0 · jhts 창구 단일 · 자가수집 네트워크 코드 0 · 머리/공통↛operations 역류 0.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
