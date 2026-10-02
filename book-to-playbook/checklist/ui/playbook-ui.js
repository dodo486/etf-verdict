// 플레이북(원문) 렌더 — 책 무관 SSOT.
//   #src(마크다운 원문) → #content 로 굽고, 판정 결과(#verdict-data)의 refs(소절별 체크리스트 반영 현황)를
//   소절 제목에 배지로 겹친다 — 소절이 체크리스트(조건 트리)에 몇 개 조건으로 들어갔는지, 못 들어갔으면 왜인지.
//   좌측 목차(nav)·스크롤 하이라이트·모바일 메뉴·본문 검색·소절 원문 보기도 여기서 배선한다.
//
//   책 하드코딩 없음: DOM id(#src #verdict-data #content #nav .navlink #side #menubtn)와 판정 출력 계약만 안다.
//   점프는 window.__jumpToSheet(review-ui) 에 위임한다. 고치는 곳은 언제나 이 파일이다.
(function(){
  const raw = document.getElementById('src').textContent;
  const esc = window.BP.esc;            // 공용 부품(shared-ui) — 고치는 곳은 거기 하나
  const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  const REFS = (function(){ try { return JSON.parse(document.getElementById('verdict-data').textContent).refs || {}; } catch(e){ return {}; } })();
  const ZW = window.BP.ZW;
  function refBadge(headText){
    const m = headText.match(window.BP.REF_RE); if(!m) return '';
    const r = REFS[m[1]];
    if(r && (r.auto + r.manual) > 0){
      const z = (r.zones||[]).map(x=>ZW[x]||x).join('·');
      return ' <span class="covb ref" title="체크리스트 '+esc(z)+' — 자동 '+r.auto+' · 수동 '+r.manual+'">✅ '+esc(z)+'</span>';
    }
    if(r && r.unexpressed) return ' <span class="covb gap" title="'+esc(r.unexpressed.map(u=>u.rule+' — '+u.reason).join(' / '))+'">⚠ 트리로 못 옮김</span>';
    return ' <span class="covb mind" title="체크리스트에 해당 조건 없음(원칙·배경이거나 판단 규칙이 아님)">— 체크리스트 없음</span>';
  }

  const lines = raw.split('\n');
  let html = '';            // main content
  const nav = [];           // {id,num,title}
  let chapOpen = false;
  let listBuf = [];
  let tableBuf = [];
  let secIdx = 0;

  function flushList(){
    if(listBuf.length){
      html += '<ul>'+listBuf.map(li=>'<li>'+inline(li)+'</li>').join('')+'</ul>';
      listBuf = [];
    }
  }
  function flushTable(){
    if(!tableBuf.length) return;
    const rows = tableBuf.filter(r=>!/^\|[\s:|-]+\|$/.test(r.trim()));
    let out = '<div class="tablewrap"><table>';
    rows.forEach((r,i)=>{
      const cells = r.split('|').slice(1,-1).map(c=>c.trim());
      const tag = i===0 ? 'th' : 'td';
      const sect = i===0 ? 'thead':'tbody';
      if(i===0) out += '<thead><tr>'+cells.map(c=>'<th>'+inline(c)+'</th>').join('')+'</tr></thead><tbody>';
      else out += '<tr>'+cells.map(c=>'<td>'+inline(c)+'</td>').join('')+'</tr>';
    });
    out += '</tbody></table></div>';
    html += out;
    tableBuf = [];
  }
  function closeChap(){
    if(chapOpen){ flushList(); flushTable(); html += '</div></details></section>'; chapOpen=false; }
  }

  for(let line of lines){
    const t = line.trim();
    if(t.startsWith('|')){ flushList(); tableBuf.push(t); continue; }
    else if(tableBuf.length){ flushTable(); }

    if(t.startsWith('## ')){
      closeChap();
      const title = t.slice(3);
      const m = title.match(/^([0-9A-Z]+)\.\s*(.*)$/);
      const num = m ? m[1] : '';
      const label = m ? m[2] : title;
      const id = 'c'+(secIdx++);
      nav.push({id, num, title:label});
      const isPrinciple = num==='0';
      html += '<section class="chap" id="'+id+'"><details class="chap"'+(isPrinciple?' open':'')+'>'
            + '<summary><span class="cn">'+esc(num)+'</span><h2>'+inline(label)+'</h2><span class="chev">▶</span></summary>'
            + '<div class="chap-body'+(isPrinciple?' principles':'')+'">';
      chapOpen = true;
    }
    else if(t.startsWith('### ')){
      flushList();
      const ht = t.slice(4);
      html += '<h3 class="sec">'+inline(ht)+refBadge(ht)+'</h3>';
    }
    else if(t.startsWith('- ')){
      listBuf.push(t.slice(2));
    }
    else if(t===''){
      flushList();
    }
    else {
      flushList();
      html += '<p>'+inline(t)+'</p>';
    }
  }
  closeChap();

  document.getElementById('content').innerHTML = html;

  // ── 소절 원문보기 (책 무관 · 검수여부 무관) ──────────────────────────────
  //   #source-data(소절 ref → 책 원문)를 각 소절 헤딩에 '원문' 토글로 붙인다.
  //   원문 파일이 있는 책만 실제 원문이 뜨고, 없는 책은 '원문 미제공'으로 표시.
  (function(){
    var SRC = {}; try { SRC = JSON.parse(document.getElementById('source-data').textContent) || {}; } catch(e){}
    var st = document.createElement('style');
    st.textContent =
      '.pb-src-btn{margin-left:8px;font-size:11px;padding:2px 8px;border:1px solid var(--line,#ccc);'
      +'border-radius:10px;background:transparent;color:var(--mute,#888);cursor:pointer;vertical-align:middle}'
      +'.pb-src-btn:hover{color:inherit;border-color:var(--accent,#888)}'
      +'.pb-src-btn.on{background:var(--accent,#3fae7a);color:#fff;border-color:transparent}'
      +'.pb-src-panel{margin:6px 0 12px;padding:12px 14px;border-left:3px solid var(--accent,#3fae7a);'
      +'background:var(--s2,rgba(127,127,127,.08));border-radius:0 8px 8px 0;white-space:pre-wrap;'
      +'font-size:13.5px;line-height:1.7;color:var(--text,inherit)}'
      +'.pb-src-panel.empty{color:var(--mute,#999);font-style:italic;border-left-color:var(--line,#ccc)}';
    document.head.appendChild(st);
    Array.prototype.forEach.call(document.querySelectorAll('#content h3.sec'), function(h){
      var m = (h.textContent||'').match(window.BP.REF_RE); if(!m) return;
      var ref = m[1], text = SRC[ref];
      var btn = document.createElement('button');
      btn.type = 'button'; btn.className = 'pb-src-btn'; btn.textContent = '원문';
      var panel = document.createElement('div');
      panel.className = 'pb-src-panel' + (text ? '' : ' empty');
      panel.textContent = text || '원문 미제공 (이 책은 원문 파일이 없습니다)';
      panel.style.display = 'none';
      btn.addEventListener('click', function(ev){
        ev.stopPropagation();
        var show = panel.style.display === 'none';
        panel.style.display = show ? 'block' : 'none';
        btn.classList.toggle('on', show);
      });
      h.appendChild(btn);
      h.parentNode.insertBefore(panel, h.nextSibling);
    });
  })();

  document.getElementById('nav').innerHTML = nav.map(n=>
    '<li><a class="navlink" href="#'+n.id+'"><span class="n">'+esc(n.num)+'</span><span>'+esc(n.title)+'</span></a></li>'
  ).join('');

  // active section highlight
  const links = [...document.querySelectorAll('.navlink')];
  const map = {};
  links.forEach(l=>map[l.getAttribute('href').slice(1)]=l);
  const obs = new IntersectionObserver(entries=>{
    entries.forEach(e=>{
      if(e.isIntersecting){
        links.forEach(l=>l.classList.remove('active'));
        const l = map[e.target.id];
        if(l) l.classList.add('active');
      }
    });
  },{rootMargin:'-10% 0px -80% 0px'});
  nav.forEach(n=>{const el=document.getElementById(n.id); if(el) obs.observe(el);});

  // clicking a nav link opens that chapter
  links.forEach(l=>l.addEventListener('click',()=>{
    const el = document.getElementById(l.getAttribute('href').slice(1));
    const d = el && el.querySelector('details');
    if(d) d.open = true;
    document.getElementById('side').classList.remove('open');
  }));

  // mobile menu
  const btn = document.getElementById('menubtn');
  const side = document.getElementById('side');
  if(btn) btn.addEventListener('click',()=>side.classList.toggle('open'));

  // ── 본문 단어 검색 (책 무관 · 검수여부 무관) ──────────────────────────────
  //   #content 텍스트에서 단어를 찾아 하이라이트, 매치 든 챕터를 펼치고, 이전/다음 점프.
  //   스타일도 여기서 주입한다(페이지 CSS 손 안 대고 모든 책에 전파).
  (function(){
    const content = document.getElementById('content');
    if(!content) return;
    const st = document.createElement('style');
    st.textContent =
      '.pb-search-bar{position:sticky;top:0;z-index:20;display:flex;gap:6px;align-items:center;'
      +'padding:8px 0;margin-bottom:6px;background:var(--bg,#fff)}'
      +'.pb-search-bar input{flex:1;min-width:0;padding:7px 10px;border:1px solid var(--line,#ccc);'
      +'border-radius:8px;font-size:14px;background:var(--surface,#fff);color:inherit}'
      +'.pb-search-bar button{padding:6px 9px;border:1px solid var(--line,#ccc);border-radius:8px;'
      +'background:transparent;color:inherit;cursor:pointer;font-size:13px}'
      +'.pb-search-bar .pbs-count{font-size:12px;color:var(--mute,#888);min-width:44px;text-align:center}'
      +'mark.pb-s{background:#ffe58a;color:inherit;border-radius:2px;padding:0 1px}'
      +'mark.pb-s.cur{background:#ff9f43;box-shadow:0 0 0 2px rgba(255,159,67,.4)}';
    document.head.appendChild(st);

    const bar = document.createElement('div');
    bar.className = 'pb-search-bar';
    bar.innerHTML = '<input type="search" placeholder="본문에서 단어 검색…" aria-label="본문 검색">'
      + '<span class="pbs-count"></span>'
      + '<button class="pbs-prev" title="이전(Shift+Enter)">↑</button>'
      + '<button class="pbs-next" title="다음(Enter)">↓</button>';
    content.parentNode.insertBefore(bar, content);
    const input = bar.querySelector('input');
    const cnt = bar.querySelector('.pbs-count');
    let marks = [], idx = -1;

    function unmark(){
      content.querySelectorAll('mark.pb-s').forEach(m=>{
        m.parentNode.replaceChild(document.createTextNode(m.textContent), m);
      });
      content.normalize(); marks = []; idx = -1;
    }
    function textNodes(){
      const w = document.createTreeWalker(content, NodeFilter.SHOW_TEXT, {
        acceptNode: n => (n.parentNode && /^(SCRIPT|STYLE|MARK)$/.test(n.parentNode.nodeName))
          ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
      const out = []; while(w.nextNode()) out.push(w.currentNode); return out;
    }
    function focusMark(){
      marks.forEach(m=>m.classList.remove('cur'));
      const m = marks[idx]; if(!m) return;
      m.classList.add('cur');
      m.scrollIntoView({block:'center', behavior:'smooth'});
      cnt.textContent = (idx+1)+' / '+marks.length;
    }
    function step(d){ if(!marks.length) return; idx = (idx+d+marks.length)%marks.length; focusMark(); }
    function search(q){
      unmark();
      if(!q){ cnt.textContent = ''; return; }
      const ql = q.toLowerCase();
      textNodes().forEach(function(node){
        const txt = node.nodeValue, low = txt.toLowerCase();
        let i = low.indexOf(ql); if(i < 0) return;
        const frag = document.createDocumentFragment(); let last = 0;
        while(i >= 0){
          if(i > last) frag.appendChild(document.createTextNode(txt.slice(last, i)));
          const mk = document.createElement('mark'); mk.className = 'pb-s';
          mk.textContent = txt.slice(i, i+q.length);
          frag.appendChild(mk); marks.push(mk);
          last = i + q.length; i = low.indexOf(ql, last);
        }
        if(last < txt.length) frag.appendChild(document.createTextNode(txt.slice(last)));
        node.parentNode.replaceChild(frag, node);
      });
      marks.forEach(m=>{ const d = m.closest('details'); if(d) d.open = true; });
      cnt.textContent = marks.length ? ('1 / '+marks.length) : '없음';
      idx = marks.length ? 0 : -1;
      if(idx === 0) focusMark();
    }
    let deb;
    input.addEventListener('input', ()=>{ clearTimeout(deb); deb = setTimeout(()=>search(input.value.trim()), 120); });
    input.addEventListener('keydown', e=>{
      if(e.key === 'Enter'){ e.preventDefault(); step(e.shiftKey ? -1 : 1); }
      else if(e.key === 'Escape'){ input.value = ''; search(''); }
    });
    bar.querySelector('.pbs-next').addEventListener('click', ()=>step(1));
    bar.querySelector('.pbs-prev').addEventListener('click', ()=>step(-1));
  })();
})();
