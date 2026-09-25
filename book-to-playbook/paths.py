#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""경로·인코딩 공통 모듈 (macOS / Windows 공용).

이 파이프라인은 원래 macOS(launchd + ~/.claude/skills/book-to-playbook)만 가정했다.
여기서 그 가정을 걷어내고, 어느 OS·어느 폴더에 두든 그대로 돌게 만든다.

경로 결정 순서
  BASE   = $BOOK_TO_PLAYBOOK_HOME  또는  이 파일이 있는 폴더
  PUBLIC = $BOOK_TO_PLAYBOOK_PUBLIC 또는  (부모가 배포 리포면 부모) 아니면 BASE/public
  LOGS   = BASE/logs

부모 폴더에 `.nojekyll`이 있으면 그 폴더를 GitHub Pages 배포 루트로 본다.
(이 리포 구조: <repo>/.nojekyll + <repo>/book-to-playbook/ → PUBLIC=<repo>)
"""
import os
import sys

# ---------------------------------------------------------------- 인코딩
# Windows 콘솔 기본 코드페이지(cp949)에서 한글·이모지 출력 시 UnicodeEncodeError가 난다.
# 표준 스트림을 UTF-8로 고정한다. (Python 3.7+)
def force_utf8_io():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


force_utf8_io()


# ---------------------------------------------------------------- 경로
BASE = os.environ.get("BOOK_TO_PLAYBOOK_HOME") or os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(BASE)


def _detect_public():
    env = os.environ.get("BOOK_TO_PLAYBOOK_PUBLIC")
    if env:
        return os.path.abspath(env)
    parent = os.path.dirname(BASE)
    # 부모가 이미 GitHub Pages 배포 루트면 거기에 바로 쓴다(리포 안에서 실행하는 경우)
    if os.path.exists(os.path.join(parent, ".nojekyll")):
        return parent
    return os.path.join(BASE, "public")


PUBLIC = _detect_public()
LOGS = os.path.join(BASE, "logs")


def path(*parts):
    """BASE 기준 경로."""
    return os.path.join(BASE, *parts)


def public_path(*parts):
    """PUBLIC(배포 루트) 기준 경로."""
    return os.path.join(PUBLIC, *parts)


def ensure_dir(p):
    os.makedirs(p, exist_ok=True)
    return p


# ---------------------------------------------------------------- 파일 IO
def read_text(p):
    """항상 UTF-8로 읽는다."""
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def write_text(p, s):
    """항상 UTF-8 + LF로 쓴다.

    newline=""를 주지 않으면 Windows에서 \\n 이 \\r\\n 으로 바뀌어,
    같은 입력인데 OS마다 결과 파일이 달라지고 git diff가 통째로 뜬다.
    """
    ensure_dir(os.path.dirname(os.path.abspath(p)))
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)


def load_env_file(p):
    """KEY=VALUE 형식 파일을 os.environ에 주입. 없으면 조용히 통과.

    run.sh의 `set -a && . telegram.env` 를 OS 중립으로 대체한다.
    """
    if not os.path.exists(p):
        return {}
    out = {}
    for line in read_text(p).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        out[k] = v
        os.environ.setdefault(k, v)
    return out


# ---------------------------------------------------------------- 책 레지스트리
# 배포·서빙·엔진호출이 특정 책(etf)에 안 박히도록, "어느 책?"은 books.json 에서 온다.
# 파일 규칙(책-무관): 플레이북 원본 = BASE/<slug>-playbook.html · 배포 = PUBLIC/<slug>/.
import json as _json


def load_books():
    """books.json 의 books 목록. 없으면 빈 리스트."""
    p = os.path.join(BASE, "books.json")
    if not os.path.exists(p):
        return []
    return _json.loads(read_text(p)).get("books", [])


def book_meta(slug):
    for b in load_books():
        if b.get("slug") == slug:
            return b
    return {}


def live_slugs():
    """live:true 인 책 slug 들(시세 엔진·라이브 서빙 대상)."""
    return [b["slug"] for b in load_books() if b.get("live")]


def default_slug():
    """인자 없이 서빙/발행할 때의 기본 책 — 첫 live 책, 없으면 첫 등록 책.
    (ETF 를 코드에 박지 않고 설정에서 고른다)"""
    live = live_slugs()
    if live:
        return live[0]
    books = load_books()
    return books[0]["slug"] if books else None


def book_engine(slug, kind):
    """그 책의 시세 엔진 스크립트명(daily/intraday). 없으면 None(=엔진 없는 책)."""
    return (book_meta(slug).get("engine") or {}).get(kind)


def playbook_src(slug):
    """플레이북 원본 HTML 경로(BASE/<slug>-playbook.html)."""
    return os.path.join(BASE, "%s-playbook.html" % slug)


def public_book_dir(slug):
    """그 책의 배포 디렉터리(PUBLIC/<slug>/)."""
    return os.path.join(PUBLIC, slug)


if __name__ == "__main__":
    print("BASE   =", BASE)
    print("PUBLIC =", PUBLIC)
    print("LOGS   =", LOGS)
    print("platform =", sys.platform)
