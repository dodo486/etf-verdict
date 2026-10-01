(function(){
  'use strict';
  /* ============================================================
     실전 체크리스트 — 조건 트리 판정 결과(#verdict-data)만 그린다 (책 무관 · 종목 하드코딩 없음)
     · 트리를 직접 읽지 않는다. 구간③ 판정 엔진(verdict_engine)이 낸 칸별 설명(view)을 그대로 그린다.
     · 사람이 체크하는 건 수동(✋) 조건뿐이다. 체크하면 엔진과 같은 3값 논리로 등급을 다시 낸다
       (자동 조건은 잠겨 있다). 첫 렌더에서 '아무것도 체크 안 함' 결과가 엔진 값과 같은지 스스로 확인하고,
       다르면 경고를 띄운다 — 화면 계산이 엔진과 조용히 갈라지지 않게.
     ============================================================ */

  /* ---- 탭 전환 ---- */
  const tabs = document.querySelectorAll('.tab');
  tabs.forEach(t=>t.addEventListener('click',()=>{
    tabs.forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    document.querySelectorAll('.tabpanel').forEach(p=>p.classList.remove('active'));
    document.getElementById('panel-'+t.dataset.tab).classList.add('active');
    window.scrollTo(0,0);
  }));

  const root = document.getElementById('sheet-root');
  if(!root) return;
  const esc = s => String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  function readVD(){ try { return JSON.parse(document.getElementById('verdict-data').textContent); } catch(e){ return null; } }
  let VD = readVD();
  let curP = null;
  const LS = 'ck.v2';
  let store = {};
  try { store = JSON.parse(localStorage.getItem(LS) || '{}') || {}; } catch(e){ store = {}; }
  function save(){ try { localStorage.setItem(LS, JSON.stringify(store)); } catch(e){} }
  // 수동 조건 답은 그날(판정일) 것만 쓴다 — 어제 체크가 오늘 판정에 섞이지 않게.
  function answers(){ const k = (VD && VD.slug || '') + ':' + (VD && VD.date || ''); store.ans = store.ans || {}; store.ans[k] = store.ans[k] || {}; return store.ans[k]; }

  /* ---- 3값 논리 (shared/cond.py 와 같은 규칙) ----
     fill = 답 안 한 수동 조건에 넣을 값(null = 모름). not 아래에서는 뒤집힌다(cond 의 극성 규칙). */
  function and3(vs){ if(vs.some(v=>v===false)) return false; if(vs.some(v=>v===null)) return null; return true; }
  function or3(vs){ if(vs.some(v=>v===true)) return true; if(vs.some(v=>v===null)) return null; return false; }
  // 수동 조건의 답은 조건 자체로 묶는다: 여러 상품이 같이 보는 정의 안(shared)이면 책 전체에 하나,
  //   아니면 상품마다 하나. path 앞머리(상품 이름 또는 'common')에서 상품을 꺼낸다.
  function mkey(it, path){ return (it.shared ? '*' : path.split('.')[0]) + '|' + it.manual; }
  function ev(it, fill, ans, path){
    if(it.manual !== undefined){ const a = ans[mkey(it, path)]; return a === undefined ? fill : a; }
    if(!it.op) return it.v === undefined ? null : it.v;
    const k = it.kids || [];
    if(it.op === 'not'){ const x = ev(k[0], fill===null?null:!fill, ans, path+'.0'); return x===null?null:!x; }
    if(it.op === 'ref') return ev(k[0], fill, ans, path+'.0');
    const vs = k.map((c,i)=>ev(c, fill, ans, path+'.'+i));
    if(it.op === 'all') return and3(vs);
    if(it.op === 'any') return or3(vs);
    const t = vs.filter(v=>v===true).length, u = vs.filter(v=>v===null).length;   // atleast
    return t >= it.n ? true : (t + u < it.n ? false : null);
  }
  const GR = {buy:'✅ 매수 후보', confirm:'🟡 확인 대기', nofilter:'🚫 진입 금지', avoid:'⛔ 보류', wait:'⚪ 관망', unknown:'❔ 판정 불가'};
  const GCLS = {buy:'go', confirm:'small', unknown:'small', nofilter:'no', avoid:'no', wait:''};
  // shared/tree_grade.ProductEval.grade_key 와 같은 순서
  function gradeKey(v, ans){
    const z = v.zones || {}, P = s => v.prod+'.'+s;
    const o = {filter:ev(z.filter,true,ans,P('filter')), entry:ev(z.entry,true,ans,P('entry')), avoid:ev(z.avoid,false,ans,P('avoid'))};
    const p = {filter:ev(z.filter,false,ans,P('filter')), entry:ev(z.entry,false,ans,P('entry')), avoid:ev(z.avoid,true,ans,P('avoid'))};
    if(p.filter===true && p.avoid===false && p.entry===true) return 'buy';
    if(o.filter===true && o.avoid===false && o.entry===true) return 'confirm';
    if(o.filter===false) return 'nofilter';
    if(o.avoid===true) return 'avoid';
    if(o.filter===true && o.avoid===false && o.entry===false) return 'wait';
    return 'unknown';
  }
  function selfCheck(){
    const bad = [];
    (VD.verdicts||[]).forEach(v=>{
      if(!v.zones) return;
      if(gradeKey(v, {}) !== v.key) bad.push(v.prod);
    });
    return bad;
  }

  /* ---- 그리기 ---- */
  const MARK = v => v===true ? '<span class="ck-m t">●</span>' : (v===false ? '<span class="ck-m f">○</span>' : '<span class="ck-m u">?</span>');
  const OPW = it => it.op==='all' ? '모두' : it.op==='any' ? '하나 이상' : it.op==='atleast' ? (it.n+'개 이상') : it.op==='not' ? '아님 — 아래가 거짓이어야 참' : '';
  function refChip(ref){ return ref ? ' <a class="ck-ref" data-ref="'+esc(ref)+'" title="플레이북 원문 소절로">'+esc(ref)+'</a>' : ''; }
  function fmtV(v){ return typeof v === 'number' ? (Math.abs(v) >= 100 ? v.toFixed(1) : v.toFixed(2)) : ''; }
  // 항목 하나(노드) — 숨김 잎은 계산에만 쓰고 그리지 않는다. 라벨 없는 묶음은 묶음 줄 없이 자식만 들여쓴다.
  function node(it, path, ans, depth){
    if(!it) return '';
    if(it.hidden && !it.kids) return '';
    const kids = (it.kids||[]).map((c,i)=>node(c, path+'.'+i, ans, depth+1)).join('');
    const showRow = it.label || it.manual !== undefined;
    if(!showRow){
      if(!kids) return '';
      return it.op ? '<div class="ck-grp"><div class="ck-op">'+esc(OPW(it))+'</div>'+kids+'</div>' : kids;
    }
    const isM = it.manual !== undefined;
    const a = isM ? ans[mkey(it, path)] : undefined;
    const val = isM ? (a === undefined ? null : a) : (it.op ? ev(it, null, ans, path) : it.v);
    let ctl;
    if(isM){
      ctl = '<span class="ck-man" data-key="'+esc(mkey(it, path))+'"'+(it.shared?' title="여러 상품이 같이 보는 조건 — 한 번 체크하면 모든 상품에 적용"':'')+'>'
          + '<button data-a="1" class="'+(a===true?'on':'')+'">참</button>'
          + '<button data-a="0" class="'+(a===false?'on':'')+'">거짓</button>'
          + (a!==undefined ? '<button data-a="x" title="답 지우기">↺</button>' : '') + '</span>';
    } else ctl = MARK(val);
    const num = (!isM && typeof it.v === 'number') ? ' <span class="dataval">'+fmtV(it.v)+'</span>' : '';
    const why = isM ? '<div class="ck-why">✋ '+esc(it.manual)+'</div>' : (it.note ? '<div class="ck-why">'+esc(it.note)+'</div>' : '');
    const opl = it.op ? ' <span class="ck-opl">'+esc(OPW(it))+'</span>' : '';
    return '<div class="ck-row'+(isM?' man':' auto')+'" '+(it.ref?'data-ref="'+esc(it.ref)+'"':'')+'>'
      + '<div class="ck-line">'+ctl+'<span class="ck-t">'+esc(it.label || '수동 확인')+opl+num+refChip(it.ref)+'</span></div>'
      + why + (kids ? '<div class="ck-kids">'+kids+'</div>' : '') + '</div>';
  }
  function zoneHead(title, want, val){
    const ok = val === null ? '' : (val === want ? ' ok' : ' bad');
    return '<div class="grouplabel ck-zone'+ok+'">'+title+' <span class="ck-zv">'+(val===true?'참':val===false?'거짓':'확인 필요')+'</span></div>';
  }
  function sellText(s){ return s==='all' ? '남은 전량' : (s.initial!==undefined ? '산 물량의 '+Math.round(s.initial*100)+'%' : '남은 물량의 '+Math.round(s.remaining*100)+'%'); }
  function cautionOf(v, ans){
    let f = 1; const unspec = [], unk = [];
    (v.caution||[]).forEach((c,i)=>{
      const x = ev(c.view, null, ans, v.prod+'.caution.'+i);
      if(x === true){ if(c.scale == null) unspec.push(c.label); else f *= c.scale; }
      else if(x === null) unk.push(c.label);
    });
    return {f:f, unspec:unspec, unk:unk};
  }

  function renderProduct(v){
    const ans = answers();
    const key = v.zones ? gradeKey(v, ans) : v.key;
    const P = s => v.prod+'.'+s;
    let h = '<div class="ck-head"><h3><span class="tk">'+esc(v.prod)+'</span>'+(v.index?' <span class="subtle">기준 지수 '+esc(v.index)+'</span>':'')+'</h3>'
          + '<span class="verdict '+(GCLS[key]||'')+'" style="margin:0;padding:4px 11px;font-size:13.5px">'+GR[key]+'</span></div>';
    if(v.close != null) h += '<p class="subtle" style="margin:4px 0 2px">'+esc(v.date)+' 종가 <b style="color:var(--head)">'+v.close.toFixed(2)+'</b>'+(v.chg!=null?' · 당일 '+(v.chg>=0?'+':'')+v.chg.toFixed(2)+'%':'')+'</p>';
    h += '<p class="subtle" style="margin:2px 0 10px">엔진 판정: '+esc(v.reason)+(key!==v.key?' <b style="color:var(--gold)">→ 체크한 수동 조건 반영: '+GR[key]+'</b>':'')+'</p>';
    if(!v.zones){ return h; }
    const z = v.zones;
    h += zoneHead('① 필터 — 참이어야 본다', true, ev(z.filter,null,ans,P('filter'))) + node(z.filter, P('filter'), ans, 0);
    h += zoneHead('② 회피 — 참이면 보류', false, ev(z.avoid,null,ans,P('avoid'))) + node(z.avoid, P('avoid'), ans, 0);
    h += zoneHead('③ 진입 — 참이면 매수 자리', true, ev(z.entry,null,ans,P('entry'))) + node(z.entry, P('entry'), ans, 0);
    if((v.caution||[]).length){
      const c = cautionOf(v, ans);
      h += '<div class="grouplabel ck-zone" style="color:var(--gold)">④ 조심 — 사더라도 금액을 줄인다 <span class="ck-zv">금액 ×'+c.f.toFixed(2)+(c.unspec.length?' · 폭 미명시 '+c.unspec.length:'')+(c.unk.length?' · 확인 필요 '+c.unk.length:'')+'</span></div>';
      v.caution.forEach((r,i)=>{
        const lab = r.label + (r.scale!=null ? ' (금액 ×'+(+r.scale).toFixed(2)+')' : ' (줄일 폭 저자 미명시)');
        h += node(Object.assign({}, r.view, {label: lab, ref: r.ref, note: r.note}), P('caution.'+i), ans, 0);
      });
    }
    // 매도 규칙 + 내 포지션
    if((v.exit||[]).length){
      h += '<div class="grouplabel ck-zone" style="color:var(--entry)">⑥ 매도 — 보유분을 팔 때 (걸리면 다음 날 시가)</div>';
      const pos = v.positions || [];
      v.exit.forEach((r,i)=>{
        const live = pos.map(ps => (ps.exit||[])[i]).filter(Boolean);
        const st = live.length ? live.map(e=>MARK(e.v)).join('') : '<span class="ck-m n">—</span>';
        h += '<div class="ck-row auto" '+(r.ref?'data-ref="'+esc(r.ref)+'"':'')+'><div class="ck-line">'+st+'<span class="ck-t">'+esc(r.label)+' <span class="ck-opl">'+esc(sellText(r.sell))+'</span>'+refChip(r.ref)+'</span></div>'+(r.note?'<div class="ck-why">'+esc(r.note)+'</div>':'')+'</div>';
      });
      if(pos.length){
        pos.forEach(ps=>{
          h += '<p class="subtle" style="margin:6px 0 0">보유: '+esc(ps.entry_date)+' 매입가 '+esc(ps.entry_px)+' · 수익 '+(ps.ret!=null?(ps.ret>=0?'+':'')+ps.ret.toFixed(2)+'%':'?')+' · '+(ps.days!=null?ps.days+'거래일':'')+(ps.next_tranche?' · 다음 분할 「'+esc(ps.next_tranche.label)+'」 '+(ps.next_tranche.v===true?'<b style="color:var(--entry)">조건 충족</b>':ps.next_tranche.v===false?'미충족':'확인 필요'):'')+'</p>';
        });
      } else {
        h += '<p class="subtle" style="margin:6px 0 0">보유 포지션 없음 — 내 포지션은 로컬 파일(books/&lt;slug&gt;/positions.json)에 적으면 로컬 서버 화면에서 규칙별로 판정됩니다(공개 페이지에는 안 실림).</p>';
      }
    }
    return h;
  }

  function renderSizing(){
    const cap = +(store.capital || 1000);
    const vs = (VD.verdicts||[]).filter(v=>v.sizing);
    if(!vs.length) return '';
    const anyW = vs.some(v=>v.sizing.weight_set);
    const anyT = vs.some(v=>(v.sizing.tranches||[]).length);
    if(!anyW && !anyT) return '';
    let h = '<h2 id="sheet-sizing"><span class="step">⑤</span>비중 · 분할 계산</h2><div class="card">'
          + '<div class="calcrow"><label>총 투자금(만 원) <input id="ckCap" type="number" min="0" step="100" value="'+cap+'"></label></div>'
          + '<div class="tablewrap" style="margin-top:6px"><table><thead><tr><th>상품</th><th>오늘 비중</th><th>오늘 금액</th><th>분할</th></tr></thead><tbody>';
    let sum = 0, known = true;
    vs.forEach(v=>{
      const s = v.sizing, c = cautionOf(v, answers());
      let w = s.weight, wtxt;
      if(!s.weight_set){ wtxt = '<span class="manual-tag">저자 미명시</span>'; w = null; }
      else if(w == null){ known = false; wtxt = '<span class="manual-tag">✋ 확인 필요 '+(s.weight_range||[]).map(x=>x.toFixed(0)+'%').join(' / ')+'</span>'; }
      else { sum += w; wtxt = w.toFixed(1)+'%'; }
      const amt = w == null ? null : cap * w / 100 * c.f;
      const trs = (s.tranches||[]).map(t=>esc(t.label)+(t.frac==null ? ' <span class="manual-tag">비율 저자 미명시</span>' : ' '+Math.round(t.frac*100)+'%'+(amt!=null?' = '+Math.round(amt*t.frac).toLocaleString('ko-KR')+'만':''))+(t.conditional?' <span class="subtle">(조건부)</span>':'')).join('<br>') || '한 번에 전량';
      h += '<tr><td style="color:var(--'+esc(v.prod.toLowerCase())+',var(--head))"><b>'+esc(v.prod)+'</b>'+refChip(s.ref)+'</td><td>'+wtxt+'</td><td>'
         + (amt!=null ? Math.round(amt).toLocaleString('ko-KR')+'만'+(c.f<1?' <span class="subtle">(조심 ×'+c.f.toFixed(2)+')</span>':'') : '—')
         + (c.unspec.length ? '<br><span class="manual-tag">줄일 폭 저자 미명시: '+esc(c.unspec.join(' · '))+'</span>' : '') + '</td><td>'+trs+'</td></tr>';
    });
    h += '</tbody></table></div>';
    if(anyW) h += '<p class="subtle" style="margin:8px 0 0">현금 '+(known && VD.cash!=null ? '<b style="color:var(--gold)">'+(100-sum).toFixed(1)+'%</b> = '+Math.round(cap*(100-sum)/100).toLocaleString('ko-KR')+'만' : '— 비중 확인이 필요한 상품이 있어 계산 보류')+' · 비중은 트리의 sizing.weight(모드 조건 포함)에서, 금액 축소는 ④ 조심 규칙에서 옵니다.</p>';
    return h + '</div>';
  }

  function render(){
    VD = readVD();
    if(!VD || VD.error || !VD.verdicts){
      root.innerHTML = '<div class="note bad">판정 데이터가 없습니다'+(VD && VD.error ? ': '+esc(VD.error) : '')+'</div>';
      return;
    }
    const prods = VD.verdicts.map(v=>v.prod);
    if(!curP || prods.indexOf(curP) < 0) curP = store.cur && prods.indexOf(store.cur) >= 0 ? store.cur : prods[0];
    const bad = selfCheck();
    let h = '';
    if(bad.length) h += '<div class="note bad">⚠ 화면 계산이 엔진 판정과 다릅니다('+esc(bad.join(', '))+') — 엔진 판정을 따르세요. (checklist-ui 와 shared/tree_grade 를 대조해야 합니다)</div>';
    const d = VD.ts ? new Date(VD.ts) : null, pad = n => String(n).padStart(2,'0');
    h += '<p class="subtle" id="td-ts">'+(VD.date?'<b>'+esc(VD.date)+'</b> 종가 기준':'')+(d?' · 판정 '+d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+' '+pad(d.getHours())+':'+pad(d.getMinutes()):'')+' · 출처 '+esc(VD.source||'')+' · ● 참 ○ 거짓 ? 모름 · ✋ 수동 조건만 직접 체크</p>';
    if(VD.missing && Object.keys(VD.missing).length){
      h += '<div class="note warn">시세 없음 → jhts 수집 요청: '+Object.keys(VD.missing).map(s=>esc(s)+' #'+esc(VD.missing[s])).join(' · ')+' — 그 심볼을 쓰는 조건은 ❔ 로 남습니다.</div>';
    }
    if((VD.common||[]).length){
      const ans = answers();
      h += '<h2 id="sheet-common"><span class="step">공통</span>여러 상품이 같이 보는 조건</h2><div class="card">'
        + VD.common.map(c=>node(Object.assign({}, c.view, {label:c.label, ref:c.ref}), 'common.'+c.name, ans, 0)).join('') + '</div>';
    }
    h += '<h2 id="sheet-step2"><span class="step">판정</span>상품별 체크리스트</h2>';
    h += '<div id="td-chips" style="display:grid;grid-template-columns:repeat('+prods.length+',1fr);gap:10px;margin:2px 0 14px">'
      + VD.verdicts.map(v=>{ const k = v.zones ? gradeKey(v, answers()) : v.key;
          return '<button class="td-chip" data-jump="'+esc(v.prod)+'" style="text-align:left;cursor:pointer;background:'+(v.prod===curP?'var(--surface-2)':'var(--surface)')+';border:1px solid var(--line);border-top:3px solid var(--'+esc(v.prod.toLowerCase())+',var(--line));border-radius:10px;padding:11px 13px">'
            + '<div style="font-weight:800;font-size:15px">'+esc(v.prod)+'</div>'
            + '<div class="verdict '+(GCLS[k]||'')+'" style="margin:6px 0 0;padding:3px 9px;font-size:12.5px;display:inline-block">'+GR[k]+'</div></button>'; }).join('')
      + '</div>';
    const cur = VD.verdicts.find(v=>v.prod===curP);
    h += '<div class="card acc" id="entryCard" style="--pc:var(--'+esc(curP.toLowerCase())+',var(--line))">'+renderProduct(cur)+'</div>';
    h += renderSizing();
    root.innerHTML = h;
    bind();
  }

  function bind(){
    root.querySelectorAll('.td-chip').forEach(el=>el.addEventListener('click',()=>{ curP = el.dataset.jump; store.cur = curP; save(); render(); }));
    root.querySelectorAll('.ck-man button').forEach(b=>b.addEventListener('click',ev=>{
      ev.stopPropagation();
      const key = b.parentNode.dataset.key, ans = answers();
      if(b.dataset.a === 'x') delete ans[key]; else ans[key] = b.dataset.a === '1';
      save(); render();
    }));
    root.querySelectorAll('.ck-ref').forEach(a=>a.addEventListener('click',ev=>{
      ev.preventDefault(); ev.stopPropagation();
      if(window.__jumpToPlaybook) window.__jumpToPlaybook(a.dataset.ref, '');
    }));
    const cap = document.getElementById('ckCap');
    if(cap) cap.addEventListener('change',()=>{ store.capital = +cap.value || 0; save(); render(); });
  }

  // 화면 스타일 — 페이지 CSS 를 손대지 않고 모든 책에 같은 모양(공통 UI 가 자기 스타일을 가진다).
  (function(){
    const st = document.createElement('style');
    st.textContent =
      '#sheet-root .ck-head{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}'
      +'#sheet-root .ck-zone{margin-top:16px;display:flex;gap:8px;align-items:baseline}'
      +'#sheet-root .ck-zone .ck-zv{font-size:12px;font-weight:600;color:var(--mute)}'
      +'#sheet-root .ck-zone.ok .ck-zv{color:var(--entry)} #sheet-root .ck-zone.bad .ck-zv{color:var(--warn)}'
      +'#sheet-root .ck-row{padding:6px 0 6px 2px;border-bottom:1px dashed var(--line)}'
      +'#sheet-root .ck-kids{margin:4px 0 0 18px;border-left:2px solid var(--line);padding-left:10px}'
      +'#sheet-root .ck-grp{margin:2px 0}#sheet-root .ck-op{font-size:11.5px;color:var(--mute);margin:4px 0 0}'
      +'#sheet-root .ck-line{display:flex;gap:8px;align-items:flex-start}'
      +'#sheet-root .ck-t{flex:1;line-height:1.5}#sheet-root .ck-opl{font-size:11.5px;color:var(--mute);margin-left:4px}'
      +'#sheet-root .ck-why{font-size:12px;color:var(--mute);margin:2px 0 0 26px;line-height:1.5}'
      +'#sheet-root .ck-m{display:inline-block;width:18px;text-align:center;font-weight:800}'
      +'#sheet-root .ck-m.t{color:var(--entry)}#sheet-root .ck-m.f{color:var(--mute)}#sheet-root .ck-m.u{color:var(--gold)}#sheet-root .ck-m.n{color:var(--line)}'
      +'#sheet-root .ck-man{display:inline-flex;gap:3px}#sheet-root .ck-man button{font-size:11px;padding:1px 7px;border:1px solid var(--line);border-radius:8px;background:transparent;color:var(--mute);cursor:pointer}'
      +'#sheet-root .ck-man button.on{background:var(--gold);color:#111;border-color:transparent}'
      +'#sheet-root .ck-ref{font-size:11px;padding:0 6px;margin-left:4px;border:1px solid var(--line);border-radius:8px;color:var(--mute);cursor:pointer;text-decoration:none}'
      +'#sheet-root .ck-ref:hover{color:var(--head)}#sheet-root .ck-row.man .ck-t{color:var(--gold)}'
      +'#sheet-root .calcrow input{width:120px;margin-left:6px}';
    document.head.appendChild(st);
  })();

  render();
  // 라이브 모듈이 새 판정을 받으면 이 훅으로 다시 그린다.
  window.__applyVerdict = render;
})();
