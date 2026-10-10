(function(){
  'use strict';
  /* ============================================================
     실전 체크리스트 — 조건 트리 판정 결과(#verdict-data)만 그린다 (책 무관 · 종목 하드코딩 없음)
     · 트리를 직접 읽지 않는다. 판정 화면 데이터(consumers/display/verdict_view)가 낸 칸별 설명(view)을 그대로 그린다.
     · 사람이 체크하는 건 수동(✋) 조건뿐이다. 체크하면 그 답을 서버(POST /api/verdict)에 보내고, 서버가 답까지
       반영해 낸 판정(등급·칸 값·금액)을 그대로 다시 그린다 — 서버 권위. 화면은 등급·3값 논리를 계산하지 않는다
       (평가기는 dsl/tradeTool.py 한 벌). 서버 없이 열면 체크는 저장되지만 판정은 바뀌지 않는다(그렇다고 알린다).
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

  // 수동 답 열쇠 — 서버(dsl/tradeTool.answer_key)와 같은 규칙: 여러 상품이 같이 보는 정의 안(shared)이면 책 전체에
  //   하나("*"), 아니면 상품마다(path 앞머리 = 상품). 본체는 "?" 식이면 엔진이 준 식 열쇠(it.mkey), 문장 수동은 그 문장.
  //   화면은 이 열쇠로 답을 모아 보낼 뿐 — 답으로 값을 계산하는 건 서버다.
  function mkey(it, path){ return (it.shared ? '*' : path.split('.')[0]) + '|' + (it.mkey || it.manual); }
  // 등급 글자표는 엔진이 판정 JSON(VD.grades, = dsl/tradeTool.GRADES)에 실어보낸다 — 화면은 받아 쓴다.
  // 고치는 곳은 파이썬 한 곳. 혹시 없으면 키 그대로 보여 깨지지 않게.
  const GR = k => ((VD && VD.grades) || {})[k] || k;
  const GCLS = {buy:'go', confirm:'small', unknown:'small', nofilter:'no', avoid:'no', wait:''};
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
  // 항목 하나(노드) — 숨김 잎은 그리지 않는다. 라벨 없는 묶음은 묶음 줄 없이 자식만 들여쓴다.
  // 값(●/○/?)은 서버가 낸 it.v(사람이 답한 수동까지 반영 — 답 없는 수동은 ? 모름) 그대로.
  function node(it, path, ans, depth, seen){
    if(!it) return '';
    if(it.hidden && !it.kids) return '';
    if(!seen) seen = new Set();
    // 표시 전용 중복 제거: 같은 조건(라벨+기준+측정값)이 한 패턴 안에서 되풀이되면 한 번만.
    //   (streak/barssince 파생조건이 라벨 없이 안쪽 건물블록만 반복 노출되는 경우를 걷어낸다.)
    //   zone 바로 밑 패턴마다 집합을 새로 둬서 다른 패턴끼리는 제거하지 않는다(각 카드가 자기 조건을 다 보이게).
    const sig = (it.label || it.manual) ? ((it.label||it.manual)+'|'+(it.ref||'')+'|'+(it.detail?JSON.stringify(it.detail):'')) : null;
    const dup = !!(sig && seen.has(sig));
    if(sig) seen.add(sig);
    const kids = (it.kids||[]).map((c,i)=>node(c, path+'.'+i, ans, depth+1, depth===0 ? new Set() : seen)).join('');
    const showRow = it.label || it.manual !== undefined;
    if(!showRow){
      if(!kids) return '';
      const gop = OPW(it);
      return it.op ? '<div class="ck-grp">'+(gop?'<div class="ck-op">'+esc(gop)+'</div>':'')+kids+'</div>' : kids;
    }
    if(dup) return '';   // 같은 조건을 이미 보여줬다 — 한 번만
    const isM = it.manual !== undefined && !(it.observed && it.v !== null && it.v !== undefined);
    const a = isM ? ans[mkey(it, path)] : undefined;
    const val = it.v === undefined ? null : it.v;
    // folded = 같은 칸 다른 곳에 이미 펼쳐 둔 조건(엔진이 표시) — 화면엔 한 줄만.
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
  // 칸(avoid/entry = any 묶음)을 원문 소절(ref)별로 모아 같은 절의 규칙이 붙어 보이게 한다(순서 보존).
  //   원문 표시는 각 규칙 줄의 뱃지 하나뿐 — 따로 소절 머리글을 달지 않는다(같은 원문을 두 번 보이지 않게).
  function zoneByRef(zone, path, ans){
    if(!zone || !zone.kids || !zone.kids.length) return node(zone, path, ans, 0);
    const order = [], bucket = {};
    // 공통(allprod) 규칙은 맨 위 공통 섹션에서만 그린다 — 상품 카드에선 그 상품 전용(on 에 그 상품이 든)만.
    zone.kids.forEach((k,i)=>{ if(isAllprod(k)) return; const r = k.ref || ''; if(!(r in bucket)){ bucket[r] = []; order.push(r); } bucket[r].push([k,i]); });
    return order.map(r => bucket[r].map(([k,i]) => node(k, path+'.'+i, ans, 0)).join('')).join('');
  }
  // 공통(allprod) 규칙만 걸러낸다 — 상품 카드에선 빼고, 화면 맨 위 "공통 시장 신호" 섹션에 한 번만 그린다.
  const isAllprod = it => !!(it && it.allprod);
  // 공통 섹션 — on 없는 규칙(모든 상품에 같은 규칙)을 칸별로 한 번만. 단, $index/$self 를 쓰면 값이 상품마다
  //   다르므로 각 규칙에 상품별 결과 칩(prod● / prod○ / prod?)을 붙이고, 수동(✋)은 상품별 토글로 그린다
  //   (답 열쇠 mkey 는 지금 규칙 그대로 — 상품마다 자기 답을 가진다. 값 손실·답 혼선 없음).
  function prodChips(pv){            // pv = [[prod, v], …] — 값이 다 같으면 칩 하나로 합친다
    const vals = pv.map(x=>x[1]);
    const same = vals.every(x=>x===vals[0]);
    if(same) return '<span class="ck-pc">'+MARK(vals[0])+'</span>';
    return '<span class="ck-pcs">'+pv.map(([p,v])=>'<span class="ck-pc" title="'+esc(p)+'"><span class="ck-pcl">'+esc(p)+'</span>'+MARK(v)+'</span>').join('')+'</span>';
  }
  // 공통 매도 규칙 한 줄 — 카드의 매도 줄과 같은 모양(라벨·판다 폭·원문). 매도는 보유분에만 걸리므로 상품별
  //   결과 칩은 '내 포지션'이 있을 때만(ps.exit[그 규칙 index]) 상품별로 보여준다(없으면 —).
  function commonExitRow(lab, perProd, vs){
    const r0 = perProd[0][1];
    // 포지션 보유분 마크 — 각 상품의 exit 목록에서 이 label 의 index 를 찾아 그 상품 포지션들의 판정을 모은다
    const marks = [];
    vs.forEach(v=>{
      const idx = (v.exit||[]).findIndex(e=>e.label===lab);
      if(idx < 0) return;
      (v.positions||[]).forEach(ps=>{ const e = (ps.exit||[])[idx]; if(e) marks.push([v.prod, e.v]); });
    });
    // 보유분 판정 마크(상품별) — 카드 매도 줄과 같게 줄 앞에. 포지션 없으면 '—'(걸릴 보유분이 없음).
    const st = marks.length ? prodChips(marks) : '<span class="ck-m n">—</span>';
    const row = '<div class="ck-row auto" '+(r0.ref?'data-ref="'+esc(r0.ref)+'"':'')
      + '><div class="ck-line">'+st+'<span class="ck-t">'+esc(lab)+' <span class="ck-opl">'+esc(r0.sell)+'</span>'+refChip(r0.ref)+'</span></div>'
      + (r0.note?'<div class="ck-why">'+esc(r0.note)+'</div>':'')+'</div>';
    return '<div class="ck-cm">'+row+'</div>';
  }
  function renderCommon(){
    const vs = VD.verdicts || [];
    if(vs.length < 1) return '';
    const ans = answers();
    // 칸별(회피·진입·매도) 공통 규칙을 첫 상품 순서대로 모은다(라벨로 상품 간 교차참조).
    const secs = [['avoid','② '], ['entry','③ '], ['exit','⑥ ']];
    const zl = k => (VD.zones && VD.zones[k]) || k;
    let body = '';
    secs.forEach(([sec, num])=>{
      // 첫 상품에서 이 칸의 공통 규칙 라벨 순서를 잡는다
      const kidsOf = v => sec==='exit' ? (v.exit||[]) : ((v.zones && v.zones[sec] && v.zones[sec].kids) || []);
      const order = [];
      kidsOf(vs[0]).forEach(k=>{ if(isAllprod(k) && order.indexOf(k.label) < 0) order.push(k.label); });
      if(!order.length) return;
      body += '<div class="grouplabel ck-zone" style="margin-top:14px">'+num+esc(zl(sec))+'</div>';
      order.forEach(lab=>{
        // 각 상품에서 같은 label 의 항목을 찾아 교차참조(한 상품에만 있어도 공통 규칙이면 보인다)
        const perProd = vs.map(v=>[v.prod, (kidsOf(v).find(k=>k.label===lab)||null)]).filter(x=>x[1]);
        if(!perProd.length) return;
        if(sec === 'exit'){ body += commonExitRow(lab, perProd, vs); return; }
        const pv = perProd.map(([p,it])=> [p, (it.v===undefined?null:it.v)]);
        // 상품별 결과 칩 — 값이 다 같으면 칩 하나, 다르면 TQQQ● SOXL○ UPRO? 처럼 상품마다.
        const chips = '<div class="ck-cm-chips">'+prodChips(pv)+'</div>';
        const allProds = perProd.map(x=>x[0]);
        // allsame = 상품에 안 기대는 공통 규칙(값·질문이 상품마다 같음) → 한 줄로 합친다. 수동 토글은 한 번 누르면
        //   세 상품 열쇠에 같은 답을 넣는다(mkey 는 상품별 그대로, 서버 무변). $index/$self 규칙은 상품마다 달라 따로.
        let inner;
        if(perProd[0][1].allsame){
          let html = node(perProd[0][1], allProds[0]+'.common', ans, 0);
          // 각 수동 토글(.ck-man)의 data-key="P0|본체" → 모든 상품 열쇠 data-keys 로 (접두 상품만 바꿔 같은 본체).
          //   data-key 는 이미 HTML 이스케이프됨 → 원문으로 되돌려 열쇠를 만들고, 속성값은 한 번만 다시 이스케이프.
          const unesc = s => s.replace(/&quot;/g,'"').replace(/&gt;/g,'>').replace(/&lt;/g,'<').replace(/&amp;/g,'&');
          html = html.replace(/data-key="([^"]*)"/g, (m, k)=>{
            const raw = unesc(k), bar = raw.indexOf('|'); if(bar < 0) return m;
            const bodyk = raw.slice(bar);
            const keys = allProds.map(p=>p+bodyk);   // 같은 본체, 상품 접두만 바꾼다(mkey 규칙 그대로)
            return 'data-key="'+esc(keys[0])+'" data-keys="'+esc(JSON.stringify(keys))+'"';
          });
          inner = html;
        } else {
          // 상품마다 값·답이 다른 공통 규칙($index/$self) — 상품별로 node() 로 그린다(각자 자기 열쇠).
          inner = perProd.map(([p,it])=>'<div class="ck-cm-prod"><div class="ck-cm-pl">'+esc(p)+' 기준</div>'+node(it, p+'.common', ans, 0)+'</div>').join('');
        }
        body += '<div class="ck-cm">'+chips+inner+'</div>';
      });
    });
    if(!body) return '';
    return '<h2 id="sheet-common2"><span class="step">공통</span>공통 시장 신호 — 모든 상품에 같이 적용</h2><div class="card">'
      + '<p class="subtle" style="margin:0 0 10px">아래는 특정 상품용이 아니라 시장 전체에 거는 규칙입니다. 상품마다 결과가 다를 수 있어 상품별 ●/○/? 를 함께 보여줍니다(예: 기준 지수가 상품마다 달라 값이 갈립니다).</p>'
      + body + '</div>';
  }
  function renderProduct(v){
    const ans = answers();
    const key = v.key;                          // 서버 판정(답한 수동까지 반영) 그대로
    const P = s => v.prod+'.'+s;
    let h = '<div class="ck-head"><h3><span class="tk">'+esc(v.prod)+'</span>'+(v.index?' <span class="subtle">기준 지수 '+esc(v.index)+'</span>':'')+'</h3>'
          + '<span class="verdict '+(GCLS[key]||'')+'" style="margin:0;padding:4px 11px;font-size:13.5px">'+GR(key)+'</span></div>';
    if(v.close != null) h += '<p class="subtle" style="margin:4px 0 2px">'+esc(v.date)+' 종가 <b style="color:var(--head)">'+v.close.toFixed(2)+'</b>'+(v.chg!=null?' · 당일 '+(v.chg>=0?'+':'')+v.chg.toFixed(2)+'%':'')+'</p>';
    const nAns = Object.keys((VD && VD.answers) || {}).length;
    h += '<p class="subtle" style="margin:2px 0 10px">엔진 판정: '+esc(v.reason)+(nAns?' <b style="color:var(--gold)">· 체크한 수동 조건 '+nAns+'개 반영(서버 판정)</b>':'')+'</p>';
    if(!v.zones){ return h; }
    const z = v.zones;
    // 칸 이름표(필터·회피·진입·조심·매도)는 엔진 값(VD.zones = dsl/tradeTool.ZONE_LABELS)에서 꺼낸다 — 복붙 금지.
    //   동그라미 번호는 화면 전용 머리글이라 그대로 두고, 이름표 글자만 VD.zones 에서 가져온다(없으면 키 그대로).
    const zl = k => (VD.zones && VD.zones[k]) || k;
    // 칸 머리 값 = 남은 수동 답과 상관없이 정해졌으면(서버의 낙관 opt == 비관 pes) 그 값, 아니면 서버 값(대개 ? 확인 필요).
    const zv = s => (v.opt && v.pes && v.opt[s] === v.pes[s]) ? v.opt[s] : (z[s] ? z[s].v : null);
    h += zoneHead('① '+zl('filter')+' — 참이어야 본다', true, zv('filter')) + node(z.filter, P('filter'), ans, 0);
    h += zoneHead('② '+zl('avoid')+' — 참이면 보류', false, zv('avoid')) + zoneByRef(z.avoid, P('avoid'), ans);
    h += zoneHead('③ '+zl('entry')+' — 참이면 매수 자리', true, zv('entry')) + zoneByRef(z.entry, P('entry'), ans);
    if((v.caution||[]).length){
      const c = v.amount || {}, f = c.factor == null ? 1 : c.factor;   // 금액 배수·폭 미명시·확인 필요 = 서버(dsl/tradeTool Grade)
      h += '<div class="grouplabel ck-zone" style="color:var(--gold)">④ '+esc(zl('caution'))+' — 사더라도 금액을 줄인다 <span class="ck-zv">금액 ×'+f.toFixed(2)+((c.unspecified||[]).length?' · 폭 미명시 '+c.unspecified.length:'')+((c.unknown||[]).length?' · 확인 필요 '+c.unknown.length:'')+'</span></div>';
      v.caution.forEach((r,i)=>{
        const lab = r.label + (r.scale!=null ? ' (금액 ×'+(+r.scale).toFixed(2)+')' : ' (줄일 폭 저자 미명시)');
        h += node(Object.assign({}, r.view, {label: lab, ref: r.ref, note: r.note}), P('caution.'+i), ans, 0);
      });
    }
    // 매도 규칙 + 내 포지션 — 공통(allprod) 매도 규칙은 공통 섹션에서 그리고, 카드엔 그 상품 전용만.
    //   포지션(ps.exit)은 게이트웨이 순서(원래 i)로 쌓였으니 인덱스를 보존해 매칭한다.
    const exitOwn = (v.exit||[]).map((r,i)=>[r,i]).filter(([r])=>!isAllprod(r));
    if(exitOwn.length){
      h += '<div class="grouplabel ck-zone" style="color:var(--entry)">⑥ '+esc(zl('exit'))+' — 보유분을 팔 때 (걸리면 다음 날 시가)</div>';
      const pos = v.positions || [];
      exitOwn.forEach(([r,i])=>{
        const live = pos.map(ps => (ps.exit||[])[i]).filter(Boolean);
        const st = live.length ? live.map(e=>MARK(e.v)).join('') : '<span class="ck-m n">—</span>';
        h += '<div class="ck-row auto" '+(r.ref?'data-ref="'+esc(r.ref)+'"':'')+'><div class="ck-line">'+st+'<span class="ck-t">'+esc(r.label)+' <span class="ck-opl">'+esc(r.sell)+'</span>'+refChip(r.ref)+'</span></div>'+(r.note?'<div class="ck-why">'+esc(r.note)+'</div>':'')+'</div>';
      });
      if(pos.length){
        pos.forEach(ps=>{
          h += '<p class="subtle" style="margin:6px 0 0">보유: '+esc(ps.entry_date)+' 매입가 '+esc(ps.entry_px)+' · 수익 '+(ps.ret!=null?(ps.ret>=0?'+':'')+ps.ret.toFixed(2)+'%':'?')+' · '+(ps.days!=null?ps.days+'거래일':'')+(ps.next_tranche?' · 다음 분할 「'+esc(ps.next_tranche.label)+'」 '+(ps.next_tranche.v===true?'<b style="color:var(--entry)">조건 충족</b>':ps.next_tranche.v===false?'미충족':'확인 필요'):'')+'</p>';
        });
      } else {
        h += '<p class="subtle" style="margin:6px 0 0">보유 포지션 없음 — 내 포지션은 로컬 파일(books/&lt;slug&gt;/positions.json)에 적으면 로컬 서버 화면에서 규칙별로 판정됩니다(공개 페이지에는 안 실림).</p>';
      }
    }
    else if(!(v.exit||[]).length && v.exit_policy === 'none'){
      // 매도 정책(엔진 필드 exit_policy — 정본 consumers/backtest/trades.exit_policy): 책에 매도 규칙이 없다 — 문구도 엔진(VD.no_exit_note)
      // (공통 매도 규칙만 있어 카드가 비는 경우는 제외 — 그 규칙들은 공통 섹션에서 보인다.)
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
      // 금액 = 총 투자금 × 엔진이 낸 오늘 물량(units — consumers/backtest/trades.to_units: 비중 × 분할 비율 × 조심 배수, 비중 모르면 null)
      const s = v.sizing, am = v.amount || {}, f = am.factor == null ? 1 : am.factor, unspec = am.unspecified || [];
      let w = s.weight, wtxt;
      if(!s.weight_set){ wtxt = '<span class="manual-tag">저자 미명시</span>'; w = null; }
      else if(w == null){ known = false; wtxt = '<span class="manual-tag">✋ 확인 필요 '+(s.weight_range||[]).map(x=>x.toFixed(0)+'%').join(' / ')+'</span>'; }
      else { sum += w; wtxt = w.toFixed(1)+'%'; }
      const amt = s.units == null ? null : cap * s.units;
      const trs = (s.tranches||[]).map(t=>esc(t.label)+(t.frac==null ? ' <span class="manual-tag">비율 저자 미명시</span>' : ' '+Math.round(t.frac*100)+'%'+(t.units!=null?' = '+Math.round(cap*t.units).toLocaleString('ko-KR')+'만':''))+(t.conditional?' <span class="subtle">(조건부)</span>':'')).join('<br>') || '한 번에 전량';
      h += '<tr><td style="color:var(--'+esc(v.prod.toLowerCase())+',var(--head))"><b>'+esc(v.prod)+'</b>'+refChip(s.ref)+'</td><td>'+wtxt+'</td><td>'
         + (amt!=null ? Math.round(amt).toLocaleString('ko-KR')+'만'+(f<1?' <span class="subtle">(조심 ×'+f.toFixed(2)+')</span>':'') : '—')
         + (unspec.length ? '<br><span class="manual-tag">줄일 폭 저자 미명시: '+esc(unspec.join(' · '))+'</span>' : '') + '</td><td>'+trs+'</td></tr>';
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
    let h = '';
    if(pending) h += '<div class="note">✋ 체크한 답으로 서버 판정을 다시 받는 중…</div>';
    if(serverNote) h += '<div class="note warn">'+esc(serverNote)+'</div>';
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
      +'#sheet-root .calcrow input{width:120px;margin-left:6px}'
      // 공통 시장 신호 섹션 — 규칙마다 상품별 결과 칩을 먼저, 그 아래 규칙 본체(수동 토글·증거).
      +'#sheet-root .ck-cm{margin:7px 0}'
      +'#sheet-root .ck-cm-chips{display:flex;justify-content:flex-end;margin:0 0 -4px}'
      +'#sheet-root .ck-pcs{display:inline-flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}'
      +'#sheet-root .ck-pc{display:inline-flex;align-items:center;gap:4px;font-size:11px;color:var(--mute);background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:2px 7px}'
      +'#sheet-root .ck-pcl{font-weight:700;color:var(--head)}'
      +'#sheet-root .ck-pc .ck-m{width:16px;height:16px;font-size:10px}'
      +'#sheet-root .ck-cm-prod{margin:4px 0 0}'
      +'#sheet-root .ck-cm-pl{font-size:11px;color:var(--mute);font-weight:700;margin:4px 0 2px;letter-spacing:.02em}';
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
