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
  // 색 규칙(통일) — '켜졌을 때만 색': 조건이 지금 참(ON)일 때만 역할색이 뜬다.
  //   회피(안 산다)·매도(판다) 역할이 ON → 빨강(방어 경보) · 좋은 신호(산다) 역할이 ON → 초록.
  //   참(ON)만 역할색 · 거짓은 흐린 실선 테두리 · 모름(데이터 없음·저자 미명시)은 점선+? 로 거짓과 구분한다
  //   ('모름'을 '아님'으로 오해해 잘못된 확신으로 매매하지 않게). 수동은 색 대신 손바닥(✋) — 사람이 참/거짓을 직접 고른다.
  //   pol: 'good'(산다) | 'bad'(안 산다·판다) | null(중립).
  function markCls(v, pol){
    if(v === true) return pol==='bad'?'on bad':pol==='good'?'on good':'on';
    if(v === false) return 'off';
    return 'unknown';   // null/undefined = 모름(데이터 없음·저자 미명시) — 거짓과 다르다
  }
  function dot(v, pol){
    var c = markCls(v, pol);
    return '<span class="ck-m '+c+'"'+(c==='unknown' ? ' title="모름 — 데이터 없음 또는 저자 미명시">?' : '>')+'</span>';
  }
  // 논리 묶음 캡션(모두 / 하나 이상 / N개 이상). not 은 라벨이 뜻을 전하므로 캡션 없음.
  const OPW = it => it.op==='all' ? '모두' : it.op==='any' ? '하나 이상' : it.op==='atleast' ? (it.n+'개 이상') : '';
  // 원문 소절 뱃지 — 규칙 줄마다 한 번. 이게 그 규칙의 원문 표시다(다른 데서 또 표시하지 않는다).
  function refChip(ref){ return ref ? ' <a class="ck-ref" data-ref="'+esc(ref)+'" title="플레이북 원문 소절로">'+esc(ref)+'</a>' : ''; }
  function fmtV(v){ return typeof v === 'number' ? (Math.abs(v) >= 100 ? v.toFixed(1) : v.toFixed(2)) : ''; }
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
  // 실제데이터 — 조건이 '무엇을 재서 얼마였나'(엔진 detail). 원시 입력 나열은 빼고 잰 값·기준만 간결히.
  function measCompact(detail){
    if(!detail || !detail.length) return '';
    const parts = detail.map(d=>{
      const u = d.unit ? esc(d.unit) : '';
      const noVal = (d.lhs === null || d.lhs === undefined);
      const lv = noVal ? '<span class="ev-x">측정 없음</span>' : '<b>'+fmtMeas(d.lhs)+u+'</b>';
      const L = (d.lhsd ? esc(d.lhsd)+' ' : '') + lv;
      const R = d.rhsd ? ' '+(EVSYM[d.op]||'')+' '+esc(d.rhsd)+' <b>'+fmtMeas(d.rhs)+u+'</b>'
              : (d.rhs === null || d.rhs === undefined) ? ' <span class="ev-th">· 기준 '+(EVSYM[d.op]||'')+' ? (저자 미명시)</span>'
                       : ' <span class="ev-th">· 기준 '+(EVSYM[d.op]||'')+' '+fmtMeas(d.rhs)+u+'</span>';
      return L + R;
    });
    return parts.join('<span class="ev-sep"> · </span>');
  }
  // 오른쪽 '실제데이터' 칸 — 측정값만(있을 때). 참/거짓 글자는 없다 — 상태는 동그라미가 전한다.
  function dataCell(node){
    const m = measCompact(node.detail);
    return m ? '<span class="ck-d">'+m+'</span>' : '';
  }
  // 식 글 한 줄 — 칸 밖 규칙(renderOutside)에서만 쓴다. 본 체크리스트 줄엔 수식 글줄을 넣지 않는다(피로도).
  function exprLine(x, head){ return x ? '<div class="ck-expr">'+(head?'<span class="ck-exh">'+esc(head)+'</span> ':'')+esc(x)+'</div>' : ''; }
  // 공통 규칙 = 모든 상품에 거는 **시장 신호**(엔진 allprod=규칙 레벨 on 없음 · selfdep=자기 시세/보유 안 읽음).
  //   VIX·금리·선물처럼 구체 티커만 보는 규칙이 공통이다. 상품 자기 시세($self)·기준 지수($index)·보유(pos)를
  //   읽는 규칙(갭상승·윗꼬리·수익률 등)은 상품마다 값이 실제로 달라 **상품 카드**로 보낸다(공통 아님).
  //   단 노드 레벨 on(공통 결정에 한 상품만 더 붙는 조건 — 장전 점수의 SOXL 대표주)은 공통에서 빼지 않는다(selfdep 무관).
  const isCommon = it => !!(it && it.allprod && !it.selfdep);
  // 공통 섹션 — 세 상품의 같은 규칙 노드를 나란히 걷는다(구조 동일, 값만 갈림). 값이 상품마다 같으면 칩 하나,
  //   갈리면(자기 시세·기준 지수·보유·상품 전용 노드) 상품별 칩. 측정 증거(📊 detail)는 여기선 생략 — 상품 카드에서(옵션 B).
  function valMark(v, pol){ return (typeof v === 'number') ? '<span class="dataval">'+fmtV(v)+'</span>' : dot(v===undefined?null:v, pol); }
  // 상품별 결과 마크(동사 갈래 머리칩 등) — 값이 상품마다 같으면 마크 하나, 갈리면 상품별 칩. 색은 pol 로.
  function cMark(prods, its, pol){
    // 상품별 값(off = 노드 레벨 on 에 그 상품이 없음 → 이 상품엔 적용 안 됨)
    const vals = its.map(it => !it ? undefined : (it.off ? 'off' : (it.v===undefined?null:it.v)));
    const real = vals.filter(v => v!=='off' && v!==undefined);
    const anyOff = vals.some(v => v==='off');
    const allSame = real.length>0 && real.every(v => v===real[0]);
    if(allSame && !anyOff) return valMark(real[0], pol);     // 값 공통(구체 티커) → 마크 하나
    return '<span class="ck-pcs">'+prods.map((p,i)=>{        // 갈림 → 상품별 칩
      const v = vals[i], m = (v==='off'||v===undefined) ? '<span class="ck-m n"></span>' : valMark(v, pol);
      return '<span class="ck-pc" title="'+esc(p)+'"><span class="ck-pcl">'+esc(p)+'</span>'+m+'</span>';
    }).join('')+'</span>';
  }
  // 조건 한 줄(공통·카드 공용) — [동그라미][라벨·묶음캡션·소절칩][실제데이터] 한 형식으로 통일한다.
  //   pol = 이 조건이 속한 동사 갈래의 역할색(산다=good · 안 산다/판다=bad). 중첩 자식은 부모 pol 을 잇는다.
  function commonNode(its, prods, path, ans, depth, seen, pol){
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
    if(ck && cardSeen.has(ck)) return '<div class="ck-row fold"><div class="ck-line">'+dot(it0.v===undefined?null:it0.v, pol)
      + '<span class="ck-t">'+esc(it0.label)+' <span class="ck-opl">↑ 위에서 펼침</span>'+refChip(it0.ref)+'</span></div></div>';
    if(ck) cardSeen.add(ck);
    // 상품 포크 접기 — 여러 상품 중 일부에서만 켜지는 가지(off 섞임)는 공통 뷰에서 안쪽을 펼치지 않고 한 줄로
    //   ('어느 상품에 걸렸나'까지). 상품 카드(상품 하나)에선 off 가지는 위에서 이미 걸러졌으니 gated 가 아니라 펼쳐진다.
    const gated = its.some(it => it && it.off);
    const nk = gated ? 0 : its.reduce((m,it)=> Math.max(m, it&&it.kids?it.kids.length:0), 0);
    let kidsHtml = '';
    for(let i=0;i<nk;i++){
      kidsHtml += commonNode(its.map(it => it&&it.kids?it.kids[i]:null), prods, path+'.'+i, ans, depth+1, depth===0?new Set():seen, pol);
    }
    const isM = it0.manual!==undefined && !gated;
    const showRow = it0.label || it0.manual!==undefined || it0.expr || gated;
    if(!showRow){
      if(!kidsHtml) return '';
      const gop = OPW(it0);
      // 묶음 캡션(모두·하나 이상·N개 이상)이 있으면 그 아래 조건을 들여써서 '이 캡션이 지배하는 줄'을 눈으로 묶는다.
      //   중첩(모두 { … 하나 이상 { … } })이 평평하게 섞여 어느 캡션이 어느 줄을 가리키는지 흐려지지 않게.
      return it0.op ? '<div class="ck-grp">'+(gop?'<div class="ck-op">'+esc(gop)+'</div><div class="ck-gkids">'+kidsHtml+'</div>':kidsHtml)+'</div>' : kidsHtml;
    }
    if(dup) return '';
    // 왼쪽 동그라미 + 오른쪽 실제데이터
    let circle, data;
    if(isM){
      // 수동 — 체크 동그라미에 손바닥(✋). 눌러서 체크(✔)↔해제. 참/거짓 글자는 없다(동그라미가 상태를 전한다).
      //   한 번 누르면 세 상품 열쇠에 같은 답(mkey 는 상품별 그대로 — 서버 무변). bind() 가 data-keys 로 처리.
      const body = it0.mkey || it0.manual, keys = prods.map(p=>p+'|'+body), a = ans[keys[0]];
      const onc = a===true ? ' on'+(pol==='bad'?' bad':pol==='good'?' good':'') : '';
      circle = '<span class="ck-man" data-key="'+esc(keys[0])+'" data-keys="'+esc(JSON.stringify(keys))+'">'
             + '<button type="button" data-a="1" class="ck-m man'+onc+'" title="수동 확인 — 눌러서 체크">✋</button></span>';
      data = '';
    } else {
      const vals = its.map(it => !it ? undefined : (it.off ? 'off' : (it.v===undefined?null:it.v)));
      const real = vals.filter(v => v!=='off' && v!==undefined);
      const allSame = real.length>0 && real.every(v => v===real[0]) && !vals.some(v=>v==='off');
      circle = cMark(prods, its, pol);
      data = (gated || !allSame) ? '' : dataCell(it0);   // 상품마다 값이 갈리면 동그라미 칩이 이미 상태를 전한다
    }
    // 적용되는 상품만 꼬리표(상품 포크면 '· 상품 카드에서'로 안쪽을 거기서 보라고 안내)
    const act = prods.filter((p,i)=> its[i] && !its[i].off);
    const offNote = (act.length && act.length<prods.length)
      ? ' <span class="ck-opl">'+esc(act.join(','))+' 전용'+(gated?' · 상품 카드에서':'')+'</span>' : '';
    const opw = OPW(it0), opl = (opw && !gated)?' <span class="ck-opl">'+esc(opw)+'</span>':'';
    // 라벨 없으면: 수동 사유 → 묶음 캡션 → 식 순으로 라벨 자리를 채운다(식 글줄은 따로 넣지 않으므로 여기서만).
    const txt = it0.label || (isM ? (it0.manual||'수동 확인') : (gated && it0.op ? OPW(it0)+' 조건' : (it0.expr||'수동 확인')));
    return '<div class="ck-row'+(isM?' man':'')+'" '+(it0.ref?'data-ref="'+esc(it0.ref)+'"':'')+'>'
      + '<div class="ck-line">'+circle+'<span class="ck-t">'+esc(txt)+opl+offNote+refChip(it0.ref)+'</span>'+data+'</div>'
      + (kidsHtml?'<div class="ck-kids">'+kidsHtml+'</div>':'') + '</div>';
  }
  // 판다(매도) 갈래 한 줄 — 매도는 보유분에만 걸리므로 상품별 결과 칩은 '내 포지션'이 있을 때만(없으면 흐린 동그라미).
  //   역할색 bad(방어). 조건 설명은 '언제' 글을 라벨 자리에 둔다(수식 글줄은 따로 넣지 않는다).
  function commonExitFace(sell, vs, lab){
    const r0 = sell[0][1];
    const marks = [];
    vs.forEach(v=>{
      const idx = (v.sells||[]).findIndex(e=>e.label===lab);
      if(idx < 0) return;
      (v.positions||[]).forEach(ps=>{ const e = (ps.sells||[])[idx]; if(e) marks.push([v.prod, {v:e.v}]); });
    });
    const st = marks.length ? cMark(marks.map(x=>x[0]), marks.map(x=>x[1]), 'bad') : '<span class="ck-m off"></span>';
    const txt = r0.when || r0.sell || lab;
    return '<div class="ck-row"><div class="ck-line">'+st
      + '<span class="ck-t">'+esc(txt)+' <span class="ck-opl">③ '+esc((VD.verbs||[])[2]||'')+(r0.sell?' · '+esc(r0.sell):'')+'</span></span></div></div>';
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
      items += commonNode(byProd.map(b=>b.s.at.kids[i]), prods, 'common', ans, 0, new Set(), 'good');   // 점수 지표 = 유리할수록 좋음(초록)
    }
    // 상품 전용 가지(대표주 등 extras) — extras 가 있는 갈래(보통 산다)에서 상품별로 가져온다
    const ef = parsed.find(x=>x.sc.extras.length);
    if(ef){
      const eb = ef.f.perProd.map(x=>({prod:x[0], s:findScore(x[1])}));
      const ne = Math.max.apply(null, eb.map(b=>b.s?b.s.extras.length:0).concat(0));
      for(let i=0;i<ne;i++){
        items += commonNode(eb.map(b=> b.s && b.s.extras[i] || null), eb.map(b=>b.prod), 'common', ans, 0, new Set(), 'good');
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
    // 특수 머리칩은 없앴다(통일) — 유리 지표를 같은 줄로 나열하고, 임계만 한 줄 요약으로.
    const band = bands.length ? '<div class="ck-sc-band">판정: '+total+'개 중 '+bands.join(' · ')+'</div>' : '';
    return items + band;
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
    const V = VD.verbs || [], vnum = {}, vcls = {}, vpol = {};
    vnum[V[0]]='① '; vnum[V[1]]='② '; vnum[V[2]]='③ '; vcls[V[0]]='bad'; vcls[V[1]]='ok';
    vpol[V[0]]='bad'; vpol[V[1]]='good'; vpol[V[2]]='bad';   // 안 산다·판다=방어(빨강) · 산다=좋음(초록)
    let block = '<div class="ck-cm-rule"><span class="ck-cm-name">'+esc(info.label)+'</span>'+refChip(info.ref)+'</div>';
    const sc = info.faces.length ? scoreCard(info, ans) : null;   // 점수 규칙만 특수(임계 한 줄) — 나머지는 전부 같은 줄
    if(sc){ block += sc; }
    else info.faces.forEach(f=>{
      const pol = vpol[f.verb] || null;
      const chips = cMark(f.perProd.map(x=>x[0]), f.perProd.map(x=>x[1]), pol);
      const bare = f.perProd.map(x=>{ const n = Object.assign({}, x[1]); delete n.label; delete n.ref; delete n.note; return n; });
      const cond = commonNode(bare, f.perProd.map(x=>x[0]), 'common', ans, 0, new Set(), pol);
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
    h += '<p class="subtle" id="td-ts">'+(VD.date?'<b>'+esc(VD.date)+'</b> 종가 기준':'')+(d?' · 판정 '+d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+' '+pad(d.getHours())+':'+pad(d.getMinutes()):'')+' · 출처 '+esc(VD.source||'')+' · 동그라미는 켜졌을 때만 색: <span style="color:var(--entry)">●</span> 좋은 신호 · <span style="color:var(--warn)">●</span> 회피·매도 · ○ 거짓 · <span class="ck-m unknown" style="display:inline-flex">?</span> 모름(데이터·숫자 없음) · ✋ 수동(눌러서 체크)</p>';
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
      +'#sheet-root .ck-gkids{margin:0 0 0 3px;border-left:1px solid var(--line);padding-left:13px}'
      +'#sheet-root .ck-line{display:flex;gap:10px;align-items:center}'
      +'#sheet-root .ck-t{flex:1;min-width:0;font-size:13.5px;line-height:1.5;color:var(--text)}'
      +'#sheet-root .ck-row.man .ck-t{color:var(--head)}'
      +'#sheet-root .ck-opl{font-size:11.5px;color:var(--mute);margin-left:6px}'
      // 칸 밖 규칙에서만 쓰는 식 글·사유줄(본 체크리스트 줄엔 없다)
      +'#sheet-root .ck-expr{font-size:12px;color:var(--text);margin:4px 0 0 2px;line-height:1.55;font-family:ui-monospace,Consolas,monospace;opacity:.85;word-break:break-word}'
      +'#sheet-root .ck-expr .ck-exh{font-family:inherit;color:var(--mute);font-weight:700;margin-right:2px}'
      +'#sheet-root .ck-why{font-size:12px;color:var(--mute);margin:4px 0 0 2px;line-height:1.5}'
      // 실제데이터 칸(오른쪽) — 측정값 + 지금 상태(참/거짓/확인 필요)
      +'#sheet-root .ck-d{flex:none;max-width:52%;text-align:right;font-size:12px;color:var(--mute);line-height:1.5}'
      +'#sheet-root .ck-d b{color:var(--head);font-weight:700}'
      +'#sheet-root .ck-d .ev-x{color:var(--gold);font-weight:700}#sheet-root .ck-d .ev-th{color:var(--mute)}#sheet-root .ck-d .ev-sep{color:var(--line);margin:0 2px}'
      // 동그라미 — 켜졌을 때만 색(초록=좋음·빨강=회피/매도), 거짓·모름은 흐린 테두리. 수동은 손바닥(✋).
      +'#sheet-root .ck-m{flex:none;box-sizing:border-box;display:inline-flex;align-items:center;justify-content:center;width:15px;height:15px;border-radius:50%;border:2px solid var(--line);background:transparent;line-height:1}'
      +'#sheet-root .ck-m.on{border-color:transparent;background:var(--mute)}'
      +'#sheet-root .ck-m.on.good{background:var(--entry)}'
      +'#sheet-root .ck-m.on.bad{background:var(--warn)}'
      +'#sheet-root .ck-m.off{border-color:var(--line);background:transparent}'
      +'#sheet-root .ck-m.unknown{border-color:var(--line);border-style:dashed;background:transparent;color:var(--mute);font-size:10px}'
      +'#sheet-root .ck-m.n{border-color:var(--line);background:transparent;opacity:.5}'
      // 수동 = 체크 동그라미에 손바닥(✋) — 눌러서 체크↔해제. 미체크는 점선 테두리(확인 필요), 체크하면 역할색으로 채움.
      +'#sheet-root button.ck-m{padding:0;cursor:pointer;font:inherit;color:inherit;transition:background .12s,border-color .12s}'
      +'#sheet-root .ck-m.man{width:18px;height:18px;border:2px dashed var(--gold);background:transparent;color:var(--gold);font-size:10px}'
      +'#sheet-root .ck-m.man:hover{border-color:var(--head);color:var(--head)}'
      +'#sheet-root .ck-m.man.on{border-style:solid;border-color:transparent;background:var(--gold);color:#0d0f14}'
      +'#sheet-root .ck-m.man.on.good{background:var(--entry)}'
      +'#sheet-root .ck-m.man.on.bad{background:var(--warn)}'
      +'#sheet-root .ck-man{flex:none;align-self:center;display:inline-flex}'
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
