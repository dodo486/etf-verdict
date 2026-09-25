#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""books.json → public/index.html (책 선택 홈/런처). 카드 클릭 시 /slug/ 로 이동."""
import os, sys, json, html

from paths import BASE, PUBLIC, ensure_dir, read_text, write_text

manifest = json.loads(read_text(os.path.join(BASE, "books.json")))
outdir = ensure_dir(PUBLIC)

def esc(s): return html.escape(str(s))

cards = []
for b in manifest["books"]:
    live = b.get("live")
    badge = ('<span class="live"><span class="dot"></span>시세 자동판정</span>'
             if live else '<span class="static">수동 체크 시트</span>')
    cards.append(f'''    <a class="card" href="{esc(b['slug'])}/" style="--accent:{esc(b.get('accent','#d4a24e'))}">
      <div class="tk">{esc(b.get('tickers',''))}</div>
      <h2>{esc(b['title'])}</h2>
      <div class="author">{esc(b.get('author',''))}</div>
      <p>{esc(b.get('desc',''))}</p>
      <div class="foot">{badge}<span class="go">열기 →</span></div>
    </a>''')

page = f'''<!doctype html><html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(manifest.get("site_title","트레이딩 책 플레이북"))}</title>
<style>
:root{{--ground:#12141a;--surface:#1a1e28;--s2:#20242f;--line:#2b303c;--text:#c7ccd6;--head:#eef1f6;--mute:#7a8194;--entry:#3fb950}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--ground);color:var(--text);font-family:-apple-system,"Apple SD Gothic Neo","Pretendard","Segoe UI",sans-serif;line-height:1.6;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:900px;margin:0 auto;padding:56px 20px 100px}}
header{{margin-bottom:34px}}
.kicker{{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--mute);font-weight:700}}
h1{{font-size:clamp(26px,4vw,38px);color:var(--head);font-weight:800;margin:10px 0 6px;letter-spacing:-.01em}}
.sub{{color:var(--mute);font-size:15px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}}
.card{{display:block;text-decoration:none;background:var(--surface);border:1px solid var(--line);border-top:3px solid var(--accent);border-radius:14px;padding:22px 22px 18px;transition:transform .15s,border-color .15s,background .15s}}
.card:hover{{transform:translateY(-3px);background:var(--s2);border-color:var(--accent)}}
.card .tk{{font-size:12px;font-weight:800;letter-spacing:.04em;color:var(--accent)}}
.card h2{{margin:8px 0 2px;font-size:20px;color:var(--head);font-weight:800;line-height:1.3}}
.card .author{{font-size:13px;color:var(--mute);margin-bottom:10px}}
.card p{{font-size:13.5px;color:var(--text);min-height:38px;margin:0 0 14px}}
.card .foot{{display:flex;justify-content:space-between;align-items:center;border-top:1px solid var(--line);padding-top:12px}}
.card .go{{color:var(--accent);font-weight:700;font-size:14px}}
.live{{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:700;color:var(--entry)}}
.live .dot{{width:7px;height:7px;border-radius:50%;background:var(--entry);animation:p 1.5s ease-in-out infinite}}
.static{{font-size:12px;color:var(--mute);font-weight:600}}
@keyframes p{{0%{{box-shadow:0 0 0 0 rgba(63,185,80,.5)}}70%{{box-shadow:0 0 0 6px rgba(63,185,80,0)}}100%{{box-shadow:0 0 0 0 rgba(63,185,80,0)}}}}
.note{{margin-top:30px;color:var(--mute);font-size:12.5px;border-top:1px solid var(--line);padding-top:16px;line-height:1.7}}
@media(prefers-reduced-motion:reduce){{.card{{transition:none}}.live .dot{{animation:none}}}}
</style></head><body><div class="wrap">
<header>
  <div class="kicker">Trading Book Playbooks</div>
  <h1>{esc(manifest.get("site_title","트레이딩 책 플레이북"))}</h1>
  <div class="sub">{esc(manifest.get("site_subtitle",""))}</div>
</header>
<div class="grid">
{chr(10).join(cards)}
</div>
<div class="note">각 책은 저자가 명시한 매매기법만 정량화한 체크리스트입니다. <b>시세 자동판정</b>이 붙은 책은 매일 자동으로 값이 채워지고, <b>수동 체크</b> 책은 무료 데이터가 없어 직접 확인이 필요합니다.</div>
</div></body></html>'''

write_text(os.path.join(outdir, "index.html"), page)
print(f"홈 생성: {os.path.join(outdir, 'index.html')} ({len(manifest['books'])}권)")

# 정적 책(라이브 아님) 조립: 소스 HTML에 레일 주입 → public/slug/index.html
# (라이브 책=etf는 publish_pages.py가 담당하므로 건너뜀)
from inject_nav import inject
from inject_rules import gate as rules_gate
from paths import playbook_src   # 소스 경로는 규칙(<slug>-playbook.html)에서 — 책마다 dict 에 안 박음
for b in manifest["books"]:
    if b.get("live"):
        continue
    slug = b["slug"]; src = playbook_src(slug)
    if not src or not os.path.exists(src):
        print(f"  (건너뜀: {slug} 소스 없음)"); continue
    s = read_text(src)
    # 규칙 사본 드리프트 게이트 — 갈라진 채로 내보내지 않는다(분리 전 책은 '미적용'으로 보고)
    ok, lines = rules_gate(s, slug)
    for l in lines:
        print(f"  {l}")
    if not ok:
        print("  규칙 드리프트 — 발행을 멈춥니다.", file=sys.stderr)
        sys.exit(1)
    d = ensure_dir(os.path.join(outdir, slug))
    write_text(os.path.join(d, "index.html"), inject(s, slug))
    print(f"  정적 책 조립: {os.path.join(d, 'index.html')}")
