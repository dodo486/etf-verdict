#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""플레이북 창작 검사 — 구간 ① 의 창작(fabrication) 검사. 모든 책 공통.

## 왜 있나

이 파이프라인의 변환은 세 구간이고, 구간마다 지킬 건 둘뿐이다.
**창작 없이**(원문에 없는 게 들어오지 않는다) · **누락 없이**(원문에 있는 게 빠지지 않는다).

| 구간 | 창작 검사 | 누락 검사 |
|---|---|---|
| ① 책 → 플레이북 | **이 파일** | `book_source.py` 가 키 수준 대조 |
| ② 플레이북 → 체크리스트 | `verify_coverage.py` 출처 4단 | `verify_coverage.py` 커버리지 전수 |
| ③ 체크리스트 → 수집요청 | `verify_rules_vs_spec.py` | `verify_rules_vs_spec.py` |

①칸의 **창작** 자리가 비어 있었다. `verify_source_integrity.py` 는 저자 원문(`#src`·
규칙 근거표)이 **기준 대비 안 바뀌었나**만 본다 — 플레이북이 저자에게 돌린 주장이
그 원문에 실제로 **근거하는가**는 아무도 안 봤다. 그래서 플레이북이 책에 없는 수치를
저자 말인 양 지어내도(예: 저자가 말한 적 없는 '2거래일 20일선 유지') 아무 검사에도
안 걸렸다. 이 파일이 그 구멍을 막는다.

이건 `verify_coverage`(소절→구현 방향: 소절이 말한 수치가 시트에 반영됐나)의 **거울**이다.
여기서는 반대 방향 — 플레이북-주장 → 소절-원문: 플레이북이 저자에게 돌린 각 규칙의
정량 토큰이 그 규칙이 가리키는(`ref`) **소절 원문**에 실제로 있는가.

## 무엇을 무엇과 대조하나

입력은 **JSON 두 개뿐**이다: `books/<slug>/rules.json`(플레이북이 저자에게 돌린 주장)과
`books/<slug>/source_index.json`(원문 소절별 정량 토큰). HTML 은 읽지 않는다.
소절 원문 자체는 저작권물이라 리포에 없다 — `source_index.json` 은 저자 원문을
`verify_coverage.TOKEN_RE` **같은 토크나이저**로 뽑아 소절별 `tokens` 로 커밋해 둔
'토큰 지문'이다. 그래서 원문 파일(BOOK_RAW_DIR) 없이도 커밋본만으로 돌아간다.

    검사 1 (고아 주장)  규칙 ──ref──▶ 소절     모든 저자-귀속 규칙이 **실존하는**
                                              소절 키를 `ref` 로 가리키는가.
                                              ref 없음 또는 없는 소절 = 창작 후보.
    검사 2 (근거 없는 토큰)  규칙 토큰 ──▶ 소절 토큰  규칙 문구의 정량 토큰이
                                              그 소절 원문 토큰 지문에 다 있는가.
                                              하나라도 없으면 = 플레이북이 지어낸 것.

## 창작의 기계적 정의 (블랙박스 아님)

- **규칙(저자-귀속 주장)**: `t`(라벨) 문자열을 가진 dict. `verify_contract.iter_rules`
  와 **같은** 정의로 훑는다(복붙하면 두 검사기의 규칙 정의가 갈라진다).
- **정량 토큰**: `verify_coverage.TOKEN_RE` 로 뽑은 것 — `-5%`·`20일선`·`2거래일`·
  `1.5배`·`0.1%p`·`3개`·`30분`. 이게 창작 판정의 유일한 대상이다.
  숫자가 안 붙은 산문(패러프레이즈)은 판정하지 않는다 — 저자 문장을 글자 그대로
  베끼라는 게 아니라, **저자가 숫자로 말한 것**을 안 지어내는지만 본다.
- **근거 있음(grounded)**: 규칙 토큰이 그 소절의 `source_index` 토큰 지문에
  **정규화 후 그대로** 들어 있음(`norm` 으로 공백 제거 후 문자열 동일).
  토크나이저가 양쪽에 같으므로 `20 일선`↔`20일선` 같은 표기 흔들림은 이미 접혔다.

### 관용(tolerance) — 무엇을 봐주고 무엇을 안 봐주나

