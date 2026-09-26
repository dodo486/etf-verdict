#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""규칙 JSON을 책 페이지 HTML에 주입한다(빌드 시) — `inject_nav.py` 와 같은 자리.

## 왜 있나

규칙이 HTML 안 JS 리터럴(`const DATA = [...]`)로 박혀 있으면 읽는 쪽이 책마다
달라진다. 검사기가 etf 전용이 된 원인이 정확히 그것이다(계약 2).
그래서 **규칙은 파일로 나온다**: `books/<slug>/rules.json` 이 단일 진실(SSOT)이다.

다만 이 페이지들은 **자체완결**이어야 한다 — 오프라인·아티팩트에서도 떠야 하므로
HTML 이 JSON 을 fetch 하면 안 된다. 그래서 파일을 fetch 하는 대신
`<script type="application/json" id="rules">` 블록으로 **사본을 주입**한다.
HTML 안의 것은 사본일 뿐이고, 고치는 곳은 언제나 JSON 파일이다.

사본이 있는 한 **드리프트**(파일과 페이지가 갈라짐)가 생길 수 있다. 그래서
`--check` 를 둔다. 조용히 갈라지게 두지 않는다.

## 사용

    python inject_rules.py etf            # JSON → HTML 의 id="rules" 블록에 주입
    python inject_rules.py etf --check    # 사본과 파일이 다르면 exit 1
    python inject_rules.py etf --show     # 주입될 블록을 표준출력으로

`--target <경로>` 로 대상 HTML 을 직접 지정할 수 있다(기본: `<slug>-playbook.html`).
import 해서 `inject(html, slug)` / `check(html, slug)` 로도 쓴다.
"""
import io
import json
import os
import re
import sys

import paths
from paths import BASE, read_text, write_text

BLOCK_RE = re.compile(
    r'[ \t]*<script type="application/json" id="rules">.*?</script>[ \t]*\n?',
    re.S)

# #src 마크다운 블록 뒤가 주입 자리 — 이 블록을 읽는 <script> 들보다 앞이어야 한다
# (DOM 파싱 시점에 이미 있어야 getElementById 가 잡는다).
AFTER_RE = re.compile(r'<script type="text/markdown" id="src">.*?</script>\n', re.S)
FIRST_SCRIPT_RE = re.compile(r'\n<script>\n')


def rules_path(slug):
    return os.path.join(BASE, "books", slug, "rules.json")


def html_path(slug):
    return os.path.join(BASE, "%s-playbook.html" % slug)


# 프런트(#rules)는 t/ref/k/subs 만 읽는다. rules.json 이 자기완결로 승격되며 규칙마다
# 백엔드 판정 필드(metric·metric_candidates·combine)를 품는데, 이건 해석기/엔진 몫이라
# HTML 에는 넣지 않는다(시트 계약·무결성 해시 불변 유지).
_BACKEND_KEYS = ("metric", "metric_candidates", "combine")


def _strip_backend(obj):
    data = obj.get("DATA") if isinstance(obj, dict) else None
    if isinstance(data, dict):
        for cfg in data.values():
            if not isinstance(cfg, dict):
                continue
            for items in cfg.values():
                if not isinstance(items, list):
                    continue
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    for k in _BACKEND_KEYS:
                        it.pop(k, None)
                    for s in it.get("subs") or []:
                        if isinstance(s, dict):
                            for k in _BACKEND_KEYS:
                                s.pop(k, None)
    return obj


def load_rules(slug):
    p = rules_path(slug)
    if not os.path.exists(p):
        raise SystemExit("규칙 파일이 없습니다: %s" % p)
    return _strip_backend(json.loads(read_text(p)))


def dumps(obj):
    """파일에 쓰는 것과 **같은** 직렬화. 파일/사본이 글자까지 같아야 대조가 쉽다."""
    return json.dumps(obj, ensure_ascii=False, indent=2)


def canon(obj):
    """의미 비교용 정규형(키 순서·들여쓰기 무시)."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def block_text(obj):
    """주입할 `<script type="application/json">` 블록 전체.

    `</script>` 가 값 안에 있으면 그 자리에서 스크립트가 끊겨 페이지가 깨진다.
    JSON 은 `\\/` 를 `/` 의 이스케이프로 허용하므로 `</` 를 `<\\/` 로 적으면
    **파싱 결과는 한 글자도 다르지 않으면서** 태그가 끊기지 않는다.
    """
    body = dumps(obj).replace("</", "<\\/")
    return '<script type="application/json" id="rules">\n%s\n</script>\n' % body


