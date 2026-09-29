// 플레이북(원문) 렌더 — 책 무관 SSOT.
//   #src(마크다운 원문) → #content 로 굽고, coverage-data(반영여부)·rules(저자조건)를 겹쳐
//   반영된 저자 조건 bullet 을 노랑(pb-hit)으로 칠하고 클릭 시 그 소절 시트 항목으로 점프시킨다.
//   좌측 목차(nav)·스크롤 하이라이트·모바일 메뉴도 여기서 배선한다.
//
//   책 하드코딩 없음: DOM id(#src #coverage-data #rules #content #nav .navlink #side #menubtn)와
//   rules.json 스키마만 안다. 점프는 window.__jumpToSheet(review-ui) 에 위임한다.
//   고치는 곳은 언제나 이 파일이고, inject_ui.py 가 각 책 페이지에 사본을 심는다.
(function(){
  const raw = document.getElementById('src').textContent;
  const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  // 시트 반영여부 매핑 (coverage-data JSON, build 시 주입)
  const COV = (function(){ try { return (JSON.parse(document.getElementById('coverage-data').textContent).map)||{}; } catch(e){ return {}; } })();
  const RULES = JSON.parse(document.getElementById('rules').textContent);
  const STEPNAME = RULES.STEPNAME;
  function covKey(headText){
    const m = headText.match(/^\s*([0-9]+-[0-9]+|에필로그)/);
    return m ? m[1] : null;
  }
  function covBadge(headText){
    const k = covKey(headText); if(!k) return '';
    const c = COV[k]; if(!c) return '';
    if(c.status==='reflected') return ' <span class="covb ref" title="'+esc(c.note||'')+'">✅ '+esc(STEPNAME[c.step]||'시트 반영')+'</span>';
    if(c.status==='gap')      return ' <span class="covb gap" title="'+esc(c.note||'')+'">⚠ 시트 미반영</span>';
    return ' <span class="covb mind" title="'+esc(c.note||'')+'">💭 원칙·배경</span>';
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
      html += '<h3 class="sec">'+inline(ht)+'</h3>';   // 소절 배지 제거 — 대신 반영된 bullet 을 노랑+점프로
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

  // 반영된 저자 조건(bullet) → 노랑 글씨 + 클릭 시 그 소절의 체크리스트 항목으로 점프.
  //   규칙에 bkey(그 조건이 나온 bullet 의 고유 문구)가 있으면, 그 소절 bullet 에서 찾아 링크한다.
  //   한 조건이 여러 소절에 나오면 xref:[{ref,bkey}] 로 보조 위치도 링크.
  //   동의어로 subs 에 합쳐진 조건도 각 sub 의 bkey/ref 로 링크한다 —
  //   점프 목적지(jref)·시트 항목명(t)은 부모 규칙의 것을 그대로 쓴다(sub 는 같은 말이므로 같은 항목으로 착지).
  //   점프 목적지(jref)는 그 규칙이 사는 소절(primary ref)이다.
  (function(){
    var RD = RULES.DATA || {};
    var bk = [];   // {bkey, ref(bullet 있는 소절), jref(점프 목적지), t}
    Object.keys(RD).forEach(function(prod){
      var cfg = RD[prod]; if(!cfg || typeof cfg !== 'object') return;
      ['filter','entry','avoid','caution','exit'].forEach(function(grp){
        (cfg[grp] || []).forEach(function(r){
          if(!r || typeof r !== 'object') return;
          var t = r.t || r.L || '';
          if(r.bkey && r.ref) bk.push({bkey:r.bkey, ref:r.ref, jref:r.ref, t:t});
          (r.xref || []).forEach(function(x){ if(x.bkey && x.ref) bk.push({bkey:x.bkey, ref:x.ref, jref:r.ref, t:t}); });
          (r.subs || []).forEach(function(s){
            if(!s || !s.bkey) return;
            var sref = s.ref || r.ref;   // sub 자체 소절이 있으면 거기서, 없으면 부모 소절에서 찾는다
            if(sref) bk.push({bkey:s.bkey, ref:sref, jref:r.ref, t:t});
          });
        });
      });
    });
    if(!bk.length) return;
    var curRef = null;
    Array.prototype.forEach.call(document.querySelectorAll('#content h3.sec, #content li'), function(n){
      if(n.tagName === 'H3'){ var m=(n.textContent||'').match(/^\s*([0-9]+-[0-9]+|에필로그)/); curRef = m?m[1]:null; return; }
      var txt = n.textContent || '';
      var hit = null;
      for(var i=0;i<bk.length;i++){ if(bk[i].ref===curRef && txt.indexOf(bk[i].bkey)>=0){ hit=bk[i]; break; } }
      if(hit){
        n.classList.add('pb-hit');
        n.setAttribute('title', '시트 항목: ' + hit.t);
        n.addEventListener('click', function(ev){ ev.stopPropagation(); if(window.__jumpToSheet) window.__jumpToSheet(hit.jref, hit.t.slice(0,32), hit.t); });
      }
    });
  })();

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
      var m = (h.textContent||'').match(/^\s*(\d+-\d+|프롤로그|에필로그)/); if(!m) return;
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