- 산문/어순/조사 차이는 **본다(허용)**: 토큰만 대조하므로 문장이 달라도 통과.
- `source:"manual"` 규칙은 **건너뛴다**: 미구현이라고 스스로 밝힌 것이지 저자 주장이 아니다.
- 토큰이 **하나도 없는** 규칙은 창작이 아니다: 지어낼 정량이 없다(고아 검사만 받는다).
- `coverage_exempt.json` 의 `_source_fabrication` 버킷에 **분류(kind)+사유(why)**를
  적어 면제할 수 있다(다른 검사기와 **같은** 면제 형식·검증). 사유 없는 면제는 안 통한다.

## 등급 (다른 검사기와 같은 관례)

    0  모든 저자 주장이 근거 있음 — 통과
    1  창작 발견(고아 주장 또는 근거 없는 토큰) — **발행 정지**(거짓이므로)
    2  검사 불가 — 계약 구조(rules.json / ref / source_index)를 못 채운 책 — **경고**
       (발행은 막지 않음. supply 처럼 아직 rules.json 이 없는 책이 여기 해당)

## 사용

    python verify_source_fabrication.py          # 검사 (창작 있으면 exit 1)
    python verify_source_fabrication.py --json    # {slug:{claims,orphans,ungrounded,fabrications}}
    python verify_source_fabrication.py --show 3-2 # 그 소절의 규칙·토큰·근거 상세
