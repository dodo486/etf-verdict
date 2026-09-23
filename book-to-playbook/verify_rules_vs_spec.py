#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""체크리스트 ↔ 수집요청 대조 — 구간 ③ 의 층1. 모든 책 공통.

## 왜 있나

이 파이프라인의 변환은 세 구간이고, 구간마다 지킬 건 둘뿐이다.
**창작 없이**(원문에 없는 게 들어오지 않는다) · **누락 없이**(원문에 있는 게 빠지지 않는다).

| 구간 | 창작 검사 | 누락 검사 |
|---|---|---|
| ① 책 → 플레이북 | (없음) | `book_source.py` 가 키 수준 대조 |
| ② 플레이북 → 체크리스트 | `verify_coverage.py` 출처 4단 | `verify_coverage.py` 커버리지 전수 |
| ③ 체크리스트 → 수집요청 | **이 파일** | **이 파일** |

③칸이 비어 있어서 실제 결함이 살아남았다. 규칙은 "20일선 회복 후 2거래일 동안 다시
안 깸"인데 수집요청(data_spec)에는 `above_ma 20` 만 있는 식이다. 규칙 쪽도 원문 쪽도
각각은 검사를 통과한다 — **둘을 짝지어 보는 검사가 없었기 때문이다.**

## 무엇을 무엇과 짝짓나

입력은 **JSON 두 개뿐**이다: `books/<slug>/rules.json` 과 data_spec.
짝짓기 열쇠는 `ref`(소절 키) — 계약 2·4 가 그 열쇠를 요구하는 이유가 이것이다.
책 지식은 0이고, HTML 은 읽지 않는다(읽는 순간 첫 책 전용 검사기가 하나 더 는다).
소절 본문은 `book_source.load_sections(slug)` 로만 읽는다.

    검사 1 (누락)  규칙 ──ref──▶ spec 항목    규칙이 요구하는 정량 조건이
                                              그 ref 의 spec 항목들에 다 있는가
    검사 2 (창작)  spec 항목 ──ref──▶ 소절 본문  spec 의 정량 파라미터가
                                              그 소절 원문에 실제로 있는가

토큰 추출은 `verify_coverage.TOKEN_RE` 를 **import** 한다(복붙하면 두 검사기의
토큰 정의가 갈라진다).

## 한계 (정직하게)

층1은 **수치만** 본다. 심볼이 맞는지(`^NDX` 지수 vs `NQ=F` 선물)는 못 본다 —
심볼↔저자표현 사전은 사람이 승인해야 하는 물건이라 층2의 몫이다. 못 보는 건
'미적용'으로 **찍어서 보여준다.** 조용히 통과시키지 않는다.

## 사용

    python verify_rules_vs_spec.py           # 검사 (위반·검사불가 있으면 exit 1)
    python verify_rules_vs_spec.py --show 5-2  # 그 소절의 규칙·spec·판정 상세
