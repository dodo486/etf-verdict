#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""책 계약 검사 — 검사기가 책에 맞추는 게 아니라, 책이 계약에 맞춘다. 모든 책 공통.

## 왜 있나

검사기(`verify_coverage.py` 등)가 첫 책(etf)의 생김새에 맞춰져 있었다. 두 번째 책
(supply)은 coverage-data 블록도 rules JSON도 없으니 검사기가 "검사 대상 아님"으로
**통째로 건너뛰었다.** 책이 둘로 늘어난 순간 검증층의 실효가 0이 된 것이다.
침묵으로 통과시키는 게 가장 비싼 실패다.

그래서 방향을 뒤집는다. 검사기를 책마다 고치는 대신 **책이 갖춰야 할 최소 형식**을
계약으로 못박고, 계약을 못 채우는 책은 검사를 건너뛰는 게 아니라 **등록이 안 된다.**

## 무엇을 보나 (책 계약 4조)

| 조항 | 내용 |
|---|---|
| 계약 1 | 원문이 소절 단위로 잘려 있고 소절마다 고유 키가 있다 (`N-n` · `프롤로그` · `에필로그`) |
| 계약 2 | 규칙이 JSON 파일로 있고 규칙마다 `ref`(소절 키)가 있다 |
| 계약 3 | 커버리지 맵이 소절 **전수**를 분류한다 (reflected / gap / mindset) |
| 계약 4 | `data_spec` 항목마다 `ref` 가 있다 — 규칙과 수집요청을 짝지을 유일한 열쇠 |

계약 2의 HTML 안 JS 리터럴(`const DATA = [...]`)은 **계약 위반**이다. 파서가 책마다
달라지는 원인이 거기 있다. 규칙은 파일로 나와야 한다.

## 한계 (정직하게)

형식만 본다. `ref` 가 **맞는** 출처인지, 커버리지 주장이 **사실**인지는 여기서 안 본다
— 그건 `verify_coverage.py` 의 일이다. 이 검사는 그 검사가 **돌 수 있는 상태인지**만
확인한다. 통과했다고 책이 옳다는 뜻이 아니다. 반대로 **여기서 막히면 뒤의 검사는
전부 무의미**하다(검사 대상이 아니라고 조용히 넘어가기 때문에).

지금 시점에는 실패가 정상이다. 계약을 채우는 건 책 쪽 작업이지 이 스크립트 쪽이
아니다. **통과시키려고 검사를 느슨하게 만들지 말 것.**

## 사용

    python verify_contract.py        # 검사 (미충족 있으면 exit 1)
"""
import io
import json
import os
import re
import sys
import unicodedata

import paths
from paths import BASE, PUBLIC

KEY_RE = re.compile(r"^(?:[0-9]+-[0-9]+|프롤로그|에필로그)$")
HEAD_RE = re.compile(r"^#{2,3}\s*([0-9]+-[0-9]+|프롤로그|에필로그)[.\s]", re.M)
STATUS = {"reflected", "gap", "mindset"}
CONTRACTS = ["계약1 소절키", "계약2 규칙ref", "계약3 커버리지", "계약4 spec ref"]


def pad(s, w):
    """한글·이모지는 터미널에서 두 칸을 먹는다. %-14s 로는 표가 어긋난다."""
    n = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)
    return s + " " * max(0, w - n)


def load_json(p):
    return json.loads(io.open(p, encoding="utf-8").read())


def book_html(slug):
    """배포본(PUBLIC/<slug>/index.html) 우선, 없으면 작업본."""
    for c in (os.path.join(PUBLIC, slug, "index.html"),
              os.path.join(BASE, "%s-playbook.html" % slug)):
        if os.path.exists(c):
            return c
    return None


def src_keys(html):
    """#src 마크다운에서 소절 키를 뽑는다(과도기 — 계약1이 서면 source_index.json 이 기준)."""
    m = re.search(r'<script type="text/markdown" id="src">(.*?)</script>', html, re.S)
    return HEAD_RE.findall(m.group(1)) if m else []


def c1(slug):
    p = os.path.join(BASE, "books", slug, "source_index.json")
    if not os.path.exists(p):
        return False, "books/%s/source_index.json 없음" % slug
    d = load_json(p)
    keys = list(d.get("sections", d) if isinstance(d, dict) else d)
    bad = [k for k in keys if not KEY_RE.match(str(k))]
    if not keys:
        return False, "소절 키가 비어 있음"
    if bad:
        return False, "키 형식 위반 %d개: %s" % (len(bad), ", ".join(map(str, bad[:5])))
    return True, "소절 %d개" % len(keys)


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


