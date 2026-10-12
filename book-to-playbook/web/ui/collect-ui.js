/* ============================================================
   데이터 수집 현황 — 소스(jhts 시세팀) + 갱신 모드(실시간 폴링 / 정적 스냅샷)
   ============================================================ */
(function(){
  'use strict';
  var box = document.getElementById('collect');
  if(!box) return;
  var VD = null;
  function reloadVD(){ try { VD = JSON.parse(document.getElementById('verdict-data').textContent); } catch(e){ VD = null; } }
  reloadVD();

  var elWhen = document.getElementById('cWhen'),
      elAgo  = document.getElementById('cAgo'),
      elEod  = document.getElementById('cEod'),
      elIntra= document.getElementById('cIntra');

  function pad(n){ return String(n).padStart(2,'0'); }
  function stamp(d){
    var today = new Date();
    var sameDay = d.getFullYear()===today.getFullYear() && d.getMonth()===today.getMonth() && d.getDate()===today.getDate();
    var hm = pad(d.getHours())+':'+pad(d.getMinutes());
    return sameDay ? ('오늘 '+hm) : (d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+' '+hm);
  }
  function ago(d){
    var s = Math.max(0, (Date.now()-d.getTime())/1000);
    if(s < 60)    return '방금';
    if(s < 3600)  return Math.floor(s/60)+'분 전';
    if(s < 86400) return Math.floor(s/3600)+'시간 전';
    return Math.floor(s/86400)+'일 전';
  }

  function hms(d){ return pad(d.getHours())+':'+pad(d.getMinutes())+':'+pad(d.getSeconds()); }
  function render(){
    if(!VD){
      box.className = 'collect old';
      elWhen.textContent = '불러오지 못함';
      elEod.textContent = ''; elIntra.textContent = '';
      return;
    }
    var eod = VD.ts ? new Date(VD.ts) : null;
    // 라이브 모드 = 로컬 실시간 서버가 /api/verdict 를 제공(유일한 보기 경로, 정직한 소스/신선도 표기).
    // 서버 없이 열면 라이브 아님 — 오래된 값을 '지금 값'처럼 보여주지 않는다(정적 스냅샷 모드 폐지).
    var live = !!(window.__liveMode || VD.live);
    var src  = VD.source || 'jhts 시세팀';

    // --- 소스 1: 종가·지표(수집 단계 = 조건 트리가 쓰는 심볼 전부) ---
    elEod.innerHTML = eod
      ? '<span>🤖 종가·지표('+src+')</span> <b>'+stamp(eod)+'</b> <span class="cst ok">수집됨</span>'
      : '<span>🤖 종가·지표('+src+')</span> <span class="cst err">없음</span>';

    // --- 소스 2: 갱신 모드(라이브 폴링 / 서버 없음) ---
    var iHtml;
    if(live){
      iHtml = '<span>🟢 실시간 · '+src+'</span> '
            + (eod ? '<b>갱신 '+hms(eod)+'</b> ' : '')
            + '<span class="cst ok">폴링 중</span>';
    } else {
      iHtml = '<span>⚠ 서버 연결 안 됨</span> '
            + '<span class="cst err">값 없음 — 라이브 서버로 열어야 지금 값을 봅니다</span>';
    }
    elIntra.innerHTML = iHtml;

    // --- 전체: EOD 기준 시각 ---
    var last = eod;
    if(!live){
      box.className = 'collect old';
      elWhen.textContent = '라이브 아님'; elAgo.textContent = '(서버 연결 필요)';
      return;
    }
    if(!last){
      box.className = 'collect old';
      elWhen.textContent = '없음'; elAgo.textContent = '';
      return;
    }
    // 라이브 모드는 방금 받은 값이므로 항상 fresh.
    elWhen.textContent = '실시간 · 갱신 '+hms(last);
    elAgo.textContent = '(' + ago(last) + ')';
    box.className = 'collect fresh';
  }

  // 탭 바가 sticky(top:0)라 그 높이만큼 내려 붙어야 가려지지 않는다.
  function fitTop(){
    var bar = document.querySelector('.tabbar');
    box.style.top = (bar ? bar.offsetHeight : 0) + 'px';
  }
  fitTop();
  window.addEventListener('resize', fitTop);

  render();
  setInterval(render, 30000);   // 열어둔 채로도 상대시간이 굳지 않도록
  // 라이브 폴링이 새 판정을 받으면 소스를 다시 읽어 신선도 라벨을 갱신한다.
  window.addEventListener('verdict:updated', function(){ reloadVD(); render(); });
})();