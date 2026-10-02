/* ============================================================
   검수 모드 — 플레이북 소절 ↔ 체크리스트(조건 트리 판정) 위치 대조 (책 무관)
   · 소절 → 체크리스트: 판정 결과 refs[소절].prods 의 상품 카드를 열고 data-ref="<소절>" 줄로 점프
   · 체크리스트 → 소절: 줄의 ref 칩을 누르면 플레이북 그 소절로(window.__jumpToPlaybook)
   ============================================================ */
(function(){
  'use strict';
  var btn = document.getElementById('splitbtn');
  var note = document.getElementById('jumpnote');
  if(!btn) return;

  function refs(){ try { return JSON.parse(document.getElementById('verdict-data').textContent).refs || {}; } catch(e){ return {}; } }
  var ZW = window.BP.ZW;                 // 공용 부품(shared-ui)
  function zones(r){ return (r.zones || []).map(function(z){ return ZW[z] || z; }).join('·'); }

  /* ---- 분할 모드 토글 ---- */
  function fitTop(){
    var bar = document.querySelector('.tabbar'), col = document.getElementById('collect');
    var t = (bar ? bar.offsetHeight : 0) + (col ? col.offsetHeight : 0);
    document.documentElement.style.setProperty('--splittop', t + 'px');
  }
  function setSplit(on){
    document.body.classList.toggle('split', on);
    btn.classList.toggle('on', on);
    btn.textContent = on ? '⇄ 나란히 검수 끄기' : '⇄ 나란히 검수';
    if(on){
      document.getElementById('panel-playbook').classList.add('active');
      document.getElementById('panel-sheet').classList.add('active');
      fitTop();
    } else {
      note.classList.remove('show');
      var act = document.querySelector('.tab.active');
      var want = act ? act.dataset.tab : 'playbook';
      ['playbook','sheet'].forEach(function(k){
        document.getElementById('panel-'+k).classList.toggle('active', k === want);
      });
    }
    try { localStorage.setItem('pb-split', on ? '1' : '0'); } catch(e){}
  }
  btn.addEventListener('click', function(){ setSplit(!document.body.classList.contains('split')); });
  window.addEventListener('resize', function(){ if(document.body.classList.contains('split')) fitTop(); });

  function flash(el){
    el.classList.remove('jump-hit');
    void el.offsetWidth;
    el.classList.add('jump-hit');
    setTimeout(function(){ el.classList.remove('jump-hit'); }, 2200);
  }
  function bindClose(){
    var x = document.getElementById('jnx');
    if(x) x.onclick = function(){ note.classList.remove('show'); };
  }
  function scrollIn(pane, el, off){
    if(document.body.classList.contains('split') && pane){
      var pr = pane.getBoundingClientRect(), er = el.getBoundingClientRect();
      pane.scrollTo({top: pane.scrollTop + (er.top - pr.top) - off, behavior:'smooth'});
    } else {
      el.scrollIntoView({behavior:'smooth', block:'center'});
    }
  }

  /* ---- 소절 → 체크리스트 ---- */
  function jump(key, title){
    var r = refs()[key];
    var unex = (r && r.unexpressed) || [];
    if(!r || (r.auto + r.manual) === 0){
      note.innerHTML = '<span class="x" id="jnx">✕</span><b>' + (title || key) + '</b> — 체크리스트에 이 소절 조건이 없습니다.'
        + (unex.length ? '<br><span style="color:var(--warn)">트리로 못 옮긴 규칙:</span> '
             + unex.map(function(u){ return u.rule + ' <span style="color:var(--mute)">(' + u.reason + ')</span>'; }).join(' · ')
           : ' 원칙·배경이거나 판단 규칙이 아닙니다.');
      note.classList.add('show');
      bindClose();
      return;
    }
    var prod = (r.prods || [])[0];
    var chip = prod && document.querySelector('.td-chip[data-jump="' + prod + '"]');
    if(chip) chip.click();          // 그 소절 조건이 사는 상품 카드를 연다
    if(!document.body.classList.contains('split')){
      var sheetTab = document.querySelector('.tab[data-tab="sheet"]');
      if(sheetTab) sheetTab.click();
    }
    setTimeout(function(){
      var hits = document.querySelectorAll('#panel-sheet [data-ref="' + key + '"]');
      var target = hits[0] || document.getElementById('sheet-step2');
      if(!target) return;
      scrollIn(document.getElementById('panel-sheet'), target, 12);
      Array.prototype.forEach.call(hits.length ? hits : [target], flash);
    }, 80);
    note.innerHTML = '<span class="x" id="jnx">✕</span><b>' + (title || key) + '</b> → ✅ 체크리스트 ' + zones(r)
      + ' · 자동 ' + r.auto + ' · 수동 ' + r.manual + ' · ' + (r.prods || []).join(', ')
      + (unex.length ? '<br><span style="color:var(--warn)">일부는 트리로 못 옮김:</span> '
           + unex.map(function(u){ return u.rule; }).join(' · ') : '');
    note.classList.add('show');
    bindClose();
  }
  window.__jumpToSheet = jump;

  /* ---- 체크리스트 → 플레이북 소절 ---- */
  function jumpToPlaybook(key){
    if(!key) return;
    var heads = document.querySelectorAll('#content h3.sec, #content h3');
    var head = null;
    for(var i=0;i<heads.length;i++){
      var m = (heads[i].textContent || '').match(window.BP.REF_RE);
      if(m && m[1] === String(key)){ head = heads[i]; break; }
    }
    if(!head) return;   // 플레이북에 별도 소절이 없으면(0장 흡수 등) 조용히 넘어간다
    var det = head.closest('details'); if(det && !det.open){ det.open = true; }
    if(!document.body.classList.contains('split')){
      var pbTab = document.querySelector('.tab[data-tab="playbook"]');
      if(pbTab) pbTab.click();
    }
    setTimeout(function(){ scrollIn(document.getElementById('panel-playbook'), head, 60); flash(head); }, 60);
  }
  window.__jumpToPlaybook = jumpToPlaybook;

  /* ---- 플레이북 소절 제목 클릭 → 체크리스트 ---- */
  function decorate(){
    Array.prototype.forEach.call(document.querySelectorAll('#content h3, #content h2'), function(h){
      if(h.dataset.jumpReady) return;
      var t = (h.textContent || '').trim();
      var m = t.match(window.BP.REF_RE);
      if(!m) return;
      h.dataset.jumpReady = '1';
      h.classList.add('jumpable');
      h.addEventListener('click', function(ev){
        if(ev.target.closest('button')) return;      // '원문' 버튼은 따로
        ev.stopPropagation();
        jump(m[1], t.slice(0, 40));
      });
    });
  }
  decorate();
  document.addEventListener('toggle', function(){ setTimeout(decorate, 0); }, true);

  try { if(localStorage.getItem('pb-split') === '1') setSplit(true); } catch(e){}
})();

