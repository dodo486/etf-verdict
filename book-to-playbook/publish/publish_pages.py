#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""책 페이지 조립·발행 — <slug>-playbook.html 에 최신 판정(verdict-data)과 공유 UI 를 얹어
PUBLIC/<slug>/index.html 로 출력한다. GitHub Pages 자동 갱신용. 조립(assemble)은 로컬 실시간
서버(serve)와 같은 함수 하나다 — 두 화면이 다르게 조립되지 않게.

어느 책인지는 books.json 에서 온다(코드에 특정 책을 박지 않는다):
  · 인자 있으면 그 slug, 없으면 live:true 인 책 전부.
  · 비-라이브 책의 홈/발행은 build_home.py 가 맡는다(역할 분담).
"""
import os, re, sys
import json
from shared.paths import (BASE, book_meta, live_slugs, playbook_src, public_book_dir,
                          ensure_dir, read_text, write_text, PUBLIC,
                          latest_verdict_path, backtest_path, source_index_path)

VERDICT_RE = re.compile(
    r'(<script type="application/json" id="verdict-data">)(.*?)(</script>)', re.S)


def _source_sections(slug):
    """books/<slug>/source_index.json 의 source_file(책 원문)을 소절(ref)로 분해 → {ref: 원문}.
    원문 파일이 repo 에 없으면(실제 책 미커밋 등) 빈 {} — 프런트가 '원문 미제공'으로 처리한다.
    자작/공개 원문이 있는 책만 소절 원문이 노출된다(없는 책은 아무것도 새로 드러나지 않음)."""
    try:
        idx = json.loads(read_text(source_index_path(slug)))
    except Exception:
        return {}
    sf = idx.get("source_file", "")
    p = sf if os.path.isabs(sf) else os.path.join(BASE, sf)
    if not sf or not os.path.exists(p):
        return {}
    secs, key, buf = {}, None, []
    for line in read_text(p).split("\n"):
        m = re.match(r"^\s*(\d+-\d+|프롤로그|에필로그)[.\s]", line)
        if m:
            if key:
                secs[key] = "\n".join(buf).strip()
            key, buf = m.group(1), [line]
        elif key is not None:
            buf.append(line)
    if key:
        secs[key] = "\n".join(buf).strip()
    return secs


def _inject_source(html, slug):
    """소절 원문을 #source-data JSON 블록으로 페이지에 심는다(playbook-ui 의 '원문' 버튼이 읽음)."""
    body = json.dumps(_source_sections(slug), ensure_ascii=False).replace("</", "<\\/")
    block = '<script type="application/json" id="source-data">%s</script>\n' % body
    # 치환 문자열은 lambda 로 준다 — 일반 문자열이면 re 가 JSON 의 \n·\t 이스케이프를
    # 역참조/제어문자로 해석해 JSON 이 깨진다.
    if 'id="source-data"' in html:
        return re.sub(r'<script type="application/json" id="source-data">.*?</script>\n?',
                      lambda _m: block, html, flags=re.S)
    return re.sub(r'<script type="text/markdown" id="src">',
                  lambda m: block + m.group(0), html, count=1)


BACKTEST_BEGIN, BACKTEST_END = "<!-- INJECT:backtest -->", "<!-- /INJECT:backtest -->"


def _inject_backtest(html, slug):
    """백테스트 탭(책 무관): backtest-<slug>.json(operations.backtest --page) + checklist/ui/backtest-ui.js 를
    checklist-ui 바로 앞에 심는다 — checklist-ui 가 로드 때 .tab 을 묶기 전에 탭이 생겨야 기존 탭 전환에 묶인다.
    데이터가 없는 책은 탭을 만들지 않는다(빈 탭을 보이지 않는다). 다시 발행하면 이전 주입분을 갈아끼운다."""
    html = re.sub(re.escape(BACKTEST_BEGIN) + r".*?" + re.escape(BACKTEST_END) + r"\n?", "", html, flags=re.S)
    data_p = backtest_path(slug)
    ui_p = os.path.join(BASE, "checklist", "ui", "backtest-ui.js")
    if not (os.path.exists(data_p) and os.path.exists(ui_p)):
        return html
    body = read_text(data_p).replace("</", "<\\/")
    block = "%s\n<script type=\"application/json\" id=\"backtest-data\">%s</script>\n<script>\n%s\n</script>\n%s\n" % (
        BACKTEST_BEGIN, body, read_text(ui_p), BACKTEST_END)
    anchor = "<!-- INJECT:checklist-ui -->"
    if anchor in html:
        return html.replace(anchor, block + anchor, 1)
    return html.replace("</body>", block + "</body>", 1)


def assemble(slug, data, public=True):
    """책 페이지 한 장을 조립한다 — 정적 발행(publish)과 로컬 실시간 서버(serve)가 같이 쓰는 단일 경로.
    판정(#verdict-data) · 공유 UI(ui/*.js) · 책 레일 · 소절 원문 · 백테스트 탭을 얹는다.
    public=True 면 내 포지션(로컬 개인 파일에서 온 값)을 판정에서 뺀다 — 공개 페이지에 싣지 않는다."""
    html = read_text(playbook_src(slug))
    if data is not None:
        if public:
            data = dict(data, verdicts=[{k: x for k, x in v.items() if k != "positions"}
                                        for v in data.get("verdicts", [])])
            data.pop("positions_note", None)
        if not VERDICT_RE.search(html):
            raise ValueError("verdict-data 블록을 찾지 못함(%s)" % slug)
        blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        html = VERDICT_RE.sub(lambda m: m.group(1) + blob + m.group(3), html)
    from checklist.inject_ui import inject as _inject_ui
    html = _inject_ui(html)
    from publish.inject_nav import inject as _inject_nav
    html = _inject_nav(html, slug)
    html = _inject_source(html, slug)
    return _inject_backtest(html, slug)


def publish(slug):
    """한 책을 발행한다. 라이브 책이면 최신 판정(latest-verdict-<slug>.json)을 싣는다. 성공 시 True."""
    src = playbook_src(slug)
    if not os.path.exists(src):
        print("· %-8s 플레이북 원본 없음(%s) — 건너뜀" % (slug, os.path.basename(src)), file=sys.stderr)
        return True   # 없는 책은 이 스크립트 대상이 아님(실패로 치지 않는다)
    data = None
    if book_meta(slug).get("live"):
        js = latest_verdict_path(slug)
        if not os.path.exists(js):
            print("판정 파일 없음(%s) — run.py daily 가 먼저 돌아야 한다" % os.path.basename(js), file=sys.stderr)
            return False
        data = json.loads(read_text(js))
    try:
        html = assemble(slug, data, public=True)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return False
    outd = ensure_dir(public_book_dir(slug))
    write_text(os.path.join(outd, "index.html"), html)
    open(os.path.join(PUBLIC, ".nojekyll"), "a").close()
    print("%s 갱신 완료" % os.path.join(outd, "index.html"))
    return True


def main(argv):
    slugs = [a for a in argv if not a.startswith("-")]
    if not slugs:
        slugs = live_slugs()          # 인자 없으면 라이브 책 전부(코드에 특정 책 안 박음)
    if not slugs:
        print("발행할 라이브 책이 없습니다(books.json 의 live:true 확인).", file=sys.stderr)
        return 1
    ok = True
    for slug in slugs:
        ok = publish(slug) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
