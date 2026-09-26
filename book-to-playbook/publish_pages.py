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
from paths import (BASE, book_meta, live_slugs, playbook_src, public_book_dir,
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


def publish(slug):
    """한 책을 발행한다. 라이브 책이면 최신 판정을 병합한다. 성공 시 True."""
    src = playbook_src(slug)
    if not os.path.exists(src):
        print("· %-8s 플레이북 원본 없음(%s) — 건너뜀" % (slug, os.path.basename(src)), file=sys.stderr)
        return True   # 없는 책은 이 스크립트 대상이 아님(실패로 치지 않는다)
    meta = book_meta(slug)
    html = read_text(src)

    # 규칙 사본 드리프트 게이트 — JSON(단일 진실)과 HTML 사본이 갈라졌으면 발행 중단.
    from inject_rules import gate as _rules_gate
    _ok, _lines = _rules_gate(html, slug)
    for _l in _lines:
        print(_l, file=sys.stderr if not _ok else sys.stdout)
    if not _ok:
        print("규칙 드리프트(%s) — 발행을 멈춥니다." % slug, file=sys.stderr)
        return False

    # 라이브 책만 최신 판정(verdict-data) 병합. 비-라이브 책은 정적 페이지 그대로.
    if meta.get("live"):
        js = os.path.join(BASE, "latest-verdict.json")
        if os.path.exists(js):
            data = _merge_intraday(json.loads(read_text(js)),
                                   os.path.join(BASE, "kis-intraday.json"))
            data_str = json.dumps(data, ensure_ascii=False)
            if not VERDICT_RE.search(html):
                print("verdict-data 블록을 찾지 못함(%s)" % slug, file=sys.stderr)
                return False
            html = VERDICT_RE.sub(lambda m: m.group(1) + "\n" + data_str + "\n" + m.group(3), html)

    # 책-무관 검수 모드 UI JS 주입 (SSOT = ui/*.js — 한 번 고치면 모든 책에 전파)
    try:
        from inject_ui import inject as _inject_ui
        html = _inject_ui(html)
    except Exception as e:
        print("검수 UI 주입 실패(무시):", e, file=sys.stderr)

    # 책 전환 사이드 레일 주입
    try:
        from inject_nav import inject
        html = inject(html, slug)
    except Exception as e:
        print("레일 주입 실패(무시):", e, file=sys.stderr)

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