def c2(slug):
    p = os.path.join(BASE, "books", slug, "rules.json")
    if not os.path.exists(p):
        return False, "books/%s/rules.json 없음 (HTML 안 JS 리터럴은 계약 위반)" % slug
    d = load_json(p)
    rules = list(iter_rules(d))
    miss = [r for r in rules if not r.get("ref")]
    if not rules:
        return False, "규칙을 한 개도 못 읽음 (라벨 t 를 가진 항목이 없음)"
    if miss:
        return False, "규칙 %d개 중 ref 없음 %d개" % (len(rules), len(miss))
    return True, "규칙 %d개 전부 ref 있음" % len(rules)


def c3(html_path):
    if not html_path:
        return False, "책 HTML 을 못 찾음"
    html = io.open(html_path, encoding="utf-8").read()
    m = re.search(r'<script type="application/json" id="coverage-data">\s*(\{.*?\})\s*</script>',
                  html, re.S)
    if not m:
        return False, "coverage-data 블록 없음"
    cov = json.loads(m.group(1)).get("map", {})
    keys = src_keys(html)
    if not keys:
        return False, "원문(#src)에서 소절을 못 찾음"
    unclassified = [k for k in keys if k not in cov]
    badstat = sorted({v.get("status") for v in cov.values()} - STATUS)
    if unclassified:
        return False, "소절 %d개 중 미분류 %d개: %s" % (
            len(keys), len(unclassified), ", ".join(unclassified[:5]))
    if badstat:
        return False, "알 수 없는 status: %s" % ", ".join(map(str, badstat))
    extra = [k for k in cov if k not in keys]
    note = "소절 %d개 전수 분류" % len(keys)
    if extra:
        note += " (맵에만 있는 키 %d개: %s)" % (len(extra), ", ".join(extra[:5]))
    return True, note



# ---------------------------------------------------------------- 규칙 누출 검사
# 계약 2 보충 — "규칙은 JSON 파일로 존재한다"를 "JSON 파일 **안에만** 존재한다"로
# 좁힌다. 41번째 규칙 사고(2026-09-23, etf e_vol): 렌더링 코드 안에 규칙 리터럴이
# `{t:'...'}` 로 직접 박혀 있으면 c2()의 rules.json 검사는 그 존재를 전혀 모른다
# — 계약2를 충족한 책도 그 안 어딘가에 파일로 안 나온 규칙을 여전히 숨길 수 있다.
#
# id="rules" 블록(파일의 사본, inject_rules.py 가 주입) · #src 마크다운(저자 본문,
# 규칙 근거표 등에 "책의 표현"이 그대로 인용됨) · coverage-data 블록(커버리지 노트)은
# 규칙 리터럴이 보여도 유출이 아니다 — 그 세 곳을 지운 사본에서만 찾는다.
LEAK_EXCLUDE_RE = [
    re.compile(r'<script type="application/json" id="rules">.*?</script>', re.S),
    re.compile(r'<script type="text/markdown" id="src">.*?</script>', re.S),
    re.compile(r'<script type="application/json" id="coverage-data">.*?</script>', re.S),
]
# 규칙 리터럴 = 라벨 키 `t` 를 가진 객체. JS 한따옴표(`t:'...'`)와 JSON 겹따옴표
# (`"t": "..."`) 둘 다 잡는다. 앞에 word/quote 문자가 오면(`amount:`, `cnt:` 등)
# `t` 로 끝나는 다른 키와 헷갈리므로 그 경계를 앞에서 막는다.
RULE_LIT_RE = re.compile(
    r"(?:(?<![\w'\"])t\s*:\s*'((?:\\.|[^'\\])*)'"
    r"|\"t\"\s*:\s*\"((?:\\.|[^\"\\])*)\")"
)


def _blank(m):
    """블록 내용을 공백으로 지우되 줄바꿈은 남긴다 — 이후 찾는 줄 번호가 밀리지 않게."""
    return re.sub(r"[^\n]", " ", m.group(0))


def leak_scan_text(slug):
    """유출 탐지용 사본 — id=rules·#src·coverage-data 를 지운 책 HTML 전체."""
    hp = book_html(slug)
    if not hp:
        return None
    html = io.open(hp, encoding="utf-8").read()
    for pat in LEAK_EXCLUDE_RE:
        html = pat.sub(_blank, html)
    return html


def rule_leaks(slug):
    """[(줄번호, 문구)] — 위 세 블록 밖에서 발견된 규칙 리터럴 전부."""
    text = leak_scan_text(slug)
    if text is None:
        return None
    out = []
    for m in RULE_LIT_RE.finditer(text):
        t = m.group(1) if m.group(1) is not None else m.group(2)
        line = text.count("\n", 0, m.start()) + 1
        out.append((line, t))
    return out


