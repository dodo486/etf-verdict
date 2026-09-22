#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""커버리지 배지 검증 — '✅ 반영'이 사실인지 기계로 대조한다. 모든 책 공통.

## 왜 있나

커버리지 배지(✅반영 / ⚠미반영 / 💭원칙)는 **검증된 사실이 아니라 사람이 적은 주장**이었다.
coverage-data 에 `status:"reflected"` 라고 써넣으면 그대로 ✅가 찍힌다. 그 주장을
실제 시트 구현과 대조하는 장치가 없었다.

실제 사고(2026-09-22, etf 5-2):
  저자 5-2 "그다음 2거래일 동안 20일선 다시 안 깸" · 규칙 근거표에도 "이후 2거래일
  20일선 안 깸"이라고 정량 정의까지 적혀 있었다. 그런데 구현은 당일 종가 1회만 비교.
  커버리지 노트에는 "2일 유지 = UPRO filter 에 반영"이라고 **거짓으로** 적혀 있었고
  배지는 ✅였다. 사람이 화면을 보다가 발견했다.

`verify_source_integrity.py` 는 "원문이 안 바뀌었나"를 본다. 이 스크립트는
**"원문대로 구현됐나"** 를 본다.

## 어떻게 검사하나

저자 소절 본문에서 **정량 토큰**(2거래일 · 20일선 · 1.5배 · -5% · 0.1%p · 3개 …)을
뽑고, 그 소절이 `reflected` 로 표시돼 있으면 해당 STEP 의 **구현 범위 안에** 그 토큰이
실제로 등장하는지 확인한다. 안 보이면 "주장과 구현이 다를 수 있음"으로 세운다.

범위(scope)를 STEP 별로 자르는 게 핵심이다. 시트 전체에서 찾으면 **규칙 근거표**에
적힌 정의가 잡혀서 "구현됐다"고 오판한다 — 5-2 사고가 정확히 그 모양이었다.
그래서 규칙 근거표와 책 본문은 범위에서 **제외**한다.

## 한계 (정직하게)

토큰이 보인다고 제대로 구현됐다는 보증은 아니다(위치·방향까지는 못 본다).
반대로 **안 보이면 거의 확실히 빠진 것**이다. 즉 이 검사는 거짓 ✅를 잡는 용도다.

숫자를 안 쓰고 구현한 항목, 저자 예시 금액처럼 규칙이 아닌 숫자는 오탐이 된다.
그런 건 `coverage_exempt.json` 에 **이유를 적어** 면제한다. 침묵으로 넘기지 못하게
이유 문자열을 필수로 받는다.

## 사용

    python verify_coverage.py              # 검사 (미해명 누락 있으면 exit 1)
    python verify_coverage.py --show 5-2   # 그 소절의 토큰·범위·판정 상세
    python verify_coverage.py --list       # 누락 전체를 면제 파일 양식으로 출력