"""
import io
import json
import os
import re
import sys

import paths  # noqa: F401  (경로·UTF-8 출력 고정. 반드시 먼저 import)
from paths import BASE

import book_source
from verify_coverage import TOKEN_RE, norm   # 토큰 정의는 하나뿐이어야 한다
# 면제 형식·분류도 하나뿐이어야 한다(복붙하면 두 검사기의 면제 기준이 갈라진다)
from verify_coverage import exempt_entries, exempt_help

EXEMPT = os.path.join(BASE, "coverage_exempt.json")

# 소절 키 형식(계약 1). 규칙/spec 의 ref 가 이 모양이어야 '출처'로 본다.
KEY_RE = re.compile(r"^(?:[0-9]+-[0-9]+|프롤로그|에필로그)$")

# 숫자 하나 — 3,300 · 9.7 · 20 을 값으로 끊어 읽는다.
# 부분일치("2025" 안의 "20")를 막으려고 앞뒤 숫자 경계를 본다.
NUM_RE = re.compile(r"(?<![\d.,])\d+(?:,\d{3})*(?:\.\d+)?(?![\d,]*\d)")

# 규칙 dict 에서 '규칙 문구'로 세지 않는 키.
#   ref — 짝짓기 열쇠 그 자체
#   src — 수집 소스 주석(구현 쪽 문구). 저자 문구가 아니므로 규칙 문구로 세면
#         구현이 구현을 검증하는 꼴이 된다
# 책마다 다르면 books.json 의 `verify.rule_text_skip` 으로 덮어쓴다.
RULE_TEXT_SKIP = ("ref", "src")

# 정량 파라미터 → 원문에서 어떤 단위로 나타나야 하는가.
# metric.type 카탈로그(ADAPTERS.md)의 파라미터 의미에서 온 것이지 책에서 온 게 아니다.
#   period : 기간/일수 파라미터 — 원문에 '20일선'·'2거래일' 처럼 날짜 단위로 적혀야 한다
#   (없는 키) : 단위를 모른다 → 숫자만 대조(느슨함. 오탐이 나면 사유를 적어 면제)
PERIOD_KEYS = ("ma", "n", "base", "ref", "days", "window", "period", "lookback", "bars")
PERIOD_UNITS = ("일선", "거래일", "영업일", "일")


# ---------------------------------------------------------------- 입력
def books():
    man = json.loads(io.open(os.path.join(BASE, "books.json"), encoding="utf-8").read())
    return [b for b in man.get("books", []) if b.get("slug")]


def rules_path(slug):
    return os.path.join(BASE, "books", slug, "rules.json")


def spec_path(slug):
    """계약 4 위치를 먼저 보고, 없으면 과도기 경로로 폴백."""
    for p in (os.path.join(BASE, "books", slug, "data_spec.json"),
              os.path.join(BASE, "%s_data_spec.json" % slug)):
        if os.path.exists(p):
            return p
    return None


def rel(p):
    """보기 좋은 상대경로. Windows 에서 드라이브가 다르면 relpath 가 터진다."""
    try:
        return os.path.relpath(p, BASE)
    except ValueError:
        return p


def load_json(p):
    return json.loads(io.open(p, encoding="utf-8").read())


def load_exempt():
    if not os.path.exists(EXEMPT):
        return {}
    return load_json(EXEMPT)


def exempt_of(slug, bucket):
    """coverage_exempt.json 과 **같은 방식** — 분류(kind)가 허용 목록 밖이거나
    사유(why)가 비면 면제되지 않는다. 옛 문자열 형식도 인정하지 않는다."""
    return exempt_entries((load_exempt().get(slug, {}) or {}).get(bucket))[0]


def exempt_rejected(slug):
    """이 검사기가 읽는 두 버킷에서 **인정되지 않은** 면제 목록."""
    out = []
    for bucket in ("_rules_vs_spec", "_rules_vs_spec_spec"):
        d = (load_exempt().get(slug, {}) or {}).get(bucket)
        for tok, why in exempt_entries(d)[1]:
            out.append(("%s / %s" % (bucket, tok), why))
    return out


def spec_items(spec):
    if isinstance(spec, dict):
        spec = spec.get("items", [])
    return spec if isinstance(spec, list) else []


# ---------------------------------------------------------------- 공통 추출
def numbers_of(obj):
    """구조 안의 모든 수 — 숫자 리터럴과 문자열 속 숫자 둘 다."""
    out = set()

    def walk(o):
        if isinstance(o, bool):
            return
        if isinstance(o, (int, float)):
            out.add(float(o))
        elif isinstance(o, str):
            for m in NUM_RE.finditer(o):
                try:
                    out.add(float(m.group(0).replace(",", "")))
                except ValueError:
                    pass
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    return out


def tokens_of_text(text):
    """정량 토큰 — verify_coverage 와 같은 정의."""
    out = []
    for t in TOKEN_RE.findall(text):
        t = norm(t[0] if isinstance(t, tuple) else t)
        if t and t not in out:
            out.append(t)
    return out


def token_number(tok):
    """'2거래일' → 2.0 · '-5%' → 5.0 · '7~10%' → 7.0(범위는 앞 수)."""
    m = NUM_RE.search(tok)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def fmt_num(v):
    return ("%g" % v)


# ---------------------------------------------------------------- 규칙 읽기
def walk_rules(obj, skip, path="", out=None):
    """규칙 = `ref`(문자열 소절키)를 가진 dict. 책 구조를 모른 채 전수로 훑는다."""
    if out is None:
        out = []
    if isinstance(obj, dict):
        ref = obj.get("ref")
        if isinstance(ref, str) and KEY_RE.match(ref):
            texts = [v for k, v in obj.items()
                     if isinstance(v, str) and k not in skip]
            out.append({
                "path": path or "(root)",
                "ref": ref,
                "text": " · ".join(texts),
                "source": obj.get("source"),
                "raw": obj,
            })
        for k, v in obj.items():
            walk_rules(v, skip, "%s.%s" % (path, k) if path else str(k), out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk_rules(v, skip, "%s[%d]" % (path, i), out)
    return out


# ---------------------------------------------------------------- 검사 1 — 누락
def item_content(item):
    """spec 항목에서 **내용**만 — `ref` 는 짝짓기 열쇠지 수집 조건이 아니다.

    이걸 안 빼면 소절키 '5-2' 가 숫자 5·2 로 읽혀서, 규칙의 '2거래일' 이
    출처 표기만으로 커버된 것처럼 보인다. 열쇠가 자기 자신을 증명하는 꼴이다.
    """
    return {k: v for k, v in item.items() if k != "ref"}


def covers(tok, items):
    """spec 항목들이 이 토큰을 커버하는가 — 글자 그대로 또는 수치로."""
    t = norm(tok)
    n = token_number(tok)
    for it in items:
        body = item_content(it)
        itext = norm(json.dumps(body, ensure_ascii=False))
        if t in itext:
            return True
        if n is not None and n in numbers_of(body):
            return True
    return False


def check_missing(slug, rules, items, sections):
    """규칙이 요구하는 정량 조건이 같은 ref 의 spec 항목들에 다 들어 있는가."""
    by_ref = {}
    for it in items:
        r = it.get("ref")
        if isinstance(r, str):
            by_ref.setdefault(r, []).append(it)

    ex = exempt_of(slug, "_rules_vs_spec")
    out = []
    for rule in rules:
        # 규칙이 스스로 수동이라고 밝혔다면 수집요청이 없는 게 정상이다.
        if rule.get("source") == "manual":
            continue
        ref = rule["ref"]
        if sections is not None and ref not in sections:
            out.append({"kind": "ref", "rule": rule,
                        "why": "없는 소절을 가리킴: %s" % ref})
            continue
        cand = by_ref.get(ref) or []
        if not cand:
            out.append({"kind": "nospec", "rule": rule,
                        "why": "spec 에 ref=%s 인 수집요청이 하나도 없음" % ref})
            continue
        toks = tokens_of_text(rule["text"])
        miss = [t for t in toks if not covers(t, cand)]
        miss = [t for t in miss if not ex.get("%s::%s" % (ref, t))]
        if miss:
            auto = [c for c in cand if c.get("source") != "manual"]
            out.append({"kind": "cond", "rule": rule, "miss": miss,
                        "cand": cand,
                        "why": "ref=%s spec 항목 %d개(자동 %d개)가 못 담은 조건: %s"
                               % (ref, len(cand), len(auto), ", ".join(miss))})
    return out


# ---------------------------------------------------------------- 검사 2 — 창작
def metric_params(item):
    """spec 항목의 정량 파라미터 — (키경로, 키이름, 값)."""
    out = []

    def walk(o, path):
        if isinstance(o, bool):
            return
        if isinstance(o, (int, float)):
            out.append((path, path.split(".")[-1], float(o)))
        elif isinstance(o, dict):
            for k, v in o.items():
                walk(v, "%s.%s" % (path, k) if path else k)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, "%s[%d]" % (path, i))

    walk(item.get("metric") or {}, "metric")
    return out


def in_body_with_unit(body, val, units):
    """본문에 '20일선'·'2거래일' 처럼 **단위까지 붙은 채로** 있는가."""
    nb = norm(body)
    s = fmt_num(val)
    for u in units:
        if re.search(r"(?<![\d.])%s%s" % (re.escape(s), re.escape(u)), nb):
            return u
    return None


def in_body_bare(body, val):
    """단위를 모르는 파라미터 — 숫자만 대조(느슨함)."""
    return val in numbers_of(body)


def check_invention(slug, items, sections):
    """spec 의 정량 파라미터가 그 ref 소절 원문에 실제로 있는가."""
    ex = exempt_of(slug, "_rules_vs_spec_spec")
    out = []
    for it in items:
        ref = it.get("ref")
        if not isinstance(ref, str):
            continue                       # 계약 4 미충족은 verify_contract 의 일
        if it.get("source") == "manual":
            continue                       # 수동 항목엔 자동 판정 수치가 없다
        body = sections.get(ref)
        if body is None:
            out.append({"kind": "ref", "item": it,
                        "why": "없는 소절을 가리킴: %s" % ref})
            continue
        for path, key, val in metric_params(it):
            k = "%s::%s=%s" % (it.get("item", "?"), path, fmt_num(val))
            if ex.get(k):
                continue
            if key in PERIOD_KEYS:
                if in_body_with_unit(body, val, PERIOD_UNITS):
                    continue
                why = ("%s=%s — %s 본문에 '%s일'·'%s거래일'·'%s일선' 어디에도 없음"
                       % (path, fmt_num(val), ref, fmt_num(val), fmt_num(val), fmt_num(val)))
            else:
                if in_body_bare(body, val):
                    continue
                why = ("%s=%s — %s 본문에 그 수치가 없음(단위 미상이라 숫자만 대조)"
                       % (path, fmt_num(val), ref))
            out.append({"kind": "param", "item": it, "param": path,
                        "val": val, "why": why})
    return out


# ---------------------------------------------------------------- 미적용 검사
def unapplied(book):
    """층1이 **못 보는** 것을 이름 붙여 남긴다. 못 본 건 통과가 아니다."""
    cfg = (book.get("verify") or {})
    out = []
    if not cfg.get("attribution_axis"):
        out.append(("오귀속 축(종목↔장 매핑)",
                    "books.json 의 verify.attribution_axis 없음 — spec 항목이 "
                    "남의 장 소절을 출처로 삼았는지 못 본다"))
    if not cfg.get("symbol_lexicon"):
        out.append(("심볼 대조(저자 표현 ↔ 수집 심볼)",
                    "books.json 의 verify.symbol_lexicon 없음 — '선물'이라 쓴 소절에 "
                    "지수 심볼을 붙였는지 못 본다(층2: 사람 승인 사전)"))
    return out


# ---------------------------------------------------------------- 출력
def show_ref(slug, ref, rules, items, sections):
    print("[%s] %s" % (slug, ref))
    body = (sections or {}).get(ref)
    print("  소절 본문      : %s" % ("%d자" % len(body) if body is not None else "(없음)"))
    if body is not None:
        print("  본문 정량 토큰 : %s" % (", ".join(tokens_of_text(body)) or "(없음)"))
    rs = [r for r in rules if r["ref"] == ref]
    print("  규칙 %d개" % len(rs))
    for r in rs:
        print("    - %s  [%s]" % (r["text"][:70], r["path"]))
        print("      토큰: %s" % (", ".join(tokens_of_text(r["text"])) or "(없음)"))
    its = [i for i in items if i.get("ref") == ref]
    print("  spec 항목 %d개" % len(its))
    for i in its:
        print("    - %s  source=%s" % (i.get("item"), i.get("source")))
        print("      파라미터: %s" % (", ".join(
            "%s=%s" % (p, fmt_num(v)) for p, _k, v in metric_params(i)) or "(없음)"))


def main(argv):
    show = None
    if "--show" in argv:
        i = argv.index("--show")
        show = argv[i + 1] if i + 1 < len(argv) else None

    bad = 0            # 위반
    blocked = 0        # 검사 불가 — '통과'가 아니다
    skipped_checks = []

    for book in books():
        slug = book["slug"]
        rp, sp = rules_path(slug), spec_path(slug)

        # ---- 입력이 있는가. 없으면 '검사 불가'로 **찍는다**(조용한 스킵 금지)
        why = []
        if not os.path.exists(rp):
            why.append("rules.json 없음(계약2 미충족)")
        if sp is None:
            why.append("data_spec 없음(계약4 미충족)")
        if why:
            print("· %-8s 검사 불가 — %s" % (slug, " · ".join(why)))
            blocked += 1
            continue

        rules_doc = load_json(rp)
        skip = tuple((book.get("verify") or {}).get("rule_text_skip") or RULE_TEXT_SKIP)
        rules = walk_rules(rules_doc, skip)
        items = spec_items(load_json(sp))

        try:
            sections = book_source.load_sections(slug)
        except Exception as e:                       # 원문이 손에 없는 경우
            sections = None
            print("· %-8s 원문 본문 없음(%s) — 검사2(창작)는 돌 수 없음"
                  % (slug, type(e).__name__))

        if show:
            if sections is None:
                print("본문이 없어 상세를 보여줄 수 없습니다.")
                return 2
            show_ref(slug, show, rules, items, sections)
            continue

        print("%s — 규칙 %d개(ref 있는 것만, %s) · spec 항목 %d개(%s)"
              % (slug, len(rules), rel(rp), len(items), rel(sp)))

        # ---- 면제부터 검사한다 — 인정되지 않는 면제는 위반으로 센다
        rej = exempt_rejected(slug)
        if rej:
            print("  [면제] 인정되지 않는 면제 %d건" % len(rej))
            for where, why in rej:
                print("    ✗ %-52s %s" % (where[:52], why))
            print(exempt_help())
        bad += len(rej)

        # ---- 빈 입력으로 '이상 없음'을 내지 않는다
        if not rules or not items:
            print("  ✗ 입력이 비었습니다(규칙 %d · spec %d) — 이 검사는 돌지 않았습니다."
                  % (len(rules), len(items)))
            blocked += 1
            continue

        # ---- 검사 1 — 누락
        miss = check_missing(slug, rules, items, sections)
        print("  [검사1 누락] 규칙 %d개 중 문제 %d개" % (len(rules), len(miss)))
        for m in miss:
            mark = "✗" if m["kind"] == "ref" else "⚠"
            print("    %s %-58s %s" % (mark, m["rule"]["text"][:58], m["why"]))
            print("      └ 규칙 위치: %s" % m["rule"]["path"])
        bad += len(miss)

        # ---- 검사 2 — 창작
        if sections is None:
            skipped_checks.append((slug, "검사2 창작", "원문 본문 없음"))
        else:
            inv = check_invention(slug, items, sections)
            auton = len([i for i in items if i.get("source") != "manual"])
            print("  [검사2 창작] 자동 spec %d개 중 원문에 없는 수치 %d개"
                  % (auton, len(inv)))
            for x in inv:
                print("    ⚠ %-40s %s" % ((x["item"].get("item") or "?")[:40], x["why"]))
            bad += len(inv)

        # ---- 못 보는 것 — 통과로 찍지 않는다
        for name, reason in unapplied(book):
            print("  [미적용]    %s — %s" % (name, reason))
            skipped_checks.append((slug, name, reason))

    if show:
        return 0

    print("\n" + "=" * 74)
    print("위반 %d건 · 검사 불가 %d권 · 미적용 검사 %d건"
          % (bad, blocked, len(skipped_checks)))
    for slug, name, reason in skipped_checks:
        print("  · %-8s %s — %s" % (slug, name, reason))
    if bad:
        print("-" * 74)
        print("처리 방법은 셋뿐이다.")
        print("  ① 수집요청을 규칙에 맞춘다(데이터를 구할 수 있으면 구한다)")
        print("  ② 못 구하면 source:\"manual\" + reason 으로 **미구현이라고 적는다**")
        print("  ③ 규칙이 아닌 숫자라면 coverage_exempt.json 의 "
              "`_rules_vs_spec` / `_rules_vs_spec_spec` 에 "
              "**분류(kind)와 사유(why)를 적어** 면제한다")
        print(exempt_help())
        print("규칙 문구(저자 문구)를 spec 에 맞춰 고치는 건 선택지가 아니다.")
    if blocked:
        print("-" * 74)
        print("'검사 불가'는 통과가 아니다. 계약 2·4 를 채우기 전까지 이 책은 "
              "검증되지 않은 상태다.")
    print("=" * 74)
    return 1 if (bad or blocked) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
