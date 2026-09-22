#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""저자 원문 무결성 검사 — 모든 책 공통.

## 왜 있나

이 파이프라인의 전제는 **책 = 사양, 코드 = 구현** 이다.
그런데 자동판정을 붙이다 보면 "구현이 보는 것"과 "책이 시킨 것"이 어긋나는 순간이
반드시 온다. 그때 **책 문구를 구현에 맞춰 고치고 싶은 유혹**이 생긴다.

실제 사고(2026-09-22, etf):
  시트 라벨은 저자 2-6대로 "나스닥 **선물** 방향"이었는데 파이프라인은 지수(^NDX)를
  보고 있었다. 라벨을 "나스닥100 방향"으로 바꿔 구현에 맞췄다.
  → 불일치가 사라진 게 아니라 **안 보이게** 됐고, 커버리지 배지(✅반영)까지 거짓이 됐다.
  (실제로는 NQ=F·ES=F 선물이 야후에서 그냥 받아졌다. 구할 수 있는 걸 안 구하고 사양을 깎은 것)

## 규칙

원문과 구현이 어긋나면 선택지는 둘뿐이다.
  ① 구현을 원문에 맞춘다
  ② 미구현/수동으로 남기고 그렇게 **표시**한다
**원문 문구 수정은 선택지가 아니다.**

## 무엇을 지키나

책 페이지 HTML에서 '저자의 말'에 해당하는 블록만 골라 해시로 고정한다.
  - `#src`        플레이북 마크다운(책 본문 전체)
  - 규칙 근거표    "책의 표현 → 정량 정의" 표(저자 문구 인용)
  - 체크 항목 라벨  스코어카드/진입·회피 체크박스에 적힌 규칙 문구

판정 수치(verdict-data)·커버리지 노트·UI 코드는 매일 바뀌므로 검사 대상이 아니다.

## 사용

    python verify_source_integrity.py            # 검사 (다르면 종료코드 1)
    python verify_source_integrity.py --accept   # 원문을 의도적으로 고쳤을 때 기준 갱신
    python verify_source_integrity.py --show etf # 해당 책이 가진 라벨 목록 출력

