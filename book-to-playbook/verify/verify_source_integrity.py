#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""저자 원문 무결성 검사 — 모든 책 공통.

## 왜 있나

이 파이프라인의 전제는 **책 = 사양, 코드 = 구현** 이다.
그런데 자동판정을 붙이다 보면 "구현이 보는 것"과 "책이 시킨 것"이 어긋나는 순간이
반드시 온다. 그때 **책 문구를 구현에 맞춰 고치고 싶은 유혹**이 생긴다.

실제 사고(2026-09-22):
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

책 페이지 HTML의 `#src` — 플레이북 마크다운(책 본문을 소절별로 정리한 저자의 말)을 해시로 고정한다.
체크리스트는 조건 트리(books/<slug>/tree.json)라 저자 문구가 아니라 기계가 실행하는 규칙이다 —
트리가 원문 뜻대로 옮겨졌는지는 글자 해시가 아니라 verify.verify_tree 가 실행으로 검사한다.
판정 수치(verdict-data)·UI 코드는 매일 바뀌므로 검사 대상이 아니다.

## 사용

    python -m verify.verify_source_integrity              # 검사 (다르면 종료코드 1)
    python -m verify.verify_source_integrity --accept --why "사유"  # 원문을 의도적으로 고쳤을 때 기준 갱신

기준값은 `source_baseline.json`에 저장되며 **커밋 대상**이다.
새 책을 추가하면 처음 한 번 `--accept --why "사유"` 로 기준을 등록한다.

`--accept` 는 원문 해시 기준을 덮어쓰는 가장 위험한 인간 승인 지점이다.
`--why "사유"` 없이는 갱신을 거부한다 — 사유가 기록되지 않는 accept 는
진짜 원문 수정과 무심코 누른 accept 를 구분할 방법을 없앤다.
사유는 `source_baseline.json` 의 `accept_log` 배열에 타임스탬프와 함께 append 된다.
"""
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime

from shared import paths  # noqa: F401  (경로·UTF-8 출력 고정)
from shared.paths import BASE
from authoring.playbook.pages import book_pages

# 기준 해시는 '만드는' 쪽(authoring)의 소유물이라 authoring/playbook/ 에 산다(커밋 대상).
# 이 검사기는 verify/ 로 옮겼으므로 __file__ 이 아니라 BASE 기준으로 그 파일을 가리킨다.
BASELINE = os.path.join(BASE, "authoring", "playbook", "source_baseline.json")


def extract(html, slug=None):
    """저자 문구에 해당하는 조각 — 플레이북 마크다운 본문(#src)."""
    m = re.search(r'<script type="text/markdown" id="src">(.*?)</script>', html, re.S)
    return {"src": m.group(1).strip() if m else ""}


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


NAMES = {"src": "플레이북 본문(#src)"}


def main(argv):
    accept = "--accept" in argv
    why = None
    if "--why" in argv:
        i = argv.index("--why")
        why = argv[i + 1] if i + 1 < len(argv) else None
    # --accept 없이 --why 만 있는 건 허용(무해). --accept 와 함께 쓸 때만 필수.
    if accept and not why:
        print("오류: --accept 사용 시 --why \"<사유>\" 가 필요합니다.", file=sys.stderr)
        print("  예) python -m verify.verify_source_integrity --accept --why \"오탈자 수정\"", file=sys.stderr)
        print("사유 없는 기준 갱신은 거부됩니다 — 진짜 원문 수정과 실수를 구분할 수 없습니다.", file=sys.stderr)
        return 1

    pages = book_pages()
    if not pages:
        print("검사할 책 페이지를 찾지 못했습니다.", file=sys.stderr)
        return 2

    base = load_baseline()
    cur, bad, new = {}, [], []

    for slug, path in sorted(pages.items()):
        parts = extract(io.open(path, encoding="utf-8").read(), slug)
        d = digest(parts)
        cur[slug] = d
        old = base.get(slug)
        if old is None:
            new.append(slug)
            print("· %-8s 기준 없음 — 새 책 (--accept 로 등록)" % slug)
            continue
        if not parts["src"]:
            # 지킬 본문이 없으면 보호가 없다는 뜻이다. 통과로 찍으면 보호 상실이 조용히 지나간다.
            bad.append((slug, ["src"], parts, old, d))
            print("✗ %-8s 플레이북 본문(#src)이 비어 있음 — 지킬 원문이 없습니다(보호 상실)." % slug)
            continue
        diff = [k for k in d if old.get(k) != d[k]]
        if diff:
            bad.append((slug, diff, parts, old, d))
            print("✗ %-8s 원문이 바뀜: %s" % (slug, ", ".join(NAMES.get(k, k) for k in diff)))
        else:
            print("✓ %-8s 원문 그대로 — 플레이북 본문 %d줄" % (slug, len(parts["src"].splitlines())))

    if accept:
        # 감사 기록: accept_log 는 slug 키와 충돌하지 않는 전용 최상위 키.
        # cur 에는 slug 키만 들어있으므로 load_baseline() 의 accept_log 를 직접 넣는다.
        existing_log = load_baseline().get("accept_log", [])
        log_entry = {"ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "why": why}
        to_save = dict(cur)
        to_save["accept_log"] = existing_log + [log_entry]
        save_baseline(to_save)
        print("\n기준 갱신 완료 → %s" % os.path.basename(BASELINE))
        print("  감사 기록: %s — %s" % (log_entry["ts"], why))
        for slug in sorted(pages):
            print("  · %-8s 플레이북 본문(#src)을 기준으로 고정" % slug)
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
