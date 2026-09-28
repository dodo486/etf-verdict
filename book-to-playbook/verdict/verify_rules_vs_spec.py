#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""체크리스트 ↔ 수집요청 대조 — 구간 ③ 의 층1+층2. 모든 책 공통.

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
    검사 3 (심볼)  사전 표현 ──▶ spec 심볼      사전에 등록된 표현↔심볼 승인이
                                              spec 의 실제 심볼과 일치하는가
    검사 4 (방향)  규칙 라벨 방향어 ↔ metric.op  라벨의 방향 어휘와 op 선언이
                                              서로 모순되지 않는가(rules.json 자기모순)

토큰 추출은 `shared.tokens.TOKEN_RE` 를 **import** 한다(복붙하면 두 검사기의
토큰 정의가 갈라진다).

## 한계 (정직하게)

층1은 **수치만** 본다.
층2(검사3)는 사전(verify.symbol_lexicon)이 있을 때만 돈다. 사전 자체(표현→심볼 선택)가
옳은지는 사람 승인의 몫이고, 검사는 사전↔spec 의 일관성과 사전의 원문 인용 형식만
강제한다. 표현이 항목명에 안 나오면 3c 는 못 짝짓고 3b 만 적용된다.
검사4는 어휘 사전 기반이라 방향어가 없는 라벨은 못 보고, 문맥 의존적 표현은 오탐이
날 수 있다(오탐은 면제(`_rules_vs_spec_direction`)로 처리, 어휘를 임의로 빼지 않는다).

## 사용

    python -m verdict.verify_rules_vs_spec           # 검사 (위반·검사불가 있으면 exit 1)
    python -m verdict.verify_rules_vs_spec --show 5-2  # 그 소절의 규칙·spec·판정 상세
