#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""books.json → 책 선택 앱 셸(좌측 책목록 + 본문 iframe) HTML.

순수 함수 render_home(manifest) 하나뿐이다 — 파일을 쓰지 않는다. 라이브 서버(entry.serve)가
홈(`/`)을 그릴 때 이걸 그대로 쓴다. 정적 발행(파일로 굽기)은 폐지됐다 — 오래된 스냅샷이 매매를
오도하지 않게, 화면은 라이브 서버가 매 요청 엔진을 새로 돌려 그린다.
"""
import html


def esc(s):
    return html.escape(str(s))


def render_home(manifest):
    """books.json(dict) → 단일 앱 셸 HTML. 순수 — 파일을 쓰지 않는다.

    책마다 '따로 사이트'가 아니라 **한곳**에서 관리한다: 좌측 고정 책목록(books.json 그대로 — 책이
    들어오면 자동으로 목록에 뜬다) + 우측 본문(iframe)만 바뀐다. 책을 눌러도 좌측 셸은 그대로라 한
    사이트처럼 느껴진다(전체 리로드·깜빡임 없음). 책 페이지는 각자 자체완결 문서라 그대로 재사용하고,
    셸 안에서 열릴 때는 자기 책목록 레일을 숨긴다(inject_nav 가 iframe 안이면 숨김)."""
    books = manifest.get("books", [])
    items = []
    for b in books:
        slug = esc(b["slug"])
        dot = '<span class="bd"></span>' if b.get("live") else ''
        items.append(
            f'<a class="bitem" data-slug="{slug}" href="{slug}/" style="--ac:{esc(b.get("accent","#d4a24e"))}" title="{esc(b.get("desc",""))}">'
            f'<span class="bt">{esc(b["title"])}</span>'
            f'<span class="bs">{esc(b.get("tickers","") or b.get("author",""))}{dot}</span></a>'
        )
    slugs_js = "[" + ",".join(f'"{esc(b["slug"])}"' for b in books) + "]"
    title = esc(manifest.get("site_title", "트레이딩 책 플레이북"))
    sub = esc(manifest.get("site_subtitle", ""))
    return f'''<!doctype html><html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title}</title>
<style>
:root{{--ground:#0d0f14;--surface:#1a1e28;--s2:#20242f;--line:#2b303c;--text:#c7ccd6;--head:#eef1f6;--mute:#7a8194;--entry:#3fb950;--rail:230px}}
*{{box-sizing:border-box}}
html,body{{height:100%}}
body{{margin:0;background:var(--ground);color:var(--text);font-family:-apple-system,"Apple SD Gothic Neo","Pretendard","Segoe UI",sans-serif;-webkit-font-smoothing:antialiased;overflow:hidden}}
#app{{display:flex;height:100vh;height:100dvh}}
#rail{{width:var(--rail);flex:none;background:var(--ground);border-right:1px solid var(--line);overflow-y:auto;padding:18px 12px;display:flex;flex-direction:column}}
#rail .brand{{font-size:15px;font-weight:800;color:var(--head);line-height:1.3;padding:4px 8px 2px}}
#rail .tag{{font-size:11.5px;color:var(--mute);padding:0 8px 14px;line-height:1.4}}
#rail .rh{{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--mute);font-weight:700;padding:6px 8px 8px}}
#rail .bitem{{display:block;text-decoration:none;padding:11px 12px;border-radius:11px;margin-bottom:7px;border:1px solid transparent;border-left:3px solid transparent;transition:background .12s,border-color .12s}}
#rail .bitem:hover{{background:#171a22}}
#rail .bitem.active{{background:var(--surface);border-color:var(--ac);border-left:3px solid var(--ac)}}
#rail .bt{{display:block;font-size:13.5px;font-weight:700;color:var(--head);line-height:1.35}}
#rail .bitem.active .bt{{color:var(--ac)}}
#rail .bs{{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--mute);margin-top:3px}}
#rail .bd{{width:6px;height:6px;border-radius:50%;background:var(--entry);display:inline-block}}
#rail .foot{{margin-top:auto;font-size:11px;color:var(--mute);padding:12px 8px 4px;border-top:1px solid var(--line);line-height:1.6}}
#stage{{flex:1;position:relative;background:var(--surface)}}
#view{{position:absolute;inset:0;width:100%;height:100%;border:0}}
#menu{{display:none}}
@media(max-width:820px){{
  :root{{--rail:76vw}}
  #rail{{position:fixed;left:0;top:0;bottom:0;z-index:30;max-width:300px;transform:translateX(-100%);transition:transform .2s;box-shadow:0 0 50px rgba(0,0,0,.6)}}
  #rail.open{{transform:none}}
  #menu{{display:inline-flex;align-items:center;gap:6px;position:fixed;z-index:40;top:10px;left:12px;background:var(--s2);color:var(--head);border:1px solid var(--line);border-radius:10px;padding:8px 13px;font-size:14px;font-weight:700;cursor:pointer}}
  #scrim{{position:fixed;inset:0;z-index:25;background:rgba(0,0,0,.5);opacity:0;pointer-events:none;transition:opacity .2s}}
  #scrim.on{{opacity:1;pointer-events:auto}}
}}
</style></head><body>
<div id="app">
  <nav id="rail">
    <div class="brand">📚 {title}</div>
    <div class="tag">{sub}</div>
    <div class="rh">내 책</div>
    {''.join(items)}
    <div class="foot">책이 늘면 여기 자동으로 추가됩니다.<br>시세 자동판정 ● 은 매일 값이 채워집니다.</div>
  </nav>
  <div id="stage">
    <button id="menu" onclick="RAIL(true)">☰ 책</button>
    <iframe id="view" name="view" title="{title}"></iframe>
  </div>
</div>
<div id="scrim" onclick="RAIL(false)"></div>
<script>
(function(){{
  var SLUGS = {slugs_js};
  var rail = document.getElementById('rail'), scrim = document.getElementById('scrim');
  function RAIL(open){{ rail.classList.toggle('open', open); if(scrim) scrim.classList.toggle('on', open); }}
  window.RAIL = RAIL;
  function sel(slug, push){{
    if(!slug || SLUGS.indexOf(slug) < 0) slug = SLUGS[0];
    document.getElementById('view').src = slug + '/';
    var items = document.querySelectorAll('#rail .bitem');
    for(var k=0;k<items.length;k++) items[k].classList.toggle('active', items[k].getAttribute('data-slug') === slug);
    document.title = slug + ' · {title}';
    if(push && location.hash.slice(1) !== slug) history.replaceState(null, '', '#' + slug);
    RAIL(false);
  }}
  var items = document.querySelectorAll('#rail .bitem');
  for(var k=0;k<items.length;k++) items[k].addEventListener('click', function(e){{
    e.preventDefault(); sel(this.getAttribute('data-slug'), true);
  }});
  window.addEventListener('hashchange', function(){{ sel(location.hash.slice(1), false); }});
  sel(location.hash.slice(1) || SLUGS[0], true);
}})();
</script>
</body></html>'''


if __name__ == "__main__":
    import sys
    from shared.paths import load_manifest
    sys.stdout.write(render_home(load_manifest()))   # 미리보기용 — 파일로 굽지 않는다(라이브 서버가 그린다)
