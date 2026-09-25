/* ============================================================
   검수 모드 — 플레이북 소절 ↔ 실전 시트 구현 위치 대조
   ============================================================ */
(function(){
  'use strict';
  var btn = document.getElementById('splitbtn');
  var note = document.getElementById('jumpnote');
  if(!btn) return;

  var COV = {};
  try { COV = (JSON.parse(document.getElementById('coverage-data').textContent).map) || {}; } catch(e){}

  // 개별 판정 항목(precise anchor)이 있는 소절 집합을 미리 만든다.
  //   ① rules.json 의 ref (STEP2 진입카드 chk-<ref> 로 렌더됨 — 종목 칩을 눌러야 DOM 에 뜨므로 규칙에서 직접 수집)
  //   ② 시트 정적 블록의 data-ref (스코어카드·계산기·게이트 등 — 항상 DOM 에 있음)
  // 개별 판정 항목(precise anchor)의 두 갈래를 따로 모은다 — "도달 가능성"이 다르기 때문.
  //   REF_STEP2: rules.json ref → chk-<ref> 는 STEP2 진입카드 안에만 렌더된다.
  //              그러니 그 소절이 STEP2 로 점프할 때만 실제로 도달한다(2-5처럼 STEP1 로 가는 소절은 도달 불가).
  //   STATIC:    시트 정적 블록의 data-ref → 그 STEP 위치에 늘 존재하므로 항상 도달 가능.
  var REF_STEP2 = {};
  var REF_PROD = {};   // ref → 그 항목이 사는 종목(STEP2 카드에서 어느 칩을 열어야 chk-<ref> 가 뜨는지)
  var STATIC_REF = {};
  try {
    var _rules = JSON.parse(document.getElementById('rules').textContent);
    var _data = (_rules && _rules.DATA) || {};
    Object.keys(_data).forEach(function(prod){
      var cfg = _data[prod]; if(!cfg || typeof cfg !== 'object') return;
      ['filter','entry','avoid','caution'].forEach(function(grp){
        (cfg[grp] || []).forEach(function(c){
          if(c && c.ref){ REF_STEP2[c.ref] = 1; if(!REF_PROD[c.ref] && prod !== 'COMMON') REF_PROD[c.ref] = prod; }
        });
      });
    });
  } catch(e){}
  Array.prototype.forEach.call(document.querySelectorAll('#panel-sheet [data-ref]'), function(el){
    (el.getAttribute('data-ref') || '').split(/\s+/).forEach(function(k){ if(k) STATIC_REF[k] = 1; });
  });
  // 헤딩 태그·판정용: 이 소절이 클릭했을 때 실제로 개별 항목에 도달하는가?
  //   jump 이 REF_PROD 칩을 늘 열고 chk 탐색은 시트 전체를 훑으므로,
  //   rules ref(REF_STEP2)든 정적 data-ref(STATIC_REF)든 항상 도달 가능.
  function hasPrecise(key){ return !!(STATIC_REF[key] || REF_STEP2[key]); }

  // 커버리지의 step → 시트 앵커. 일부 소절은 실제 구현 위치가 달라 따로 지정한다.
  var STEP2ANCHOR = {
    'STEP1':'sheet-step1', 'STEP2-filter':'sheet-step2', 'STEP2-entry':'sheet-step2',
    'STEP2-avoid':'sheet-step2', 'STEP2-exit':'sheet-step2', 'STEP3':'sheet-step3',
    'STEP3-B':'sheet-step3b', 'STEP3-C':'sheet-step3c', 'STEP4':'sheet-step4',
    'STEP5':'sheet-step5', 'STEP6':'sheet-step6', 'STEP7':'sheet-step7'
  };
  var OVERRIDE = { '5-5':'sheet-step3b' };   // 5-3 은 경기침체 전용 패널 삭제로 STEP2 카드(카운트-그룹)로 자연 라우팅
  // 장 번호 → 그 장이 다루는 종목(시트 STEP2 칩을 맞춰 연다)
  var CHAP_PROD = { '3':'TQQQ', '4':'SOXL', '5':'UPRO' };

  function anchorFor(key){
    if(OVERRIDE[key]) return OVERRIDE[key];
    var c = COV[key];
    if(!c) return null;
    if(c.status === 'mindset') return null;
    return STEP2ANCHOR[c.step] || null;
  }

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
      // 두 패널을 동시에 보여야 하므로 탭 활성 상태를 둘 다 켠다
      document.getElementById('panel-playbook').classList.add('active');
      document.getElementById('panel-sheet').classList.add('active');
      fitTop();
    } else {
      note.classList.remove('show');
      // 탭 버튼이 가리키는 패널만 남긴다
      var act = document.querySelector('.tab.active');
      var want = act ? act.dataset.tab : 'playbook';
      ['playbook','sheet'].forEach(function(k){
        document.getElementById('panel-'+k).classList.toggle('active', k === want);
      });
    }
    try { localStorage.setItem('etf-split', on ? '1' : '0'); } catch(e){}
  }
  btn.addEventListener('click', function(){ setSplit(!document.body.classList.contains('split')); });
  window.addEventListener('resize', function(){ if(document.body.classList.contains('split')) fitTop(); });

  /* ---- 소절 → 시트 점프 ---- */
  function flash(el){
    el.classList.remove('jump-hit');
    void el.offsetWidth;            // 리플로우로 애니메이션 재시작
    el.classList.add('jump-hit');
    setTimeout(function(){ el.classList.remove('jump-hit'); }, 2200);
  }

  function jump(key, title, targetLabel){
    var id = anchorFor(key);
    var c = COV[key] || {};
    var pane = document.getElementById('panel-sheet');

    if(!id){
      note.innerHTML = '<span class="x" id="jnx">✕</span><b>' + (title || key) + '</b> — '
        + (c.status === 'mindset'
            ? '체크리스트 대상이 아닌 <b>원칙·배경</b>입니다. ' + (c.note || '')
            : '연결된 시트 위치가 없습니다.');
      note.classList.add('show');
      bindClose();
      return;
    }
    var target = document.getElementById(id);
    if(!target){ return; }

    // STEP2 진입카드는 종목별 — 이 소절의 chk-<ref> 가 사는 종목 칩을 먼저 연다.
    //   jump 의 chk 탐색은 시트 전체를 훑으므로(특정 STEP 만이 아님), 그 항목이 어느 STEP 으로
    //   분류됐든(예: 3-2 는 STEP3 계산기로 분류되지만 chk-3-2 는 TQQQ STEP2 필터에 있다)
    //   해당 종목 카드가 렌더돼 있어야 도달한다. 그래서 STEP2 여부와 무관하게 항상 연다.
    var m = String(key).match(/^(\d+)-/);
    var prod = REF_PROD[key] || (m && CHAP_PROD[m[1]]);
    if(prod){
      var chip = document.querySelector('.td-chip[data-jump="' + prod + '"]');
      if(chip) chip.click();
    }

    if(!document.body.classList.contains('split')){
      // 단일 탭 모드면 시트 탭으로 전환
      var sheetTab = document.querySelector('.tab[data-tab="sheet"]');
      if(sheetTab) sheetTab.click();
    }

    // 이 소절 ref 로 심어둔 개별 판정 항목을 찾는다 — 있으면 큰 제목이 아니라 그 항목을 가리킨다.
    //   ① STEP2 진입카드: chk() 가 붙인 id="chk-<ref>"[-n]  (book-agnostic, rules.json ref)
    //   ② 그 외 STEP(스코어카드·계산기·게이트 등): 해당 시트 블록에 심은 data-ref="<key>"
    //      (정적 HTML이라 id 충돌 없이, 한 블록이 여러 소절을 겸하면 data-ref="a b" 로 나열)
    var checks = document.querySelectorAll(
      '#panel-sheet [id="chk-' + key + '"], #panel-sheet [id^="chk-' + key + '-"], ' +
      '#panel-sheet [data-ref~="' + key + '"]');
    var hasChk = checks.length > 0;

    // 여러 규칙이 한 소절을 공유하면(4-3 등), 클릭한 bullet 의 규칙 라벨과 일치하는 항목을 콕 집는다.
    var pick = null;
    if(hasChk && targetLabel){
      var want = String(targetLabel).replace(/\s+/g,'');
      for(var ci=0; ci<checks.length; ci++){
        var ctxt = ((checks[ci].querySelector('.txt') || checks[ci]).textContent || '').replace(/\s+/g,'');
        if(ctxt.indexOf(want) >= 0){ pick = checks[ci]; break; }
      }
    }

    setTimeout(function(){
      var scrollTo = pick || (hasChk ? checks[0] : target);   // 규칙 콕집기 > 소절 첫항목 > STEP 제목
      if(document.body.classList.contains('split') && pane){
        // pane 뷰포트 대비 실제 위치로 계산해 정확한 항목으로 스크롤한다(offsetParent 기준 아님).
        var pr = pane.getBoundingClientRect(), er = scrollTo.getBoundingClientRect();
        pane.scrollTo({top: pane.scrollTop + (er.top - pr.top) - 12, behavior:'smooth'});
      } else {
        scrollTo.scrollIntoView({behavior:'smooth', block:'start'});
      }
      if(hasChk){
        if(pick){ flash(pick); } else { Array.prototype.forEach.call(checks, flash); }   // 콕집은 그 항목만, 아니면 소절 전체
      } else {
        flash(target.nextElementSibling && target.nextElementSibling.classList.contains('card')
              ? target.nextElementSibling : target);
      }
    }, 60);

    var st = c.status === 'reflected' ? '✅ 반영' : (c.status === 'gap' ? '⚠ 미반영' : '💭 원칙');
    var hitTxt = hasChk
      ? ((checks[0].querySelector('.txt') || checks[0]).textContent || '').trim().slice(0, 40)
      : (target.textContent || '').trim().slice(0, 40);
    // 개별 판정 항목이 없으면 "STEP 전체로 갔다"는 걸 정직하게 알린다(고장난 점프가 아님).
    var fbNote = '';
    if(!hasChk){
      fbNote = '<br><span style="color:var(--warn)">⚠ 이 소절은 개별 판정 항목이 없습니다 — '
             + (c.status === 'gap'
                 ? 'STEP 전체에 해당(시트 미반영 부분 있음)'
                 : 'STEP 전체에 걸쳐 반영') + '</span>';
    }
    note.innerHTML = '<span class="x" id="jnx">✕</span><b>' + (title || key) + '</b> → <b id="jhit">'
      + hitTxt + '</b> &nbsp;' + st + fbNote
      + '<br><span style="color:var(--mute)">' + (c.note || '') + '</span>';
    note.classList.add('show');
    bindClose();
  }

  window.__jumpToSheet = jump;   // 요약표에서 재사용

  function bindClose(){
    var x = document.getElementById('jnx');
    if(x) x.onclick = function(){ note.classList.remove('show'); };
  }

  /* ---- 플레이북 소절 제목에 점프 버튼 달기 ---- */
  function decorate(){
    var heads = document.querySelectorAll('#content h3, #content h2');
    Array.prototype.forEach.call(heads, function(h){
      if(h.dataset.jumpReady) return;
      var t = (h.textContent || '').trim();
      var m = t.match(/^\s*([0-9]+-[0-9]+|에필로그)/);
      if(!m) return;
      var key = m[1];
      h.dataset.jumpReady = '1';
      h.classList.add('jumpable');
      // '시트에서 보기 →' 배지는 표시하지 않는다(소절 제목 자체가 클릭 가능).
      h.addEventListener('click', function(ev){
        ev.stopPropagation();
        jump(key, t.replace(/시트에서 보기 →|STEP 전체 보기 →|원칙\(시트 없음\)/, '').trim().slice(0, 40));
      });
    });
  }
  decorate();
  // 챕터를 펼칠 때 새로 그려지는 소절에도 붙인다
  document.addEventListener('toggle', function(){ setTimeout(decorate, 0); }, true);

  try { if(localStorage.getItem('etf-split') === '1') setSplit(true); } catch(e){}
})();