"""
import io
import json
import os
import re
import sys

import paths
from paths import BASE, PUBLIC

EXEMPT = os.path.join(BASE, "coverage_exempt.json")

# 정량 토큰 — 저자가 숫자로 말한 것만
TOKEN_RE = re.compile(
    r"(\d+\s*~\s*\d+\s*%p?"          # 7~10%
    r"|[+-]?\d+(?:\.\d+)?\s*%p"      # 0.1%p
    r"|[+-]?\d+(?:\.\d+)?\s*%"       # -5%, 30%
    r"|\d+\s*거래일"                  # 2거래일
    r"|\d+\s*일선"                    # 20일선
    r"|\d+(?:\.\d+)?\s*배"            # 1.5배
    r"|\d+\s*개"                      # 3개
    r"|\d+\s*분)"                     # 30분
)


def norm(t):
    return re.sub(r"\s+", "", t).replace("＋", "+")


def book_pages():
    man = json.loads(io.open(os.path.join(BASE, "books.json"), encoding="utf-8").read())
    out = {}
    for b in man.get("books", []):
        slug = b["slug"]
        for c in (os.path.join(PUBLIC, slug, "index.html"),
                  os.path.join(BASE, "%s-playbook.html" % slug)):
            if os.path.exists(c):
                out[slug] = c
                break
    return out


def split_sections(src):
    """플레이북 마크다운 → {소절키: 본문}"""
    out, key, buf = {}, None, []
    for line in src.split("\n"):
        m = re.match(r"^#{2,3}\s*([0-9]+-[0-9]+|에필로그)[.\s]", line)
        if m:
            if key:
                out[key] = "\n".join(buf)
            key, buf = m.group(1), [line]
        elif re.match(r"^##\s", line):
            # 새 장/부록이 시작되면 직전 소절은 거기서 끝난다.
            # (이게 없으면 '에필로그'가 뒤의 부록 숫자표까지 통째로 삼킨다)
            if key:
                out[key] = "\n".join(buf)
            key, buf = None, []
        elif key:
            buf.append(line)
    if key:
        out[key] = "\n".join(buf)
    return out


def _const_blocks(html):
    out = {}
    for m in re.finditer(r"\n\s*const ([A-Z][A-Z0-9_]*)\s*=\s*([\[{])", html):
        name, op = m.group(1), m.group(2)
        cl = "]" if op == "[" else "}"
        i = m.end() - 1
        depth, j, ins, q, esc = 0, i, False, "", False
        while j < len(html):
            c = html[j]
            if ins:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == q:
                    ins = False
            else:
                if c in ('"', "'", "`"):
                    ins, q = True, c
                elif c == op:
                    depth += 1
                elif c == cl:
                    depth -= 1
                    if depth == 0:
                        break
            j += 1
        out[name] = html[i:j + 1]
    return out


def sheet_scopes(html):
    """STEP → 그 STEP 의 구현 텍스트.

    규칙 근거표(정의표)와 책 본문(#src)은 **제외**한다. 거기엔 '정의'가 적혀 있어서
    포함하면 구현 안 된 항목도 통과해 버린다.
    """
    body = html
    # 책 본문 제거
    body = re.sub(r'<script type="text/markdown" id="src">.*?</script>', " ", body, flags=re.S)
    # 규칙 근거표(details 블록) 제거
    body = re.sub(r"<details[^>]*>\s*<summary[^>]*>\s*📖 규칙 근거.*?</details>", " ", body, flags=re.S)
    # 커버리지 노트 자체도 제외(자기 주장으로 자기를 통과시키면 안 된다)
    body = re.sub(r'<script type="application/json" id="coverage-data">.*?</script>', " ", body, flags=re.S)

    consts = _const_blocks(body)
    data_txt = consts.get("DATA", "") + consts.get("DEFS", "") + consts.get("ENTRY", "") + \
        consts.get("EXITS", "") + consts.get("SC", "") + consts.get("ROUTINE", "")

    # 종목별로 DATA 를 쪼개 둔다. 한 덩어리로 보면 TQQQ 에 있는 문구가 UPRO 의
    # 누락을 가린다 — 5-2 사고가 정확히 그렇게 통과했다.
    prod_txt = {}
    dt = consts.get("DATA", "")
    if dt:
        marks = [(p, dt.find("\n    %s:{" % p)) for p in ("TQQQ", "SOXL", "UPRO")]
        marks = [(p, i) for p, i in marks if i >= 0]
        marks.sort(key=lambda kv: kv[1])
        for n, (p, i) in enumerate(marks):
            j = marks[n + 1][1] if n + 1 < len(marks) else len(dt)
            prod_txt[p] = dt[i:j]

    # STEP 앵커별 HTML 조각
    anchors = re.findall(r'<h2 id="(sheet-step[0-9a-z]+)"', body)
    slices = {}
    for i, a in enumerate(anchors):
        start = body.index('<h2 id="%s"' % a)
        end = len(body)
        if i + 1 < len(anchors):
            end = body.index('<h2 id="%s"' % anchors[i + 1])
        slices[a] = body[start:end]

    # 스크립트 전체(계산 로직이 JS에 있는 항목 — 환전 임계 등)
    scripts = " ".join(re.findall(r"<script>(.*?)</script>", body, flags=re.S))

    def s(*keys):
        return " ".join(slices.get(k, "") for k in keys)

    return {
        "_prod": prod_txt,
        "STEP1": s("sheet-step1") + scripts,
        "STEP2-filter": data_txt, "STEP2-entry": data_txt,
        "STEP2-avoid": data_txt, "STEP2-exit": data_txt + s("sheet-step2b"),
        "STEP2-B": s("sheet-step2b"),
        "STEP3": s("sheet-step3") + scripts,
        "STEP3-B": s("sheet-step3b") + scripts,
        "STEP3-C": s("sheet-step3c") + scripts,
        "STEP4": s("sheet-step4") + scripts,
        "STEP5": s("sheet-step5") + scripts,
        "STEP6": s("sheet-step6") + scripts,
        "STEP7": s("sheet-step7") + scripts,
    }


def load_exempt():
    if os.path.exists(EXEMPT):
        return json.loads(io.open(EXEMPT, encoding="utf-8").read())
    return {}


def analyze(slug, path):
    html = io.open(path, encoding="utf-8").read()
    m = re.search(r'<script type="application/json" id="coverage-data">\s*(\{.*?\})\s*</script>',
                  html, re.S)
    if not m:
        return None
    cov = json.loads(m.group(1))["map"]
    ms = re.search(r'<script type="text/markdown" id="src">(.*?)</script>', html, re.S)
    if not ms:
        return None
    secs = split_sections(ms.group(1))
    scopes = sheet_scopes(html)
    ex = load_exempt().get(slug, {})

    rows = []
    for key, c in cov.items():
        if c.get("status") != "reflected":
            continue
        body = secs.get(key)
        if body is None:
            rows.append({"key": key, "err": "소절 본문을 못 찾음"})
            continue
        toks = []
        for t in TOKEN_RE.findall(body):
            t = norm(t[0] if isinstance(t, tuple) else t)
            if t and t not in toks:
                toks.append(t)
        step = c.get("step", "")
        scope_txt = scopes.get(step, "")
        # 3장=TQQQ · 4장=SOXL · 5장=UPRO — 그 장의 소절은 해당 종목 블록만 본다
        chap = key.split("-")[0]
        prod = {"3": "TQQQ", "4": "SOXL", "5": "UPRO"}.get(chap)
        if prod and step.startswith("STEP2"):
            pt = (scopes.get("_prod") or {}).get(prod)
            if pt:
                scope_txt = pt + (scopes.get("sheet-step2b") or "")
        scope = norm(scope_txt)
        if not scope:
            rows.append({"key": key, "err": "step=%s 의 구현 범위를 못 찾음" % c.get("step")})
            continue
        miss = [t for t in toks if t not in scope]
        exs = ex.get(key, {})
        unresolved = [t for t in miss if t not in exs]
        rows.append({"key": key, "step": c.get("step"), "tokens": toks,
                     "miss": miss, "unresolved": unresolved, "exempt": exs})
    return rows


def main(argv):
    show = None
    if "--show" in argv:
        i = argv.index("--show")
        show = argv[i + 1] if i + 1 < len(argv) else None
    listing = "--list" in argv

    pages = book_pages()
    total_bad, out_list = 0, {}

    for slug, path in sorted(pages.items()):
        rows = analyze(slug, path)
        if rows is None:
            print("· %-8s 커버리지/본문 없음 — 검사 대상 아님" % slug)
            continue
        if show:
            r = next((x for x in rows if x["key"] == show), None)
            if not r:
                print("그런 소절이 없거나 reflected 가 아님: %s" % show)
                return 2
            print("[%s] %s  step=%s" % (slug, show, r.get("step")))
            print("  원문 정량 토큰 :", ", ".join(r.get("tokens") or []) or "(없음)")
            print("  구현에서 못 찾음:", ", ".join(r.get("miss") or []) or "(없음)")
            print("  면제됨         :", ", ".join((r.get("exempt") or {}).keys()) or "(없음)")
            return 0

        bad = [r for r in rows if r.get("unresolved") or r.get("err")]
        total_bad += len(bad)
        out_list[slug] = {}
        print("%s — reflected %d개 중 확인 필요 %d개" % (slug, len(rows), len(bad)))
        for r in bad:
            if r.get("err"):
                print("  ✗ %-6s %s" % (r["key"], r["err"]))
                continue
            print("  ⚠ %-6s [%s] 구현에서 안 보이는 수치: %s"
                  % (r["key"], r.get("step"), ", ".join(r["unresolved"])))
            out_list[slug][r["key"]] = {t: "" for t in r["unresolved"]}

    if listing:
        print("\n--- coverage_exempt.json 양식 (사유를 채워 넣으세요) ---")
        print(json.dumps(out_list, ensure_ascii=False, indent=2))
        return 0

    if total_bad:
        print("\n" + "=" * 70)
        print("'✅ 반영'이라고 적혀 있는데 구현 범위에서 그 수치가 안 보이는 소절이 있습니다.")
        print("  ① 구현한다  ② status 를 gap 으로 내린다")
        print("  ③ 규칙이 아닌 숫자라면 coverage_exempt.json 에 **사유를 적어** 면제한다")
        print("=" * 70)
        return 1

    print("\n전부 통과 — '반영' 주장과 구현이 어긋나는 곳 없음.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
