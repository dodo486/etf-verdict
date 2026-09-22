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

    # STEP2 는 DATA 말고도 두 곳에 규칙이 있다.
    #  · 카드 밖 안내 문구(전체 계좌 -5/-8/-12% 공통 손실선 등) → sheet-step2 슬라이스
    #  · renderEntry 안에 하드코딩된 항목(거래량 1.5배 e_vol 등) → 그 함수 본문
    m_re = re.search(r"function renderEntry\(p\)\{.*?\n  \}", scripts, re.S)
    render_txt = m_re.group(0) if m_re else ""
    step2_extra = s("sheet-step2") + render_txt

    return {
        "_prod": prod_txt,
        "_step2_extra": step2_extra,
        "STEP1": s("sheet-step1") + scripts,
        "STEP2-filter": data_txt + step2_extra, "STEP2-entry": data_txt + step2_extra,
        "STEP2-avoid": data_txt + step2_extra,
        "STEP2-exit": data_txt + step2_extra + s("sheet-step2b"),
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
                scope_txt = pt + (scopes.get("_step2_extra") or "")
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


def reverse_audit(slug, path):
    """역방향 — 시트에는 있는데 **원문에는 없는** 수치(=지어낸 규칙) 찾기.

    정방향 검사(analyze)는 '원문에 있는 게 시트에 있나'만 본다. 그것만으로는
    시트가 저자가 말한 적 없는 숫자를 만들어 넣어도 통과한다. 이 프로젝트의
    절대규칙은 '저자 명시분만 · 원문 숫자 그대로 · 지어내기 금지'이고, 실전용으로
    수치화한 것은 반드시 <운영> 으로 표시하게 돼 있다. 그 표시 누락을 잡는다.
    """
    html = io.open(path, encoding="utf-8").read()
    ms = re.search(r'<script type="text/markdown" id="src">(.*?)</script>', html, re.S)
    if not ms:
        return None
    book = norm(ms.group(1))

    scopes = sheet_scopes(html)
    # 체크리스트 규칙이 실제로 적힌 곳만 본다(정의표는 이미 제외돼 있다)
    rule_text = " ".join([scopes.get(k, "") for k in
                          ("STEP2-entry", "STEP2-B", "STEP3", "STEP3-B", "STEP3-C",
                           "STEP4", "STEP5", "STEP6", "STEP7")])

    # CSS 값(translateX(-80%) 같은 것)은 규칙이 아니다 — 스타일은 걷어낸다
    rule_text = re.sub(r'style="[^"]*"', " ", rule_text)
    rule_text = re.sub(r"<style>.*?</style>", " ", rule_text, flags=re.S)

    def bare(x):
        """부호 표기 차이를 흡수. 책이 '10%'라 쓰고 시트가 '+10%'라 쓴 건 같은 값이다."""
        return x.lstrip("+-")

    book_bare = norm(re.sub(r"[+-](?=\d)", "", ms.group(1)))

    ex = (load_exempt().get(slug, {}) or {}).get("_sheet", {})
    seen, out = set(), []
    for t in TOKEN_RE.findall(rule_text):
        t = norm(t[0] if isinstance(t, tuple) else t)
        if not t or t in seen:
            continue
        seen.add(t)
        if t in book or bare(t) in book_bare:
            continue
        out.append({"tok": t, "why": ex.get(t)})
    return out


def provenance_audit(slug, path):
    """출처 검사 — 규칙마다 적힌 ref(출처 소절)가 맞는지 확인한다.

    왜 ref 가 필요한가:
      토큰 대조로는 창작(저자가 말한 적 없는 규칙)을 못 잡는다. 실증:
      SOXL 필터에 '20일선 회복 후 2거래일 동안 다시 안 깸'을 심어도 통과했다 —
      '20일선'과 '2거래일'이 7-6("S&P500 20일선 2거래일 연속 이탈")에 함께 있기 때문.
      사후 추론도 불가능했다(40개 규칙 중 유일 후보가 나온 건 1개뿐).

    그래서 **규칙을 만들 때 출처를 적게** 한다. `{t:'...', ref:'3-2', ...}`.
    검사는 셋을 본다.
      ① ref 가 있는가
      ② ref 소절이 실제로 존재하는가
      ③ 그 소절이 **이 종목의 장 또는 공통 장**인가
         (3장=TQQQ · 4장=SOXL · 5장=UPRO. 다른 종목 장을 가리키면 오귀속)
      ④ 규칙의 수치 토큰이 그 소절 본문에 있는가

    ③이 SOXL 사고를 잡는다 — 그 규칙의 정직한 출처는 3-2(TQQQ 장)라서 장이 어긋난다.
    """
    html = io.open(path, encoding="utf-8").read()
    ms = re.search(r'<script type="text/markdown" id="src">(.*?)</script>', html, re.S)
    if not ms:
        return None
    src = ms.group(1)

    secs, chap_of, key, buf, cur = {}, {}, None, [], None
    for line in src.split("\n"):
        mc = re.match(r"^##\s+(\d+)\.\s*Chapter", line)
        if mc:
            cur = mc.group(1)
        elif re.match(r"^##\s", line):
            cur = "_etc"
        m = re.match(r"^#{2,3}\s*([0-9]+-[0-9]+|에필로그)[.\s]", line)
        if m:
            if key:
                secs[key] = "\n".join(buf)
            key, buf = m.group(1), [line]
            chap_of[key] = cur
        elif key:
            buf.append(line)
    if key:
        secs[key] = "\n".join(buf)
    nsecs = {k: norm(t) for k, t in secs.items()}

    OWN = {"TQQQ": "3", "SOXL": "4", "UPRO": "5"}
    scopes = sheet_scopes(html)
    prod_txt = scopes.get("_prod") or {}
    out = []
    for prod, blob in prod_txt.items():
        banned = {c for p, c in OWN.items() if p != prod}
        for m in re.finditer(r"\{t:'((?:[^'\\]|\\.)*)'([^}]*)\}", blob):
            lab, rest = m.group(1), m.group(2)
            rm = re.search(r"ref:'([^']+)'", rest)
            if not rm:
                out.append({"prod": prod, "label": lab, "why": "출처(ref) 미기재"})
                continue
            ref = rm.group(1)
            if ref not in secs:
                out.append({"prod": prod, "label": lab, "why": "없는 소절을 가리킴: %s" % ref})
                continue
            if chap_of.get(ref) in banned:
                out.append({"prod": prod, "label": lab,
                            "why": "다른 종목 장의 규칙을 끌어옴: %s (%s장)" % (ref, chap_of.get(ref))})
                continue
            toks = []
            for t in TOKEN_RE.findall(lab):
                t = norm(t[0] if isinstance(t, tuple) else t)
                if t and t not in toks:
                    toks.append(t)
            missing = [t for t in toks if t not in nsecs[ref]]
            if missing:
                out.append({"prod": prod, "label": lab,
                            "why": "%s 본문에 없는 수치: %s" % (ref, ", ".join(missing))})
    return out


def attribution_audit(slug, path):
    """귀속 검사(참고) — 종목별 규칙이 **그 종목에 대해** 저자가 말한 것인지 본다.

    토큰만 보는 reverse_audit 은 종목 오귀속을 못 잡는다. 실제 사고:
      SOXL 필터에 '20일선 회복 후 2거래일 동안 다시 안 깸'을 넣었는데, 저자는
      3-2(TQQQ)·5-2(UPRO)에만 그렇게 말했고 4장(SOXL)엔 "모두 20일선 위여야"
      까지만 썼다. 그런데 '2거래일'이라는 토큰 자체는 책 어딘가에 있으니 통과했다.

    그래서 **문장 단위**로 본다. 시트의 규칙 문구에서 뽑은 토큰들이 **한 문장 안에
    모두** 나오는 곳이 그 종목에게 허용된 범위(해당 장 + 공통 장)에 있는지 확인한다.
    다른 종목 장은 제외한다 — 거기 있는 규칙을 끌어다 쓰면 그게 오귀속이다.
    """
    html = io.open(path, encoding="utf-8").read()
    ms = re.search(r'<script type="text/markdown" id="src">(.*?)</script>', html, re.S)
    if not ms:
        return None
    src = ms.group(1)

    # 장별로 자른다. 3장=TQQQ · 4장=SOXL · 5장=UPRO, 나머지는 공통
    chaps, cur = {}, None
    for line in src.split("\n"):
        m = re.match(r"^##\s+(\d+)\.\s*Chapter", line)
        if m:
            cur = m.group(1)
            chaps[cur] = []
        elif re.match(r"^##\s", line):
            cur = "_etc"
            chaps.setdefault(cur, [])
        elif cur:
            chaps[cur].append(line)
    OWN = {"TQQQ": "3", "SOXL": "4", "UPRO": "5"}

    def allowed_sentences(prod):
        skip = {v for k, v in OWN.items() if k != prod}
        txt = []
        for c, lines in chaps.items():
            if c in skip:
                continue
            txt.extend(lines)
        # 문장 단위로 쪼갠다(불릿 한 줄 = 한 문장 단위로 취급)
        out = []
        for l in txt:
            for piece in re.split(r"[·。]|\. ", l):
                out.append(norm(piece))
        return out

    scopes = sheet_scopes(html)
    prod_txt = scopes.get("_prod") or {}
    ex = (load_exempt().get(slug, {}) or {}).get("_attribution", {})

    out = []
    for prod, blob in prod_txt.items():
        sents = allowed_sentences(prod)
        for lab in re.findall(r"\{t:'((?:[^'\\]|\\.)*)'", blob):
            toks = []
            for t in TOKEN_RE.findall(lab):
                t = norm(t[0] if isinstance(t, tuple) else t)
                if t and t not in toks:
                    toks.append(t)
            if len(toks) < 2:
                continue              # 토큰 1개 이하면 문장 대조가 의미 없다
            if any(all(t in s for t in toks) for s in sents):
                continue
            key = "%s::%s" % (prod, lab[:40])
            out.append({"prod": prod, "label": lab, "tokens": toks, "why": ex.get(key)})
    return out


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

        # 출처 검사 — ref 가 가리키는 소절이 맞는지(오귀속·잘못된 출처 탐지)
        prov = provenance_audit(slug, path) or []
        provbad = [x for x in prov if not x["why"].startswith("출처")]
        provmiss = [x for x in prov if x["why"].startswith("출처")]
        if provbad:
            print("%s — 출처(ref)가 틀린 규칙 %d개" % (slug, len(provbad)))
            for x in provbad:
                print("  ✗ %-5s %-44s %s" % (x["prod"], x["label"][:44], x["why"]))
        if provmiss:
            print("%s — 출처(ref) 미기재 규칙 %d개 (새 책은 필수, 기존분은 순차 보강)"
                  % (slug, len(provmiss)))
        total_bad += len(provbad)

        # 역방향 — 시트엔 있는데 원문엔 없는 수치(지어낸 규칙)
        rev = reverse_audit(slug, path) or []
        revbad = [x for x in rev if not x.get("why")]
        if revbad:
            print("%s — 시트 규칙에 쓰였는데 원문에 없는 수치 %d개 (지어내기 의심)"
                  % (slug, len(revbad)))
            for x in revbad:
                print("  ⚠ %s" % x["tok"])
        total_bad += len(revbad)

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
