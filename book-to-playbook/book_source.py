#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""책 원문 → 소절 단위 인덱스. "① 책 → 플레이북" 창작/누락 검사의 재료.

## 왜 있나

이 리포의 검사기들(`verify_source_integrity.py` · `verify_coverage.py`)은 전부
**플레이북 안쪽**만 본다. `#src` 마크다운이 안 바뀌었나, 그 마크다운에 적힌 수치가
시트 구현에 있나. 정작 그 `#src` 가 **책 원문에 충실한가**는 아무도 안 봤다 —
원문이 리포 안에 없었기 때문이다.

원문은 여기 있다(저작권물이라 리포로 복사하지 않는다).

    D:/jhts2/data/raw/미국-돈복사-ETF-투자방법.md      (slug: etf)
    D:/jhts2/data/raw/외국인-매집-3일-먼저-읽는-법.md  (slug: supply)

경로는 `book_sources.json` 이 들고 있고 환경변수로 덮어쓴다. 리포에 남는 건
`books/<slug>/source_index.json` — **소절 키·제목·줄범위·글자수·해시·정량토큰**뿐,
본문 텍스트는 한 글자도 담지 않는다.

## 자르는 규칙

    ^\\s*(Chapter\\s+\\d+)\\.   또는  ^\\s*(\\d+)\\s*장\\.   → 장 경계
    ^\\s*(\\d+-\\d+)\\.                                    → 소절
    ^\\s*(프롤로그|에필로그)[:\\s]                          → 특수 소절

소절 본문은 **다음 표지 전까지**(장 표지도 표지로 친다).

## 두 책이 같지 않다 (정직하게)

etf 는 깨끗하다 — `Chapter N.` · 표지 한 줄 · 목차 없음 · 중복 없음.
supply 는 스캔/OCR 산물이라 셋이 다르다.

  1. 장 표지가 `N장.` 형식이다(`Chapter N.` 아님).
  2. 앞에 **목차 블록**이 있어 모든 소절 표지가 한 번씩 더 나온다.
  3. 본문이 고정폭으로 **하드랩**돼 제목이 두 줄에 걸친다. 페이지 반복 탓에
     같은 소절 표지가 두 번 나오는 자리도 있다.

그래서 같은 키가 여러 번 나오면 **본문이 가장 긴 것**을 정본으로 잡고, 나머지는
버리지 않고 `duplicates` 에 줄범위와 함께 기록한다. 조용히 지우면 다음 사람이
"왜 30개지?" 하고 다시 센다.

## 사용

    python book_source.py                 # 파싱 요약(장별 분포)
    python book_source.py --write         # books/<slug>/source_index.json 생성
    python book_source.py --diff          # 원문 소절 키 ↔ 플레이북 소절 키 대조
    python book_source.py --slug supply --show 3-1
