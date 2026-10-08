(function(){
  'use strict';
  /* ============================================================
     실전 체크리스트 — 조건 트리 판정 결과(#verdict-data)만 그린다 (책 무관 · 종목 하드코딩 없음)
     · 트리를 직접 읽지 않는다. 판정 화면 데이터(web/verdict_view)가 낸 칸별 설명(view)을 그대로 그린다.
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
  const esc = window.BP.esc;            // 공용 부품(shared-ui) — 고치는 곳은 거기 하나
  function readVD(){ try { return JSON.parse(document.getElementById('verdict-data').textContent); } catch(e){ return null; } }
  let VD = readVD();
  let curP = null;
  const LS = 'ck.v2';
  let store = {};
  try { store = JSON.parse(localStorage.getItem(LS) || '{}') || {}; } catch(e){ store = {}; }
  function save(){ try { localStorage.setItem(LS, JSON.stringify(store)); } catch(e){} }
  // 수동 조건 답은 그날(판정일) 것만 쓴다 — 어제 체크가 오늘 판정에 섞이지 않게.
  function answers(){ const k = (VD && VD.slug || '') + ':' + (VD && VD.date || ''); store.ans = store.ans || {}; store.ans[k] = store.ans[k] || {}; return store.ans[k]; }

  /* ---- 3값 논리 (checklist/cond.py 와 같은 규칙) ----
     fill = 답 안 한 수동 조건에 넣을 값(null = 모름). not 아래에서는 뒤집힌다(cond 의 극성 규칙).

     ⚠ EXCLUDED(제외) 개념은 여기 없다 — 의도적이다. checklist/cond.py 에는 unobserved="exclude" 문맥에서
       관측값 없는 observe 가 내는 EXCLUDED 표지와, '자식이 모두 EXCLUDED 인 논리 묶음'(빈 묶음) 처리가 있다
       (cond.py 의 _Excluded / all·any 의 vals 필터 / "cols and not vals → EXCLUDED" 참고).
       이 화면 엔진(ev/and3/or3)에는 그 3값째가 없다 — true/false/null 뿐이다.
     ★ 괜찮은 이유: EXCLUDED 는 백테스트 전용(unobserved="exclude")이고, 매일 판정 JSON(web/verdict_view →
       #verdict-data)은 그 모드로 돌지 않아 브라우저에 EXCLUDED/빈-전부-제외 노드가 실려오지 않는다.
       만약 그런 노드가 실전 판정 JSON 에 새어 들어오면 이 엔진은 그걸 null 로 오해해 등급이 엔진과 갈라질 수 있다.
     ☞ 따라서 'EXCLUDED/전부-제외 논리 노드는 실전 판정 JSON 에 절대 실리면 안 된다'는 불변식을 파이썬에서
       검사로 강제한다 — checklist/verify_primitives.py 의 t_no_excluded_live(). 이 엔진은 고치지 않는다. */
  function and3(vs){ if(vs.some(v=>v===false)) return false; if(vs.some(v=>v===null)) return null; return true; }
  function or3(vs){ if(vs.some(v=>v===true)) return true; if(vs.some(v=>v===null)) return null; return false; }
  // 수동 조건의 답은 조건 자체로 묶는다: 여러 상품이 같이 보는 정의 안(shared)이면 책 전체에 하나,
  //   아니면 상품마다 하나. path 앞머리(상품 이름 또는 'common')에서 상품을 꺼낸다.
  // 수동 답 열쇠 — "?" 식은 엔진이 준 식 열쇠(it.mkey: 같은 식 = 같은 질문), 문장 수동은 그 문장.
  function mkey(it, path){ return (it.shared ? '*' : path.split('.')[0]) + '|' + (it.mkey || it.manual); }
  function ev(it, fill, ans, path){
    if(it.manual !== undefined){
      if(it.observed && it.v !== null && it.v !== undefined) return it.v;   // 저자 시각에 관측됨 — 자동
      const a = ans[mkey(it, path)]; return a === undefined ? fill : a;
    }
    if(!it.op) return it.v === undefined ? null : it.v;
    const k = it.kids || [];
    if(it.op === 'not'){ const x = ev(k[0], fill===null?null:!fill, ans, path+'.0'); return x===null?null:!x; }
    const vs = k.map((c,i)=>ev(c, fill, ans, path+'.'+i));
    if(it.op === 'all') return and3(vs);
    if(it.op === 'any') return or3(vs);
    const t = vs.filter(v=>v===true).length, u = vs.filter(v=>v===null).length;   // atleast
    return t >= it.n ? true : (t + u < it.n ? false : null);
  }
  // 등급 글자표는 엔진이 판정 JSON(VD.grades, = checklist/grade.GRADES)에 실어보낸다 — 화면은 받아 쓴다.
  // 고치는 곳은 파이썬 한 곳. 혹시 없으면 키 그대로 보여 깨지지 않게.
  const GR = k => ((VD && VD.grades) || {})[k] || k;
  const GCLS = {buy:'go', confirm:'small', unknown:'small', nofilter:'no', avoid:'no', wait:''};
  // 등급 판정 사다리는 엔진이 판정 JSON(VD.grade_rules, = checklist/grade_rules.json)에 실어보낸다 — 복붙 금지.
  // 위에서 아래로 보며 when 의 모든 칸이 맞는(=== 로 엄격 비교 → null 은 true·false 어디에도 안 맞음)
  //   첫 규칙이 이긴다.
  // ★ 하드코딩 기본 사다리를 두지 않는다 — 과거엔 여기 복붙한 사다리가 있어, grade_rules.json 이 바뀐 뒤
  //   옛 페이지(VD.grade_rules 없음)가 '화면 전용 옛 규칙'으로 등급을 다시 내 엔진과 조용히 갈라졌다.
  //   규칙이 없으면 화면은 등급을 다시 내지 않고 엔진이 준 v.key 를 그대로 쓴다(canGrade=false).
  const GRADE_RULES = (VD && VD.grade_rules) || null;
  const canGrade = !!(GRADE_RULES && GRADE_RULES.rules);
  function gradeKey(v, ans){
    if(!canGrade) return v.key;   // 사다리를 못 받음 — 체크해도 다시 내지 않고 엔진 판정을 따른다
    const z = v.zones || {}, P = s => v.prod+'.'+s;
    const o = {filter:ev(z.filter,true,ans,P('filter')), entry:ev(z.entry,true,ans,P('entry')), avoid:ev(z.avoid,false,ans,P('avoid'))};
    const p = {filter:ev(z.filter,false,ans,P('filter')), entry:ev(z.entry,false,ans,P('entry')), avoid:ev(z.avoid,true,ans,P('avoid'))};
    const views = {opt:o, pes:p};
    for(const rule of GRADE_RULES.rules){
      const view = views[rule.view];
      if(Object.keys(rule.when).every(sec => view[sec] === rule.when[sec])) return rule.key;
    }
    return GRADE_RULES.default;
  }
  // 등급을 낸 뒤 '이긴 규칙'이 opt/pes 중 어느 시각을 썼는지 돌려준다 — 조건 칸의 ●/○/? 표시를
  //   그 시각(=실제 판정에 쓴 fill)과 똑같이 맞추기 위함(M3: 표시 마크가 등급과 어긋나지 않게).
  //   조건 칸이 아니거나(caution·exit) 사다리를 못 받으면 null(중립).
  function gradeView(v, ans){
    if(!canGrade) return null;
    const z = v.zones || {}, P = s => v.prod+'.'+s;
    const o = {filter:ev(z.filter,true,ans,P('filter')), entry:ev(z.entry,true,ans,P('entry')), avoid:ev(z.avoid,false,ans,P('avoid'))};
    const p = {filter:ev(z.filter,false,ans,P('filter')), entry:ev(z.entry,false,ans,P('entry')), avoid:ev(z.avoid,true,ans,P('avoid'))};
    const views = {opt:o, pes:p};
    for(const rule of GRADE_RULES.rules){
      if(Object.keys(rule.when).every(sec => views[rule.view][sec] === rule.when[sec])) return rule.view;
    }
    return null;
  }
  // 조건 칸(filter/entry/avoid)에서 미응답 수동 조건에 넣을 값 — 이긴 시각과 같게.
  //   opt: filter·entry=참, avoid=거짓 / pes: 그 반대. 시각 불명이면 null(중립).
  function zoneFill(view, sec){
    if(view === null) return null;
    const trueOnOpt = sec !== 'avoid';           // filter·entry 는 opt 에서 참, avoid 는 opt 에서 거짓
    return view === 'opt' ? trueOnOpt : !trueOnOpt;
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
  // 논리 묶음 설명. not 은 라벨·증거 줄이 뜻을 다 전하므로 캡션을 달지 않는다(군더더기 제거).
  const OPW = it => it.op==='all' ? '모두' : it.op==='any' ? '하나 이상' : it.op==='atleast' ? (it.n+'개 이상') : '';
  function refChip(ref){ return ref ? ' <a class="ck-ref" data-ref="'+esc(ref)+'" title="플레이북 원문 소절로">'+esc(ref)+'</a>' : ''; }
  function fmtV(v){ return typeof v === 'number' ? (Math.abs(v) >= 100 ? v.toFixed(1) : v.toFixed(2)) : ''; }
  // 측정 증거 — 조건이 '무엇을 재서 그 값이 얼마였나'를 한 줄로(엔진이 detail 로 실어보냄). 사용자가 ●/○ 를 믿을 근거.
  function fmtMeas(x){
    if(x === null || x === undefined) return '—';
    if(typeof x !== 'number') return esc(String(x));
    var s = Math.abs(x) >= 100 ? x.toFixed(1) : x.toFixed(2);
    if(s.indexOf('.') >= 0) s = s.replace(/0+$/,'').replace(/\.$/,'');   // 10.00→10, 0.10→0.1 (꼬리 0 정리)
    // 천단위 구분(정수부) — 거래량·지수 같은 큰 숫자 가독성: 46306400 → 46,306,400
    var neg = s.charAt(0) === '-'; if(neg) s = s.slice(1);
    var dot = s.indexOf('.'), ip = dot < 0 ? s : s.slice(0, dot), fp = dot < 0 ? '' : s.slice(dot);
    ip = ip.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return (neg ? '-' : '') + ip + fp;
  }
  const EVSYM = {gt:'>', ge:'≥', lt:'<', le:'≤'};
  function evLine(detail){
    if(!detail || !detail.length) return '';
    let missing = false;
    const parts = detail.map(d=>{
      const u = d.unit ? esc(d.unit) : '';
      const noVal = (d.lhs === null || d.lhs === undefined);
      if(noVal) missing = true;
      // 복합식이면 원시 입력값을 먼저(예: 고가 7750 · 종가 7736 →)
      let lead = '';
      if(d.inputs && d.inputs.length){
        lead = d.inputs.map(x=>esc(x.d)+' '+((x.v===null||x.v===undefined)?'<span class="ev-x">—</span>':'<b>'+fmtMeas(x.v)+'</b>')).join('<span class="ev-sep"> · </span>') + ' → ';
      }
      const lv = noVal ? '<span class="ev-x">측정 없음</span>' : '<b>'+fmtMeas(d.lhs)+u+'</b>';
      // 입력값(lead)이 있으면 파생값 이름(lhsd)은 생략 — 입력이 이미 설명한다
      const L = lead + (lead ? '' : (d.lhsd ? esc(d.lhsd)+' ' : '')) + lv;
      // 기준이 상수(rhsd 없음)면 "· 기준 op 값", 다른 식이면 "op 설명 값" — 단위는 양쪽에 같게 붙인다
      //   상수 자리가 비었으면(rhs 없음·설명 없음) 저자가 기준을 안 준 "?" 식 — '기준 ?'로 보여 사람이 숫자를 보고 고르게
      const R = d.rhsd ? ' '+(EVSYM[d.op]||'')+' '+esc(d.rhsd)+' <b>'+fmtMeas(d.rhs)+u+'</b>'
              : (d.rhs === null || d.rhs === undefined) ? ' <span class="ev-th">· 기준 '+(EVSYM[d.op]||'')+' ? (저자 미명시)</span>'
                       : ' <span class="ev-th">· 기준 '+(EVSYM[d.op]||'')+' '+fmtMeas(d.rhs)+u+'</span>';
      return L + R;
    });
    return '<div class="ck-ev'+(missing?' miss':'')+'">'+(missing?'⚠️':'📊')+' '+parts.join('<span class="ev-sep"> · </span>')+'</div>';
  }
  // 항목 하나(노드) — 숨김 잎은 계산에만 쓰고 그리지 않는다. 라벨 없는 묶음은 묶음 줄 없이 자식만 들여쓴다.
  // fill = 조건 칸에서 미응답 수동 조건에 넣을 값 — 실제 판정(등급)에 쓴 시각과 같게 받아(M3), 표시 마크가
  //   등급과 어긋나지 않게 한다. 안 넘기면 null(중립 — caution·exit 등 등급과 무관한 칸).
  function node(it, path, ans, depth, fill, seen){
    if(fill === undefined) fill = null;
    if(!it) return '';
    if(it.hidden && !it.kids) return '';
    if(!seen) seen = new Set();
    // 표시 전용 중복 제거: 같은 조건(라벨+기준+측정값)이 한 패턴 안에서 되풀이되면 한 번만.
    //   (streak/barssince 파생조건이 라벨 없이 안쪽 건물블록만 반복 노출되는 경우를 걷어낸다.)
    //   zone 바로 밑 패턴마다 집합을 새로 둬서 다른 패턴끼리는 제거하지 않는다(각 카드가 자기 조건을 다 보이게).
    const sig = (it.label || it.manual) ? ((it.label||it.manual)+'|'+(it.ref||'')+'|'+(it.detail?JSON.stringify(it.detail):'')) : null;
    const dup = !!(sig && seen.has(sig));
    if(sig) seen.add(sig);
    const kids = (it.kids||[]).map((c,i)=>node(c, path+'.'+i, ans, depth+1, fill, depth===0 ? new Set() : seen)).join('');
    const showRow = it.label || it.manual !== undefined;
    if(!showRow){
      if(!kids) return '';
      const gop = OPW(it);
      return it.op ? '<div class="ck-grp">'+(gop?'<div class="ck-op">'+esc(gop)+'</div>':'')+kids+'</div>' : kids;
    }
    if(dup) return '';   // 같은 조건을 이미 보여줬다 — 한 번만
    const isM = it.manual !== undefined && !(it.observed && it.v !== null && it.v !== undefined);
    const a = isM ? ans[mkey(it, path)] : undefined;
    // 미응답 수동 조건의 마크는 fill(판정에 쓴 시각)로 — 비워두면(null) 등급은 ✅ 인데 칸은 ? 로 떠 어긋난다.
    const val = isM ? (a === undefined ? fill : a) : (it.op ? ev(it, fill, ans, path) : it.v);
    // folded = 같은 칸 다른 곳에 이미 펼쳐 둔 조건(엔진이 표시) — 계산(ev)은 kids 로 그대로 하되 화면엔 한 줄만.
    const kidsHtml = ((it.observed && isM) || it.folded) ? '' : kids;
    let ctl;
    if(isM){
      // 수동 조건 = 참/거짓 둘 중 하나를 고르는 것(체크박스 아님). 하나로 붙은 토글(세그먼트)로.
      // 고른 쪽만 켜지고, 같은 걸 다시 누르면 해제(미확인)된다.
      ctl = '<span class="ck-man" data-key="'+esc(mkey(it, path))+'"'+(it.shared?' title="여러 상품이 같이 보는 조건 — 한 번 고르면 모든 상품에 적용"':'')+'>'
          + '<button data-a="1" class="seg t'+(a===true?' on':'')+'" title="이 조건이 참(맞음)">● 참</button>'
          + '<button data-a="0" class="seg f'+(a===false?' on':'')+'" title="이 조건이 거짓(아님)">○ 거짓</button>'
          + '</span>';
    } else ctl = MARK(val);
    const num = (!isM && typeof it.v === 'number') ? ' <span class="dataval">'+fmtV(it.v)+'</span>' : '';
    const why = isM ? '<div class="ck-why">✋ '+esc(it.manual)+'</div>' : (it.note ? '<div class="ck-why">'+esc(it.note)+'</div>' : (it.observed ? '<div class="ck-why">저자가 말한 시각의 값으로 자동 판정</div>' : ''));
    const opw = OPW(it); const opl = opw ? ' <span class="ck-opl">'+esc(opw)+'</span>' : '';
    return '<div class="ck-row'+(isM?' man':' auto')+'" '+(it.ref?'data-ref="'+esc(it.ref)+'"':'')+'>'
      + '<div class="ck-line">'+ctl+'<span class="ck-t">'+esc(it.label || '수동 확인')+opl+num+refChip(it.ref)+'</span></div>'
      + why + (it.folded && kids ? '<div class="ck-why">↕ 세부 조건은 이 칸에 따로 펼쳐 둠</div>' : '') + evLine(it.detail) + (kidsHtml ? '<div class="ck-kids">'+kidsHtml+'</div>' : '') + '</div>';
  }
  function zoneHead(title, want, val){
    const ok = val === null ? '' : (val === want ? ' ok' : ' bad');
    return '<div class="grouplabel ck-zone'+ok+'">'+title+' <span class="ck-zv">'+(val===true?'참':val===false?'거짓':'확인 필요')+'</span></div>';
  }
  function sellText(s){ if(s==='all') return '남은 전량'; const ini = s.initial!==undefined, f = ini ? s.initial : s.remaining;
    return (ini ? '산 물량의 ' : '남은 물량의 ')+(f==null ? '? (비율 저자 미명시)' : Math.round(f*100)+'%'); }
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
          + '<span class="verdict '+(GCLS[key]||'')+'" style="margin:0;padding:4px 11px;font-size:13.5px">'+GR(key)+'</span></div>';
    if(v.close != null) h += '<p class="subtle" style="margin:4px 0 2px">'+esc(v.date)+' 종가 <b style="color:var(--head)">'+v.close.toFixed(2)+'</b>'+(v.chg!=null?' · 당일 '+(v.chg>=0?'+':'')+v.chg.toFixed(2)+'%':'')+'</p>';
    h += '<p class="subtle" style="margin:2px 0 10px">엔진 판정: '+esc(v.reason)+(key!==v.key?' <b style="color:var(--gold)">→ 체크한 수동 조건 반영: '+GR(key)+'</b>':'')+'</p>';
    if(!v.zones){ return h; }
    const z = v.zones;
    // 칸 이름표(필터·회피·진입·조심·매도)는 엔진 값(VD.zones = checklist/cond.ZONE_LABELS)에서 꺼낸다 — 복붙 금지.
    //   동그라미 번호는 화면 전용 머리글이라 그대로 두고, 이름표 글자만 VD.zones 에서 가져온다(없으면 키 그대로).
    const zl = k => (VD.zones && VD.zones[k]) || k;
    // 조건 칸의 ●/○/? 는 실제 등급을 낸 시각(opt/pes)과 같은 fill 로 평가한다(M3) — 미응답 수동 조건에서
    //   등급은 정해졌는데 칸만 ? 로 뜨는 어긋남을 막는다. zoneHead 요약값도 같은 fill 로 맞춘다.
    const gv = gradeView(v, ans), fF = zoneFill(gv,'filter'), fA = zoneFill(gv,'avoid'), fE = zoneFill(gv,'entry');
    h += zoneHead('① '+zl('filter')+' — 참이어야 본다', true, ev(z.filter,fF,ans,P('filter'))) + node(z.filter, P('filter'), ans, 0, fF);
    h += zoneHead('② '+zl('avoid')+' — 참이면 보류', false, ev(z.avoid,fA,ans,P('avoid'))) + node(z.avoid, P('avoid'), ans, 0, fA);
    h += zoneHead('③ '+zl('entry')+' — 참이면 매수 자리', true, ev(z.entry,fE,ans,P('entry'))) + node(z.entry, P('entry'), ans, 0, fE);
    if((v.caution||[]).length){
      const c = cautionOf(v, ans);
      h += '<div class="grouplabel ck-zone" style="color:var(--gold)">④ '+esc(zl('caution'))+' — 사더라도 금액을 줄인다 <span class="ck-zv">금액 ×'+c.f.toFixed(2)+(c.unspec.length?' · 폭 미명시 '+c.unspec.length:'')+(c.unk.length?' · 확인 필요 '+c.unk.length:'')+'</span></div>';
      v.caution.forEach((r,i)=>{
        const lab = r.label + (r.scale!=null ? ' (금액 ×'+(+r.scale).toFixed(2)+')' : ' (줄일 폭 저자 미명시)');
        h += node(Object.assign({}, r.view, {label: lab, ref: r.ref, note: r.note}), P('caution.'+i), ans, 0);
      });
    }
    // 매도 규칙 + 내 포지션
    if((v.exit||[]).length){
      h += '<div class="grouplabel ck-zone" style="color:var(--entry)">⑥ '+esc(zl('exit'))+' — 보유분을 팔 때 (걸리면 다음 날 시가)</div>';
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
    else if(v.exit_policy === 'none'){
      // 매도 정책(엔진 필드 exit_policy — 정본 trading/trades.exit_policy): 책에 매도 규칙이 없다 — 문구도 엔진(VD.no_exit_note)
      h += '<div class="grouplabel ck-zone" style="color:var(--entry)">⑥ '+esc(zl('exit'))+'</div><p class="subtle" style="margin:6px 0 0">'+esc(VD.no_exit_note || '')+'</p>';
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
    // 현금 비중은 엔진이 실어보낸 VD.cash(파이썬에서 max(0, 100-합)으로 0 이상 클램프)를 그대로 쓴다 —
    //   화면에서 100-sum 을 다시 계산하면 비중 합이 100%를 넘을 때 음수 현금이 떠서 엔진과 갈라진다.
    if(anyW) h += '<p class="subtle" style="margin:8px 0 0">현금 '+(known && VD.cash!=null ? '<b style="color:var(--gold)">'+VD.cash.toFixed(1)+'%</b> = '+Math.round(cap*VD.cash/100).toLocaleString('ko-KR')+'만' : '— 비중 확인이 필요한 상품이 있어 계산 보류')+' · 비중은 트리의 sizing.weight(모드 조건 포함)에서, 금액 축소는 ④ 조심 규칙에서 옵니다.</p>';
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
    if(bad.length) h += '<div class="note bad">⚠ 화면 계산이 엔진 판정과 다릅니다('+esc(bad.join(', '))+') — 엔진 판정을 따르세요. (checklist-ui 와 checklist/grade 를 대조해야 합니다)</div>';
    // 등급 사다리(VD.grade_rules)를 못 받으면 화면은 등급을 다시 내지 않는다 — 옛 하드코딩 규칙으로 엔진과
    //   갈라지느니, 엔진이 준 판정(v.key)을 그대로 보여준다. 수동 체크로 등급이 바뀌지 않음을 알린다.
    if(!canGrade) h += '<div class="note warn">등급 판정표(grade_rules)를 받지 못했습니다 — 엔진 판정을 그대로 표시하며, 수동 조건을 체크해도 등급을 다시 계산하지 않습니다(페이지를 새로 받으면 복구됩니다).</div>';
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
            + '<div class="verdict '+(GCLS[k]||'')+'" style="margin:6px 0 0;padding:3px 9px;font-size:12.5px;display:inline-block">'+GR(k)+'</div></button>'; }).join('')
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
      const key = b.parentNode.dataset.key, ans = answers(), want = b.dataset.a === '1';
      if(ans[key] === want) delete ans[key]; else ans[key] = want;   // 같은 걸 다시 누르면 해제
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
      '#sheet-root{font-size:13.5px}'
      +'#sheet-root .ck-head{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px}'
      // 칸 머리글(①필터 ②회피 …) — 왼쪽 색 띠 바(참=초록·거짓=빨강)
      +'#sheet-root .ck-zone{margin:20px 0 8px;padding:9px 13px;background:var(--surface-2);border:1px solid var(--line);border-left:3px solid var(--mute);border-radius:9px;display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:13px;font-weight:700;color:var(--head);line-height:1.4;letter-spacing:.01em}'
      +'#sheet-root .ck-zone.ok{border-left-color:var(--entry)} #sheet-root .ck-zone.bad{border-left-color:var(--warn)}'
      +'#sheet-root .ck-zone .ck-zv{font-size:11.5px;font-weight:600;color:var(--mute);white-space:nowrap}'
      +'#sheet-root .ck-zone.ok .ck-zv{color:var(--entry)} #sheet-root .ck-zone.bad .ck-zv{color:var(--warn)}'
      // 조건 한 칸 = 카드(편안한 여백)
      +'#sheet-root .ck-row{background:var(--surface-2);border:1px solid var(--line);border-radius:10px;padding:10px 13px;margin:7px 0}'
      +'#sheet-root .ck-row.man{border-left:3px solid var(--gold)}'
      // 중첩 조건은 카드 안 들여쓴 목록
      +'#sheet-root .ck-kids{margin:8px 0 0 3px;border-left:1px solid var(--line);padding-left:13px;display:flex;flex-direction:column}'
      +'#sheet-root .ck-kids .ck-row{background:transparent;border:none;border-radius:0;padding:6px 0;margin:0}'
      +'#sheet-root .ck-grp{margin:0}#sheet-root .ck-op{font-size:11px;color:var(--mute);margin:2px 0 5px;letter-spacing:.02em}'
      +'#sheet-root .ck-line{display:flex;gap:10px;align-items:flex-start}'
      +'#sheet-root .ck-t{flex:1;font-size:13.5px;line-height:1.5;color:var(--text)}'
      +'#sheet-root .ck-row.man .ck-t{color:var(--head)}'
      +'#sheet-root .ck-opl{font-size:11.5px;color:var(--mute);margin-left:6px}'
      +'#sheet-root .ck-why{font-size:12px;color:var(--mute);margin:4px 0 0 32px;line-height:1.5}'
      // 측정 증거 칩
      +'#sheet-root .ck-ev{font-size:12px;color:var(--mute);margin:6px 0 0 32px;line-height:1.5;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:4px 10px;display:inline-block}'
      +'#sheet-root .ck-ev b{color:var(--head);font-weight:700}'
      +'#sheet-root .ck-ev .ev-x{color:var(--gold);font-weight:700}#sheet-root .ck-ev .ev-th{color:var(--mute)}#sheet-root .ck-ev .ev-sep{color:var(--line);margin:0 2px}'
      +'#sheet-root .ck-ev.miss{background:rgba(212,162,78,.10);border-color:var(--gold)}'
      // 마크(자동)·수동 토글 — 같은 원형 칩(통일된 시각 언어: ● 참 · ○ 거짓 · ? 모름, 참/거짓 글자 없음)
      +'#sheet-root .ck-m{flex:none;display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;font-size:12px;font-weight:800;line-height:1}'
      +'#sheet-root .ck-m.t{color:var(--entry);background:rgba(63,185,80,.15)}'
      +'#sheet-root .ck-m.f{color:var(--mute);background:rgba(122,129,148,.15)}'
      +'#sheet-root .ck-m.u{color:var(--gold);background:rgba(212,162,78,.16)}'
      +'#sheet-root .ck-m.n{color:var(--line);background:transparent}'
      // 수동 토글 = 하나로 붙은 세그먼트(참|거짓) — 체크박스 2개가 아니라 '하나를 고르는' 한 컨트롤
      +'#sheet-root .ck-man{flex:none;align-self:flex-start;display:inline-flex;border:1px solid var(--line);border-radius:999px;overflow:hidden}'
      +'#sheet-root .ck-man button{border:0;background:transparent;color:var(--mute);font-size:11.5px;font-weight:700;line-height:1;padding:4px 11px;cursor:pointer;display:inline-flex;align-items:center;gap:4px;white-space:nowrap;transition:background .12s,color .12s}'
      +'#sheet-root .ck-man button+button{border-left:1px solid var(--line)}'
      +'#sheet-root .ck-man button:hover{color:var(--head)}'
      +'#sheet-root .ck-man button.t.on{background:rgba(63,185,80,.18);color:var(--entry)}'
      +'#sheet-root .ck-man button.f.on{background:rgba(122,129,148,.22);color:var(--head)}'
      +'#sheet-root .dataval{font-size:12px;color:var(--mute);font-weight:600;margin-left:4px}'
      +'#sheet-root .ck-ref{font-size:11px;padding:0 7px;margin-left:6px;border:1px solid var(--line);border-radius:999px;color:var(--mute);cursor:pointer;text-decoration:none}'
      +'#sheet-root .ck-ref:hover{color:var(--head);border-color:var(--mute)}'
      +'#sheet-root .calcrow input{width:120px;margin-left:6px}';
    document.head.appendChild(st);
  })();

  render();
  // 라이브 모듈이 새 판정을 받으면 이 훅으로 다시 그린다.
  window.__applyVerdict = render;
})();
