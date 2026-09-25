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
  //   한 조건이 여러 소절에 나오면(예: '엔비디아만 강함'=4-2·4-5) xref:[{ref,bkey}] 로 보조 위치도 링크.
  //   동의어로 subs 에 합쳐진 조건(예: SOXL 4-3 '뉴스재료 소진')도 각 sub 의 bkey/ref 로 링크한다 —
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
})();
