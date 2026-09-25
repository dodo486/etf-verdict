(function(){
  /* ---- tab switching ---- */
  const tabs = document.querySelectorAll('.tab');
  tabs.forEach(t=>t.addEventListener('click',()=>{
    tabs.forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    document.querySelectorAll('.tabpanel').forEach(p=>p.classList.remove('active'));
    document.getElementById('panel-'+t.dataset.tab).classList.add('active');
    window.scrollTo(0,0);
  }));

  /* ---- STEP 2: scorecard ---- */
  const scBoxes = [...document.querySelectorAll('[data-sc]')];
  const scV = document.getElementById('scVerdict');
  const scMsg = document.getElementById('scMsg');
  function scUpdate(){
    const n = scBoxes.filter(b=>b.checked).length;
    scV.querySelector('.score').textContent = n+' / 5';
    scV.classList.remove('go','small','no');
    if(n>=4){scV.classList.add('go'); scMsg.textContent='공격 가능 — 진입 조건 충족 시 계획대로 매수';}
    else if(n===3){scV.classList.add('small'); scMsg.textContent='소액만 — 확인 매수 수준으로 축소';}
    else {scV.classList.add('no'); scMsg.textContent='관망 — 오늘은 신규 진입 보류';}
  }
  scBoxes.forEach(b=>b.addEventListener('change',scUpdate)); scUpdate();

  /* ---- STEP 3: entry checklist ---- */
  // VD 는 #verdict-data 를 다시 읽어 갱신 가능(라이브 모드에서 서버 폴링이 값을 갈아끼운다).
  function readVD(){ try { return JSON.parse(document.getElementById('verdict-data').textContent); } catch(e){ return null; } }
  let VD = readVD();
  const gradeCls = g => g.includes('매수 후보') ? 'go' : (g.includes('소액') ? 'small' : (g.includes('보류')||g.includes('금지') ? 'no' : ''));
  const RULES = JSON.parse(document.getElementById('rules').textContent);
  const DATA = RULES.DATA;
  // 지표 레지스트리 — 조건의 mtype 으로 🤖자동/🚧미구현/✋직접을 파생한다(게이트와 같은 기준, 주제 모름).
  const REG = (function(){ try { return JSON.parse(document.getElementById('metric-registry').textContent) || {}; } catch(e){ return {}; } })();
  const _AUTO = REG.auto_types || {}, _NODATA = REG.no_data_types || {};
  //   반환: 'auto'(값 표시) | 'todo'(🚧 데이터O·로직X) | 'manual'(✋ 데이터 없음)
  function clsOf(k, mtype){
    if(k) return 'auto';
    if(mtype && _AUTO[mtype]) return _AUTO[mtype].impl ? 'auto' : 'todo';
    if(mtype && _NODATA[mtype]) return 'manual';
    return 'manual';   // 미선언은 보수적으로 직접 취급(게이트가 별도로 미결선 잡음)
  }
  // 종목 키는 rules.json 에서 파생한다(책무관) — 특정 티커를 코드에 박지 않는다.
  const PRODS = Object.keys(DATA).filter(function(k){ return k !== 'COMMON'; });
  const card = document.getElementById('entryCard');
  let curP = PRODS[0];
  function vFor(p){ return (VD && VD.verdicts) ? VD.verdicts.find(x=>x.prod===p) : null; }
  let _chkRefSeen = {};   // 이 카드 렌더 동안 같은 ref 가 몇 번째인지 — 앵커 충돌 방지
  function renderEntry(p){
    const d = DATA[p], vv = vFor(p);
    _chkRefSeen = {};
    card.style.setProperty('--pc','var('+d.v+')');
    let h = '<div style="display:flex;justify-content:space-between;align-items:center"><h3><span class="tk">'+p+'</span> 진입 판정</h3>'
          + (vv?'<span class="verdict '+gradeCls(vv.grade)+'" style="margin:0;padding:4px 11px;font-size:13.5px">'+vv.grade+'</span>':'') + '</div>';
    if(vv && vv.close && vv.ma20){
      const side = vv.close>vv.ma20?'위':'아래';
      h += '<p class="subtle" style="margin:6px 0 2px">종가 <b style="color:var(--head)">'+vv.close.toFixed(2)+'</b> / 20일선 '+vv.ma20.toFixed(2)+' ('+side+') · 당일 '+(vv.chg>=0?'+':'')+vv.chg.toFixed(1)+'%</p>';
    }
    const ia = vv && vv.intraday_auto;  // 장중 자동판정
    const istate = (VD && VD.intraday_state) || 'pending';  // ok / pending / error
    if(vv){
      const liveNow = document.body.classList.contains('intraday-live');
      let stMsg;
      if(istate==='error') stMsg = ' <b style="color:var(--warn)">— ⚠ 장중 수집 실패'+(VD.intraday_error?': '+VD.intraday_error:'')+'</b>';
      else if(istate==='ok' && liveNow) stMsg = ' <b style="color:var(--entry)">— 지금 수집 중(깜빡임)</b>';
      else if(istate==='ok') stMsg = ' <span style="color:var(--mute)">— 방금 수집됨</span>';
      else stMsg = ' <span style="color:var(--mute)">— 개장+31분에 갱신(현재 대기)</span>';
      h += '<p class="subtle" style="margin:2px 0 10px">실시간 수집'+stMsg+'</p>';
    }
    const mt = (vv && vv.metrics) || {};
    h += '<div class="grouplabel f">① 필터 (통과 못하면 진입 금지)</div>';
    const ecf = (vv && vv.eod_checks) || {};
    d.filter.forEach((c,i)=>{
      if(c.ek){                                  // 항목별 자동 판정(예: 2거래일 유지)
        const e = ecf[c.ek];
        h+=chk('f'+i,{t:c.t, src:c.src, ref:c.ref, bkey:c.bkey, live:(e&&e.label)}, false, !!(e&&e.ok), 'eod', e?'ok':'pending');
      } else {
        h+=chk('f'+i,{t:c.t,src:c.src,ref:c.ref,bkey:c.bkey,live:mt.filter}, false, vv?!!vv.filter_ok:false, 'eod', vv?'ok':'pending');
      }
    });
    h += '<div class="grouplabel e">② 진입 조건 ('+d.need+'개 이상 충족)</div>';
    const ec = (vv && vv.eod_checks) || {};   // EOD로 자동 판정되는 진입 항목
    d.entry.forEach((c,i)=>{
      const ic = ia && c.ik && ia.checks && ia.checks[c.ik];  // 장중 자동판정 대상
      if(c.ek){                                 // 야후 EOD 자동(예: 섹터 폭)
        const e = ec[c.ek];
        h+=chk('e'+i,{t:c.t, src:c.src, ref:c.ref, bkey:c.bkey, live:(e&&e.label)}, false, !!(e&&e.ok), 'eod', e?'ok':'pending');
      } else if(c.ik){
        let st = istate;
        if(ic && ic.status==='error') st='error';
        else if(ic) st='ok';
        else if(istate!=='error') st='pending';
        // 수집된 값(live)이 있으면 출처 뒤에 붙임
        h+=chk('e'+i,{t:c.t, src:c.src, ref:c.ref, bkey:c.bkey, live:(ic&&ic.label)}, false, !!(ic&&ic.ok), 'intra', st);
      } else {
        h+=chk('e'+i,c,false, false, 'manual', (istate==='ok')?'ok':'pending');
      }
    });
    h+=chk('e_vol',{t:DATA.COMMON.entry[0].t, src:DATA.COMMON.entry[0].src, ref:DATA.COMMON.entry[0].ref, bkey:DATA.COMMON.entry[0].bkey, live:mt.vol}, false, vv?!!vv.vol_ok:false, 'eod', vv?'ok':'pending');
    h += '<div class="grouplabel x">③ 회피 신호 (하나라도 걸리면 보류)</div>';
    d.avoid.forEach((c,i)=>{
      if(c.groupNeed){
        // 카운트-그룹: 하위조건 각각의 live on/off 를 세어 임계(groupNeed) 이상이면 부모가 걸린다.
        //   렌더는 '주제'를 모른다 — groupExtra 는 verdict-data.extras 로 들어가는 불투명 키일 뿐이다.
        const g = groupState(c, vv);        // {states:[{on,auto,why}...], count}
        const trig = g.count >= c.groupNeed;
        const label = c.t + ' <b>'+g.count+'/'+(c.subs||[]).length+'</b>';
        h+=chk('x'+i,{t:label,src:c.src,ref:c.ref,bkey:c.bkey,autoLock:true},true, trig, '', vv?'ok':'pending');
        h += '<div class="subkids">';
        (c.subs || []).forEach((s,si)=>{ h += subLine(s, g.states[si]); });
        h += '</div>';
        return;
      }
      const ks=(c.k||'').split('|').filter(Boolean);
      const on = vv && ks.some(k=>(vv.avoid_keys||[]).includes(k));
      // 이 회피 항목의 대표 지표 수치(첫 키 기준)
      const mkey = ks[0];
      // 자식(subs) 각각의 실시간 값·걸림 상태를 여기서 계산해 넘긴다(렌더는 주제 모름).
      //   k 있으면 자동(그 지표 실제 값 mt[k] + avoid_keys 로 걸림판정), 없으면 수동(직접 확인).
      const subsView = (c.subs||[]).map(s=>{
        const sk=(s.k||'').split('|').filter(Boolean);
        const cls = clsOf(s.k, s.mtype);
        return {t:s.t, ref:s.ref, bkey:s.bkey, src:s.src, cls:cls, auto:cls==='auto',
                live: sk.length ? mt[sk[0]] : undefined,
                on: !!(vv && sk.some(k=>(vv.avoid_keys||[]).includes(k)))};
      });
      h+=chk('x'+i,{t:c.t,src:c.src,ref:c.ref,bkey:c.bkey,mtype:c.mtype,live:mkey?mt[mkey]:undefined,merged:subsView},true, !!on, (vv&&c.k)?'eod':'', vv?'ok':'pending');
    });
    if(d.caution){
      h += '<div class="grouplabel" style="color:var(--gold)">④ 호재·뉴스 되돌림 체크 <span class="tag a" style="text-transform:none">저자 2-7</span> — 3개 중 2개 불편하면 조심 신호</div>';
      d.caution.forEach((c,i)=>{
        h+=chk('c'+i,{t:c.t, src:c.src, ref:c.ref, bkey:c.bkey, live:c.k?mt[c.k]:undefined}, true, false, (vv&&c.k)?'eod':'', vv?'ok':'pending');
      });
      h += '<div class="note" id="cauNote" style="margin-top:8px"></div>';
    }
    h += '<div class="verdict" id="enV"><span id="enMsg">항목을 체크하세요</span></div>';
    h += '<p class="subtle" style="margin:10px 0 0">'+d.note+'</p>';
    if(d.exit){
      h += '<div class="grouplabel" style="color:var('+d.v+');margin-top:16px">🎯 매수 즉시 걸어둘 청산·손절 라인</div>';
      h += '<div class="tablewrap" style="margin:6px 0 0"><table><tbody>'
         + d.exit.map(e=>'<tr><td style="white-space:nowrap;color:var(--head)">'+e.L+'</td><td>'+e.v+'</td></tr>').join('')
         + '</tbody></table></div>';
      h += '<p class="subtle" style="margin:8px 0 0">전체 계좌 공통: -5% 신규중단 · -8% 노출 절반축소 · -12% 재설계</p>';
    }
    card.innerHTML = h;
    card.querySelectorAll('input').forEach(b=>b.addEventListener('change',()=>evalEntry(p)));
    // 줄(체크박스 제외)을 누르면 플레이북 원문의 그 bullet 로 점프. 체크 토글은 체크박스에서만.
    //   부모(.chk)·자식(.subchk) 모두 대상. 자식 클릭은 stopPropagation 으로 부모 점프를 막는다.
    card.querySelectorAll('.chk[data-ref], .subchk[data-ref]').forEach(row=>{
      row.addEventListener('click', ev=>{
        if(ev.target.closest('input')) return;   // 체크박스 클릭은 토글만(점프 안 함)
        ev.stopPropagation();
        if(window.__jumpToPlaybook) window.__jumpToPlaybook(row.getAttribute('data-ref'), row.getAttribute('data-bkey')||'');
      });
    });
    evalEntry(p);
  }
  function chk(id,c,warn,checked,bt,state){
    // bt: 'eod'|'intra'(자동수집) | 'manual'(사람 확인). 자동뱃지(🤖/⚡/✋)는 표시하지 않는다 —
    //   자동 여부는 잠김(disabled) 상태와 실제 값 노출로 드러난다.
    // 출처(src)는 작은 회색 글씨, 실제 값(live)은 데이터 pill 로 — 체크리스트 텍스트와 구분.
    let small = '';
    const srcTxt = c.src || c.s;
    if(srcTxt) small += '<span style="color:var(--mute)">'+srcTxt+'</span>';
    const hasKids = !!(c.merged && c.merged.length);
    const dataPill = (c.live && !hasKids) ? '<span class="dataval">'+c.live+'</span>' : '';
    // 비병합 항목: live 값이 없고 mtype 이 미구현/무데이터면 상태 태그(🚧/✋)로 알린다.
    let statusTag = '';
    if(!hasKids && !c.live && c.mtype){
      const cls = clsOf(null, c.mtype);
      if(cls==='todo') statusTag = ' <span class="todo-tag">🚧 자동 예정(미구현)</span>';
      else if(cls==='manual') statusTag = ' <span class="manual-tag">✋ 직접</span>';
    }
    // 소절 ref 로 안정적 앵커(chk-<ref>) + 역방향 점프용 data 속성(줄 클릭 → 그 bullet).
    let anchor = '', dataAttr = '';
    if(c.ref){
      const n = (_chkRefSeen[c.ref] = (_chkRefSeen[c.ref]||0) + 1);
      anchor = ' id="chk-' + c.ref + (n>1 ? '-'+n : '') + '"';
      dataAttr = ' data-ref="' + c.ref + '"' + (c.bkey ? ' data-bkey="' + String(c.bkey).replace(/"/g,'&quot;') + '"' : '');
    }
    // 자동수집(EOD·장중) 항목은 사람이 체크를 못 바꾼다 — 오직 자동만 제어(disabled). 수동만 토글.
    const autoLock = c.autoLock || bt==='eod' || bt==='intra';
    // 의미단위 병합(동의어) 하위 조건 — 부모와 같은 사각형 체크박스(크기만 작게)로 편다.
    //   각 자식: 작은 체크박스(자동=걸림상태 잠김 / 수동=토글) + 조건 텍스트 + 데이터값 pill(구분).
    //   chk-<sub.ref> 앵커·data-ref 로 그 소절 bullet 로 역방향 점프까지 도달.
    let merged = '';
    if(hasKids){
      merged = '<div class="subkids">'
        + c.merged.map(function(s){
            let a='';
            if(s.ref){ const n=(_chkRefSeen[s.ref]=(_chkRefSeen[s.ref]||0)+1); a=' id="chk-'+s.ref+(n>1?'-'+n:'')+'"'; }
            const dref = s.ref ? ' data-ref="'+s.ref+'"'+(s.bkey?' data-bkey="'+String(s.bkey).replace(/"/g,'&quot;')+'"':'') : '';
            const dis = s.auto ? ' disabled' : '';
            const chkd = s.on ? ' checked' : '';
            const wc = s.on ? ' class="warn"' : '';
            let dataEl;
            if(s.cls==='auto') dataEl = s.live ? '<span class="dataval">'+s.live+'</span>' : '<span class="manual-tag">수집 대기</span>';
            else if(s.cls==='todo') dataEl = '<span class="todo-tag">🚧 자동 예정(미구현)</span>';
            else dataEl = '<span class="manual-tag">✋ 직접</span>';
            return '<div class="subchk'+(s.on?' on':'')+'"'+a+dref+'><input type="checkbox"'+wc+chkd+dis+'><span class="stext">'+s.t+'</span>'+dataEl+'</div>';
          }).join('')
        + '</div>';
    }
    // <div>(라벨 아님) — 줄 텍스트 클릭은 플레이북 점프, 체크 토글은 체크박스에서만.
    return '<div class="chk'+(autoLock?' autolock':'')+'"'+anchor+dataAttr+' style="cursor:pointer">'
      +'<input type="checkbox" data-k="'+id+'"'+(warn?' class="warn"':'')+(checked?' checked':'')+(autoLock?' disabled':'')
      +'><span class="txt">'+c.t+statusTag+(small?'<small>'+small+'</small>':'')+dataPill+merged+'</span></div>';
  }
  // 카운트-그룹 라이브 판정 — 규칙(groupExtra/groupNeed)만 보고 계산한다. 특정 주제를 모른다.
  //   ① VD.extras[rule.groupExtra] 가 있으면 그 signals[] 를 하위조건과 (sub.sk 키 → 없으면 순서)로 맞춰 on 을 읽는다.
  //   ② 없으면 sub.k 를 vv.avoid_keys 로 판정(EOD 폴백). ③ 그것도 없으면 라이브 없음(정적 표시).
  function groupState(rule, vv){
    const ex = (VD && VD.extras && VD.extras[rule.groupExtra]) || null;
    const sigs = (ex && ex.signals) || null;
    const subs = rule.subs || [];
    const states = subs.map((s,si)=>{
      let sig = null;
      if(sigs){
        sig = (s.sk ? sigs.find(x=>x.key===s.sk) : null) || sigs[si] || null;
      }
      if(sig) return {live:true, on:!!sig.on, auto:!!sig.auto, why:sig.why||''};
      // 라이브 신호 없음 → EOD 키 폴백(가능하면), 아니면 정적
      const on = !!(s.k && vv && (vv.avoid_keys||[]).includes(s.k));
      return {live: !!s.k, on:on, auto:!!s.k, why:''};
    });
    const count = states.filter(x=>x.on).length;
    return {states:states, count:count};
  }
  // 동의어 병합 항목의 하위 저자 조건 — 표시 전용(체크박스 없음), 점프 도달용 chk-<ref> 앵커만 심는다.
  //   렌더는 '주제'를 모른다. subs 유무만 보고 하위줄로 펼친다(책무관).
  //   st(선택): 카운트-그룹 하위줄의 라이브 판정 {on,auto,why} — 있으면 ⚠/· 아이콘·걸림 뱃지·why 를 표시한다.
  function subLine(s, st){
    let anchor = '', dref = '';
    if(s.ref){
      const n = (_chkRefSeen[s.ref] = (_chkRefSeen[s.ref]||0) + 1);
      anchor = ' id="chk-' + s.ref + (n>1 ? '-'+n : '') + '"';
      dref = ' data-ref="'+s.ref+'"' + (s.bkey ? ' data-bkey="'+String(s.bkey).replace(/"/g,'&quot;')+'"' : '');
    }
    // 자식 체크리스트 한 줄 — 부모와 같은 사각형(작게). 자동=걸림상태 잠김, 수동=토글. 값은 데이터 pill.
    const on = !!(st && st.on);
    const auto = st ? st.auto : !!s.k;
    const dis = auto ? ' disabled' : '';
    const chkd = on ? ' checked' : '';
    const wc = on ? ' class="warn"' : '';
    let dataEl;
    if(st && st.why) dataEl = '<span class="dataval">'+st.why+'</span>';
    else if(!auto) dataEl = '<span class="manual-tag">✋ 직접</span>';
    else dataEl = '<span class="manual-tag">수집 대기</span>';
    return '<div class="subchk'+(on?' on':'')+'"'+anchor+dref+'><input type="checkbox"'+wc+chkd+dis+'><span class="stext">'+s.t+'</span>'+dataEl+'</div>';
  }
  function evalEntry(p){
    const d = DATA[p];
    const get = pre => [...card.querySelectorAll('[data-k^="'+pre+'"]')];
    const fOk = get('f').every(b=>b.checked);
    const eN = get('e').filter(b=>b.checked).length;
    const xN = get('x').filter(b=>b.checked).length;
    // ④ 호재 되돌림(저자 2-7): 3개 중 2개 이상 불편하면 조심 신호 — 진입을 막지는 않고 경고
    const cN = get('c').filter(b=>b.checked).length;
    const cau = document.getElementById('cauNote');
    if(cau){
      if(cN >= 2){
        cau.className = 'note bad';
        cau.innerHTML = '⚠ <b>조심 신호 '+cN+'/3</b> — 저자 2-7: "좋은 뉴스보다 나쁜 가격이 더 세다". 이 자리의 호재는 <b>매물을 부르는 자리</b>입니다. 진입을 미루거나 금액을 줄이세요.';
      } else if(cN === 1){
        cau.className = 'note warn';
        cau.innerHTML = '1/3 불편 — 아직 조심 신호는 아닙니다. 나머지 둘이 같이 걸리는지만 보세요.';
      } else {
        cau.className = 'note';
        cau.innerHTML = '가격 먼저, 뉴스 나중. 셋 다 괜찮으면 뉴스는 그대로 읽어도 됩니다.';
      }
    }
    const v = document.getElementById('enV'), m = document.getElementById('enMsg');
    v.classList.remove('go','small','no');
    if(!fOk){ v.classList.add('no'); m.innerHTML='🚫 진입 금지<span class="sub">필터(20일선 등) 미충족 — 추세가 살아있지 않음</span>'; return; }
    if(xN>0){ v.classList.add('no'); m.innerHTML='⛔ 보류<span class="sub">회피 신호 '+xN+'개 — 과열/추격 위험, 눌림 기다리기</span>'; return; }
    if(eN>=d.need){
      v.classList.add('go');
      const extra = (cN>=2) ? ' · <b>호재 되돌림 '+cN+'/3 → 금액 축소해서 시작</b>' : '';
      m.innerHTML='✅ 매수 후보<span class="sub">필터 통과 · 진입 '+eN+'/'+get('e').length+' · 회피 0 → 1차 분할 진입, 청산라인 동시 설정'+extra+'</span>';
    }
    else { v.classList.add('small'); m.innerHTML='🟡 장중 확인 대기<span class="sub">필터·회피 통과 — 진입 조건 '+eN+'/'+d.need+' (장중 '+(d.need-eN)+'개 더 충족 시 진입)</span>'; }
  }
  renderEntry(curP);

  /* ---- STEP 5: position calculator ---- */
  // 저자 5,000만 예시 → 비율(%)
  const MODES = RULES.MODES;
  let curMode='공격';
  const cap = document.getElementById('capital');
  const calcBody = document.querySelector('#calcTable tbody');
  const cashLine = document.getElementById('cashLine');
  const fmt = n => Math.round(n).toLocaleString('ko-KR');
  function calc(){
    const T = Math.max(0, +cap.value||0);
    const m = MODES[curMode];
    let rows='';
    PRODS.forEach(k=>{
      const amt = T*m[k]/100;
      rows += '<tr><td style="color:var(--'+k.toLowerCase()+')">'+k+' ('+m[k]+'%)</td><td>'+fmt(amt)+'만</td>'
            + '<td>'+fmt(amt*0.25)+'만</td><td>'+fmt(amt*0.30)+'만</td><td>'+fmt(amt*0.45)+'만</td></tr>';
    });
    calcBody.innerHTML = rows;
    cashLine.innerHTML = '현금 보유 <b style="color:var(--gold)">'+fmt(T*m.cash/100)+'만 ('+m.cash+'%)</b> · '
      + '각 종목은 1차 25% → 2차 30% → 3차 45% 분할 진입 (기준 깨지면 다음 차수 중단)';
    // 저자 7-3: 갭상승 추격 구간은 평소 3,000만 자리를 1,000만 이하로 = 1/3
    const gl = document.getElementById('gapLine');
    if(gl){
      const thirds = PRODS.map(k=>k+' '+fmt(T*m[k]/100*0.25/3)+'만').join(' · ');
      gl.innerHTML = '📉 <b>갭상승 추격 구간이면 1차 금액을 1/3로</b> (저자 7-3: 평소 3,000만 자리 → 1,000만 이하) — '
        + thirds + ' <span style="color:var(--mute)">(갭 %는 STEP2 회피 항목에 오늘 수치가 표시됩니다)</span>';
    }
  }
  cap.addEventListener('input',calc);
  document.querySelectorAll('#modes button').forEach(b=>b.addEventListener('click',()=>{
    document.querySelectorAll('#modes button').forEach(x=>x.classList.remove('on'));
    b.classList.add('on'); curMode=b.dataset.m; calc();
  }));
  calc();

  /* ---- STEP 6: memo ---- */
  const memoInputs = [...document.querySelectorAll('#memo [data-req]')];
  const memoWarn = document.getElementById('memoWarn');
  const memoV = document.getElementById('memoVerdict');
  const memoMsg = document.getElementById('memoMsg');
  function memoUpdate(){
    const filled = memoInputs.filter(i=>i.value.trim()).length;
    const critical = memoInputs[2].value.trim() && memoInputs[3].value.trim(); // 줄일자리·판단기간
    memoV.classList.remove('go','small','no');
    if(filled===5){ memoWarn.classList.remove('show'); memoV.classList.add('go'); memoMsg.textContent='✓ 준비 완료 — 계획대로 매수 진행'; }
    else if(!critical){ memoWarn.classList.add('show'); memoV.classList.add('no'); memoMsg.textContent='매수 보류 ('+filled+'/5) — 줄일 자리·판단 기간 필수'; }
    else { memoWarn.classList.remove('show'); memoV.classList.add('small'); memoMsg.textContent='거의 됨 ('+filled+'/5) — 나머지 칸 채우기'; }
  }
  memoInputs.forEach(i=>i.addEventListener('input',memoUpdate)); memoUpdate();

  /* ---- 오늘 자동판정: STEP2 스코어카드 프리필 + STEP3 요약 스트립/시각 ----
     applyVerdict() 로 감싸 라이브 갱신 때 다시 부를 수 있게 한다. */
  function applyVerdict(){
   VD = readVD();   // 라이브 폴링이 #verdict-data 를 갈아끼웠으면 새 값으로
   try {
    if(VD){
      const pad = n => String(n).padStart(2,'0');
      const d = new Date(VD.ts);
      const tsEl = document.getElementById('td-ts');
      if(tsEl) tsEl.innerHTML = `<b>${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}</b> 기준(최신 세션 종가) · 필터·회피 자동, 진입 조건만 장중 직접 확인`;
      // 장중 데이터 신선도 → 장중 뱃지 라이브 여부 결정 (body에 클래스)
      (function(){
        const its = VD.intraday_ts ? new Date(VD.intraday_ts) : null;
        const live = its && ((Date.now()-its.getTime())/60000 <= 20);
        document.body.classList.toggle('intraday-live', !!live);
        window.__intradayTs = its;  // 툴팁용
      })();
      // STEP 2 스코어카드 오늘 값으로 프리필
      // 스코어카드: 체크 프리필 + 항목마다 실제 근거 수치 표기(STEP2와 같은 형식)
      const SCSRC = RULES.SCSRC;
      const whyEls = [...document.querySelectorAll('#scorecard .scwhy')];
      (VD.scorecard||[]).forEach((s,i)=>{
        if(scBoxes[i]) scBoxes[i].checked = !!s.ok;
        if(whyEls[i]){
          const bad = !s.why || s.why.indexOf('수집 실패') === 0;
          whyEls[i].innerHTML = '<span style="color:var(--mute)">'+(SCSRC[i]||'')+'</span> → '
            + '<b style="color:var(' + (bad ? '--warn' : '--text') + ')">' + (s.why || '값 없음') + '</b>';
        }
      });
      scUpdate();
      // STEP 3: 3종목 요약 칩 = 종목 선택 UI (클릭 시 해당 종목 상세 판정)
      const pcol = {}; PRODS.forEach(function(k){ pcol[k] = DATA[k].v; });   // 종목→CSS색 변수, rules.json 에서 파생
      const sumEl = document.getElementById('td-summary');
      if(sumEl) sumEl.innerHTML = '<div id="td-chips" style="display:grid;grid-template-columns:repeat('+VD.verdicts.length+',1fr);gap:10px;margin:2px 0 14px">'
        + VD.verdicts.map(v=>`<button class="td-chip" data-jump="${v.prod}" style="text-align:left;cursor:pointer;background:var(--surface);border:1px solid var(--line);border-top:3px solid var(${pcol[v.prod]});border-radius:10px;padding:11px 13px;transition:background .15s">
             <div style="font-weight:800;font-size:15px;color:var(${pcol[v.prod]})">${v.color} ${v.prod}</div>
             <div class="verdict ${gradeCls(v.grade)}" style="margin:6px 0 0;padding:3px 9px;font-size:12.5px;display:inline-block">${v.grade}</div>
           </button>`).join('') + '</div>';
      const setActive = p => document.querySelectorAll('.td-chip').forEach(c=>{
        c.style.background = c.dataset.jump===p ? 'var(--surface-2)' : 'var(--surface)';
        c.style.boxShadow = c.dataset.jump===p ? 'inset 0 0 0 1px var('+pcol[p]+')' : 'none';
      });
      document.querySelectorAll('.td-chip').forEach(el=>el.addEventListener('click',()=>{
        const p = el.dataset.jump;
        setActive(p); curP=p; renderEntry(p);
      }));
      setActive(curP);
      renderEntry(curP);   // 현재 선택된 종목 상세 판정도 새 값으로 다시 그림
    }
   } catch(e){
    var el=document.getElementById('td-ts'); if(el) el.textContent='판정 데이터를 불러오지 못했습니다: '+e.message;
   }
  }
  applyVerdict();
  // 라이브 모듈이 새 판정을 받으면 이 훅으로 스코어카드·요약칩·진입판정을 다시 그린다.
  window.__applyVerdict = applyVerdict;
})();