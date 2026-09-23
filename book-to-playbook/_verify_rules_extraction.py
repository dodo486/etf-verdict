#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[임시 파일 — 1회용 대조 스크립트. 규칙 분리 검증이 끝나면 지울 것]

규칙(`DATA`/`MODES`/`SCSRC`/`STEPNAME`)을 HTML 안 JS 리터럴에서
`books/etf/rules.json` 으로 옮기면서 **저자 원문이 한 글자도 안 바뀌었음**을 증명한다.

`verify_source_integrity.py` 는 바로 그 네 상수를 원문으로 해시하고 있다. 구조를
바꾸면 해시가 깨지는 게 당연하므로, 해시 대신 **내용 1:1 대조**로 증명한다.
(`--accept` 로 기준을 갱신하는 것은 이 스크립트의 일이 아니다 — 원문 보호가
그 순간 무의미해진다. 기준 갱신 판단은 사람이 이 출력을 보고 한다.)

대조하는 것
  A. 규칙 데이터   분리 **전** HTML(git HEAD) 의 JS 리터럴  ↔  books/etf/rules.json
  B. 규칙 근거표   분리 전 HTML  ↔  분리 후 HTML            (안 건드렸으니 동일해야)
  C. 정적 체크라벨 분리 전 HTML  ↔  분리 후 HTML            (안 건드렸으니 동일해야)
  D. 주입된 사본   분리 후 HTML 의 id="rules" 블록          ↔  books/etf/rules.json

값은 공백 정규화(연속 공백 → 한 칸) 후 비교한다. 다르면 **어느 항목이 어떻게**
다른지 전부 찍는다. '대체로 같다'는 결과가 아니다.

    python _verify_rules_extraction.py [--slug etf]
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile

import paths
from paths import BASE, read_text

NAMES = ("DATA", "MODES", "SCSRC", "STEPNAME")


# ------------------------------------------------- JS 리터럴 스캐너
def const_spans(html):
    """`const NAME = [...] / {...}` 의 리터럴 span.

    verify_source_integrity.py 의 `_const_blocks` 와 **같은 스캐너**다. 다른
    스캐너로 뽑으면 '같은 것을 비교했다'는 증명이 성립하지 않는다. 차이는 공백
    정규화를 하지 않고 오프셋을 돌려준다는 것뿐.
    """
    out = {}
    for m in re.finditer(r"\n\s*const ([A-Z][A-Z0-9_]*)\s*=\s*([\[{])", html):
        name, open_ch = m.group(1), m.group(2)
        close_ch = "]" if open_ch == "[" else "}"
        i = m.end() - 1
        depth, j, in_s, q, esc = 0, i, False, "", False
        while j < len(html):
            c = html[j]
            if in_s:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == q:
                    in_s = False
            else:
                if c in ('"', "'", "`"):
                    in_s, q = True, c
                elif c == open_ch:
                    depth += 1
                elif c == close_ch:
                    depth -= 1
                    if depth == 0:
                        break
            j += 1
        out[name] = html[i:j + 1]
    return out


def eval_js(lits):
    """{이름: JS리터럴} → {이름: 값}. node 로 평가한다(손으로 파싱하면 그게 또 오차다)."""
    src = "const OUT={};\n"
    for k, v in lits.items():
        src += "OUT[%s]=(%s);\n" % (json.dumps(k), v)
    src += "process.stdout.write(JSON.stringify(OUT));\n"
    fd, p = tempfile.mkstemp(suffix=".js")
    os.close(fd)
    io.open(p, "w", encoding="utf-8", newline="").write(src)
    try:
        r = subprocess.run(["node", p], capture_output=True)
        if r.returncode != 0:
            raise SystemExit("node 평가 실패:\n" + r.stderr.decode("utf-8", "replace"))
        return json.loads(r.stdout.decode("utf-8"))
    finally:
        os.remove(p)


# ------------------------------------------------- 평탄화 / 정규화
def ws(s):
    return re.sub(r"\s+", " ", s).strip()