def extract(html):
    """HTML 안 사본 → 파이썬 값. 블록이 없으면 None."""
    m = re.search(r'<script type="application/json" id="rules">\s*(.*?)\s*</script>',
                  html, re.S)
    if not m:
        return None
    return json.loads(m.group(1))


def inject(html, slug, obj=None):
    obj = load_rules(slug) if obj is None else obj
    blk = block_text(obj)
    if BLOCK_RE.search(html):
        return BLOCK_RE.sub(lambda _: blk, html, count=1)
    m = AFTER_RE.search(html)
    if m:
        return html[:m.end()] + "\n" + blk + html[m.end():]
    m = FIRST_SCRIPT_RE.search(html)
    if m:
        return html[:m.start() + 1] + blk + html[m.start() + 1:]
    raise SystemExit("주입 위치를 못 찾았습니다(#src 도 <script> 도 없음)")


def check(html, slug):
    """(ok, 메시지) — 사본과 파일이 의미적으로 같은가."""
    cur = extract(html)
    if cur is None:
        return False, 'HTML 에 <script type="application/json" id="rules"> 블록이 없음'
    want = load_rules(slug)
    if canon(cur) == canon(want):
        return True, "사본 == books/%s/rules.json (최상위 키 %d개)" % (slug, len(want))
    diffs = _diff(want, cur, "$")
    return False, "드리프트 %d곳\n%s" % (len(diffs), "\n".join("    " + d for d in diffs[:40]))


def page_check(html, obj):
    """페이지가 이 블록으로 실제 돌 수 있는 상태인가 — 브라우저 없이 보는 범위.

    1) 블록이 유효한 JSON 인가
    2) 블록 안에 태그를 끊는 `</script` 가 날것으로 들어있지 않은가
    3) 블록이 그것을 읽는 `<script>` 들보다 **앞**에 있는가
       (DOM 파싱 순서상 뒤에 있으면 getElementById 가 null 이다)
    4) 페이지가 `RULES.X` 로 참조하는 키가 JSON 에 전부 있는가
    """
    problems = []
    m = re.search(r'<script type="application/json" id="rules">(.*?)</script>', html, re.S)
    if not m:
        return ['id="rules" 블록 없음']
    raw = m.group(1)
    try:
        json.loads(raw)
    except ValueError as e:
        problems.append("블록이 유효한 JSON 이 아님: %s" % e)
    if re.search(r"</\s*script", raw, re.I):
        problems.append("블록 안에 `</script` 가 날것으로 있음 — 태그가 거기서 끊긴다")

    readers = [mm.start() for mm in re.finditer(
        r"getElementById\('rules'\)|getElementById\(\"rules\"\)", html)]
    late = [p for p in readers if p < m.start()]
    if late:
        problems.append("블록보다 앞에서 읽는 곳 %d군데 — DOM 파싱 시점에 아직 없다" % len(late))
    if not readers:
        problems.append("블록을 읽는 코드가 없음 — 주입만 하고 아무도 안 쓴다")

    used = sorted(set(re.findall(r"RULES\.([A-Za-z_$][\w$]*)", html)))
    miss = [k for k in used if k not in obj]
    if miss:
        problems.append("페이지가 참조하는데 JSON 에 없는 키: %s" % ", ".join(miss))
    unused = [k for k in obj if k not in used]
    if unused:
        problems.append("JSON 에만 있고 페이지가 안 쓰는 키: %s" % ", ".join(unused))
    return problems


def has_rules(slug):
    """이 책이 규칙을 파일로 분리했는가(= 드리프트 검사 대상인가)."""
    return os.path.exists(rules_path(slug))


