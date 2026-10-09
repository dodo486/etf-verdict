#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""책 페이지 조립 — books/<slug>/playbook.html 에 판정(verdict-data)·공유 UI·레일·원문·백테스트를 얹어
한 장의 HTML 을 만든다. 라이브 서버(entry.serve)가 매 요청 이 assemble 로 페이지를 그린다.

정적 발행(파일로 굽기)은 폐지됐다 — 하루 지난 스냅샷이 매매를 오도하지 않게. assemble 은 파일을
쓰지 않는 순수 조립 함수다(데이터는 호출자가 넘긴다 — 라이브 서버는 방금 계산한 라이브 판정을 준다).
"""
import os, re
import json
from shared.paths import BASE, backtest_json, book_file, playbook_html, read_text, source_index_json

VERDICT_RE = re.compile(
    r'(<script type="application/json" id="verdict-data">)(.*?)(</script>)', re.S)


def _source_sections(slug):
    """books/<slug>/source_index.json 의 source_file(책 폴더 안 원문 — 예 books/trend/source.md)을 소절(ref)로 분해 → {ref: 원문}.
    원문 파일이 repo 에 없으면(실제 책 미커밋 등) 빈 {} — 프런트가 '원문 미제공'으로 처리한다.
    자작/공개 원문이 있는 책만 소절 원문이 노출된다(없는 책은 아무것도 새로 드러나지 않음)."""
    try:
        idx = json.loads(read_text(source_index_json(slug)))
    except Exception:
        return {}
    sf = idx.get("source_file", "")
    p = sf if os.path.isabs(sf) else book_file(slug, sf)     # 원문 파일 이름은 책 폴더 기준
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
    """백테스트 탭(책 무관): books/<slug>/backtest.json(consumers.display.backtest_page) + consumers/display/ui/backtest-ui.js 를
    checklist-ui 바로 앞에 심는다 — checklist-ui 가 로드 때 .tab 을 묶기 전에 탭이 생겨야 기존 탭 전환에 묶인다.
    데이터가 없는 책은 탭을 만들지 않는다(빈 탭을 보이지 않는다). 다시 발행하면 이전 주입분을 갈아끼운다."""
    html = re.sub(re.escape(BACKTEST_BEGIN) + r".*?" + re.escape(BACKTEST_END) + r"\n?", "", html, flags=re.S)
    data_p = backtest_json(slug)
    ui_p = os.path.join(BASE, "web", "ui", "backtest-ui.js")
    if not (os.path.exists(data_p) and os.path.exists(ui_p)):
        return html
    body = read_text(data_p).replace("</", "<\\/")
    block = "%s\n<script type=\"application/json\" id=\"backtest-data\">%s</script>\n<script>\n%s\n</script>\n%s\n" % (
        BACKTEST_BEGIN, body, read_text(ui_p), BACKTEST_END)
    anchor = "<!-- INJECT:checklist-ui -->"
    if anchor in html:
        return html.replace(anchor, block + anchor, 1)
    return html.replace("</body>", block + "</body>", 1)


def assemble(slug, data):
    """책 페이지 한 장을 조립한다 — 로컬 실시간 서버(serve)가 쓰는 단일 경로.
    판정(#verdict-data) · 공유 UI(ui/*.js) · 책 레일 · 소절 원문 · 백테스트 탭을 얹는다.
    (로컬 전용이라 내 포지션을 그대로 싣는다 — 정적 발행이 폐지돼 '공개 페이지' 분기는 없다.)"""
    html = read_text(playbook_html(slug))
    if data is not None:
        if not VERDICT_RE.search(html):
            raise ValueError("verdict-data 블록을 찾지 못함(%s)" % slug)
        blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        html = VERDICT_RE.sub(lambda m: m.group(1) + blob + m.group(3), html)
    from consumers.display.inject_ui import inject as _inject_ui
    html = _inject_ui(html)
    from consumers.display.inject_nav import inject as _inject_nav
    html = _inject_nav(html, slug)
    html = _inject_source(html, slug)
    return _inject_backtest(html, slug)


