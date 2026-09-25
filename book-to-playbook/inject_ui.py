#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""책-무관 공유 UI JS(들)를 책 페이지 HTML에 주입한다(빌드 시) — `inject_rules.py` 와 같은 자리.

## 왜 있나

플레이북↔실전 시트를 굴리는 자바스크립트가 `etf-playbook.html` 안에 inline `<script>` 로
**하드카피**돼 있었다. 다른 책엔 그게 없거나 사본이 어긋난다. 그래서 etf 에서 버그를
고쳐도 다른 책으로 **전파되지 않는다**.

그래서 이 UI JS 들은 **파일로 나온다**: `ui/<name>.js` 가 각자의 단일 진실(SSOT)이다.
버그는 거기서 한 번 고치면 모든 책에 주입돼 퍼진다. 지금 두 구획이 있다:

  * `review-ui`    — 좌우 분할·소절→시트 점프·노란 bullet 매핑·반영 현황 요약표
  * `checklist-ui` — 탭 전환·스코어카드·진입 체크리스트 렌더·STEP3 계산기·메모

다만 이 페이지들은 **자체완결**이어야 한다 — 오프라인·아티팩트에서도 떠야 하므로
런타임에 외부 파일을 참조(`<script src>`)하면 안 된다. 그래서 파일을 참조하는 대신
센티넬 마커 사이에 `<script>` + 파일 내용 + `</script>` 로 **사본을 inline** 한다.

    <!-- INJECT:review-ui -->
    <script>...(ui/review-ui.js 의 사본)...</script>
    <!-- /INJECT:review-ui -->

    <!-- INJECT:checklist-ui -->
    <script>...(ui/checklist-ui.js 의 사본)...</script>
    <!-- /INJECT:checklist-ui -->

HTML 안의 것은 사본일 뿐이고, 고치는 곳은 언제나 `ui/<name>.js` 다.
사본이 있는 한 **드리프트**(파일과 페이지가 갈라짐)가 생길 수 있어 `--check` 를 둔다.

## 구획 등록

`REGIONS` 에 `이름 → ui 파일` 로 등록한다. 대상 HTML 에 그 이름의 센티넬 구간이
있으면 주입/검사하고, 없으면 조용히 건너뛴다(책마다 있는 구획이 다를 수 있으므로).
새 공유 UI 를 추가하려면 `ui/<name>.js` 를 만들고 여기 한 줄만 더한다.

## 사용

    python inject_ui.py <target.html>            # 모든 구획을 ui/<name>.js 로 갱신 주입
    python inject_ui.py <target.html> --check    # 사본과 파일이 다르면 exit 1

책-무관: 대상 HTML 경로만 받는다(etf 하드코딩 없음).
import 해서 `inject(html)` / `check(html)` 로도 쓴다(모든 구획을 한 번에 처리).

## 빌드 배선

`publish_pages.py` 가 발행 직전 `inject_nav`·`inject_rules` 와 나란히 `inject_ui.inject(html)`
를 부른다(그 파일 참고). 새 책을 발행 파이프라인에 얹을 때도 같은 자리에 추가한다.
"""
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))

# 이름 → ui/<name>.js. 대상 HTML 에 그 이름의 센티넬 구간이 있을 때만 처리한다.
REGIONS = {
    "review-ui": os.path.join(BASE, "ui", "review-ui.js"),
    "checklist-ui": os.path.join(BASE, "ui", "checklist-ui.js"),
}


def _begin(name):
    return "<!-- INJECT:%s -->" % name


def _end(name):
    return "<!-- /INJECT:%s -->" % name


def _region_re(name):
    # 센티넬 사이 전체(마커 포함)를 잡는다. 마커는 그대로 두고 안쪽만 갈아끼운다.
    return re.compile(re.escape(_begin(name)) + r".*?" + re.escape(_end(name)), re.S)


def read_text(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def write_text(p, s):
    # 항상 UTF-8 + LF (OS 무관 동일 결과 — inject_rules/paths 와 동일 규약)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)


def load_ui(name):
    path = REGIONS[name]
    if not os.path.exists(path):
        raise SystemExit("UI SSOT 파일이 없습니다: %s" % path)
    return read_text(path)


def block_text(name, js=None):
    """센티넬 마커 + inline `<script>` 사본. 주입 결과와 글자까지 같아야 대조가 쉽다."""
    js = load_ui(name) if js is None else js
    return "%s\n<script>\n%s\n</script>\n%s" % (_begin(name), js, _end(name))


def has_region(html, name):
    return _region_re(name).search(html) is not None


def extract(html, name):
    """HTML 안 센티넬 구간의 inline JS → 문자열. 구간/스크립트가 없으면 None."""
    m = _region_re(name).search(html)
    if not m:
        return None
    inner = m.group(0)
    sm = re.search(r"<script>\n(.*?)\n</script>", inner, re.S)
    if not sm:
        return None
    return sm.group(1)


def inject_region(html, name, js=None):
    """한 구획만 최신 사본으로 교체한다. 그 구획이 없으면 그대로 돌려준다."""
    rgx = _region_re(name)
    if not rgx.search(html):
        return html
    js = load_ui(name) if js is None else js
    blk = block_text(name, js)
    return rgx.sub(lambda _: blk, html, count=1)


def inject(html, js=None):
    """대상 HTML 에 존재하는 모든 등록 구획을 최신 사본으로 교체해 돌려준다.

    하위호환: `js` 를 주면 `review-ui` 구획에만 그 사본을 쓴다(과거 시그니처).
    """
    out = html
    for name in REGIONS:
        region_js = js if (js is not None and name == "review-ui") else None
        out = inject_region(out, name, region_js)
    return out


def check(html):
    """(ok, 메시지) — 페이지 안 존재하는 모든 구획 사본이 각 ui/<name>.js 와 같은가."""
    present = [n for n in REGIONS if has_region(html, n)]
    if not present:
        return False, "HTML 에 등록된 INJECT 센티넬 구간이 하나도 없음 (%s)" % ", ".join(REGIONS)
    msgs = []
    ok_all = True
    for name in present:
        cur = extract(html, name)
        want = load_ui(name)
        if cur is None:
            ok_all = False
            msgs.append("%s: 구간 안 <script> 없음" % name)
        elif cur == want:
            msgs.append("%s: 사본 == ui/%s.js (%d자)" % (name, name, len(want)))
        else:
            ok_all = False
            msgs.append(
                "%s: 드리프트 — 페이지 사본(%d자) != ui/%s.js(%d자)"
                % (name, len(cur), name, len(want)))
    tail = ""
    if not ok_all:
        tail = ("\n    고치는 곳은 ui/<name>.js 이고, 페이지는 주입으로 맞춘다:"
                "  python inject_ui.py <target.html>")
    return ok_all, "; ".join(msgs) + tail


def main(argv):
    if not argv or argv[0].startswith("-"):
        print(__doc__.strip().split("## 사용")[-1].strip(), file=sys.stderr)
        return 2
    target = argv[0]
    if not os.path.exists(target):
        print("대상 HTML 이 없습니다: %s" % target, file=sys.stderr)
        return 2
    html = read_text(target)
    name = os.path.basename(target)

    if "--check" in argv:
        ok, msg = check(html)
        print("%s %-20s %s" % ("✓" if ok else "✗", name, msg))
        return 0 if ok else 1

    out = inject(html)
    if out == html:
        print("· %-20s 변경 없음" % name)
        return 0
    write_text(target, out)
    present = [n for n in REGIONS if has_region(html, n)]
    print("✓ %-20s 주입 (%s) (%d → %d자)"
          % (name, ", ".join(present), len(html), len(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