def gate(html, slug):
    """발행 게이트 — (ok, [메시지]) . `inject_rules.py <slug> --check` 와 같은 검사.

    `publish_pages.py` · `build_home.py` 가 HTML 을 내보내기 **전에** 부른다.
    JSON(단일 진실)과 HTML 사본이 갈라진 채로 발행되면, 배포본만 옛 규칙을 들고
    돌아다니고 아무도 모른다. 조용히 지나가게 두지 않는다 — 갈라지면 발행을 멈춘다.

    규칙을 아직 분리하지 않은 책(rules.json 없음)은 **검사 대상이 아니라고 말하고**
    통과시킨다. '미적용'을 '통과'로 적지 않기 위해 메시지에 그렇게 남긴다.
    """
    if not has_rules(slug):
        return True, ["· %-8s 규칙 분리 전 — 드리프트 검사 미적용(통과 아님)" % slug]
    obj = load_rules(slug)
    ok, msg = check(html, slug)
    lines = ["%s %-8s %s" % ("✓" if ok else "✗", slug, msg)]
    probs = page_check(html, obj)
    if probs:
        ok = False
        lines.append("✗ %-8s 페이지 점검 %d건" % (slug, len(probs)))
        lines += ["    · %s" % p for p in probs]
    else:
        lines.append("✓ %-8s 페이지 점검 통과 (JSON 유효 · 블록이 읽는 코드보다 앞)" % slug)
    if not ok:
        lines.append("고치는 곳은 books/%s/rules.json 이고, 페이지는 주입으로 맞춘다:"
                     "  python inject_rules.py %s" % (slug, slug))
    return ok, lines


def _diff(a, b, path):
    """파일(a) 기준으로 사본(b) 이 어디가 다른지 경로 단위로."""
    out = []
    if type(a) is not type(b):
        return ["%s: 타입 다름 %s vs %s" % (path, type(a).__name__, type(b).__name__)]
    if isinstance(a, dict):
        for k in a:
            if k not in b:
                out.append("%s.%s: 사본에 없음" % (path, k))
            else:
                out += _diff(a[k], b[k], "%s.%s" % (path, k))
        out += ["%s.%s: 파일에 없음" % (path, k) for k in b if k not in a]
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append("%s: 길이 %d vs %d" % (path, len(a), len(b)))
        for i in range(min(len(a), len(b))):
            out += _diff(a[i], b[i], "%s[%d]" % (path, i))
    elif a != b:
        out.append("%s: %r vs %r" % (path, a, b))
    return out


def main(argv):
    if not argv or argv[0].startswith("-"):
        print(__doc__.strip().split("## 사용")[-1].strip(), file=sys.stderr)
        return 2
    slug = argv[0]
    target = html_path(slug)
    if "--target" in argv:
        target = argv[argv.index("--target") + 1]

    if "--show" in argv:
        sys.stdout.write(block_text(load_rules(slug)))
        return 0

    if not os.path.exists(target):
        print("대상 HTML 이 없습니다: %s" % target, file=sys.stderr)
        return 2
    html = read_text(target)

    if "--check" in argv:
        ok, msg = check(html, slug)
        print("%s %-8s %s" % ("✓" if ok else "✗", slug, msg))
        probs = page_check(html, load_rules(slug))
        if probs:
            ok = False
            print("✗ %-8s 페이지 점검 %d건" % (slug, len(probs)))
            for p in probs:
                print("    · %s" % p)
        else:
            used = sorted(set(re.findall(r"RULES\.([A-Za-z_$][\w$]*)", html)))
            print("✓ %-8s 페이지 점검 — JSON 유효 · 블록이 읽는 코드보다 앞 · "
                  "참조 키 %s 전부 존재 · `</script` 없음" % (slug, "/".join(used)))
        if not ok:
            print("\n고치는 곳은 books/%s/rules.json 이고, 페이지는 주입으로 맞춘다:"
                  "\n    python inject_rules.py %s" % (slug, slug))
        return 0 if ok else 1

    out = inject(html, slug)
    if out == html:
        print("· %-8s 변경 없음 (%s)" % (slug, os.path.basename(target)))
        return 0
    write_text(target, out)
    print("✓ %-8s 규칙 주입 → %s (%d → %d자)"
          % (slug, os.path.basename(target), len(html), len(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
