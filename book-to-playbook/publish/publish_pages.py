#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""라이브 책의 플레이북 원본(<slug>-playbook.html)의 verdict-data JSON 블록을 최신
판정으로 교체해 PUBLIC/<slug>/index.html 로 출력. GitHub Pages 자동 갱신용.
(디자인/내용은 원본 그대로 승계)

어느 책인지는 books.json 에서 온다(코드에 특정 책을 박지 않는다):
  · 인자 있으면 그 slug, 없으면 live:true 인 책 전부.
  · 비-라이브 책의 홈/발행은 build_home.py 가 맡는다(역할 분담).
"""
import os, re, sys
import json
from shared.paths import (BASE, book_meta, live_slugs, playbook_src, public_book_dir,
                          ensure_dir, read_text, write_text, PUBLIC)

VERDICT_RE = re.compile(
    r'(<script type="application/json" id="verdict-data">)(.*?)(</script>)', re.S)


def _merge_intraday(data, intraday_js):
    """장중 자동판정 병합 + 수집상태 판정(ok / pending(대기) / error(실패))."""
    intraday_state = "pending"   # 기본: 아직 안 걷힘
    if os.path.exists(intraday_js):
        try:
            from datetime import datetime, timezone
            iv = json.loads(read_text(intraday_js))
            ts = iv.get("ts")
            age_h = 999
            if ts:
                age_h = (datetime.now(timezone.utc)
                         - datetime.fromisoformat(ts).astimezone(timezone.utc)).total_seconds() / 3600
            st = iv.get("status")
            if st == "error":
                intraday_state = "error" if age_h <= 72 else "pending"
                data["intraday_error"] = iv.get("reason")
                data["intraday_ts"] = ts
            elif st == "ok" and age_h <= 12:
                intraday_state = "ok"
                data["intraday_ts"] = ts
                for v in data.get("verdicts", []):
                    v["intraday_auto"] = iv.get("intraday", {}).get(v["prod"])
            else:
                intraday_state = "pending"
                if ts:
                    data["intraday_ts"] = ts
        except Exception as e:
            intraday_state = "error"
            data["intraday_error"] = "병합 오류: %s" % e
            print("장중 데이터 병합 실패:", e, file=sys.stderr)
    data["intraday_state"] = intraday_state
    return data


def _source_sections(slug):
    """books/<slug>/source_index.json 의 source_file(책 원문)을 소절(ref)로 분해 → {ref: 원문}.
    원문 파일이 repo 에 없으면(실제 책 미커밋 등) 빈 {} — 프런트가 '원문 미제공'으로 처리한다.
    자작/공개 원문이 있는 책만 소절 원문이 노출된다(없는 책은 아무것도 새로 드러나지 않음)."""
    try:
        idx = json.loads(read_text(os.path.join(BASE, "books", slug, "source_index.json")))
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
    """백테스트 탭(책 무관): backtest-<slug>.json(verdict.backtest --page) + checklist/ui/backtest-ui.js 를
    checklist-ui 바로 앞에 심는다 — checklist-ui 가 로드 때 .tab 을 묶기 전에 탭이 생겨야 기존 탭 전환에 묶인다.
    데이터가 없는 책은 탭을 만들지 않는다(빈 탭을 보이지 않는다). 다시 발행하면 이전 주입분을 갈아끼운다."""
    html = re.sub(re.escape(BACKTEST_BEGIN) + r".*?" + re.escape(BACKTEST_END) + r"\n?", "", html, flags=re.S)
    data_p = os.path.join(BASE, "backtest-%s.json" % slug)
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


def publish(slug):
    """한 책을 발행한다. 라이브 책이면 최신 판정을 병합한다. 성공 시 True."""
    src = playbook_src(slug)
    if not os.path.exists(src):
        print("· %-8s 플레이북 원본 없음(%s) — 건너뜀" % (slug, os.path.basename(src)), file=sys.stderr)
        return True   # 없는 책은 이 스크립트 대상이 아님(실패로 치지 않는다)
    meta = book_meta(slug)
    html = read_text(src)

    # 규칙 사본 드리프트 게이트 — JSON(단일 진실)과 HTML 사본이 갈라졌으면 발행 중단.
    from checklist.inject_rules import gate as _rules_gate
    _ok, _lines = _rules_gate(html, slug)
    for _l in _lines:
        print(_l, file=sys.stderr if not _ok else sys.stdout)
    if not _ok:
        print("규칙 드리프트(%s) — 발행을 멈춥니다." % slug, file=sys.stderr)
        return False

    # 라이브 책만 최신 판정(verdict-data) 병합. 비-라이브 책은 정적 페이지 그대로.
    if meta.get("live"):
        # 자기 책의 판정 파일을 읽는다 — 공용 파일 하나를 돌려쓰면 다른 live 책의
        # 판정이 이 페이지에 병합된다. 구버전 단일 파일은 폴백으로만.
        js = os.path.join(BASE, "latest-verdict-%s.json" % slug)
        if not os.path.exists(js):
            js = os.path.join(BASE, "latest-verdict.json")
        if os.path.exists(js):
            # 장중 판정 파일 — 옛 KIS 클라이언트가 쓰던 kis-intraday.json 을 중립 이름으로
            # 바꿨다(KIS 잔재 정리). 지금은 만드는 쪽이 없어 항상 '대기(pending)'로 나가고,
            # 장중 엔진이 재설계되면 이 파일을 쓰는 것으로 다시 잇는다.
            data = _merge_intraday(json.loads(read_text(js)),
                                   os.path.join(BASE, "intraday-verdict.json"))
            data_str = json.dumps(data, ensure_ascii=False)
            if not VERDICT_RE.search(html):
                print("verdict-data 블록을 찾지 못함(%s)" % slug, file=sys.stderr)
                return False
            html = VERDICT_RE.sub(lambda m: m.group(1) + "\n" + data_str + "\n" + m.group(3), html)

    # 책-무관 검수 모드 UI JS 주입 (SSOT = checklist/ui/*.js — 한 번 고치면 모든 책에 전파)
    try:
        from checklist.inject_ui import inject as _inject_ui
        html = _inject_ui(html)
    except Exception as e:
        print("검수 UI 주입 실패(무시):", e, file=sys.stderr)

    # 책 전환 사이드 레일 주입
    try:
        from publish.inject_nav import inject
        html = inject(html, slug)
    except Exception as e:
        print("레일 주입 실패(무시):", e, file=sys.stderr)

    # 소절 원문 주입(책 무관) — 원문 파일 있는 책만 실제 원문, 없으면 빈 데이터('원문 미제공')
    html = _inject_source(html, slug)

    # 백테스트 탭(데이터 있는 책만)
    html = _inject_backtest(html, slug)

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
