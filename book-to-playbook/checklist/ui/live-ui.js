/* ============================================================
   라이브 모드(점진적 향상) — 로컬 실시간 서버가 있으면 값이 살아 움직인다.

   · GitHub Pages(정적)로 열면 /api/verdict 가 없으니 fetch 가 실패한다
     → 아무 일도 일어나지 않고 구워진 스냅샷 그대로(에러/콘솔 스팸 없음).
   · 로컬 서버(python3 serve.py)로 열면 /api/verdict 가 응답한다
     → 15초마다 폴링(또는 /events SSE 수신)해 #verdict-data 를 갈아끼우고
       스코어카드·요약칩·진입판정·침체신호·신선도 라벨을 다시 그린다.
   ============================================================ */
(function(){
  'use strict';
  var POLL_MS = 15000;
  var VD_EL = document.getElementById('verdict-data');
  if(!VD_EL) return;

  function applyData(data){
    if(!data || data.error || !data.verdicts) return false;
    try {
      VD_EL.textContent = JSON.stringify(data);
    } catch(e){ return false; }
    // 각 패널을 새 값으로 다시 그린다.
    if(window.__applyVerdict) { try { window.__applyVerdict(); } catch(e){} }
    window.dispatchEvent(new CustomEvent('verdict:updated'));
    return true;
  }

  function fetchVerdict(){
    return fetch('/api/verdict', {cache:'no-store'})
      .then(function(r){ if(!r.ok) throw new Error('http '+r.status); return r.json(); });
  }

  // 1) 라이브 엔드포인트 탐지 — 실패하면 조용히 정적 스냅샷 유지.
  fetchVerdict().then(function(data){
    if(!(data && data.verdicts)) return;   // 응답은 왔지만 판정이 없으면 스냅샷 유지
    window.__liveMode = true;
    document.body.classList.add('live-mode');
    applyData(data);

    // 2) 갱신 구독: SSE 가 되면 tick 마다, 안 되면 폴링.
    var polling = null;
    function startPolling(){
      if(polling) return;
      polling = setInterval(function(){
        fetchVerdict().then(applyData).catch(function(){});
      }, POLL_MS);
    }
    var usingSSE = false;
    if('EventSource' in window){
      try {
        var es = new EventSource('/events');
        es.onmessage = function(){
          usingSSE = true;
          // tick 을 받으면 최신 판정을 한 번 당겨 다시 그린다.
          fetchVerdict().then(applyData).catch(function(){});
        };
        es.onerror = function(){
          // SSE 끊기면 폴링으로 폴백(서버가 살아 있는 한).
          if(!usingSSE){ try{ es.close(); }catch(e){} startPolling(); }
        };
        // SSE 가 5초 안에 한 번도 안 열리면 폴링 병행(안전망).
        setTimeout(function(){ if(!usingSSE) startPolling(); }, 5000);
      } catch(e){ startPolling(); }
    } else {
      startPolling();
    }
  }).catch(function(){
    // 정적 페이지(서버 없음) — 아무 것도 하지 않는다. 스냅샷 그대로.
  });
})();