(function(){
  'use strict';
  /* ============================================================
     판정 틀 탭 — 시세 없이 판때기(컴파일된 조건 트리)만 보인다.
     /api/board?slug=... 을 탭 첫 클릭 시 한 번만 가져온다.
     tree.json 이 바뀌지 않는 한 내용은 불변 — 새로고침 없이 그대로.
     ============================================================ */

  const esc = window.BP && window.BP.esc
    ? window.BP.esc
    : s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  /* ---- 탭·패널 삽입 ---- */
  function setup() {
    const tabbar = document.querySelector('.tabbar');
    if (!tabbar || document.getElementById('panel-board')) return;

    const btn = document.createElement('button');
    btn.className = 'tab';
    btn.dataset.tab = 'board';
    btn.textContent = '🧩 판정 틀';
    tabbar.appendChild(btn);

    const panel = document.createElement('div');
    panel.className = 'tabpanel';
    panel.id = 'panel-board';
    const lastPanel = document.querySelector('.tabpanel:last-of-type');
    if (lastPanel) lastPanel.after(panel);
    else document.body.appendChild(panel);

    /* checklist-ui 의 탭 전환이 이미 돌고 있으니 board 탭도 같은 방식으로 수동 연결 */
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      btn.classList.add('active');
      document.querySelectorAll('.tabpanel').forEach(p => p.classList.remove('active'));
      panel.classList.add('active');
      window.scrollTo(0, 0);
      loadOnce();
    });
  }

  /* ---- 데이터 로드 (탭 첫 클릭 시 한 번) ---- */
  let loaded = false;
  let _vd = null;
  function _verdictData() {
    if (!_vd) try { _vd = JSON.parse(document.getElementById('verdict-data').textContent) || {}; } catch(e) { _vd = {}; }
    return _vd;
  }
  function slug() { return _verdictData().slug || ''; }
  /* verbs 배열 — 정본 tree.gateway.VERBS(서버가 판정 JSON 에 실어 준다).
     VB[0]=안 산다(BLOCK_V), VB[1]=산다(BUY_V). */
  function _verbs() { return _verdictData().verbs || []; }

  function loadOnce() {
    if (loaded) return;
    loaded = true;
    const panel = document.getElementById('panel-board');
    panel.innerHTML = '<div style="padding:32px;color:var(--mute)">판정 틀 불러오는 중…</div>';
    fetch('/api/board?slug=' + encodeURIComponent(slug()))
      .then(r => r.json())
      .then(d => render(d))
      .catch(e => { panel.innerHTML = '<div style="padding:32px;color:var(--mute)">불러오기 실패: ' + esc(e) + '</div>'; });
  }

  /* ---- 렌더링 ---- */
  function render(data) {
    const panel = document.getElementById('panel-board');
    if (!data || !data.products || !Object.keys(data.products).length) {
      panel.innerHTML = '<div style="padding:32px;color:var(--mute)">판정 틀 없음</div>';
      return;
    }
    let h = '<div class="bd-wrap">';
    h += '<h2 class="bd-head">판정 틀 <span class="bd-sub">시세 없이 읽는 전략 구조 — 컴파일 완료, 시세만 채우면 산다/안 산다</span></h2>';
    for (const [prod, info] of Object.entries(data.products)) {
      h += renderProduct(prod, info);
    }
    if (data.grade_rules) {
      h += renderGradeRules(data.grade_rules, data.grades || {});
    }
    h += '</div>';
    panel.innerHTML = h;
  }

  function renderGradeRules(gr, grades) {
    const rules = gr.rules || [];
    const def = gr.default || 'unknown';
    const vb = _verbs(), BLOCK_V = vb[0] || '', BUY_V = vb[1] || '';
    let h = '<div class="bd-gr">';
    h += '<h3 class="bd-gr-head">등급 판정 사다리 <span class="bd-sub">게이트 평가 결과 → 최종 등급 (위에서 아래로, 첫 매칭 규칙이 이김)</span></h3>';
    h += '<table class="bd-gr-tbl"><thead><tr>'
       + '<th>#</th><th>가정</th><th>' + esc(BLOCK_V) + '</th><th>' + esc(BUY_V) + '</th><th>→ 등급</th><th>의미</th>'
       + '</tr></thead><tbody>';
    const VIEW_KO = { pes: '비관 (수동=불리)', opt: '낙관 (수동=유리)' };
    const GRADE_EXP = {
      buy:     '비관에서도 매수 — 수동 조건 관계없이 확실한 매수',
      confirm: '낙관에서만 매수 — ✋ 수동 조건 직접 확인 필요',
      avoid:   '낙관에서도 회피 — 확실한 비매수',
      wait:    '어느 신호도 없음 — 관망',
      unknown: '데이터 불충분 — 판정 보류',
    };
    rules.forEach((r, i) => {
      const when = r.when || {};
      const sell = when[BLOCK_V];
      const buy  = when[BUY_V];
      const sellStr = sell === true ? '참' : sell === false ? '거짓' : '무관';
      const buyStr  = buy  === true ? '참' : buy  === false ? '거짓' : '무관';
      const gradeLabel = (grades[r.key] || r.key);
      const exp = GRADE_EXP[r.key] || r.key;
      const viewKo = VIEW_KO[r.view] || r.view;
      h += '<tr class="bd-gr-row bd-gr-' + esc(r.key) + '">'
         + '<td class="bd-gr-idx">' + (i+1) + '</td>'
         + '<td class="bd-gr-view">' + esc(viewKo) + '</td>'
         + '<td class="bd-gr-bool ' + (sell===true?'bad':sell===false?'ok':'') + '">' + sellStr + '</td>'
         + '<td class="bd-gr-bool ' + (buy===true?'ok':buy===false?'bad':'') + '">'  + buyStr  + '</td>'
         + '<td class="bd-gr-grade">' + esc(gradeLabel) + '</td>'
         + '<td class="bd-gr-exp">' + esc(exp) + '</td>'
         + '</tr>';
    });
    /* default */
    h += '<tr class="bd-gr-row bd-gr-unknown">'
       + '<td class="bd-gr-idx">—</td><td class="bd-gr-view">—</td>'
       + '<td colspan="2" class="bd-gr-bool" style="text-align:center">위 규칙 불일치</td>'
       + '<td class="bd-gr-grade">' + esc(grades[def] || def) + '</td>'
       + '<td class="bd-gr-exp">' + esc(GRADE_EXP[def] || def) + '</td>'
       + '</tr>';
    h += '</tbody></table>';
    h += '<p class="bd-gr-note">3값 논리: 수동(✋) 조건이 미응답이면 <b>모름(None)</b> — 참·거짓 어디에도 매칭되지 않아 해당 규칙을 건너뜀.</p>';
    h += '</div>';
    return h;
  }

  function renderProduct(prod, info) {
    let h = '<div class="bd-prod">';
    h += '<div class="bd-prod-head">';
    h += '<span class="bd-ticker">' + esc(prod) + '</span>';
    if (info.index) h += '<span class="bd-index">지수: ' + esc(info.index) + '</span>';
    h += '</div>';

    /* 필요 심볼 */
    h += '<div class="bd-section"><div class="bd-sec-title">필요 심볼 <span class="bd-warmup">워밍업 ' + (info.warmup || '?') + '거래일</span></div>';
    h += '<div class="bd-chips">';
    for (const sym of (info.symbols || [])) {
      h += '<span class="bd-chip">' + esc(sym) + '</span>';
    }
    h += '</div></div>';

    /* 게이트 트리 */
    if (info.gates) {
      const vb = _verbs(), BUY_V = vb[1] || '';
      for (const [verb, gate] of Object.entries(info.gates)) {
        const polClass = verb === BUY_V ? 'good' : 'bad';
        h += '<div class="bd-section">';
        h += '<div class="bd-sec-title bd-gate-title ' + polClass + '">' + esc(verb) + ' 게이트</div>';
        h += '<div class="bd-tree">' + renderNode(gate, 0) + '</div>';
        h += '</div>';
      }
    }
    h += '</div>';
    return h;
  }

  const OP_LABEL = { any: 'OR', all: 'AND', atleast: 'atleast', not: 'NOT' };

  function renderNode(node, depth) {
    if (!node || typeof node !== 'object') return '';
    const op = node.op;
    const label = node.label || '';
    const expr = node.expr || '';
    const kids = node.kids || [];
    const indent = depth * 18;

    let h = '<div class="bd-node" style="margin-left:' + indent + 'px">';

    /* 라벨 or 식 */
    if (label) {
      h += '<span class="bd-node-label">' + esc(label) + '</span>';
      if (node.ref) h += '<span class="bd-ref"> §' + esc(node.ref) + '</span>';
    }

    if (op) {
      const opStr = node.n !== undefined
        ? 'atleast ' + node.n + '개'
        : OP_LABEL[op] || op;
      h += '<span class="bd-op">' + esc(opStr) + '</span>';
    } else if (expr && !label) {
      h += '<span class="bd-expr">' + esc(expr) + '</span>';
    }

    /* 조건 식(라벨 있어도 펼쳐 보임) */
    if (expr && label) {
      h += '<div class="bd-expr-detail">' + esc(expr) + '</div>';
    }

    /* 수동 항목 */
    if (node.manual) {
      h += '<span class="bd-manual">✋ 수동 확인</span>';
    }

    /* 다른 상품 전용이면 표시 */
    if (node.off) {
      h += '<span class="bd-off">이 상품 비해당(항상 참)</span>';
    }

    h += '</div>';

    /* 자식 */
    for (const kid of kids) {
      h += renderNode(kid, depth + 1);
    }

    return h;
  }

  /* ---- CSS ---- */
  const CSS = `
#panel-board{padding:0 clamp(16px,3vw,24px) 60px}
.bd-wrap{max-width:860px;margin:0 auto}
.bd-head{font-size:20px;font-weight:800;color:var(--head);margin:28px 0 6px;padding:0}
.bd-sub{font-size:13px;font-weight:400;color:var(--mute);margin-left:10px}
.bd-prod{background:var(--surface);border:1px solid var(--line);border-radius:12px;margin:18px 0;padding:18px 20px}
.bd-prod-head{display:flex;align-items:baseline;gap:12px;margin-bottom:14px}
.bd-ticker{font-size:18px;font-weight:800;color:var(--head)}
.bd-index{font-size:13px;color:var(--mute)}
.bd-section{margin-bottom:16px}
.bd-sec-title{font-size:13px;font-weight:700;color:var(--mute);margin-bottom:8px;text-transform:uppercase;letter-spacing:.04em}
.bd-gate-title{font-size:14px;font-weight:700;margin-bottom:8px}
.bd-gate-title.good{color:#3ecf8e}
.bd-gate-title.bad{color:#f26b6b}
.bd-warmup{font-size:12px;font-weight:400;color:var(--mute);margin-left:8px;text-transform:none;letter-spacing:0}
.bd-chips{display:flex;flex-wrap:wrap;gap:6px}
.bd-chip{background:var(--ground);border:1px solid var(--line);border-radius:20px;padding:3px 10px;font-size:12.5px;font-weight:600;color:var(--head);font-variant-numeric:tabular-nums}
.bd-tree{border-left:2px solid var(--line);padding-left:4px;margin-left:4px}
.bd-node{padding:3px 0;font-size:13px;line-height:1.5}
.bd-node-label{font-weight:700;color:var(--head);margin-right:6px}
.bd-ref{font-size:11.5px;color:var(--mute);margin-right:6px}
.bd-op{background:var(--ground);border:1px solid var(--line);border-radius:4px;padding:1px 6px;font-size:11px;font-weight:700;color:var(--gold);margin-right:6px;font-variant-numeric:tabular-nums}
.bd-expr{color:var(--text);font-size:12.5px}
.bd-expr-detail{color:var(--mute);font-size:11.5px;margin-top:1px;margin-left:2px}
.bd-manual{background:#fff3cd;color:#856404;border-radius:4px;padding:1px 7px;font-size:11px;font-weight:700}
.bd-off{color:var(--mute);font-size:11px;font-style:italic}
.bd-gr{margin-top:32px;padding:20px;background:var(--surface);border:1px solid var(--line);border-radius:12px}
.bd-gr-head{font-size:16px;font-weight:800;color:var(--head);margin:0 0 14px}
.bd-gr-tbl{width:100%;border-collapse:collapse;font-size:13px}
.bd-gr-tbl th{text-align:left;padding:7px 10px;border-bottom:2px solid var(--line);color:var(--mute);font-size:11.5px;font-weight:700;text-transform:uppercase}
.bd-gr-tbl td{padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
.bd-gr-idx{color:var(--mute);font-size:11px;width:28px}
.bd-gr-view{font-size:12px;color:var(--mute);white-space:nowrap}
.bd-gr-bool{font-weight:700;font-size:13px;text-align:center;width:60px}
.bd-gr-bool.ok{color:#3ecf8e}
.bd-gr-bool.bad{color:#f26b6b}
.bd-gr-grade{font-weight:700;white-space:nowrap}
.bd-gr-exp{color:var(--mute);font-size:12.5px}
.bd-gr-buy .bd-gr-grade{color:#3ecf8e}
.bd-gr-confirm .bd-gr-grade{color:var(--gold)}
.bd-gr-avoid .bd-gr-grade{color:#f26b6b}
.bd-gr-wait .bd-gr-grade{color:var(--mute)}
.bd-gr-unknown .bd-gr-grade{color:var(--mute)}
.bd-gr-note{font-size:12px;color:var(--mute);margin:10px 0 0;padding:8px 10px;background:var(--ground);border-radius:6px}
`;

  const style = document.createElement('style');
  style.id = 'board-ui-css';
  style.textContent = CSS;
  document.head.appendChild(style);

  setup();

})();