"""
import io
import json
import os
import re
import sys

from shared import paths  # noqa: F401  (경로·UTF-8 출력 고정. 반드시 먼저 import)
from shared.paths import BASE

from shared.tokens import TOKEN_RE, norm   # 토큰 정의는 하나뿐이어야 한다
# 면제 형식·분류도 하나뿐이어야 한다(복붙하면 두 검사기의 면제 기준이 갈라진다)
from shared.exempt import EXEMPT, exempt_entries, exempt_help  # noqa: F401

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

# ---------------------------------------------------------------- 검사 4 — 방향 어휘
# 상방(UP): '위'는 '위험' 안의 '위'를 제외하기 위해 부정 전방탐색을 씀.
DIR_UP_RE = re.compile(r"위(?!험)|이상|돌파|상회|회복|↑")
DIR_DOWN_RE = re.compile(r"아래|밑|이하|미만|하회|이탈|깨|깸|↓")
# 하방어 앞 3자 이내의 부정(안/않) → 하방어를 상방으로 반전
DIR_NEG_RE = re.compile(r"[안않]")
# op → 방향 매핑
DIR_OP_UP = frozenset(("above", ">", ">="))
DIR_OP_DOWN = frozenset(("below", "<", "<="))


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
    """이 검사기가 읽는 네 버킷에서 **인정되지 않은** 면제 목록."""
    out = []
    for bucket in ("_rules_vs_spec", "_rules_vs_spec_spec",
                   "_rules_vs_spec_symbols", "_rules_vs_spec_direction"):
        d = (load_exempt().get(slug, {}) or {}).get(bucket)
        for tok, why in exempt_entries(d)[1]:
            out.append(("%s / %s" % (bucket, tok), why))
    return out


def spec_items(spec):
    if isinstance(spec, dict):
        spec = spec.get("items", [])
    return spec if isinstance(spec, list) else []


def sheet_sections(rules):
    """시트(rules.json) 규칙 라벨을 ref별로 묶는다 — ③ 검사2(창작)의 대조 대상.

    구간③의 바로 앞 구간은 시트다. spec 의 수치가 지어낸 것인지 볼 때
    원문 본문으로 직행하지 않고, 그 수치를 요구한 시트 규칙(같은 ref)에 있는지 본다.
    ①②가 통과했다면 시트 수치는 이미 원문까지 전이 보장되므로 원문 본문이 필요 없다.
    """
    secs = {}
    for r in rules:
        ref = r.get("ref")
        if isinstance(ref, str):
            secs.setdefault(ref, []).append(r.get("text", ""))
    return {k: " · ".join(v) for k, v in secs.items()}


def source_keys(slug):
    """계약1 소절 키 집합(커밋된 source_index.json) — 원문 '본문' 없이도 소절 존재를 판정.

    ref 가 실존 소절을 가리키는지 확인하는 데엔 키만 있으면 된다. 저작권 본문은 필요 없다.
    """
    p = os.path.join(BASE, "books", slug, "source_index.json")
    try:
        secs = (load_json(p).get("sections") or {})
        return set(secs.keys()) if isinstance(secs, dict) else None
    except Exception:
        return None


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


def check_invention(slug, items, sheet_secs, valid_keys):
    """spec 의 정량 파라미터가 그 ref 를 요구한 **시트 규칙**에 실제로 있는가.

    구간③의 바로 앞 구간은 시트다. 원문 본문으로 직행하지 않는다 —
    ①②가 통과했다면 시트 수치는 원문까지 전이 보장되므로, spec 이 시트에 없는
    수치를 넣었다면 그건 ③ 단계에서 지어낸 것이다.
    """
    ex = exempt_of(slug, "_rules_vs_spec_spec")
    out = []
    for it in items:
        ref = it.get("ref")
        if not isinstance(ref, str):
            continue                       # 계약 4 미충족은 verify_contract 의 일
        if it.get("source") == "manual":
            continue                       # 수동 항목엔 자동 판정 수치가 없다
        if valid_keys is not None and ref not in valid_keys:
            out.append({"kind": "ref", "item": it,
                        "why": "없는 소절을 가리킴: %s" % ref})
            continue
        body = sheet_secs.get(ref, "")     # 그 ref 를 쓴 시트 규칙 라벨 묶음
        for path, key, val in metric_params(it):
            k = "%s::%s=%s" % (it.get("item", "?"), path, fmt_num(val))
            if ex.get(k):
                continue
            if key in PERIOD_KEYS:
                if in_body_with_unit(body, val, PERIOD_UNITS):
                    continue
                why = ("%s=%s — %s 시트 규칙에 '%s일'·'%s거래일'·'%s일선' 어디에도 없음(③에서 지어냄)"
                       % (path, fmt_num(val), ref, fmt_num(val), fmt_num(val), fmt_num(val)))
            else:
                if in_body_bare(body, val):
                    continue
                why = ("%s=%s — %s 시트 규칙에 그 수치가 없음(③에서 지어냄, 단위 미상이라 숫자만 대조)"
                       % (path, fmt_num(val), ref))
            out.append({"kind": "param", "item": it, "param": path,
                        "val": val, "why": why})
    return out


# ---------------------------------------------------------------- 검사 3 — 심볼(층2)

# reason 이 소절 키 인용으로 시작하는 형식: "1-1: ..." · "프롤로그: ..." · "에필로그: ..."
REASON_KEY_RE = re.compile(r"^\s*([0-9]+-[0-9]+|프롤로그|에필로그)\s*:")


def item_symbols(item):
    """spec 항목의 수집 심볼 — metric.symbol(문자열) 과 metric.symbols(목록) 둘 다."""
    m = item.get("metric") or {}
    out = []
    s = m.get("symbol")
    if isinstance(s, str) and s:
        out.append(s)
    sl = m.get("symbols")
    if isinstance(sl, list):
        for x in sl:
            if isinstance(x, str) and x and x not in out:
                out.append(x)
    return out


def phrase_matches(text, lex):
    """텍스트에 등장하는 사전 표현 집합(최장일치 — 포함관계인 짧은 매치 제거).

    "S&P500 선물 방향"에서 "S&P500 선물"이 잡히면 그 안의 "S&P500"은 버린다.
    단 서로 다른 위치에 있으면 둘 다 유지한다.
    """
    # (start, end, 표현) 전체 수집
    hits = []
    for phrase in lex:
        pat = re.compile(re.escape(phrase))
        for m in pat.finditer(text):
            hits.append((m.start(), m.end(), phrase))
    # 어떤 hit 이 다른 hit 의 범위 안에 완전히 포함되면 제거(진부분집합 범위)
    kept = []
    for i, (s1, e1, p1) in enumerate(hits):
        dominated = False
        for j, (s2, e2, p2) in enumerate(hits):
            if i == j:
                continue
            if s2 <= s1 and e1 <= e2 and (s2, e2) != (s1, e1):
                dominated = True
                break
        if not dominated:
            kept.append(p1)
    return set(kept)


def check_symbols(slug, items, lex, valid_keys):
    """검사3 — 심볼 대조(층2). 위반 dict 리스트 반환.

    3a: 사전 항목 형식 검사(symbols 비어있지 않음 · reason 소절 키 인용 · 키 실존).
    3b: 사전 미등록 심볼(사전 전체의 승인 심볼에 없는 spec 심볼).
    3c: 표현↔심볼 대조(항목명에 나타난 표현의 승인 심볼 집합에 항목 심볼이 없음).
    """
    ex = exempt_of(slug, "_rules_vs_spec_symbols")
    out = []

    # ---- 3a 사전 근거 검사
    for phrase, entry in lex.items():
        tok = "lexicon::%s" % phrase
        if ex.get(tok):
            continue
        if not isinstance(entry, dict):
            out.append({"kind": "lex_fmt", "phrase": phrase,
                        "why": "사전 항목이 dict 가 아님 — {symbols:[...], reason:\"...\"} 이어야 함"})
            continue
        syms = entry.get("symbols")
        if not isinstance(syms, list) or not any(isinstance(s, str) and s for s in syms):
            out.append({"kind": "lex_sym", "phrase": phrase,
                        "why": "symbols 가 비어있거나 문자열 목록이 아님 — 승인 심볼이 없는 사전 항목"})
            continue
        reason = entry.get("reason")
        if not isinstance(reason, str) or not REASON_KEY_RE.match(reason):
            out.append({"kind": "lex_reason", "phrase": phrase,
                        "why": ("reason 이 소절 키 인용('N-n: …')으로 시작하지 않음 — "
                                "근거 없는 사전 항목 (현재: %r)" % (reason or ""))})
            continue
        # reason 에서 인용된 소절 키가 실존하는지
        if valid_keys is not None:
            m = REASON_KEY_RE.match(reason)
            cited = m.group(1) if m else None
            if cited and cited not in valid_keys:
                out.append({"kind": "lex_key", "phrase": phrase,
                            "why": "reason 인용 소절 키 '%s' 가 source_index 에 없음" % cited})

    # ---- 사전 전체의 승인 심볼 합집합
    approved = set()
    for entry in lex.values():
        if isinstance(entry, dict):
            for s in (entry.get("symbols") or []):
                if isinstance(s, str) and s:
                    approved.add(s)

    # ---- 3b 미등록 심볼 + 3c 표현↔심볼 대조
    unknown_reported = set()   # 3b 에서 보고한 심볼은 3c 에서 중복 보고 안 함
    for it in items:
        if it.get("source") == "manual":
            continue
        syms = item_symbols(it)
        name = it.get("item") or "?"

        # 3b
        for s in syms:
            tok = "symbol::%s" % s
            if ex.get(tok):
                continue
            if s not in approved:
                out.append({"kind": "sym_unknown", "item": it,
                            "why": "사전에 없는 심볼 %s — 저자 표현↔심볼 승인 없이 수집 중" % s})
                unknown_reported.add(s)

        # 3c
        matched = phrase_matches(name, lex)
        if not matched:
            continue   # 표현이 없으면 3b 가 최소 방어선
        allowed = set()
        for phrase in matched:
            entry = lex.get(phrase)
            if isinstance(entry, dict):
                for s in (entry.get("symbols") or []):
                    if isinstance(s, str) and s:
                        allowed.add(s)
        for s in syms:
            if s in unknown_reported:
                continue   # 3b 에서 이미 보고
            tok = "%s::%s" % (name, s)
            if ex.get(tok):
                continue
            if s not in allowed:
                out.append({"kind": "sym_mismatch", "item": it,
                            "why": ("심볼 %s — 항목명에 나온 표현 %s 의 승인 심볼 {%s}에 없음"
                                    % (s, "/".join(sorted(matched)),
                                       ",".join(sorted(allowed)) or "(없음)"))})
    return out


# ---------------------------------------------------------------- 검사 4 — 방향(라벨 방향어 ↔ metric.op)

def _label_direction(text):
    """라벨 텍스트에서 방향 집합 {UP, DOWN} 을 추출한다.

    부정 반전: 하방어 바로 앞 3자 이내에 '안'/'않' 이 있으면 그 하방어를 UP 으로 반전.
    예) "다시 안 깸" → DOWN 어 '깸' 앞에 '안' → UP 집합에 추가.
    반환: frozenset — 원소 없으면 방향어 없음, {UP, DOWN} 혼재.
    """
    dirs = set()
    for _ in DIR_UP_RE.finditer(text):
        dirs.add("UP")
    for m in DIR_DOWN_RE.finditer(text):
        start = m.start()
        window = text[max(0, start - 3):start]
        if DIR_NEG_RE.search(window):
            dirs.add("UP")   # 부정 반전 → 상방
        else:
            dirs.add("DOWN")
    return frozenset(dirs)


def check_direction(slug, rules):
    """검사4 — rules.json 자기모순: 라벨 방향어 집합과 metric.op 방향의 대조.

    - op 가 DIR_OP_UP / DIR_OP_DOWN 에 없는 규칙은 판정 대상이 아님(skip).
    - 방향어 없음 또는 혼재({UP,DOWN}) → 판정 불가(indeterminate). 위반 아님.
    - {UP} 인데 op=DOWN, 또는 {DOWN} 인데 op=UP → 위반.
    반환: (violations, indeterminate_count)
    """
    ex = exempt_of(slug, "_rules_vs_spec_direction")
    viols = []
    indet = 0

    for rule in rules:
        metric = rule["raw"].get("metric") or {}
        op = metric.get("op")
        if op in DIR_OP_UP:
            op_dir = "UP"
        elif op in DIR_OP_DOWN:
            op_dir = "DOWN"
        else:
            continue   # op 없거나 판정 대상 아님

        text = rule["text"]
        dirs = _label_direction(text)

        if len(dirs) != 1:
            # 방향어 없음(0) 또는 혼재(2) → 판정 불가
            indet += 1
            continue

        lbl_dir = next(iter(dirs))
        if lbl_dir == op_dir:
            continue   # 일치 — 이상 없음

        tok = "%s::%s" % (rule["ref"], text[:60])
        if ex.get(tok):
            continue

        viols.append({
            "kind": "direction",
            "rule": rule,
            "lbl_dir": lbl_dir,
            "op_dir": op_dir,
            "why": ("라벨 방향=%s, op 방향=%s — 자기모순 (op=%r, 라벨: %s)"
                    % (lbl_dir, op_dir, op, text[:60])),
        })

    return viols, indet


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
                    "books.json 의 verify.symbol_lexicon 없음 — 사전이 없어 "
                    "검사3(심볼 대조)을 못 돈다(층2: 사람 승인 사전을 채워야 활성화됨)"))
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
        syms = item_symbols(i)
        print("      심볼    : %s" % (", ".join(syms) or "(없음)"))


def main(argv):
    show = None
    if "--show" in argv:
        i = argv.index("--show")
        show = argv[i + 1] if i + 1 < len(argv) else None
    json_mode = "--json" in argv

    def out(msg=""):
        if not json_mode:
            print(msg)

    bad = 0            # 위반
    blocked = 0        # 검사 불가 — '통과'가 아니다
    skipped_checks = []
    # --json 통계: 책마다 위반 건수. None = 이 책은 검사 자체가 안 돌았다(검사 불가) —
    # 0 과 다르다. 0 은 "돌았고 위반 없음", None 은 "안 돌았다".
    book_violations = {}

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
            out("· %-8s 검사 불가 — %s" % (slug, " · ".join(why)))
            blocked += 1
            book_violations[slug] = None
            continue

        rules_doc = load_json(rp)
        skip = tuple((book.get("verify") or {}).get("rule_text_skip") or RULE_TEXT_SKIP)
        rules = walk_rules(rules_doc, skip)
        items = spec_items(load_json(sp))

        # 바로 앞 구간(시트)만 본다: 규칙 라벨을 ref별로 묶고, 소절 존재는 커밋된 키로.
        sheet_secs = sheet_sections(rules)
        valid_keys = source_keys(slug)

        if show:
            show_ref(slug, show, rules, items, sheet_secs)
            continue

        out("%s — 규칙 %d개(ref 있는 것만, %s) · spec 항목 %d개(%s)"
            % (slug, len(rules), rel(rp), len(items), rel(sp)))

        # ---- 면제부터 검사한다 — 인정되지 않는 면제는 위반으로 센다
        rej = exempt_rejected(slug)
        if rej:
            out("  [면제] 인정되지 않는 면제 %d건" % len(rej))
            for where, why in rej:
                out("    ✗ %-52s %s" % (where[:52], why))
            if not json_mode:
                print(exempt_help())
        bad += len(rej)
        book_bad = len(rej)

        # ---- 빈 입력으로 '이상 없음'을 내지 않는다
        if not rules or not items:
            out("  ✗ 입력이 비었습니다(규칙 %d · spec %d) — 이 검사는 돌지 않았습니다."
                % (len(rules), len(items)))
            blocked += 1
            book_violations[slug] = None
            continue

        # ---- 검사 1 — 누락
        miss = check_missing(slug, rules, items, valid_keys)
        out("  [검사1 누락] 규칙 %d개 중 문제 %d개" % (len(rules), len(miss)))
        for m in miss:
            mark = "✗" if m["kind"] == "ref" else "⚠"
            out("    %s %-58s %s" % (mark, m["rule"]["text"][:58], m["why"]))
            out("      └ 규칙 위치: %s" % m["rule"]["path"])
        bad += len(miss)
        book_bad += len(miss)

        # ---- 검사 2 — 창작 (원문 본문 없이 항상 돈다: 시트 대조)
        inv = check_invention(slug, items, sheet_secs, valid_keys)
        auton = len([i for i in items if i.get("source") != "manual"])
        out("  [검사2 창작] 자동 spec %d개 중 시트에 없는 수치 %d개"
            % (auton, len(inv)))
        for x in inv:
            out("    ⚠ %-40s %s" % ((x["item"].get("item") or "?")[:40], x["why"]))
        bad += len(inv)
        book_bad += len(inv)

        # ---- 검사 3 — 심볼(층2): symbol_lexicon 이 있을 때만
        lex = (book.get("verify") or {}).get("symbol_lexicon") or {}
        if lex:
            sym_viols = check_symbols(slug, items, lex, valid_keys)
            out("  [검사3 심볼] 사전 표현 %d개 · spec 심볼 문제 %d개"
                % (len(lex), len(sym_viols)))
            for x in sym_viols:
                kind = x["kind"]
                if kind.startswith("lex_"):
                    label = "lexicon::%s" % x["phrase"]
                    out("    ⚠ %-52s %s" % (label[:52], x["why"]))
                else:
                    label = (x["item"].get("item") or "?")
                    out("    ⚠ %-52s %s" % (label[:52], x["why"]))
            bad += len(sym_viols)
            book_bad += len(sym_viols)

        # ---- 검사 4 — 방향(라벨 방향어 ↔ metric.op)
        dir_viols, dir_indet = check_direction(slug, rules)
        op_targets = sum(
            1 for r in rules
            if (r["raw"].get("metric") or {}).get("op") in (DIR_OP_UP | DIR_OP_DOWN)
        )
        out("  [검사4 방향] 대상 규칙 %d개 · 모순 %d건 · 판정 불가 %d건"
            % (op_targets, len(dir_viols), dir_indet))
        for x in dir_viols:
            out("    ✗ %-58s %s" % (x["rule"]["text"][:58], x["why"]))
            out("      └ 규칙 위치: %s" % x["rule"]["path"])
        bad += len(dir_viols)
        book_bad += len(dir_viols)

        book_violations[slug] = book_bad

        # ---- 못 보는 것 — 통과로 찍지 않는다
        for name, reason in unapplied(book):
            out("  [미적용]    %s — %s" % (name, reason))
            skipped_checks.append((slug, name, reason))

    if show:
        return 0

    if json_mode:
        print(json.dumps(book_violations, ensure_ascii=False))
    else:
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
            print("  심볼 위반(검사3): 사전(verify.symbol_lexicon)에 소절 키 인용과 함께 "
                  "표현→심볼을 등록하거나, 수집 심볼이 저자 표현과 다르면 spec 을 수정한다")
            print(exempt_help())
            print("규칙 문구(저자 문구)를 spec 에 맞춰 고치는 건 선택지가 아니다.")
        if blocked:
            print("-" * 74)
            print("'검사 불가'는 통과가 아니다. 계약 2·4 를 채우기 전까지 이 책은 "
                  "검증되지 않은 상태다.")
        print("=" * 74)

    # 종료코드: 0=전부 통과 · 1=위반 있음(발행 정지, 누락·창작은 거짓이다)
    #          · 2=위반은 없고 검사 불가만 있음(경고 — 아직 계약을 못 채워 검사를
    #            못 돌린 것뿐, 발행은 막지 않음)
    if bad:
        return 1
    if blocked:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