"""
import io
import json
import os
import re
import sys

import paths  # noqa: F401  (경로·UTF-8 출력 고정. 반드시 먼저 import)
from paths import BASE

# 토큰·정규화·면제 형식은 한 곳에서만 정의돼야 한다(복붙하면 검사기끼리 갈라진다).
from verify_coverage import TOKEN_RE, norm, exempt_entries, exempt_help
# 규칙(저자-귀속 주장) 정의도 하나뿐이어야 한다.
from verify_contract import iter_rules

EXEMPT = os.path.join(BASE, "coverage_exempt.json")

# 소절 키 형식(계약 1). ref 가 이 모양이어야 '출처'로 본다.
KEY_RE = re.compile(r"^(?:[0-9]+-[0-9]+|프롤로그|에필로그)$")


# ---------------------------------------------------------------- 입력
def books():
    man = json.loads(io.open(os.path.join(BASE, "books.json"), encoding="utf-8").read())
    return [b for b in man.get("books", []) if b.get("slug")]


def rules_path(slug):
    return os.path.join(BASE, "books", slug, "rules.json")


def source_index_path(slug):
    return os.path.join(BASE, "books", slug, "source_index.json")


def load_json(p):
    return json.loads(io.open(p, encoding="utf-8").read())


def rel(p):
    try:
        return os.path.relpath(p, BASE)
    except ValueError:
        return p


# ---------------------------------------------------------------- 원문 토큰 지문
def source_tokens(slug):
    """{소절키: [정량토큰...]} — 저자 원문을 같은 토크나이저로 뽑아 커밋한 지문.

    본문 텍스트는 저작권물이라 리포에 없다. source_index.json 의 소절별 `tokens` 가
    'book_source.py 가 verify_coverage.TOKEN_RE 로 뽑아 둔' 원문 정량 토큰이다.
    그래서 원문 파일 없이도 커밋본만으로 근거 검사가 돈다.
    """
    p = source_index_path(slug)
    if not os.path.exists(p):
        return None
    idx = load_json(p)
    secs = idx.get("sections")
    if not isinstance(secs, dict):
        return None
    out = {}
    for key, meta in secs.items():
        toks = meta.get("tokens") if isinstance(meta, dict) else None
        out[key] = [norm(t) for t in toks] if isinstance(toks, list) else []
    return out


def tokens_of_text(text):
    """규칙 문구의 정량 토큰 — verify_coverage 와 같은 정의."""
    out = []
    for t in TOKEN_RE.findall(text or ""):
        t = norm(t[0] if isinstance(t, tuple) else t)
        if t and t not in out:
            out.append(t)
    return out


# ---------------------------------------------------------------- 규칙 읽기
def claim_text(rule):
    """규칙 dict → 토큰을 뽑을 텍스트. 저자 문구가 담긴 모든 문자열 값을 잇는다.

    `ref` 는 짝짓기 열쇠(예: '5-2')지 저자 문구가 아니므로 뺀다 — 안 빼면 '5-2' 가
    숫자 5·2 로 읽혀 자기 자신을 근거로 삼는 꼴이 된다. `src`(수집 소스 주석)도
    구현 쪽 문구라 뺀다.
    """
    parts = []
    for k, v in rule.items():
        if k in ("ref", "src", "source"):
            continue
        if isinstance(v, str):
            parts.append(v)
    return " · ".join(parts)


def rule_ref(rule):
    ref = rule.get("ref")
    return ref if isinstance(ref, str) and KEY_RE.match(ref) else None


# ---------------------------------------------------------------- 면제
def load_exempt():
    if not os.path.exists(EXEMPT):
        return {}
    return load_json(EXEMPT)


def exempt_of(slug):
    """`_source_fabrication` 버킷 — 분류·사유가 통과한 면제만. 형식·검증은 공용."""
    d = (load_exempt().get(slug, {}) or {}).get("_source_fabrication")
    return exempt_entries(d)[0]


def exempt_rejected(slug):
    """인정되지 않은 면제(분류 밖 또는 사유 빔) — 위반으로 센다."""
    d = (load_exempt().get(slug, {}) or {}).get("_source_fabrication")
    return exempt_entries(d)[1]


# ---------------------------------------------------------------- 검사
def check_book(slug):
    """한 책의 창작 검사. 돌려주는 것:
        (status, stats, findings, rejected_exempts)
    status: 0=통과 · 1=창작 있음 · 2=검사 불가(계약 미충족)
    """
    rp = rules_path(slug)
    src_tok = source_tokens(slug)

    # ---- 검사 불가(계약 미충족)를 '찍는다'. 조용한 스킵 금지.
    why = []
    if not os.path.exists(rp):
        why.append("rules.json 없음(계약2 미충족)")
    if src_tok is None:
        why.append("source_index.json 없음(원문 토큰 지문이 없어 근거를 대조할 수 없음)")
    if why:
        return 2, {"reason": " · ".join(why)}, [], []

    rules = list(iter_rules(load_json(rp)))
    if not rules:
        return 2, {"reason": "rules.json 에 규칙(라벨 t)이 하나도 없음"}, [], []

    ex = exempt_of(slug)
    findings = []
    claims = orphans = ungrounded = 0

    for rule in rules:
        # 스스로 수동/미구현이라 밝힌 규칙은 저자-귀속 주장이 아니다.
        if rule.get("source") == "manual":
            continue
        claims += 1
        label = rule.get("t", "")
        ref = rule_ref(rule)

        # ---- 검사 1 — 고아 주장(ref 없음 / 없는 소절)
        if ref is None:
            raw_ref = rule.get("ref")
            reason = ("ref 없음(어느 소절에도 근거를 안 댐)" if not raw_ref
                      else "잘못된 소절키 형식: %r" % raw_ref)
            findings.append({"kind": "orphan", "label": label, "ref": raw_ref,
                             "why": reason})
            orphans += 1
            continue
        if ref not in src_tok:
            findings.append({"kind": "orphan", "label": label, "ref": ref,
                             "why": "없는 소절을 가리킴: %s" % ref})
            orphans += 1
            continue

        # ---- 검사 2 — 근거 없는 토큰
        have = src_tok[ref]
        for tok in tokens_of_text(label):
            if tok in have:
                continue
            if ex.get("%s::%s" % (ref, tok)):
                continue
            findings.append({"kind": "ungrounded", "label": label, "ref": ref,
                             "token": tok,
                             "why": "'%s' 이(가) %s 원문 토큰에 없음(플레이북이 지어냄)"
                                    % (tok, ref)})
            ungrounded += 1

    rejected = [("%s" % tok, why) for tok, why in exempt_rejected(slug)]
    fabrications = orphans + ungrounded
    stats = {"claims": claims, "orphans": orphans,
             "ungrounded": ungrounded, "fabrications": fabrications}
    status = 1 if (fabrications or rejected) else 0
    return status, stats, findings, rejected


# ---------------------------------------------------------------- 상세(--show)
def show_ref(slug, ref):
    src_tok = source_tokens(slug)
    if src_tok is None:
        print("[%s] source_index.json 이 없어 상세를 보여줄 수 없습니다." % slug)
        return 2
    rp = rules_path(slug)
    if not os.path.exists(rp):
        print("[%s] rules.json 이 없습니다." % slug)
        return 2
    print("[%s] %s" % (slug, ref))
    have = src_tok.get(ref)
    if have is None:
        print("  소절 없음(원문 지문에 %s 키가 없음)" % ref)
    else:
        print("  원문 토큰 지문 : %s" % (", ".join(have) or "(없음)"))
    rs = [r for r in iter_rules(load_json(rp)) if rule_ref(r) == ref]
    print("  이 소절을 근거로 삼은 규칙 %d개" % len(rs))
    for r in rs:
        toks = tokens_of_text(r.get("t", ""))
        miss = [t for t in toks if have is not None and t not in have]
        print("    - %s" % r.get("t", "")[:70])
        print("      토큰: %s%s" % (", ".join(toks) or "(없음)",
                                   ("  ✗근거없음: %s" % ", ".join(miss)) if miss else ""))
    return 0


# ---------------------------------------------------------------- 실행
def main(argv):
    show = None
    if "--show" in argv:
        i = argv.index("--show")
        show = argv[i + 1] if i + 1 < len(argv) else None
    json_mode = "--json" in argv

    def out(msg=""):
        if not json_mode:
            print(msg)

    if show:
        rc = 2
        for b in books():
            slug = b["slug"]
            if show in (source_tokens(slug) or {}):
                return show_ref(slug, show)
        # 어느 책에도 그 소절이 없으면 첫 책 기준으로 안내
        for b in books():
            return show_ref(b["slug"], show)
        return rc

    fab_total = 0          # 창작(고아+근거없음)
    blocked = 0            # 검사 불가 — '통과'가 아니다
    skipped = []
    # --json: 책마다 카운트. None = 검사 자체가 안 돌았다(검사 불가) — 0(돌았고 없음)과 다르다.
    book_stats = {}

    for b in books():
        slug = b["slug"]
        status, stats, findings, rejected = check_book(slug)

        if status == 2:
            out("· %-8s 검사 불가 — %s" % (slug, stats.get("reason")))
            blocked += 1
            book_stats[slug] = {"claims": None, "orphans": None,
                                "ungrounded": None, "fabrications": None}
            skipped.append((slug, stats.get("reason")))
            continue

        book_stats[slug] = stats
        out("%s — 저자 주장 %d개(%s) · 원문 소절 토큰 지문 대조"
            % (slug, stats["claims"], rel(rules_path(slug))))

        # 인정되지 않은 면제부터 — 위반으로 센다
        if rejected:
            out("  [면제] 인정되지 않는 면제 %d건" % len(rejected))
            for tok, why in rejected:
                out("    ✗ %-40s %s" % (tok[:40], why))
            if not json_mode:
                print(exempt_help())
            fab_total += len(rejected)

        orphans = [f for f in findings if f["kind"] == "orphan"]
        ung = [f for f in findings if f["kind"] == "ungrounded"]
        out("  [검사1 고아주장] 근거를 안 댄 주장 %d개" % len(orphans))
        for f in orphans:
            out("    ✗ %-48s %s" % (f["label"][:48], f["why"]))
        out("  [검사2 근거없는 토큰] 원문에 없는 정량 토큰 %d개" % len(ung))
        for f in ung:
            out("    ⚠ %-48s %s" % (f["label"][:48], f["why"]))

        fab_total += stats["fabrications"]

    if json_mode:
        # run.py record_verify_history 가 읽는 형태: {slug: {counts...}}
        print(json.dumps(book_stats, ensure_ascii=False))
    else:
        print("\n" + "=" * 74)
        print("창작 %d건 · 검사 불가 %d권" % (fab_total, blocked))
        for slug, reason in skipped:
            print("  · %-8s %s" % (slug, reason))
        if fab_total:
            print("-" * 74)
            print("플레이북이 책에 없는 걸 저자 말인 양 지어냈다. 처리 방법은 셋뿐이다.")
            print("  ① 규칙에 올바른 ref(그 수치가 실제로 나온 소절)를 단다")
            print("  ② 저자 주장이 아니라 우리 참고/판단이면 source:\"manual\" 로 표시한다")
            print("  ③ 원문에 있는데 토크나이저가 못 잡은 표기라면 coverage_exempt.json 의 "
                  "`_source_fabrication` 에 **분류(kind)와 사유(why)**를 적어 면제한다")
            print(exempt_help())
            print("원문에 없는 수치를 저자 문구에 넣는 건 선택지가 아니다.")
        if blocked:
            print("-" * 74)
            print("'검사 불가'는 통과가 아니다. rules.json·source_index.json 을 채우기 "
                  "전까지 이 책의 창작 여부는 검증되지 않은 상태다.")
        print("=" * 74)

    # 종료코드: 0=통과 · 1=창작(발행 정지) · 2=위반 없고 검사 불가만(경고)
    if fab_total:
        return 1
    if blocked:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