/* ============================================================
   체크리스트 반영 현황 요약표 — 소절을 하나씩 안 눌러도 전체가 보이게
   ============================================================ */
(function(){
  'use strict';
  var rowsEl = document.getElementById('covRows');
  if(!rowsEl) return;

  var COV = {};
  try { COV = (JSON.parse(document.getElementById('coverage-data').textContent).map) || {}; } catch(e){}

  var STEPNAME = JSON.parse(document.getElementById('rules').textContent).STEPNAME;   // SSOT: rules.json STEPNAME (하드코딩 제거)

  // 소절 제목은 플레이북 원문에서 가져온다(따로 적지 않는다 — 어긋날 수 있으므로)
  var TITLE = {};
  (function(){
    var raw = '';
    try { raw = document.getElementById('src').textContent; } catch(e){ return; }
    raw.split('\n').forEach(function(l){
      var m = l.match(/^#{2,3}\s*([0-9]+-[0-9]+|에필로그)[.\s]\s*(.*)$/);
      if(m) TITLE[m[1]] = (m[2] || '').replace(/\*\*/g, '').trim();
    });
  })();

  function keyNum(k){
    if(k === '에필로그') return [99, 99];
    if(k === '0') return [0, 0];
    var p = k.split('-');
    return [parseInt(p[0], 10) || 0, parseInt(p[1], 10) || 0];
  }
  var keys = Object.keys(COV).sort(function(a, b){
    var x = keyNum(a), y = keyNum(b);
    return x[0] - y[0] || x[1] - y[1];
  });

  var n = {reflected:0, gap:0, mindset:0};
  keys.forEach(function(k){ var s = (COV[k]||{}).status; if(n[s] !== undefined) n[s]++; });
  document.getElementById('covTally').innerHTML =
      '<span class="pill ref">✅ 반영 ' + n.reflected + '</span>'
    + '<span class="pill gap">⚠ 미반영 ' + n.gap + '</span>'
    + '<span class="pill mind">💭 원칙 ' + n.mindset + '</span>';

  function render(filter){
    var html = '', lastChap = null;
    keys.forEach(function(k){
      var c = COV[k] || {};
      if(filter !== 'all' && c.status !== filter) return;
      var chap = k === '에필로그' ? '에필로그'
               : k === '0' ? '0. 저자가 반복 강조하는 핵심 원칙'
               : ('Chapter ' + k.split('-')[0]);
      if(chap !== lastChap){ html += '<div class="covchap">' + chap + '</div>'; lastChap = chap; }
      var where = c.status === 'reflected' ? (STEPNAME[c.step] || '시트 반영')
                : c.status === 'gap' ? '⚠ 미반영'
                : '💭 원칙·배경';
      html += '<div class="covrow ' + (c.status === 'reflected' ? 'ref' : c.status)
           + '" data-k="' + k + '">'
           + '<span class="k">' + k + '</span>'
           + '<span class="ttl">' + (TITLE[k] || '<span style="color:var(--mute);font-weight:400">플레이북 본문에 별도 소절 없음 (0장 핵심 원칙에 흡수)</span>')
           + '<span class="note">' + (c.note || '') + '</span></span>'
           + '<span class="where">' + where + '</span>'
           + '</div>';
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

  // 행 클릭 → 시트의 구현 위치로 (검수 모드의 점프 로직 재사용)
  rowsEl.addEventListener('click', function(e){
    var row = e.target.closest('.covrow');
    if(!row) return;
    var k = row.dataset.k;
    if(window.__jumpToSheet) window.__jumpToSheet(k, k + '. ' + (TITLE[k] || ''));
  });
})();