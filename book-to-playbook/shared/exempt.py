#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""면제(coverage_exempt.json) 읽기·검증 — 파이프라인 전체의 단일 기준.

면제는 **검사를 끄는 스위치**다. 사유를 받는 것만으로는 부족했다 — 사유가
타당한지를 아무도 안 봤고, 실제로 "저자 조건과 구현이 다르다"가 면제로 덮여
있었다(3-1·4-1·7-1·7-5. 전부 저자의 시간 조건이 수익률 등으로 대체된 모양).
그래서 사유에 **분류를 강제한다.** 분류는 아래 다섯뿐이고 '구현이 다름'은
없다 — 그건 면제가 아니라 gap 이거나 구현 대상이다.

원래 verify_coverage.py(구간②)에 있었지만 구간①(창작검사)·계약검사도 같은 판정을
빌려 쓴다 — 면제 기준이 둘이면 검사기마다 갈라진다. 그래서 공통층으로 나왔다.
"""
import io
import json
import os

from shared.paths import BASE

EXEMPT = os.path.join(BASE, "coverage_exempt.json")

EXEMPT_KINDS = {
    "설명": "규칙이 아니라 설명·심리 경고 문장에 나온 숫자",
    "예시": "저자가 든 사례 수치(임계값 아님)",
    "표기차이": "같은 값의 다른 표기(10거래일↔10일, %p↔%포인트)",
    "단위": "소요시간·항목 개수 등 판정 임계값이 아닌 수치",
    "UI": "매매 규칙이 아닌 화면 코드",
}

EXEMPT_FORM = '"<토큰>": {"kind": "<분류>", "why": "<사유>"}'


def load_exempt():
    if os.path.exists(EXEMPT):
        return json.loads(io.open(EXEMPT, encoding="utf-8").read())
    return {}


def exempt_help():
    """면제가 거부됐을 때 보여줄 안내문."""
    lines = ["  면제 형식: %s" % EXEMPT_FORM, "  허용 분류는 다섯뿐입니다."]
    lines += ["    · %-4s %s" % (k, v) for k, v in EXEMPT_KINDS.items()]
    lines.append("  '구현이 다름'은 허용 분류가 **아닙니다** — 저자 조건과 구현이 다르면")
    lines.append("  면제가 아니라 status 를 gap 으로 내리거나 구현할 것.")
    return "\n".join(lines)


def exempt_entries(bucket):
    """{토큰: {kind, why}} 에서 **유효한 면제만** 추린다. (유효, 거부목록) 반환.

    옛 문자열 형식({토큰: "사유"})은 분류가 없으므로 면제로 인정하지 않는다.
    """
    valid, bad = {}, []
    for tok, v in (bucket or {}).items():
        if isinstance(v, str):
            bad.append((tok, "옛 문자열 형식(분류 없음) — %s 로 바꿀 것" % EXEMPT_FORM))
            continue
        if not isinstance(v, dict):
            bad.append((tok, "형식이 잘못됨 — %s 이어야 함" % EXEMPT_FORM))
            continue
        kind = v.get("kind")
        kind = kind.strip() if isinstance(kind, str) else ""
        why = v.get("why")
        why = why.strip() if isinstance(why, str) else ""
        if not kind:
            bad.append((tok, "kind 없음"))
        elif kind not in EXEMPT_KINDS:
            bad.append((tok, "허용 분류가 아님: '%s'" % kind))
        elif not why:
            bad.append((tok, "why 가 비어 있음(분류 '%s')" % kind))
        else:
            valid[tok] = v
    return valid, bad