기준값은 `source_baseline.json`에 저장되며 **커밋 대상**이다.
새 책을 추가하면 처음 한 번 `--accept` 로 기준을 등록한다.
"""
import hashlib
import io
import json
import os
import re
import sys

import paths
from paths import BASE, PUBLIC

BASELINE = os.path.join(BASE, "source_baseline.json")


# ---------------------------------------------------------------- 책 찾기
def book_pages():
    """{slug: html경로} — books.json 기준, 배포본(PUBLIC/<slug>/index.html) 우선."""
    manifest = json.loads(io.open(os.path.join(BASE, "books.json"), encoding="utf-8").read())
    out = {}
    for b in manifest.get("books", []):
        slug = b["slug"]
        for cand in (os.path.join(PUBLIC, slug, "index.html"),
                     os.path.join(BASE, "%s-playbook.html" % slug)):
            if os.path.exists(cand):
                out[slug] = cand
                break
    return out


# ---------------------------------------------------------------- 원문 블록 추출
def _const_blocks(html):
    """`const NAME = [...]` / `{...}` 중 대문자 상수만 뽑는다.

    이 템플릿은 책의 규칙 문구(필터·진입·회피·청산·정의·루틴)를 전부 대문자 const
    배열/객체에 담는다. 체크박스 라벨이 JS로 그려지는 책(supply 등)은 여기가 원문이다.
    """
    out = {}
    for m in re.finditer(r'\n\s*const ([A-Z][A-Z0-9_]*)\s*=\s*([\[{])', html):
        name, open_ch = m.group(1), m.group(2)
        close_ch = ']' if open_ch == '[' else '}'
        i = m.end() - 1
        depth, j, in_s, q, esc = 0, i, False, '', False
        while j < len(html):
            c = html[j]
            if in_s:
                if esc:
                    esc = False
                elif c == '\\':
                    esc = True
                elif c == q:
                    in_s = False
            else:
                if c in ('"', "'", '`'):
                    in_s, q = True, c
                elif c == open_ch:
                    depth += 1
                elif c == close_ch:
                    depth -= 1
                    if depth == 0:
                        break
            j += 1
        out[name] = re.sub(r'\s+', ' ', html[i:j + 1])
    return out


def extract(html):
    """저자 문구에 해당하는 조각만 뽑아 dict로."""
    parts = {}

    # 1) 플레이북 마크다운 본문
    m = re.search(r'<script type="text/markdown" id="src">(.*?)</script>', html, re.S)
    parts["src"] = m.group(1).strip() if m else ""

    # 2) 규칙 근거표 — "책의 표현 / 정량 정의" 표 전체
    m = re.search(r'<thead><tr><th>책의 표현.*?</table>', html, re.S)
    parts["def_table"] = m.group(0).strip() if m else ""

    # 3) 정적 체크 항목 라벨(HTML에 직접 박힌 것)
    labels = re.findall(r'<input type="checkbox"[^>]*><span class="txt">(.*?)</span></label>',
                        html, re.S)
    clean = []
    for t in labels:
        t = re.sub(r'<small class="scwhy"></small>', '', t)          # 값이 주입되는 빈 칸
        t = re.sub(r'<span class="tag[^>]*>.*?</span>', '', t, flags=re.S)  # 자동/직접 뱃지
        t = re.sub(r'\s+', ' ', t).strip()
        # JS 템플릿 조각(동적 렌더)은 라벨이 아니다 — 아래 rule_data 가 담당
        if t and "'+" not in t and 'esc(' not in t:
            clean.append(t)
    parts["labels"] = clean

    # 4) 규칙 데이터 — JS 상수에 담긴 필터·진입·회피·청산·정의·루틴 문구
    #    (체크리스트를 JS로 그리는 책은 여기가 원문이다)
    parts["rule_data"] = _const_blocks(html)
    return parts


def digest(parts):
    h = {}
    for k, v in parts.items():
        blob = (json.dumps(v, ensure_ascii=False, sort_keys=True)
                if isinstance(v, (list, dict)) else v)
        h[k] = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
    return h


# ---------------------------------------------------------------- 실행
def load_baseline():
    if os.path.exists(BASELINE):
        return json.loads(io.open(BASELINE, encoding="utf-8").read())
    return {}


def save_baseline(data):
    io.open(BASELINE, "w", encoding="utf-8", newline="\n").write(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n")


NAMES = {"src": "플레이북 본문(#src)", "def_table": "규칙 근거표",
         "labels": "체크 항목 라벨", "rule_data": "규칙 데이터(JS 상수)"}


def main(argv):
    accept = "--accept" in argv
    show = None
    if "--show" in argv:
        i = argv.index("--show")
        show = argv[i + 1] if i + 1 < len(argv) else None

    pages = book_pages()
    if not pages:
        print("검사할 책 페이지를 찾지 못했습니다.", file=sys.stderr)
        return 2

    if show:
        p = pages.get(show)
        if not p:
            print("그런 책이 없습니다: %s (있는 책: %s)" % (show, ", ".join(pages)))
            return 2
        parts = extract(io.open(p, encoding="utf-8").read())
        print("%s — 정적 라벨 %d개" % (show, len(parts["labels"])))
        for t in parts["labels"]:
            print("  ·", t[:150])
        print("%s — 규칙 데이터(JS 상수) %d개" % (show, len(parts["rule_data"])))
        for k, v in sorted(parts["rule_data"].items()):
            print("  · %-8s %d자  %s" % (k, len(v), v[:110]))
        return 0

    base = load_baseline()
    cur, bad, new = {}, [], []

    for slug, path in sorted(pages.items()):
        parts = extract(io.open(path, encoding="utf-8").read())
        d = digest(parts)
        cur[slug] = d
        old = base.get(slug)
        if old is None:
            new.append(slug)
            print("· %-8s 기준 없음 — 새 책 (--accept 로 등록)" % slug)
            continue
        diff = [k for k in d if old.get(k) != d[k]]
        if diff:
            bad.append((slug, diff, parts, old, d))
            print("✗ %-8s 원문이 바뀜: %s" % (slug, ", ".join(NAMES.get(k, k) for k in diff)))
        else:
            print("✓ %-8s 원문 그대로 — 라벨 %d · 규칙데이터 %d(%s)"
                  % (slug, len(parts["labels"]), len(parts["rule_data"]),
                     ", ".join(sorted(parts["rule_data"])) or "없음"))

    if accept:
        save_baseline(cur)
        print("\n기준 갱신 완료 → %s" % os.path.basename(BASELINE))
        print("원문을 **의도적으로** 고친 경우에만 이 커밋이 정당합니다.")
        return 0

    if bad:
        print("\n" + "=" * 68)
        print("저자 원문이 바뀌었습니다. 구현을 맞추려고 원문을 고친 것이라면 되돌리세요.")
        print("  ① 구현을 원문에 맞춘다   ② 미구현/수동으로 남기고 그렇게 표시한다")
        print("  원문 수정은 선택지가 아닙니다.")
        print("의도적인 원문 수정(오탈자·새 책 반영)이라면: --accept")
        print("=" * 68)
        return 1

    if new:
        print("\n새 책 %s 의 기준이 없습니다. --accept 로 등록하세요." % ", ".join(new))
        return 1

    print("\n전부 통과 — 저자 원문 무결.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
