#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""규칙 파일(books/<slug>/rules.json) 읽기 — 파이프라인 전체의 단일 기준.

rules.json 은 구간②(체크리스트 조립)의 산출물이자 구간③(판정)·검사기들의 입력이다.
경로 규칙과 중첩 순회가 파일마다 제각각이면 "같은 규칙"을 서로 다르게 읽는다.
그래서 읽기는 여기 하나로 모은다. (쓰는 쪽은 없다 — 규칙을 만드는 건 책 추출 작업이다.)
"""
import io
import json
import os

from shared.paths import BASE


def rules_path(slug):
    return os.path.join(BASE, "books", slug, "rules.json")


def load_rules(slug):
    """`books/<slug>/rules.json` 구조 그대로. 없으면 None."""
    if not slug:
        return None
    p = rules_path(slug)
    if not os.path.exists(p):
        return None
    return json.loads(io.open(p, encoding="utf-8").read())


def iter_rules(obj):
    """중첩 어디에 있든 규칙을 훑는다. 규칙 = 라벨(`t`)을 가진 dict.

    rules.json 이 `{DATA:{종목:{filter:[...],entry:[...]}}, MODES, SCSRC, STEPNAME}`
    처럼 중첩돼 있는데 플랫 배열을 기대하면 **"규칙이 비어 있음"으로 오진**한다.
    없는 것과 못 읽은 것은 다르다 — 못 읽은 것을 없다고 적는 순간 검사는 거짓이 된다.

    반대 방향(파일에 플랫 사본을 하나 더 두기)은 **안 된다.** 같은 규칙의 사본이
    둘이면 반드시 드리프트한다. 데이터는 그대로 두고 검사기가 중첩을 훑는다.
    """
    if isinstance(obj, dict):
        if isinstance(obj.get("t"), str):
            yield obj
            return                      # 규칙 안쪽은 더 파고들지 않는다
        for v in obj.values():
            for r in iter_rules(v):
                yield r
    elif isinstance(obj, list):
        for v in obj:
            for r in iter_rules(v):
                yield r