def flatten(obj, path="$", out=None):
    """{경로: 스칼라값} — 리스트 순서·딕셔너리 키까지 전부 경로로 편다."""
    out = {} if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(v, "%s.%s" % (path, k), out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            flatten(v, "%s[%d]" % (path, i), out)
    else:
        out[path] = ws(obj) if isinstance(obj, str) else obj
    return out


def compare(label, a, b, name_a, name_b):
    """평탄화 dict 2개를 1:1 대조. (동일수, 차이목록)"""
    ka, kb = set(a), set(b)
    diffs = []
    for k in sorted(ka - kb):
        diffs.append("  %s 에만 있음  %s = %r" % (name_a, k, a[k]))
    for k in sorted(kb - ka):
        diffs.append("  %s 에만 있음  %s = %r" % (name_b, k, b[k]))
    same = 0
    for k in sorted(ka & kb):
        if a[k] == b[k]:
            same += 1
        else:
            diffs.append("  값 다름  %s\n      %s: %r\n      %s: %r"
                         % (k, name_a, a[k], name_b, b[k]))
    print("[%s] 항목 %d개 대조 — 동일 %d · 차이 %d"
          % (label, max(len(ka), len(kb)), same, len(diffs)))
    for d in diffs:
        print(d)
    return len(diffs) == 0


# ------------------------------------------------- HTML 안 원문 조각(이동 대상 아님)
def def_table(html):
    m = re.search(r"<thead><tr><th>책의 표현.*?</table>", html, re.S)
    return ws(m.group(0)) if m else ""


def static_labels(html):
    """verify_source_integrity.extract() 의 라벨 추출과 같은 규칙."""
    out = []
    for t in re.findall(
            r'<input type="checkbox"[^>]*><span class="txt">(.*?)</span></label>', html, re.S):
        t = re.sub(r'<small class="scwhy"></small>', "", t)
        t = re.sub(r'<span class="tag[^>]*>.*?</span>', "", t, flags=re.S)
        t = ws(t)
        if t and "'+" not in t and "esc(" not in t:
            out.append(t)
    return out


def rule_labels(data):
    """DATA 안 규칙 라벨(t:) 전체 — 종목·그룹별로."""
    out = []
    for prod, d in data.items():
        for grp in ("filter", "entry", "avoid", "caution"):
            for i, it in enumerate(d.get(grp, [])):
                out.append(("%s.%s[%d]" % (prod, grp, i), ws(it["t"]), it.get("ref")))
    return out


# ------------------------------------------------- 실행
def main(argv):
    slug = "etf"
    if "--slug" in argv:
        slug = argv[argv.index("--slug") + 1]

    after_path = os.path.join(BASE, "%s-playbook.html" % slug)
    rules_path = os.path.join(BASE, "books", slug, "rules.json")
    repo = os.path.dirname(BASE)
    rel = "%s/%s-playbook.html" % (os.path.basename(BASE), slug)

    r = subprocess.run(["git", "-C", repo, "show", "HEAD:%s" % rel], capture_output=True)
    if r.returncode != 0:
        raise SystemExit("분리 전 HTML 을 못 꺼냈습니다: " + r.stderr.decode("utf-8", "replace"))
    before = r.stdout.decode("utf-8")
    after = read_text(after_path)
    rules = json.loads(read_text(rules_path))

    print("분리 전 HTML : git HEAD:%s  (%d자)" % (rel, len(before)))
    print("분리 후 HTML : %s  (%d자)" % (os.path.basename(after_path), len(after)))
    print("규칙 JSON    : books/%s/rules.json  (%d자)\n" % (slug, len(read_text(rules_path))))

    ok = True

    # ── A. 규칙 데이터: 분리 전 JS 리터럴 ↔ rules.json
    lits = const_spans(before)
    missing = [n for n in NAMES if n not in lits]
    if missing:
        raise SystemExit("분리 전 HTML 에서 %s 를 못 찾았습니다." % ", ".join(missing))
    print("분리 전 HTML 의 JS 상수: %s" % ", ".join(sorted(lits)))
    src_vals = eval_js({n: lits[n] for n in NAMES})

    for n in NAMES:
        ok &= compare("A-%s" % n,
                      flatten(src_vals[n], "$"),
                      flatten(rules.get(n), "$"),
                      "분리전 JS", "rules.json")
    extra = [k for k in rules if k not in NAMES]
    if extra:
        print("[A] ⚠ rules.json 에 원본에 없던 최상위 키: %s" % ", ".join(extra))
        ok = False
    print()

    # ── A-2. 규칙 라벨(t:) 낱개 대조 — 갯수와 ref 보유 현황까지 눈으로 볼 수 있게
    lb_before = rule_labels(src_vals["DATA"])
    lb_after = rule_labels(rules["DATA"])
    print("[A-labels] 규칙 라벨(t:) — 분리전 %d개 / rules.json %d개"
          % (len(lb_before), len(lb_after)))
    if lb_before == lb_after:
        nref = sum(1 for _, _, rf in lb_after if rf)
        print("  ✓ %d개 전부 1:1 동일 (위치·문구·ref 모두). ref 있음 %d · 없음 %d"
              % (len(lb_after), nref, len(lb_after) - nref))
        for loc, t, rf in lb_after:
            print("    %-18s %-8s %s" % (loc, ("ref=" + rf) if rf else "ref없음", t))
    else:
        ok = False
        for x, y in zip(lb_before, lb_after):
            if x != y:
                print("  ✗ %r  vs  %r" % (x, y))
        if len(lb_before) != len(lb_after):
            print("  ✗ 갯수가 다름")
    print()

    # ── B. 규칙 근거표 (HTML 에 그대로 남아 있어야 함)
    dt_b, dt_a = def_table(before), def_table(after)
    print("[B] 규칙 근거표 — 분리전 %d자 / 분리후 %d자" % (len(dt_b), len(dt_a)))
    if dt_b and dt_b == dt_a:
        rows = len(re.findall(r"<tr>", dt_a)) - 1
        print("  ✓ 완전 동일 (행 %d개). 이 표는 옮기지 않았고 건드리지도 않았다." % rows)
    else:
        ok = False
        print("  ✗ 다름 또는 못 찾음")
        print("    분리전: %r" % dt_b[:400])
        print("    분리후: %r" % dt_a[:400])
    print()

    # ── C. 정적 체크 항목 라벨(스코어카드 등)
    lb, la = static_labels(before), static_labels(after)
    print("[C] 정적 체크 항목 라벨 — 분리전 %d개 / 분리후 %d개" % (len(lb), len(la)))
    if lb == la:
        print("  ✓ %d개 전부 동일" % len(la))
        for t in la:
            print("    · %s" % t)
    else:
        ok = False
        for i in range(max(len(lb), len(la))):
            x = lb[i] if i < len(lb) else "(없음)"
            y = la[i] if i < len(la) else "(없음)"
            if x != y:
                print("  ✗ [%d] 분리전 %r / 분리후 %r" % (i, x, y))
    print()

    # ── D. 주입된 사본 ↔ rules.json
    m = re.search(r'<script type="application/json" id="rules">\s*(.*?)\s*</script>',
                  after, re.S)
    print("[D] 분리 후 HTML 의 주입 사본 ↔ rules.json")
    if not m:
        ok = False
        print("  ✗ id=\"rules\" 블록이 없음")
    else:
        copy = json.loads(m.group(1))
        ok &= compare("D", flatten(copy), flatten(rules), "HTML 사본", "rules.json")
    print()

    print("=" * 68)
    if ok:
        nrules = len(lb_after)
        print("결론: 규칙 %d개(+MODES %d · SCSRC %d · STEPNAME %d)를 옮겼고,"
              % (nrules, len(rules["MODES"]), len(rules["SCSRC"]), len(rules["STEPNAME"])))
        print("      대조한 모든 항목이 1:1 완전 동일하다. 원문은 한 글자도 안 바뀌었다.")
        print("      (담는 그릇만 HTML 안 JS 리터럴 → books/%s/rules.json 으로 바뀜)" % slug)
    else:
        print("결론: 차이가 있다. 위 목록을 보고 고칠 것. '대체로 같다'는 결과가 아니다.")
    print("=" * 68)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
