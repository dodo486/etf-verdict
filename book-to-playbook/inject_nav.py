#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""책 페이지 HTML에 '책 전환 사이드 레일'을 주입한다(빌드 시).
좌측 고정 레일 = books.json의 모든 책. 현재 책 강조. 클릭 시 ../slug/ 로 전환.
드릴다운 없이 책 사이를 바로 오간다. import 해서 inject(html, cur_slug) 사용."""
import os, json, html as H

BASE = os.path.dirname(os.path.abspath(__file__))

def _books():
    return json.load(open(os.path.join(BASE, "books.json"), encoding="utf-8"))

def inject(html, cur_slug):
    m = _books()
    items = []
    for b in m["books"]:
        slug = b["slug"]
        active = " active" if slug == cur_slug else ""
        live = '<span class="bd"></span>' if b.get("live") else ''
        href = "../%s/" % slug
        short = H.escape(b.get("tickers","") or b["title"])
        items.append(
            f'<a class="bitem{active}" href="{href}" style="--ac:{H.escape(b.get("accent","#d4a24e"))}" title="{H.escape(b["title"])}">'
            f'<span class="bt">{H.escape(b["title"])}</span>'
            f'<span class="bs">{short}{live}</span></a>'
        )
    rail = f'''<style>
:root{{--rail:186px}}
#bookrail{{position:fixed;left:0;top:0;bottom:0;width:var(--rail);z-index:200;background:#0d0f14;border-right:1px solid #2b303c;overflow-y:auto;padding:16px 12px}}
#bookrail .rh{{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#7a8194;font-weight:700;padding:4px 8px 10px}}
#bookrail .bitem{{display:block;text-decoration:none;padding:11px 12px;border-radius:10px;margin-bottom:6px;border:1px solid transparent;transition:background .15s,border-color .15s}}
#bookrail .bitem:hover{{background:#171a22}}
#bookrail .bitem.active{{background:#1a1e28;border-color:var(--ac);border-left:3px solid var(--ac)}}
#bookrail .bt{{display:block;font-size:13.5px;font-weight:700;color:#eef1f6;line-height:1.35}}
#bookrail .bitem.active .bt{{color:var(--ac)}}
#bookrail .bs{{display:flex;align-items:center;gap:6px;font-size:11px;color:#7a8194;margin-top:3px}}
#bookrail .bd{{width:6px;height:6px;border-radius:50%;background:#3fb950;display:inline-block}}
#bookrail .home{{display:block;margin-top:10px;padding:8px 12px;font-size:12px;color:#7a8194;text-decoration:none;border-top:1px solid #2b303c}}
#bookrail .home:hover{{color:#d4a24e}}
body{{padding-left:var(--rail)}}
.tabbar{{left:var(--rail)}}
#railtoggle{{display:none}}
@media(max-width:820px){{
  :root{{--rail:0px}}
  body{{padding-left:0}}
  #bookrail{{width:200px;transform:translateX(-100%);transition:transform .2s;box-shadow:0 0 40px rgba(0,0,0,.6)}}
  #bookrail.open{{transform:none}}
  #railtoggle{{display:inline-flex;position:fixed;z-index:210;top:10px;right:12px;background:#20242f;color:#d4a24e;border:1px solid #2b303c;border-radius:9px;padding:8px 12px;font-size:13px;font-weight:700;cursor:pointer}}
}}
</style>
<button id="railtoggle" onclick="document.getElementById('bookrail').classList.toggle('open')">📚 책</button>
<nav id="bookrail">
  <div class="rh">📚 책 목록</div>
  {''.join(items)}
  <a class="home" href="../">＋ 전체 홈</a>
</nav>
'''
    # <body ...> 바로 뒤에 주입 (없으면 맨 앞)
    import re
    m2 = re.search(r'<body[^>]*>', html, re.I)
    if m2:
        return html[:m2.end()] + "\n" + rail + html[m2.end():]

    # <body> 가 없는 자체완결 문서(이 리포의 책 페이지)는 charset 선언 **뒤에**
    # 넣는다. 맨 앞에 붙이면 <meta charset> 이 브라우저의 1024바이트 스니핑 창
    # 밖으로 밀려, charset 헤더를 안 보내는 서버나 file:// 에서 한글이 깨진다.
    m3 = re.search(r'<meta\s+charset=[^>]*>', html, re.I)
    if m3:
        return html[:m3.end()] + "\n" + rail + html[m3.end():]
    return '<meta charset="utf-8">\n' + rail + html

if __name__ == "__main__":
    import sys
    src, slug = sys.argv[1], sys.argv[2]
    s = open(src, encoding="utf-8").read()
    print("주입 결과 길이:", len(inject(s, slug)))