/* ============================================================
   체크리스트 반영 현황 요약표 — 플레이북 소절마다 체크리스트에 들어갔는지 한눈에
   ============================================================ */
(function(){
  'use strict';
  var rowsEl = document.getElementById('covRows');
  if(!rowsEl) return;
  var REFS = {};
  try { REFS = JSON.parse(document.getElementById('verdict-data').textContent).refs || {}; } catch(e){}
  var ZW = window.BP.ZW;                 // 공용 부품(shared-ui)

  // 소절 목록·제목은 플레이북 원문(#src)에서 가져온다(따로 적지 않는다 — 어긋날 수 있으므로)
  var TITLE = {}, KEYS = [], CHAP = {};
  try {
    document.getElementById('src').textContent.split('\n').forEach(function(l){
      var c = l.match(/^##\s+([0-9A-Za-z가-힣]+)\.\s*(.*)$/);
      if(c){ CHAP[c[1]] = (c[1] + '. ' + c[2]).trim(); return; }
      var m = l.match(window.BP.REF_HEAD_RE);
      if(m && !TITLE[m[1]]){ TITLE[m[1]] = (m[2] || '').replace(/\*\*/g, '').trim(); KEYS.push(m[1]); }
    });
  } catch(e){}
  Object.keys(REFS).forEach(function(k){ if(KEYS.indexOf(k) < 0) KEYS.push(k); });

  function st(k){
    var r = REFS[k];
    if(r && (r.auto + r.manual) > 0) return r.unexpressed ? 'part' : 'ref';
    if(r && r.unexpressed) return 'gap';
    return 'none';
  }
  var n = {ref:0, part:0, gap:0, none:0};
  KEYS.forEach(function(k){ n[st(k)]++; });
  var tally = document.getElementById('covTally');
  if(tally) tally.innerHTML =
      '<span class="pill ref">✅ 반영 ' + (n.ref + n.part) + '</span>'
    + '<span class="pill gap">⚠ 트리로 못 옮김 ' + (n.gap + n.part) + '</span>'
    + '<span class="pill mind">— 없음 ' + n.none + '</span>';

  function render(filter){
    var html = '', lastChap = null;
    KEYS.forEach(function(k){
      var s = st(k), r = REFS[k] || {};
      if(filter === 'reflected' && !(s === 'ref' || s === 'part')) return;
      if(filter === 'gap' && !(s === 'gap' || s === 'part')) return;
      if(filter === 'mindset' && s !== 'none') return;
      var ck = k.indexOf('-') > 0 ? k.split('-')[0] : k;
      var chap = CHAP[ck] || ck;
      if(chap !== lastChap){ html += '<div class="covchap">' + chap + '</div>'; lastChap = chap; }
      var where = (s === 'ref' || s === 'part')
        ? (r.zones || []).map(function(z){ return ZW[z] || z; }).join('·') + ' · 자동 ' + r.auto + ' · 수동 ' + r.manual
        : (s === 'gap' ? '⚠ 트리로 못 옮김' : '— 체크리스트 없음');
      var why = (r.unexpressed || []).map(function(u){ return u.rule + ' (' + u.reason + ')'; }).join(' · ');
      html += '<div class="covrow ' + (s === 'none' ? 'mindset' : (s === 'gap' ? 'gap' : 'ref')) + '" data-k="' + k + '">'
           + '<span class="k">' + k + '</span>'
           + '<span class="ttl">' + (TITLE[k] || '') + '<span class="note">' + why + '</span></span>'
           + '<span class="where">' + where + '</span></div>';
    });
    rowsEl.innerHTML = html || '<div style="padding:16px;color:var(--mute)">해당 항목이 없습니다.</div>';
  }
  render('all');
  document.querySelectorAll('#covFilters button').forEach(function(b){
    b.addEventListener('click', function(){
      document.querySelectorAll('#covFilters button').forEach(function(x){ x.classList.remove('on'); });
      b.classList.add('on');
      render(b.dataset.f);
    });
  });
  rowsEl.addEventListener('click', function(e){
    var row = e.target.closest('.covrow');
    if(!row) return;
    var k = row.dataset.k;
    if(window.__jumpToSheet) window.__jumpToSheet(k, k + '. ' + (TITLE[k] || ''));
  });
})();
