#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""경로·인코딩 공통 모듈 (macOS / Windows 공용).

이 파이프라인은 원래 macOS(launchd + ~/.claude/skills/book-to-playbook)만 가정했다.
여기서 그 가정을 걷어내고, 어느 OS·어느 폴더에 두든 그대로 돌게 만든다.

경로 결정 순서
  BASE   = $BOOK_TO_PLAYBOOK_HOME  또는  이 파일이 있는 폴더(shared/)의 부모
  LOGS   = BASE/logs

화면은 로컬 실시간 서버(web.serve)가 매 요청 그린다 — 정적 발행(GitHub Pages)은 폐지됐다.
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
# 이 파일은 shared/ 안에 있다 — BASE 는 그 부모(book-to-playbook 루트).
BASE = os.environ.get("BOOK_TO_PLAYBOOK_HOME") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.abspath(BASE)


LOGS = os.path.join(BASE, "logs")


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
# 배포·서빙·엔진호출이 특정 책에 안 박히도록, "어느 책?"은 books.json 에서 온다.
# 책마다의 산출물은 전부 books/<slug>/ 한 곳에 산다(아래 '책 산출물 경로').
import json as _json


def load_manifest():
    """books.json 전체(dict) — site_title · site_subtitle · books 를 담는다.
    없으면 빈 dict. books.json 을 읽는 입구는 이 함수 하나다(아래 load_books 도 이걸 쓴다)."""
    p = os.path.join(BASE, "books.json")
    if not os.path.exists(p):
        return {}
    return _json.loads(read_text(p))


def load_books():
    """books.json 의 books 목록. 없으면 빈 리스트."""
    return load_manifest().get("books", [])


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
    (특정 책을 코드에 박지 않고 설정에서 고른다)"""
    live = live_slugs()
    if live:
        return live[0]
    books = load_books()
    return books[0]["slug"] if books else None


def book_engine(slug, kind):
    """그 책의 시세 엔진 모듈명(daily/intraday, 예: 'web.verdict_view').
    없으면 None(=엔진 없는 책). 실행은 `python -m <모듈명> <slug>` (cwd=BASE)."""
    return (book_meta(slug).get("engine") or {}).get(kind)


# ---------------------------------------------------------------- 책 산출물 경로
# 책마다의 산출물은 전부 BASE/books/<slug>/ 한 곳에 산다. 그 경로를 짓는 코드는 이 파일 하나다 —
# 다른 파일이 BASE 에 "books"·slug 를 이어 붙이면 verify_code 주인 표('책 산출물 경로')가 막는다.
#   tracked : playbook.html(플레이북 원본) · source.md(자작 원문) · source_index.json · tree.json · tree_candidates/ · scenarios.json
#   runtime : backtest.json(백테스트 탭 데이터) · logs/(책별 실행 로그·심판 덤프) · positions.json(내 포지션 — 개인 파일)
BOOKS = os.path.join(BASE, "books")


def book_dir(slug):
    """책 하나의 산출물 폴더(BASE/books/<slug>)."""
    return os.path.join(BOOKS, slug)


def book_file(slug, name):
    """책 폴더 안의 파일(name 은 'tree_candidates/a.json' 처럼 하위 경로여도 된다)."""
    return os.path.join(book_dir(slug), name)


def playbook_html(slug):
    """플레이북 원본 HTML(books/<slug>/playbook.html)."""
    return book_file(slug, "playbook.html")


def source_index_json(slug):
    """원문 소절 인덱스(books/<slug>/source_index.json)."""
    return book_file(slug, "source_index.json")


def backtest_json(slug):
    """책 페이지 '백테스트' 탭 데이터(books/<slug>/backtest.json) — web.backtest_page 가 쓰고 book_page 가 읽는다."""
    return book_file(slug, "backtest.json")


def positions_json(slug):
    """내 포지션(books/<slug>/positions.json — 커밋하지 않는 개인 파일)."""
    return book_file(slug, "positions.json")


def book_log(slug, name):
    """책별 실행 로그·덤프(books/<slug>/logs/<name>). 책과 무관한 러너 로그는 LOGS."""
    return book_file(slug, os.path.join("logs", name))


if __name__ == "__main__":
    print("BASE   =", BASE)
    print("LOGS   =", LOGS)
    print("platform =", sys.platform)
