(function(){
  'use strict';
  /* ============================================================
     실전 체크리스트 — 조건 트리 판정 결과(#verdict-data)만 그린다 (책 무관 · 종목 하드코딩 없음)
     · 트리를 직접 읽지 않는다. 판정 화면 데이터(web/verdict_view)가 낸 동사별 설명(view)을 그대로 그린다.
     · 머리글은 동사 셋(VD.verbs = ① 안 산다 ② 산다 ③ 판다, 정본 tree/gateway.VERBS) + ④ 얼마나(비중·분할).
     · 사람이 체크하는 건 수동(✋) 조건뿐이다. 체크하면 그 답을 서버(POST /api/verdict)에 보내고, 서버가 답까지
       반영해 낸 판정(등급·동사 값·금액)을 그대로 다시 그린다 — 서버 권위. 화면은 등급·3값 논리를 계산하지 않는다
       (계산기는 judge/eval.py 한 벌). 서버 없이 열면 체크는 저장되지만 판정은 바뀌지 않는다(그렇다고 알린다).
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

  // 수동 답 열쇠 — 서버(tree/gateway.answer_key)와 같은 규칙: 상품 + '|' + 본체(=엔진이 준 식 열쇠 it.mkey, 문장 수동은
  //   그 문장). commonNode 가 상품마다 'prod|본체'로 만들어 토글의 data-keys 에 담는다(값 계산은 서버).
  // 등급 글자표는 엔진이 판정 JSON(VD.grades, = judge/judge.GRADES)에 실어보낸다 — 화면은 받아 쓴다.
  // 고치는 곳은 파이썬 한 곳. 혹시 없으면 키 그대로 보여 깨지지 않게.
  const GR = k => ((VD && VD.grades) || {})[k] || k;
  const GCLS = {buy:'go', confirm:'small', unknown:'small', avoid:'no', wait:''};
  let pending = false, serverNote = '';   // 답을 보내고 서버 판정을 기다리는 중 · 서버 판정을 못 받음 알림

  /* ---- 그리기 ---- */
  const MARK = v => v===true ? '<span class="ck-m t">●</span>' : (v===false ? '<span class="ck-m f">○</span>' : '<span class="ck-m u">?</span>');
  // 논리 묶음 설명. not 은 라벨·증거 줄이 뜻을 다 전하므로 캡션을 달지 않는다(군더더기 제거).
  const OPW = it => it.op==='all' ? '모두' : it.op==='any' ? '하나 이상' : it.op==='atleast' ? (it.n+'개 이상') : '';
  // 원문 소절 뱃지 — 규칙 줄마다 한 번. 이게 그 규칙의 원문 표시다(다른 데서 또 표시하지 않는다).
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
  // 식 글 한 줄 — 라벨·수동 사유가 '무엇을 재는지'를 가리지 않게 규칙의 식을 그대로 보인다(엔진이 it.expr 로 실어보냄).
  function exprLine(x, head){ return x ? '<div class="ck-expr">'+(head?'<span class="ck-exh">'+esc(head)+'</span> ':'')+esc(x)+'</div>' : ''; }
  // 공통 규칙 = 모든 상품에 거는 **시장 신호**(엔진 allprod=규칙 레벨 on 없음 · selfdep=자기 시세/보유 안 읽음).
  //   VIX·금리·선물처럼 구체 티커만 보는 규칙이 공통이다. 상품 자기 시세($self)·기준 지수($index)·보유(pos)를
  //   읽는 규칙(갭상승·윗꼬리·수익률 등)은 상품마다 값이 실제로 달라 **상품 카드**로 보낸다(공통 아님).
  //   단 노드 레벨 on(공통 결정에 한 상품만 더 붙는 조건 — 장전 점수의 SOXL 대표주)은 공통에서 빼지 않는다(selfdep 무관).
  const isCommon = it => !!(it && it.allprod && !it.selfdep);
  // 공통 섹션 — 세 상품의 같은 규칙 노드를 나란히 걷는다(구조 동일, 값만 갈림). 값이 상품마다 같으면 칩 하나,
  //   갈리면(자기 시세·기준 지수·보유·상품 전용 노드) 상품별 칩. 측정 증거(📊 detail)는 여기선 생략 — 상품 카드에서(옵션 B).
  function valMark(v){ return (typeof v === 'number') ? '<span class="dataval">'+fmtV(v)+'</span>' : MARK(v===undefined?null:v); }
  function cMark(prods, its){
    // 상품별 값(off = 노드 레벨 on 에 그 상품이 없음 → 이 상품엔 적용 안 됨)
    const vals = its.map(it => !it ? undefined : (it.off ? 'off' : (it.v===undefined?null:it.v)));
    const real = vals.filter(v => v!=='off' && v!==undefined);
    const anyOff = vals.some(v => v==='off');
    const allSame = real.length>0 && real.every(v => v===real[0]);
    if(allSame && !anyOff) return valMark(real[0]);          // 값 공통(구체 티커) → 칩 하나
    return '<span class="ck-pcs">'+prods.map((p,i)=>{        // 갈림 → 상품별 칩
      const v = vals[i], m = (v==='off'||v===undefined) ? '<span class="ck-m n">—</span>' : valMark(v);
      return '<span class="ck-pc" title="'+esc(p)+'"><span class="ck-pcl">'+esc(p)+'</span>'+m+'</span>';
    }).join('')+'</span>';
  }
  function commonNode(its, prods, path, ans, depth, seen){
    // 구조 기준은 off 아닌(활성) 상품 노드 — off 껍데기는 op·kids 가 없어 식 글만 있다(상품 포크의 주인 상품을 따른다).
    const it0 = its.find(it => it && !it.off) || its.find(Boolean); if(!it0) return '';
    // 주어진 상품 전부에서 off(=다른 상품 전용 노드)면 이 뷰에선 안 보인다 — 상품 카드(상품 하나)에선 그 상품에 안 걸리는
    //   가지를 숨기고, 공통(여러 상품)에선 한 상품이라도 켜지면 보인다.
    if(its.every(n => !n || n.off)) return '';
    if(!seen) seen = new Set();
    // 표시 중복 제거(패턴 안 반복) · 카드 반복 접기 — 공유 이름 조건은 섹션에서 한 번만 펼친다
    const sig = (it0.label||it0.manual||it0.expr) ? ((it0.label||it0.manual||'')+'|'+(it0.expr||'')+'|'+(it0.ref||'')) : null;
    const dup = !!(sig && seen.has(sig)); if(sig) seen.add(sig);
    const ck = (depth>0 && it0.label && it0.manual===undefined && (it0.kids||it0.expr)) ? it0.label+'|'+(it0.expr||'') : null;
    if(ck && cardSeen.has(ck)) return '<div class="ck-row auto fold"><div class="ck-line">'+cMark(prods,its)
      + '<span class="ck-t">'+esc(it0.label)+' <span class="ck-opl">↑ 위에서 펼침</span>'+refChip(it0.ref)+'</span></div></div>';
    if(ck) cardSeen.add(ck);
    // 상품 포크 접기 — 여러 상품 중 일부에서만 켜지는 가지(off 섞임)는 공통 뷰에서 안쪽을 펼치지 않고 한 줄로
    //   ('어느 상품에 걸렸나'까지). 상품 카드(상품 하나)에선 off 가지는 위에서 이미 걸러졌으니 gated 가 아니라 펼쳐진다.
    const gated = its.some(it => it && it.off);
    const nk = gated ? 0 : its.reduce((m,it)=> Math.max(m, it&&it.kids?it.kids.length:0), 0);
    let kidsHtml = '';
    for(let i=0;i<nk;i++){
      kidsHtml += commonNode(its.map(it => it&&it.kids?it.kids[i]:null), prods, path+'.'+i, ans, depth+1, depth===0?new Set():seen);
    }
    const showRow = it0.label || it0.manual!==undefined || it0.expr || gated;
    if(!showRow){
      if(!kidsHtml) return '';
      const gop = OPW(it0);
      return it0.op ? '<div class="ck-grp">'+(gop?'<div class="ck-op">'+esc(gop)+'</div>':'')+kidsHtml+'</div>' : kidsHtml;
    }
    if(dup) return '';
    const isM = it0.manual!==undefined && !gated;
    let ctl;
    if(isM){
      // 수동 토글 한 번 누르면 세 상품 열쇠에 같은 답(mkey 는 상품별 그대로 — 서버 무변). bind() 가 data-keys 로 처리.
      const body = it0.mkey || it0.manual, keys = prods.map(p=>p+'|'+body), a = ans[keys[0]];
      ctl = '<span class="ck-man" data-key="'+esc(keys[0])+'" data-keys="'+esc(JSON.stringify(keys))+'">'
          + '<button data-a="1" class="seg t'+(a===true?' on':'')+'" title="참">● 참</button>'
          + '<button data-a="0" class="seg f'+(a===false?' on':'')+'" title="거짓">○ 거짓</button></span>';
    } else ctl = cMark(prods, its);
    // 적용되는 상품만 꼬리표(상품 포크면 '· 상품 카드에서'로 안쪽을 거기서 보라고 안내)
    const act = prods.filter((p,i)=> its[i] && !its[i].off);
    const offNote = (act.length && act.length<prods.length)
      ? ' <span class="ck-opl">'+esc(act.join(','))+' 전용'+(gated?' · 상품 카드에서':'')+'</span>' : '';
    const why = (!gated && isM) ? '<div class="ck-why">✋ '+esc(it0.manual)+'</div>' : ((!gated && it0.note)?'<div class="ck-why">'+esc(it0.note)+'</div>':'');
    const opw = OPW(it0), opl = (opw && !gated)?' <span class="ck-opl">'+esc(opw)+'</span>':'';
    // 접힌 포크 줄 이름: 라벨 없으면 묶음 캡션('3개 이상' 등)으로 짧게 — 긴 식 글은 숨긴다
    const txt = it0.label || (gated && it0.op ? OPW(it0)+' 조건' : (it0.expr||'수동 확인'));
    // 측정 증거(📊) — 공통·카드 어디서든 실제 데이터를 보인다(체크리스트는 둘 다 같은 구조). 📊 가 값까지 보이면 그 위 식 설명줄은 중복이라 숨긴다.
    const hasDetail = !gated && it0.detail && it0.detail.length;
    const meas = hasDetail ? evLine(it0.detail) : '';
    return '<div class="ck-row'+(isM?' man':' auto')+'" '+(it0.ref?'data-ref="'+esc(it0.ref)+'"':'')+'>'
      + '<div class="ck-line">'+ctl+'<span class="ck-t">'+esc(txt)+opl+offNote+refChip(it0.ref)+'</span></div>'
      + ((!gated && it0.label && !hasDetail)?exprLine(it0.expr):'') + why + meas + (kidsHtml?'<div class="ck-kids">'+kidsHtml+'</div>':'') + '</div>';
  }
  // 규칙 블록 안의 판다(매도) 갈래 한 줄 — 매도는 보유분에만 걸리므로 상품별 결과 칩은 '내 포지션'이 있을 때만
  //   (ps.sells[그 규칙 index]), 없으면 '—'. 조건은 카드와 같은 '언제' 식 글.
  function commonExitFace(sell, vs, lab){
    const r0 = sell[0][1];
    const marks = [];
    vs.forEach(v=>{
      const idx = (v.sells||[]).findIndex(e=>e.label===lab);
      if(idx < 0) return;
      (v.positions||[]).forEach(ps=>{ const e = (ps.sells||[])[idx]; if(e) marks.push([v.prod, {v:e.v}]); });
    });
    const st = marks.length ? cMark(marks.map(x=>x[0]), marks.map(x=>x[1])) : '<span class="ck-m n">—</span>';
    return '<div class="ck-cm-face"><span class="ck-cm-verb">③ '+esc((VD.verbs||[])[2]||'')+'</span>'+st
      + ' <span class="ck-opl">'+esc(r0.sell)+'</span></div>'
      + (r0.when?'<div class="ck-expr"><span class="ck-exh">언제</span> '+esc(r0.when)+'</div>':'')
      + (r0.note?'<div class="ck-why">'+esc(r0.note)+'</div>':'');
  }
  // ── 점수 규칙(장전 5지표처럼 '5개 중 N개' 게이트) ── 산다·안산다 갈래가 **같은 지표 집합**을 임계만 달리 보는
  //   규칙은 지표를 두 번 나열하지 않고 점수표 하나 + 띠 범례로 보인다(저자의 '4점↑ 산다 · 3점 관망 · 2점↓ 안 산다').
  function leafLabel(n){
    if(!n) return '';
    if(n.label) return n.label;
    if(n.op==='not' && n.kids && n.kids[0]) return leafLabel(n.kids[0])+' 아님';
    if(n.kids && n.kids.length) return leafLabel(n.kids[0]);
    return n.expr || '';
  }
  // 노드에서 점수(atleast)를 찾는다 — 직접 · not 안 · all 안 한 개. {at, extras, neg} | null
  function findScore(node){
    if(!node) return null;
    if(node.op==='atleast') return {at:node, extras:[], neg:false};
    if(node.op==='not' && node.kids && node.kids[0] && node.kids[0].op==='atleast') return {at:node.kids[0], extras:[], neg:true};
    if(node.op==='all' && node.kids){
      const ats = node.kids.filter(k=>k.op==='atleast');
      if(ats.length===1) return {at:ats[0], extras:node.kids.filter(k=>k.op!=='atleast'), neg:false};
    }
    return null;
  }
  // info.faces(산다·안산다 게이트)가 모두 같은 지표 집합의 점수면 점수표 HTML, 아니면 null(일반 갈래 렌더로 폴백).
  function scoreCard(info, ans){
    const faces = info.faces || [];
    if(!faces.length) return null;
    const V = VD.verbs || [], BLOCK = V[0], BUY = V[1];
    // 갈래마다 활성 상품 노드로 점수 파싱
    const parsed = faces.map(f=>{
      const anchor = f.perProd.map(x=>x[1]).find(n=>n&&!n.off) || f.perProd[0][1];
      return {f, sc: findScore(anchor)};
    });
    if(parsed.some(x=>!x.sc)) return null;
    const keyOf = sc => sc.at.kids.map(leafLabel).slice().sort().join('|');
    const k0 = keyOf(parsed[0].sc);
    if(!parsed.every(x=>keyOf(x.sc)===k0)) return null;      // 갈래마다 지표 집합이 같아야 점수표
    const total = parsed[0].sc.at.kids.length;
    if(total < 2) return null;
    // 지표 항목을 상품별로 나란히(각 상품 노드의 점수 kids[i]) → commonNode 로 한 번씩
    const cf = parsed[0].f;
    const byProd = cf.perProd.map(x=>{ const s = findScore(x[1]); return {prod:x[0], s}; });
    if(byProd.some(b=>!b.s)) return null;
    const prods = byProd.map(b=>b.prod);
    let items = '';
    for(let i=0;i<total;i++){
      items += commonNode(byProd.map(b=>b.s.at.kids[i]), prods, 'common', ans, 0, new Set());
    }
    // 상품 전용 가지(대표주 등 extras) — extras 가 있는 갈래(보통 산다)에서 상품별로 가져온다
    const ef = parsed.find(x=>x.sc.extras.length);
    if(ef){
      const eb = ef.f.perProd.map(x=>({prod:x[0], s:findScore(x[1])}));
      const ne = Math.max.apply(null, eb.map(b=>b.s?b.s.extras.length:0).concat(0));
      for(let i=0;i<ne;i++){
        items += commonNode(eb.map(b=> b.s && b.s.extras[i] || null), eb.map(b=>b.prod), 'common', ans, 0, new Set());
      }
    }
    // 띠 범례 — 산다 임계(≥) · 안산다 임계(< → 이하) · 그 사이 관망
    let buyMin=null, blockN=null, extrasNote='';
    parsed.forEach(x=>{
      if(x.f.verb===BUY && !x.sc.neg){ buyMin = x.sc.at.n;
        if(x.sc.extras.length){ const e=x.sc.extras[0]; extrasNote = e.off?e.off.join('/')+' 전용':leafLabel(e); } }
      else if(x.f.verb===BLOCK && x.sc.neg){ blockN = x.sc.at.n; }
    });
    const bands = [];
    if(buyMin!=null) bands.push('<b>'+buyMin+'개 이상</b> 산다'+(extrasNote?'(+'+esc(extrasNote)+')':''));
    if(buyMin!=null && blockN!=null && (buyMin-1) >= blockN){ const lo=blockN, hi=buyMin-1; bands.push((lo===hi?lo+'개':lo+'~'+hi+'개')+' 관망'); }
    if(blockN!=null) bands.push('<b>'+(blockN-1)+'개 이하</b> 안 산다');
    else if(buyMin==null && blockN==null) return null;
    // 머리 상품별 칩 = 산다 갈래(없으면 첫 갈래) 상품별 판정
    const hf = (parsed.find(x=>x.f.verb===BUY) || parsed[0]).f;
    const headChips = cMark(hf.perProd.map(x=>x[0]), hf.perProd.map(x=>x[1]));
    const head = '<div class="ck-cm-face"><span class="ck-cm-verb">점수</span>'+headChips
      + '<span class="ck-opl">'+total+'개 중 유리한 개수로 판정</span></div>';
    const band = bands.length ? '<div class="ck-sc-band">판정: '+bands.join(' · ')+'</div>' : '';
    return head + items + band;
  }
  // ── 전제+갈림축 규칙(갭상승 눌림처럼) ── 산다·안산다가 '같은 조건을 반대 극성'으로 가르면(산다=참, 안산다=not),
  //   전제(양쪽 같은 극성)는 한 번, 갈림축(참/거짓으로 산다↔안산다)도 한 번만 보이고 각 갈래는 나머지만.
  //   키는 **라벨 기반**(상품마다 $self 식이 달라도 같은 조건으로 묶임), 극성은 not 으로 판별.
  function pivotRender(info, ans){
    const faces = info.faces || [];
    const V = VD.verbs || [], BLOCK = V[0], BUY = V[1];
    const buy = faces.find(f=>f.verb===BUY), block = faces.find(f=>f.verb===BLOCK);
    if(!buy || !block || faces.length > 2) return null;
    const kidsOf = n => (n && n.op==='all' && n.kids) ? n.kids : (n ? [n] : []);
    const keyBase = n => n ? (n.label || leafLabel(n) || n.expr || '') : '';
    const nkey = n => n && n.op==='not' ? keyBase(n.kids && n.kids[0]) : keyBase(n);   // 극성 뺀 키
    const isNeg = n => !!(n && n.op==='not');
    const anchorOf = f => f.perProd.map(x=>x[1]).find(n=>n&&!n.off) || f.perProd[0][1];
    const bK = kidsOf(anchorOf(buy)), kK = kidsOf(anchorOf(block));
    // 갈림축 = 산다엔 양(+)·안산다엔 음(not) 으로 같은 조건(정확히 하나일 때만 — 안전)
    const pivots = bK.filter(b=>!isNeg(b) && kK.some(k=>isNeg(k) && nkey(k)===nkey(b)));
    if(pivots.length !== 1) return null;
    const pk = nkey(pivots[0]);
    const preKeys = bK.filter(b=>nkey(b)!==pk && kK.some(k=>nkey(k)===nkey(b) && isNeg(k)===isNeg(b))).map(nkey);
    const prods = buy.perProd.map(x=>x[0]);
    const byKey = (face, key) => face.perProd.map(x => kidsOf(x[1]).find(c=>nkey(c)===key) || null);
    let html = '';
    if(preKeys.length){
      html += '<div class="ck-cm-face"><span class="ck-cm-verb">전제</span><span class="ck-opl">모두 필요</span></div>';
      preKeys.forEach(k=>{ html += commonNode(byKey(buy, k), prods, 'common', ans, 0, new Set()); });
    }
    html += '<div class="ck-cm-face"><span class="ck-cm-verb">갈림</span><span class="ck-opl">참이면 산다 · 거짓이면 안 산다</span></div>';
    html += commonNode(byKey(buy, pk), prods, 'common', ans, 0, new Set());
    const buyExtra = bK.filter(b=>nkey(b)!==pk && preKeys.indexOf(nkey(b))<0).map(nkey);
    html += '<div class="ck-cm-face"><span class="ck-cm-verb ok">② '+esc(BUY)+'</span>'+cMark(prods, buy.perProd.map(x=>x[1]))+'</div>';
    if(buyExtra.length) buyExtra.forEach(k=>{ html += commonNode(byKey(buy, k), prods, 'common', ans, 0, new Set()); });
    else html += '<div class="ck-row auto"><div class="ck-line"><span class="ck-m n">·</span><span class="ck-t"><span class="ck-opl">전제·갈림 충족 시</span></span></div></div>';
    const blkExtra = kK.filter(k=>nkey(k)!==pk && preKeys.indexOf(nkey(k))<0).map(nkey);
    html += '<div class="ck-cm-face"><span class="ck-cm-verb bad">① '+esc(BLOCK)+'</span>'+cMark(prods, block.perProd.map(x=>x[1]))+'</div>';
    if(blkExtra.length) blkExtra.forEach(k=>{ html += commonNode(byKey(block, k), prods, 'common', ans, 0, new Set()); });
    else html += '<div class="ck-row auto"><div class="ck-line"><span class="ck-m n">·</span><span class="ck-t"><span class="ck-opl">갈림이 거짓이면</span></span></div></div>';
    return html;
  }
  // 규칙을 라벨로 묶는다(동사 가로질러) — 공통 섹션·상품 카드가 **같은 구조**로 쓴다.
  //   keep = 이 뷰에 넣을 규칙(공통 섹션: isCommon · 상품 카드: 그 반대). verdicts = 상품 범위(공통: 전부 · 카드: 하나).
  function collectRules(verdicts, keep){
    const V = VD.verbs || [], BLOCK = V[0], BUY = V[1], v0 = verdicts[0];
    const order = [], reg = {};   // label -> {label, ref, faces:[{verb, perProd}], sell?}
    [BLOCK, BUY].forEach(sec=>{
      const kidsOf = v => ((v.gates && v.gates[sec] && v.gates[sec].kids) || []);
      kidsOf(v0).forEach(k=>{
        if(!keep(k)) return;
        if(!(k.label in reg)){ reg[k.label] = {label:k.label, ref:k.ref, faces:[]}; order.push(k.label); }
        reg[k.label].faces.push({verb:sec, perProd: verdicts.map(v=>[v.prod,(kidsOf(v).find(x=>x.label===k.label)||null)]).filter(x=>x[1])});
      });
    });
    (v0.sells||[]).forEach(s=>{
      if(!keep(s)) return;
      if(!(s.label in reg)){ reg[s.label] = {label:s.label, ref:s.ref, faces:[]}; order.push(s.label); }
      reg[s.label].sell = verdicts.map(v=>[v.prod,(v.sells||[]).find(x=>x.label===s.label)]).filter(x=>x[1]);
    });
    return order.map(lab => reg[lab]);
  }
  // 규칙 하나 블록 — 점수표 → 전제갈림 → 동사 갈래. 공통·카드 공용(perProd 길이만 다름). vs = 포지션 조회 상품 범위.
  function ruleBlock(info, ans, vs){
    const V = VD.verbs || [], vnum = {}, vcls = {};
    vnum[V[0]]='① '; vnum[V[1]]='② '; vnum[V[2]]='③ '; vcls[V[0]]='bad'; vcls[V[1]]='ok';
    let block = '<div class="ck-cm-rule"><span class="ck-cm-name">'+esc(info.label)+'</span>'+refChip(info.ref)+'</div>';
    const sc = info.faces.length ? (scoreCard(info, ans) || pivotRender(info, ans)) : null;
    if(sc){ block += sc; }
    else info.faces.forEach(f=>{
      const chips = cMark(f.perProd.map(x=>x[0]), f.perProd.map(x=>x[1]));
      const bare = f.perProd.map(x=>{ const n = Object.assign({}, x[1]); delete n.label; delete n.ref; delete n.note; return n; });
      const cond = commonNode(bare, f.perProd.map(x=>x[0]), 'common', ans, 0, new Set());
      block += '<div class="ck-cm-face"><span class="ck-cm-verb '+(vcls[f.verb]||'')+'">'+(vnum[f.verb]||'')+esc(f.verb)+'</span>'+chips+'</div>'+cond;
    });
    if(info.sell){ block += commonExitFace(info.sell, vs, info.label); }
    return '<div class="ck-cm">'+block+'</div>';
  }
  let cardSeen = new Set();   // 카드(공통 섹션·상품 카드) 하나 안에서 이미 펼친 이름 조건 — 반복 접기
  function renderCommon(){
    cardSeen = new Set();
    const vs = VD.verdicts || [];
    if(vs.length < 1) return '';
    const infos = collectRules(vs, isCommon);   // 공통 = 모든 상품에 거는 시장 신호(VIX·금리 등 구체 티커)
    if(!infos.length) return '';
    const body = infos.map(info => ruleBlock(info, answers(), vs)).join('');
    return '<h2 id="sheet-common2"><span class="step">공통</span>공통 시장 신호 — 모든 상품에 같이 적용</h2><div class="card">'
      + '<p class="subtle" style="margin:0 0 10px">모든 상품에 똑같이 거는 시장 신호입니다(VIX·금리·선물 등). 규칙마다 동사 갈래(안 산다·산다·판다)와 실제 측정값을 보이며, 값이 상품마다 같은 조건은 칩 하나, 갈리는 조건만 상품별 칩입니다. 상품 자기 시세·보유를 보는 규칙은 아래 상품별 체크리스트에 있습니다.</p>'
      + body + '</div>';
  }
  function renderProduct(v){
    cardSeen = new Set();
    const ans = answers();
    const key = v.key;                          // 서버 판정(답한 수동까지 반영) 그대로
    let h = '<div class="ck-head"><h3><span class="tk">'+esc(v.prod)+'</span>'+(v.index?' <span class="subtle">기준 지수 '+esc(v.index)+'</span>':'')+'</h3>'
          + '<span class="verdict '+(GCLS[key]||'')+'" style="margin:0;padding:4px 11px;font-size:13.5px">'+GR(key)+'</span></div>';
    if(v.close != null) h += '<p class="subtle" style="margin:4px 0 2px">'+esc(v.date)+' 종가 <b style="color:var(--head)">'+v.close.toFixed(2)+'</b>'+(v.chg!=null?' · 당일 '+(v.chg>=0?'+':'')+v.chg.toFixed(2)+'%':'')+'</p>';
    const nAns = Object.keys((VD && VD.answers) || {}).length;
    h += '<p class="subtle" style="margin:2px 0 10px">엔진 판정: '+esc(v.reason)+(nAns?' <b style="color:var(--gold)">· 체크한 수동 조건 '+nAns+'개 반영(서버 판정)</b>':'')+'</p>';
    if(!v.gates){ return h; }
    // 이 상품의 '상품별' 규칙(공통 아님 — 자기 시세·보유·전용)을 공통과 **같은 블록 렌더러**로. 상품 하나짜리 perProd.
    const infos = collectRules([v], k=>!isCommon(k));
    if(infos.length) h += infos.map(info => ruleBlock(info, ans, [v])).join('');
    const SELL = (VD.verbs||[])[2] || '';
    if(!(v.sells||[]).length && v.exit_policy === 'none'){
      // 책에 판다 규칙이 없다(엔진 exit_policy) — 공통 판다만 있어 비는 경우는 제외(그건 공통 섹션에).
      h += '<div class="ck-cm-face"><span class="ck-cm-verb">③ '+esc(SELL)+'</span><span class="ck-opl">'+esc(VD.no_exit_note || '')+'</span></div>';
    }
    // 내 포지션 보유 요약 — 매도 규칙 블록(ruleBlock 안 commonExitFace)이 보유분 판정을 이미 보였고, 여기선 매입가·수익·다음 분할.
    const pos = v.positions || [];
    const hasExit = (v.sells||[]).some(s=>!isCommon(s));
    if(pos.length){
      pos.forEach(ps=>{
        h += '<p class="subtle" style="margin:6px 0 0">보유: '+esc(ps.entry_date)+' 매입가 '+esc(ps.entry_px)+' · 수익 '+(ps.ret!=null?(ps.ret>=0?'+':'')+ps.ret.toFixed(2)+'%':'?')+' · '+(ps.days!=null?ps.days+'거래일':'')+(ps.next_tranche?' · 다음 분할 「'+esc(ps.next_tranche.label)+'」 '+(ps.next_tranche.v===true?'<b style="color:var(--entry)">조건 충족</b>':ps.next_tranche.v===false?'미충족':'확인 필요'):'')+'</p>';
      });
    } else if(hasExit){
      h += '<p class="subtle" style="margin:6px 0 0">보유 포지션 없음 — 내 포지션은 로컬 파일(books/&lt;slug&gt;/positions.json)에 적으면 로컬 서버 화면에서 규칙별로 판정됩니다(공개 페이지에는 안 실림).</p>';
    }
    return h;
  }

  function renderSizing(){
    const cap = +(store.capital || 1000);
    const vs = (VD.verdicts||[]).filter(v=>v.size);
    if(!vs.length) return '';
    const anyW = vs.some(v=>v.size.weight_set);
    const anyT = vs.some(v=>(v.size.tranches||[]).length);
    if(!anyW && !anyT) return '';
    let h = '<h2 id="sheet-sizing"><span class="step">④</span>얼마나 — 비중 · 분할 계산</h2><div class="card">'
          + '<div class="calcrow"><label>총 투자금(만 원) <input id="ckCap" type="number" min="0" step="100" value="'+cap+'"></label></div>'
          + '<div class="tablewrap" style="margin-top:6px"><table><thead><tr><th>상품</th><th>오늘 비중</th><th>오늘 금액</th><th>분할</th></tr></thead><tbody>';
    let sum = 0, known = true;
    vs.forEach(v=>{
      // 금액 = 총 투자금 × 엔진이 낸 오늘 물량(units — judge/judge.to_units: 비중 × 분할 비율, 비중 모르면 null)
      const s = v.size;
      let w = s.weight, wtxt;
      if(!s.weight_set){ wtxt = '<span class="manual-tag">저자 미명시</span>'; w = null; }
      else if(w == null){ known = false; wtxt = '<span class="manual-tag">✋ 확인 필요 '+(s.weight_range||[]).map(x=>x.toFixed(0)+'%').join(' / ')+'</span>'; }
      else { sum += w; wtxt = w.toFixed(1)+'%'; }
      const amt = s.units == null ? null : cap * s.units;
      const trs = (s.tranches||[]).map(t=>esc(t.label)+(t.ratio==null ? ' <span class="manual-tag">비율 저자 미명시</span>' : ' '+Math.round(t.ratio*100)+'%'+(t.units!=null?' = '+Math.round(cap*t.units).toLocaleString('ko-KR')+'만':''))+(t.when?' <span class="subtle">· 언제 '+esc(t.when)+'</span>':'')).join('<br>') || '한 번에 전량';
      if(s.expr) wtxt += '<div class="subtle">'+(s.label?esc(s.label)+' — ':'')+esc(s.expr)+'</div>';
      h += '<tr><td style="color:var(--'+esc(v.prod.toLowerCase())+',var(--head))"><b>'+esc(v.prod)+'</b>'+refChip(s.ref)+'</td><td>'+wtxt+'</td><td>'
         + (amt!=null ? Math.round(amt).toLocaleString('ko-KR')+'만' : '—') + '</td><td>'+trs+'</td></tr>';
    });
    h += '</tbody></table></div>';
    // 현금 비중은 엔진이 실어보낸 VD.cash(파이썬에서 max(0, 100-합)으로 0 이상 클램프)를 그대로 쓴다 —
    //   화면에서 100-sum 을 다시 계산하면 비중 합이 100%를 넘을 때 음수 현금이 떠서 엔진과 갈라진다.
    if(anyW) h += '<p class="subtle" style="margin:8px 0 0">현금 '+(known && VD.cash!=null ? '<b style="color:var(--gold)">'+VD.cash.toFixed(1)+'%</b> = '+Math.round(cap*VD.cash/100).toLocaleString('ko-KR')+'만' : '— 비중 확인이 필요한 상품이 있어 계산 보류')+' · 비중은 산다 규칙이 준 비율(qty cash — 모드 조건 포함)에서 옵니다.</p>';
    return h + '</div>';
  }

  // 칸 밖 규칙 — 트리에 있는데 ①~④ 칸에 안 실린 규칙 전부(엔진이 VD.outside 로 실어보냄). 사람은 트리를 이 화면으로만
  //   검증하므로 조용히 빠지는 규칙이 없게 이유·식 그대로 보인다(skip 사유 · 쓰이지 않는 이름 조건 · 칸에 안 실린 갈래).
  function renderOutside(){
    const xs = VD.outside || [];
    if(!xs.length) return '';
    const KIND = {skip:'못 옮김(skip)', name:'이름 조건', branch:'칸 밖 갈래'};
    let h = '<h2 id="sheet-outside"><span class="step">칸 밖</span>체크리스트 칸에 안 나오는 규칙 '+xs.length+'개</h2><div class="card">'
          + '<p class="subtle" style="margin:0 0 10px">트리에는 있지만 위 ①~④ 칸에 들어가지 않은 규칙입니다. 빠뜨리지 않고 이유와 식을 그대로 보여줍니다.</p>';
    xs.forEach(x=>{
      h += '<div class="ck-row auto" '+(x.ref?'data-ref="'+esc(x.ref)+'"':'')+'><div class="ck-line"><span class="ck-m n">·</span><span class="ck-t">'
         + esc(x.label||'(이름 없음)')+' <span class="ck-opl">'+esc(KIND[x.kind]||x.kind)+(x.on&&x.on.length?' · '+esc(x.on.join(',')):'')+'</span>'+refChip(x.ref)+'</span></div>'
         + exprLine(x.text) + '<div class="ck-why">'+(x.kind==='skip'?'✋ ':'')+esc(x.reason)+'</div></div>';
    });
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
    let h = '';
    if(pending) h += '<div class="note">✋ 체크한 답으로 서버 판정을 다시 받는 중…</div>';
    if(serverNote) h += '<div class="note warn">'+esc(serverNote)+'</div>';
    const d = VD.ts ? new Date(VD.ts) : null, pad = n => String(n).padStart(2,'0');
    h += '<p class="subtle" id="td-ts">'+(VD.date?'<b>'+esc(VD.date)+'</b> 종가 기준':'')+(d?' · 판정 '+d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+' '+pad(d.getHours())+':'+pad(d.getMinutes()):'')+' · 출처 '+esc(VD.source||'')+' · ● 참 ○ 거짓 ? 모름 · ✋ 수동 조건만 직접 체크</p>';
    if(VD.missing && Object.keys(VD.missing).length){
      h += '<div class="note warn">시세 없음 → jhts 수집 요청: '+Object.keys(VD.missing).map(s=>esc(s)+' #'+esc(VD.missing[s])).join(' · ')+' — 그 심볼을 쓰는 조건은 ❔ 로 남습니다.</div>';
    }
    h += renderCommon();
    h += '<h2 id="sheet-step2"><span class="step">판정</span>상품별 체크리스트</h2>';
    h += '<div id="td-chips" style="display:grid;grid-template-columns:repeat('+prods.length+',1fr);gap:10px;margin:2px 0 14px">'
      + VD.verdicts.map(v=>{ const k = v.key;
          return '<button class="td-chip" data-jump="'+esc(v.prod)+'" style="text-align:left;cursor:pointer;background:'+(v.prod===curP?'var(--surface-2)':'var(--surface)')+';border:1px solid var(--line);border-top:3px solid var(--'+esc(v.prod.toLowerCase())+',var(--line));border-radius:10px;padding:11px 13px">'
            + '<div style="font-weight:800;font-size:15px">'+esc(v.prod)+'</div>'
            + '<div class="verdict '+(GCLS[k]||'')+'" style="margin:6px 0 0;padding:3px 9px;font-size:12.5px;display:inline-block">'+GR(k)+'</div></button>'; }).join('')
      + '</div>';
    const cur = VD.verdicts.find(v=>v.prod===curP);
    h += '<div class="card acc" id="entryCard" style="--pc:var(--'+esc(curP.toLowerCase())+',var(--line))">'+renderProduct(cur)+'</div>';
    h += renderSizing();
    h += renderOutside();
    root.innerHTML = h;
    bind();
  }

  function bind(){
    root.querySelectorAll('.td-chip').forEach(el=>el.addEventListener('click',()=>{ curP = el.dataset.jump; store.cur = curP; save(); render(); }));
    root.querySelectorAll('.ck-man button').forEach(b=>b.addEventListener('click',ev=>{
      ev.stopPropagation();
      const span = b.parentNode, ans = answers(), want = b.dataset.a === '1';
      // 공통 'allsame' 규칙이면 data-keys(세 상품 열쇠)에 같은 답을 함께 넣는다(mkey 는 상품별 그대로 — 서버 무변).
      //   보통 조건은 data-key 하나. 같은 답을 다시 누르면 해제(첫 열쇠 기준).
      let keys; try { keys = JSON.parse(span.dataset.keys || 'null'); } catch(e){ keys = null; }
      if(!keys || !keys.length) keys = [span.dataset.key];
      const off = ans[keys[0]] === want;                     // 이미 고른 값을 또 누름 → 전부 해제
      keys.forEach(k=>{ if(off) delete ans[k]; else ans[k] = want; });
      save(); resolve();
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
      // 동사 머리글(①안 산다 ②산다 …) — 왼쪽 색 띠 바(참=초록·거짓=빨강)
      +'#sheet-root .ck-verb{margin:20px 0 8px;padding:9px 13px;background:var(--surface-2);border:1px solid var(--line);border-left:3px solid var(--mute);border-radius:9px;display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:13px;font-weight:700;color:var(--head);line-height:1.4;letter-spacing:.01em}'
      +'#sheet-root .ck-verb.ok{border-left-color:var(--entry)} #sheet-root .ck-verb.bad{border-left-color:var(--warn)}'
      +'#sheet-root .ck-verb .ck-verb-v{font-size:11.5px;font-weight:600;color:var(--mute);white-space:nowrap}'
      +'#sheet-root .ck-verb.ok .ck-verb-v{color:var(--entry)} #sheet-root .ck-verb.bad .ck-verb-v{color:var(--warn)}'
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
      +'#sheet-root .ck-expr{font-size:12px;color:var(--text);margin:4px 0 0 32px;line-height:1.55;font-family:ui-monospace,Consolas,monospace;opacity:.85;word-break:break-word}'
      +'#sheet-root .ck-expr .ck-exh{font-family:inherit;color:var(--mute);font-weight:700;margin-right:2px}'
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
      +'#sheet-root .calcrow input{width:120px;margin-left:6px}'
      // 공통 시장 신호 섹션 — 규칙 한 블록(머리=이름) 안에 동사 갈래(①②③)마다 상품별 칩 + 조건.
      +'#sheet-root .ck-cm{margin:12px 0;padding:11px 13px;background:var(--surface-2);border:1px solid var(--line);border-radius:11px}'
      +'#sheet-root .ck-cm-rule{display:flex;align-items:center;gap:6px;margin-bottom:2px}'
      +'#sheet-root .ck-cm-name{font-size:14px;font-weight:800;color:var(--head)}'
      +'#sheet-root .ck-cm-face{display:flex;align-items:center;gap:8px;margin:8px 0 2px;flex-wrap:wrap}'
      +'#sheet-root .ck-cm-verb{font-size:11.5px;font-weight:700;color:var(--mute);background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--mute);border-radius:7px;padding:3px 9px}'
      +'#sheet-root .ck-cm-verb.ok{border-left-color:var(--entry);color:var(--entry)} #sheet-root .ck-cm-verb.bad{border-left-color:var(--warn);color:var(--warn)}'
      +'#sheet-root .ck-cm .ck-row{background:transparent;border:none;border-radius:0;padding:5px 0;margin:0}'
      +'#sheet-root .ck-sc-band{margin:9px 0 0;padding:7px 11px;background:var(--surface);border:1px solid var(--line);border-radius:8px;font-size:12.5px;color:var(--text);line-height:1.5}'
      +'#sheet-root .ck-sc-band b{color:var(--head)}'
      +'#sheet-root .ck-cm-chips{display:flex;justify-content:flex-end;margin:0 0 -4px}'
      +'#sheet-root .ck-pcs{display:inline-flex;gap:6px;flex-wrap:wrap}'
      +'#sheet-root .ck-pc{display:inline-flex;align-items:center;gap:4px;font-size:11px;color:var(--mute);background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:2px 7px}'
      +'#sheet-root .ck-pcl{font-weight:700;color:var(--head)}'
      +'#sheet-root .ck-pc .ck-m{width:16px;height:16px;font-size:10px}'
      +'#sheet-root .ck-row.off{opacity:.6}'
      +'#sheet-root .ck-row.fold{padding:4px 0}';
    document.head.appendChild(st);
  })();

  // 답을 서버에 보내 판정을 다시 받는다 — live-ui 의 __refreshVerdict(받은 판정을 #verdict-data 에 넣고 다시 그림).
  function resolve(){
    const fail = '서버 판정을 받지 못했다 — 화면은 마지막 서버 판정이다(체크한 답은 저장됨, 로컬 서버로 열면 반영).';
    if(!window.__refreshVerdict){ serverNote = fail; render(); return; }
    pending = true; serverNote = ''; render();
    window.__refreshVerdict().then(ok=>{ pending = false; serverNote = ok ? '' : fail; render(); })
      .catch(()=>{ pending = false; serverNote = fail; render(); });
  }

  render();
  // 라이브 모듈이 새 판정을 받으면 이 훅으로 다시 그린다. 라이브 모듈은 판정을 받을 때마다 이 답을 함께 보낸다.
  window.__applyVerdict = render;
  window.__verdictAnswers = () => (VD ? answers() : {});
})();