"""
import hashlib
import io
import json
import os
import re
import sys

import paths
from paths import BASE

# 정량 토큰 정규식은 verify_coverage 가 기준(SSOT)이다. 복붙하면 두 곳이 갈라진다.
from verify_coverage import TOKEN_RE, norm

CONFIG = os.path.join(BASE, "book_sources.json")
BOOKS_DIR = os.path.join(BASE, "books")

MARK_CHAPTER = re.compile(r"^\s*(?:Chapter\s+(\d+)|(\d+)\s*장)\.")
MARK_SECTION = re.compile(r"^\s*(\d+-\d+)\.")
MARK_SPECIAL = re.compile(r"^\s*(프롤로그|에필로그)[:\s]")

# 하드랩 판정 — 본문 줄 길이 중앙값이 이보다 짧으면 고정폭 레이아웃으로 본다.
WRAP_MEDIAN_MAX = 45
# 목차/페이지반복으로 잘린 표지 판정 기준(글자수)
STUB_CHARS = 150
# 하드랩 제목이 넘어갈 수 있는 최대 줄 수
MAX_TITLE_WRAP = 3


class SourceMissing(Exception):
    """원문을 못 찾았다. 조용히 통과시키지 않는다."""


# ---------------------------------------------------------------- 경로 해석
def load_config():
    if not os.path.exists(CONFIG):
        raise SourceMissing("설정이 없습니다: %s" % CONFIG)
    return json.loads(io.open(CONFIG, encoding="utf-8").read())


def source_path(slug, cfg=None):
    """slug → 원문 파일 절대경로. 없으면 SourceMissing."""
    cfg = cfg or load_config()
    env_one = os.environ.get("BOOK_SOURCE_%s" % slug.upper())
    if env_one:
        p = os.path.abspath(env_one)
        if not os.path.exists(p):
            raise SourceMissing(
                "BOOK_SOURCE_%s 가 가리키는 파일이 없습니다: %s" % (slug.upper(), p))
        return p

    ent = (cfg.get("sources") or {}).get(slug)
    if not ent:
        raise SourceMissing(
            "book_sources.json 에 '%s' 항목이 없습니다. (등록된 slug: %s)"
            % (slug, ", ".join(sorted((cfg.get("sources") or {}).keys())) or "없음"))

    raw_dir = os.environ.get("BOOK_RAW_DIR") or cfg.get("raw_dir")
    if not raw_dir:
        raise SourceMissing("raw_dir 가 비어 있습니다. BOOK_RAW_DIR 로 지정하세요.")
    p = os.path.abspath(os.path.join(raw_dir, ent["file"]))
    if not os.path.exists(p):
        raise SourceMissing(
            "원문 파일이 없습니다: %s\n"
            "  (slug=%s · raw_dir=%s)\n"
            "  원문은 리포에 커밋하지 않습니다. BOOK_RAW_DIR 로 실제 위치를 지정하세요."
            % (p, slug, raw_dir))
    return p


def slugs():
    return list((load_config().get("sources") or {}).keys())


# ---------------------------------------------------------------- 파싱
def _wrapped(lines):
    """고정폭 하드랩 레이아웃인가 — 제목이 두 줄에 걸치는 책인지 판단."""
    lens = sorted(len(l.strip()) for l in lines if l.strip())
    if not lens:
        return False, 0
    med = lens[len(lens) // 2]
    p90 = lens[int(len(lens) * 0.9)]
    return med < WRAP_MEDIAN_MAX, p90


def _marks(lines):
    """표지 위치 전부. [(i, kind, key, rest)] — kind: chapter|section|special"""
    out = []
    for i, line in enumerate(lines):
        m = MARK_CHAPTER.match(line)
        if m:
            key = m.group(1) or m.group(2)
            out.append((i, "chapter", key, line[m.end():].strip()))
            continue
        m = MARK_SECTION.match(line)
        if m:
            out.append((i, "section", m.group(1), line[m.end():].strip()))
            continue
        m = MARK_SPECIAL.match(line)
        if m:
            out.append((i, "special", m.group(1), line[m.end():].strip()))
    return out


def _tnorm(s):
    """제목 비교용 — 공백·가운뎃점·따옴표 같은 OCR 흔들림을 전부 걷어낸다.

    supply 목차와 본문은 같은 제목을 다르게 찍는다
    ('메릴린치•JP모건' ↔ '메릴린치 JP모건', '단기•중기•장기' ↔ '단기 중기• 장기').
    한글·영문·숫자만 남기면 그 차이가 사라진다.
    """
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", s)


def _unwrap_title(lines, start, stop, rest, toc_title):
    """하드랩으로 두 줄에 걸친 제목을 목차 제목에 맞춰 이어 붙인다.

    폭 기준 추정(줄이 꽉 찼으면 이어진 것)은 못 쓴다 — 한 줄에 다 들어간 긴 제목
    (supply 6-2)을 잘못 이어서 본문 첫 줄을 제목으로 먹어버린다. 그래서 **목차가
    있는 책만** 목차 제목의 접두사인 동안에만 이어 붙인다. 목차가 없으면 손대지 않는다.

    돌려주는 것: (제목, 본문 시작 줄 인덱스, 목차와 끝내 안 맞으면 남는 목차 제목)
    """
    j = start + 1
    title = rest
    if not toc_title:
        return title, j, None
    tgt = _tnorm(toc_title)
    if not tgt or not tgt.startswith(_tnorm(rest)):
        return title, j, toc_title          # 접두사조차 아니면 손대지 않고 기록만
    n = 0
    while j < stop and n < MAX_TITLE_WRAP and _tnorm(title) != tgt:
        nxt = lines[j].strip()
        if not nxt:
            break
        if not tgt.startswith(_tnorm(title + nxt)):
            break
        title = (title + " " + nxt).strip()
        j += 1
        n += 1
    title = re.sub(r"\s+", " ", title).strip()
    if _tnorm(title) == tgt:
        # 두 표기가 같은 제목임이 확인됐다. 줄바꿈 자리가 단어 중간이라
        # 이어 붙인 쪽은 '없 는 3가지'처럼 벌어진다 — 안 접힌 목차 표기를 쓴다.
        return toc_title, j, None
    return title, j, toc_title


def parse(slug):
    """원문 → 구조. 본문 텍스트 포함(인덱스에는 안 실린다)."""
    cfg = load_config()
    p = source_path(slug, cfg)
    text = io.open(p, encoding="utf-8").read()
    lines = text.split("\n")
    wrapped, wrap_w = _wrapped(lines)
    marks = _marks(lines)
    if not marks:
        raise SourceMissing("표지를 하나도 못 찾았습니다: %s" % p)

    # 1차 — 표지 줄만으로 자른다(제목은 아직 표지 줄 그대로).
    occ = []
    for n, (i, kind, key, rest) in enumerate(marks):
        stop = marks[n + 1][0] if n + 1 < len(marks) else len(lines)
        body = "\n".join(lines[i + 1:stop]).strip("\n")
        occ.append({
            "kind": kind, "key": key, "rest": rest, "title": rest,
            "start_line": i + 1, "end_line": stop,       # 1-based, 표지 줄 포함
            "body_from": i + 1, "body_to": stop,
            "chars": len(norm(body)), "body": body,
        })

    by_key = {}
    for o in occ:
        by_key.setdefault((o["kind"], o["key"]), []).append(o)

    # 2차 — 목차 제목 사전. 같은 키의 occurrence 중 본문이 가장 짧은 것이 목차 항목이다.
    toc = {}
    for k, lst in by_key.items():
        if len(lst) < 2:
            continue
        stub = min(lst, key=lambda x: x["chars"])
        if stub["chars"] >= STUB_CHARS:
            continue
        # 목차 항목도 하드랩된다. 다만 쪽 넘김 글리프('〉', '- 68 -')는 제목이 아니다.
        cont = [l.strip() for l in stub["body"].split("\n")
                if _tnorm(l)]
        t = " ".join([stub["rest"]] + cont).strip()
        toc[k] = re.sub(r"\s+", " ", t)

    # 3차 — 정본(본문이 가장 긴 것)의 제목을 목차에 맞춰 이어 붙이고 본문 시작을 민다.
    canon, dups = {}, {}
    for k, lst in by_key.items():
        lst_sorted = sorted(lst, key=lambda x: -x["chars"])
        c = lst_sorted[0]
        title, bstart, unmatched = _unwrap_title(
            lines, c["start_line"] - 1, c["body_to"], c["rest"], toc.get(k))
        c["title"] = title
        c["title_toc_unmatched"] = unmatched
        c["body"] = "\n".join(lines[bstart:c["body_to"]]).strip("\n")
        c["chars"] = len(norm(c["body"]))
        canon[k] = c
        if len(lst_sorted) > 1:
            dups[k] = [{
                "start_line": d["start_line"], "end_line": d["end_line"],
                "chars": d["chars"], "title": d["title"],
                "note": "목차/잘린 표지" if d["chars"] < STUB_CHARS else "중복 표지(페이지 반복)",
            } for d in lst_sorted[1:]]

    chapters, sections = [], []
    for o in occ:
        k = (o["kind"], o["key"])
        if canon.get(k) is not o:
            continue                                   # 중복 occurrence 는 건너뛴다
        if o["kind"] == "chapter":
            chapters.append(o)
        else:
            sections.append(o)
    chapters.sort(key=lambda x: x["start_line"])
    sections.sort(key=lambda x: x["start_line"])

    return {
        "slug": slug,
        "path": p,
        "file": os.path.basename(p),
        "line_count": len(lines),
        "wrapped_layout": wrapped,
        "wrap_width": wrap_w,
        "file_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "chapters": chapters,
        "sections": sections,
        "duplicates": dups,
        "chapter_style": (cfg.get("sources", {}).get(slug) or {}).get("chapter_style"),
    }


def tokens_of(body):
    out = []
    for t in TOKEN_RE.findall(body):
        t = norm(t[0] if isinstance(t, tuple) else t)
        if t and t not in out:
            out.append(t)
    return out


def load_sections(slug):
    """{소절키: 본문} — 다른 검사기가 import 해서 쓴다.

    장 표지는 빼고 소절(`3-2`)·특수소절(`프롤로그`·`에필로그`)만 담는다.
    """
    return {s["key"]: s["body"] for s in parse(slug)["sections"]}


# ---------------------------------------------------------------- 인덱스
def build_index(slug):
    d = parse(slug)
    chap_title = {c["key"]: c["title"] for c in d["chapters"]}

    secs = {}
    for s in d["sections"]:
        chap = s["key"].split("-")[0] if s["kind"] == "section" else None
        rec = {
            "title": s["title"],
            "chapter": chap,
            "chapter_title": chap_title.get(chap),
            "start_line": s["start_line"],
            "end_line": s["end_line"],
            "chars": s["chars"],
            "sha256": hashlib.sha256(norm(s["body"]).encode("utf-8")).hexdigest(),
            "tokens": tokens_of(s["body"]),
        }
        if s.get("title_toc_unmatched"):
            # 목차 제목과 본문 표지가 끝내 안 맞았다. 맞춘 척하지 않고 둘 다 남긴다.
            rec["title_toc"] = s["title_toc_unmatched"]
        dk = d["duplicates"].get((s["kind"], s["key"]))
        if dk:
            rec["duplicates"] = dk
        secs[s["key"]] = rec

    chapdups = {k[1]: v for k, v in d["duplicates"].items() if k[0] == "chapter"}
    return {
        "slug": slug,
        "source_file": d["file"],
        "source_sha256": d["file_sha256"],
        "source_line_count": d["line_count"],
        "wrapped_layout": d["wrapped_layout"],
        "chapter_style": d["chapter_style"],
        "generated_by": "book_source.py",
        "note": "본문 텍스트는 담지 않는다(저작권). 원문 위치는 book_sources.json.",
        "chapters": [{"no": c["key"], "title": c["title"],
                      "start_line": c["start_line"], "end_line": c["end_line"]}
                     for c in d["chapters"]],
        "chapter_duplicates": chapdups or None,
        "section_count": len(secs),
        # 원문 등장 순서. sections 는 키→메타 맵이다(계약1 검사기가 키 목록으로 읽는다).
        "section_keys": list(secs.keys()),
        "sections": secs,
    }


def index_path(slug):
    return os.path.join(BOOKS_DIR, slug, "source_index.json")


def write_index(slug):
    idx = build_index(slug)
    p = index_path(slug)
    paths.write_text(p, json.dumps(idx, ensure_ascii=False, indent=2) + "\n")
    return p, idx


def load_index(slug):
    p = index_path(slug)
    if not os.path.exists(p):
        raise SourceMissing("인덱스가 없습니다: %s  (python book_source.py --write)" % p)
    return json.loads(io.open(p, encoding="utf-8").read())


# ---------------------------------------------------------------- 플레이북 대조
PB_HEAD = re.compile(r"^#{2,3}\s*(\d+-\d+|프롤로그|에필로그)\s*[.\s—-]")


def playbook_path(slug):
    p = os.path.join(BASE, "%s-playbook.html" % slug)
    return p if os.path.exists(p) else None


def playbook_keys(slug):
    """플레이북 `#src` 마크다운의 소절 키 목록(등장 순서)."""
    p = playbook_path(slug)
    if not p:
        return None
    html = io.open(p, encoding="utf-8").read()
    m = re.search(r'<script type="text/markdown" id="src">(.*?)</script>', html, re.S)
    if not m:
        return None
    out = []
    for line in m.group(1).split("\n"):
        mm = PB_HEAD.match(line)
        if mm and mm.group(1) not in out:
            out.append(mm.group(1))
    return out


def diff(slug):
    idx = build_index(slug)
    book = idx["section_keys"]
    pb = playbook_keys(slug)
    if pb is None:
        return {"slug": slug, "book": book, "playbook": None}
    return {
        "slug": slug, "book": book, "playbook": pb,
        "missing": [k for k in book if k not in pb],      # 원문엔 있는데 플레이북엔 없음
        "invented": [k for k in pb if k not in book],     # 플레이북엔 있는데 원문엔 없음
    }


# ---------------------------------------------------------------- CLI
def _summary(idx):
    print("[%s] %s" % (idx["slug"], idx["source_file"]))
    print("  원문 줄수      : %d   (sha256 %s…)" % (idx["source_line_count"],
                                                idx["source_sha256"][:12]))
    print("  장 표지 형식   : %s%s" % (idx["chapter_style"],
                                  "  · 하드랩 레이아웃" if idx["wrapped_layout"] else ""))
    print("  장 개수        : %d" % len(idx["chapters"]))
    print("  소절 개수      : %d" % idx["section_count"])

    dist = {}
    for k, s in idx["sections"].items():
        dist.setdefault(s["chapter"] or "(특수)", []).append(k)
    print("  장별 분포      :")
    for c in sorted(dist, key=lambda x: (x == "(특수)", int(x) if x.isdigit() else 0)):
        print("    %-6s %2d개  %s" % (c, len(dist[c]), " ".join(dist[c])))

    dups = [(k, d) for k, s in idx["sections"].items() for d in s.get("duplicates", [])]
    if dups or idx.get("chapter_duplicates"):
        print("  중복 표지      : 소절 %d건 / 장 %d건 (가장 긴 본문을 정본으로 채택, 나머지는 기록만)"
              % (len(dups), len(idx.get("chapter_duplicates") or {})))
        for k, d in dups:
            print("    · %-8s %d~%d줄 %d자 — %s" % (k, d["start_line"], d["end_line"],
                                                 d["chars"], d["note"]))
    bad_title = [(k, s) for k, s in idx["sections"].items() if s.get("title_toc")]
    if bad_title:
        print("  제목 불일치    : %d개 (목차 제목과 본문 표지가 안 맞음 — 둘 다 기록)" % len(bad_title))
        for k, s in bad_title:
            print("    · %-8s 본문 「%s」 / 목차 「%s」" % (k, s["title"], s["title_toc"]))
    ntok = sum(len(s["tokens"]) for s in idx["sections"].values())
    notok = [k for k, s in idx["sections"].items() if not s["tokens"]]
    print("  정량 토큰      : 총 %d개 (소절당 평균 %.1f) · 토큰 0개 소절 %d개%s"
          % (ntok, ntok / max(1, idx["section_count"]), len(notok),
             (" [%s]" % " ".join(notok)) if notok else ""))


def _diff_report(slug):
    d = diff(slug)
    print("\n[%s] 원문 ↔ 플레이북 소절 키 대조" % slug)
    if d["playbook"] is None:
        print("  플레이북(#src)을 못 찾음 — 대조 불가")
        return 1
    print("  원문 소절   %2d개" % len(d["book"]))
    print("  플레이북    %2d개" % len(d["playbook"]))
    print("  누락 후보(원문 O / 플레이북 X) %d개:" % len(d["missing"]))
    print("    %s" % (" ".join(d["missing"]) if d["missing"] else "(없음)"))
    print("  창작 후보(플레이북 O / 원문 X) %d개:" % len(d["invented"]))
    print("    %s" % (" ".join(d["invented"]) if d["invented"] else "(없음)"))
    return 0 if not (d["missing"] or d["invented"]) else 1


def main(argv):
    def opt(name, default=None):
        if name in argv:
            i = argv.index(name)
            return argv[i + 1] if i + 1 < len(argv) else default
        return default

    want = opt("--slug")
    targets = [want] if want else slugs()
    show = opt("--show")

    if show:
        if not want:
            print("--show 는 --slug 와 함께 쓰세요.")
            return 2
        idx = build_index(want)
        s = idx["sections"].get(show)
        if not s:
            print("그런 소절이 없습니다: %s  (있는 키: %s)"
                  % (show, " ".join(idx["section_keys"])))
            return 2
        print(json.dumps({show: s}, ensure_ascii=False, indent=2))
        return 0

    rc = 0
    for slug in targets:
        try:
            if "--write" in argv:
                p, idx = write_index(slug)
            else:
                idx = build_index(slug)
                p = None
            _summary(idx)
            if p:
                print("  → 기록: %s" % os.path.relpath(p, BASE))
        except SourceMissing as e:
            print("[%s] 실패 — %s" % (slug, e))
            rc = 2
            continue
        print("")

    if "--diff" in argv:
        for slug in targets:
            try:
                _diff_report(slug)
            except SourceMissing as e:
                print("[%s] 대조 실패 — %s" % (slug, e))
                rc = 2
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