def c_leak(slug):
    """(status, note, hits). status: True=유출 없음 · False=유출 있음 ·
    None=이 책은 아직 규칙 분리 전이라 검사 대상이 아님(통과로 찍지 않는다)."""
    if not os.path.exists(os.path.join(BASE, "books", slug, "rules.json")):
        return None, "규칙 분리 전(rules.json 없음) — 미적용(통과 아님)", []
    hits = rule_leaks(slug)
    if hits is None:
        return False, "책 HTML 을 못 찾음", []
    if hits:
        return False, "%d건 — id=\"rules\" JSON 밖에서 규칙 리터럴 발견" % len(hits), hits
    return True, "유출 0건 — 규칙 리터럴이 전부 id=\"rules\" JSON 안에만 있음", []


def c4(slug):
    cands = [os.path.join(BASE, "books", slug, "data_spec.json"),
             os.path.join(BASE, "%s_data_spec.json" % slug)]   # 과도기 경로
    p = next((c for c in cands if os.path.exists(c)), None)
    if not p:
        return False, "data_spec.json 없음 (books/%s/ · %s_data_spec.json 둘 다)" % (slug, slug)
    d = load_json(p)
    items = d.get("items", []) if isinstance(d, dict) else d
    miss = [i for i in items if not (isinstance(i, dict) and i.get("ref"))]
    if not items:
        return False, "%s: 항목이 비어 있음" % os.path.basename(p)
    if miss:
        return False, "%s: %d항목 중 ref 없음 %d개" % (os.path.basename(p), len(items), len(miss))
    return True, "%s: %d항목 전부 ref 있음" % (os.path.basename(p), len(items))


def main(argv):
    books = load_json(os.path.join(BASE, "books.json")).get("books", [])
    rows, bad = [], 0
    for b in books:
        slug = b["slug"]
        hp = book_html(slug)
        res = [c1(slug), c2(slug), c3(hp), c4(slug)]
        rows.append((slug, res))
        bad += sum(1 for ok, _ in res if not ok)

    print("책 계약 검사 — 계약을 못 채우는 책은 검사를 건너뛰는 게 아니라 등록이 안 된다.\n")
    print("%-8s %s" % ("책", "  ".join(pad(c, 16) for c in CONTRACTS)))
    print("-" * 78)
    for slug, res in rows:
        print("%-8s %s" % (slug, "  ".join(pad("✅ 충족" if ok else "❌ 미충족", 16)
                                           for ok, _ in res)))
    for slug, res in rows:
        miss = [(CONTRACTS[i], d) for i, (ok, d) in enumerate(res) if not ok]
        if miss:
            print("\n%s — 미충족 %d조" % (slug, len(miss)))
            for name, why in miss:
                print("  ❌ %s %s" % (pad(name, 14), why))

    # ---- 규칙 누출 검사(계약2 보충) — "JSON에 있다"가 아니라 "JSON 밖에 없다"를 본다.
    print("\n" + "-" * 78)
    print("규칙 누출 검사(계약2 보충) — id=\"rules\" JSON 밖에 규칙 리터럴(`{t:'...'}`)이 "
          "있으면 실패.")
    leakbad = 0
    for b in books:
        slug = b["slug"]
        ok, note, hits = c_leak(slug)
        mark = "✅ 없음  " if ok else ("❌ 유출  " if ok is False else "· 미적용 ")
        print("  %-8s %s %s" % (slug, mark, note))
        for line, t in hits[:20]:
            print("      %5d행  %s" % (line, t[:80]))
        if len(hits) > 20:
            print("      … 외 %d건 더" % (len(hits) - 20))
        if ok is False:
            leakbad += 1
    bad += leakbad

    if bad:
        print("\n" + "=" * 70)
        if bad - leakbad:
            print("계약 미충족 %d건. 책을 계약에 맞춰라 — 검사를 느슨하게 만들지 말 것."
                  % (bad - leakbad))
            print("  계약1: books/<slug>/source_index.json 에 소절 키")
            print("  계약2: books/<slug>/rules.json — 규칙마다 ref (HTML 안 JS 리터럴은 위반)")
            print("  계약3: coverage-data 가 소절 전수를 reflected/gap/mindset 으로 분류")
            print("  계약4: data_spec 항목마다 ref")
        if leakbad:
            print("규칙 누출 %d건. 위에 찍힌 문구를 books/<slug>/rules.json 으로 옮기고 "
                  "렌더 코드는 그 JSON을 읽게 고쳐라." % leakbad)
        print("=" * 70)
        return 1

    print("\n전부 통과 — 모든 책이 계약 4조를 충족하고, 규칙 누출도 없다.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
