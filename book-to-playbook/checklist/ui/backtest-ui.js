/* 백테스트 탭 — 책 무관. #backtest-data(verdict.backtest --page 산출물)가 있으면 탭·패널을 만들어 그린다.
 *
 * 이 스크립트는 checklist-ui 보다 **먼저** 실행된다(publish_pages 가 그 앞에 주입) — checklist-ui 가
 * 페이지 로드 때 .tab 목록을 한 번 묶으므로, 그 전에 버튼·패널을 만들어 두면 기존 탭 전환에 그대로 묶인다.
 * 순서가 어긋나도 깨지지 않게 자기 클릭 처리도 따로 둔다.
 *
 * 보이는 것: 1년/3년 전환 · 상품별 거래 성적(책 매도 규칙 vs 같은 진입 20일 보유 vs 아무 날) ·
 * 등급별 일수·신호·5/10/20일 수익률 · 거래 목록(무엇을 언제 얼마 팔았나) · 수동 조건과 가정.
 */
(function () {
  var src = document.getElementById('backtest-data');
  var bar = document.querySelector('.tabbar');
  if (!src || !bar) return;
  var D;
  try { D = JSON.parse(src.textContent); } catch (e) { return; }
  if (!D || !D.periods) return;

  // ── 탭 버튼·패널
  var btn = document.createElement('button');
  btn.className = 'tab';
  btn.dataset.tab = 'backtest';
  btn.textContent = '📊 백테스트';
  var split = document.getElementById('splitbtn');
  bar.insertBefore(btn, split || null);
  var panels = document.querySelectorAll('.tabpanel');
  var panel = document.createElement('div');
  panel.className = 'tabpanel';
  panel.id = 'panel-backtest';
  var last = panels[panels.length - 1];
  if (last) last.parentNode.insertBefore(panel, last.nextSibling); else document.body.appendChild(panel);

  btn.addEventListener('click', function () {
    document.querySelectorAll('.tab').forEach(function (t) { t.classList.toggle('active', t === btn); });
    document.querySelectorAll('.tabpanel').forEach(function (p) { p.classList.toggle('active', p === panel); });
  });
  bar.addEventListener('click', function (ev) {            // 다른 탭을 누르면 내 활성 표시를 끈다
    var t = ev.target.closest('.tab');
    if (t && t !== btn) { btn.classList.remove('active'); panel.classList.remove('active'); }
  });

  var css = document.createElement('style');
  css.textContent =
    '#panel-backtest .bt-prod{margin:26px 0 0;padding:16px 18px;background:var(--surface);border:1px solid var(--line);border-radius:12px}' +
    '#panel-backtest .bt-prod h2{margin:0 0 4px;font-size:19px;color:var(--head)}' +
    '#panel-backtest .bt-sub{color:var(--mute);font-size:13px;margin:0 0 10px}' +
    '#panel-backtest h3{margin:16px 0 6px;font-size:14px;color:var(--gold)}' +
    '#panel-backtest .bt-best{color:var(--entry,#3fb950);font-weight:800}' +
    '#panel-backtest .bt-warn{color:var(--warn,#e5484d)}' +
    '#panel-backtest .bt-muted{color:var(--mute)}' +
    '#panel-backtest details{margin-top:10px} #panel-backtest summary{cursor:pointer;color:var(--gold);font-weight:700;font-size:13.5px}' +
    '#panel-backtest .bt-tag{display:inline-block;font-size:11.5px;font-weight:700;padding:1px 7px;border-radius:6px;border:1px solid var(--line);color:var(--mute);margin-left:6px}' +
    '#panel-backtest .bt-tag.std{color:var(--warn,#e5484d);border-color:var(--warn,#e5484d)}' +
    '#panel-backtest table{min-width:560px}';
  document.head.appendChild(css);

  // ── 서식
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function pct(v, d) { return v == null || isNaN(v) ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(d == null ? 2 : d) + '%'; }
  function win(v) { return v == null || isNaN(v) ? '—' : Math.round(v) + '%'; }
  function day(s) { return s ? s.slice(0, 4) + '-' + s.slice(4, 6) + '-' + s.slice(6, 8) : '—'; }
  function f(st) { return st && st.n ? pct(st.avg) + ' · ' + win(st.win) : '—'; }

  var cur = (D.periods['3y'] ? '3y' : Object.keys(D.periods)[0]);

  function render() {
    var P = D.periods[cur];
    var H = D.horizons || [5, 10, 20];
    var h = '<div class="sheet">';
    h += '<div class="kicker">Backtest · 과거 검증</div>';
    h += '<h1>백테스트 — 이 규칙이 과거에 어땠나</h1>';
    h += '<p class="lede">매일 그날 종가까지의 데이터로 매수 판정을 다시 내고, <b>신호 다음 날 시가</b>에 샀다고 보고 결과를 셉니다. ' +
         '매수·매도 판정은 라이브와 같은 조건 트리(원문에서 독립 추출 → 실제 시세 비교 → 심판)로 냅니다.</p>';
    h += '<div class="pick" id="btPick">';
    Object.keys(D.periods).forEach(function (k) {
      var lbl = k === '1y' ? '최근 1년' : (k === '3y' ? '최근 3년' : k);
      h += '<button data-p="' + k + '" class="' + (k === cur ? 'on' : '') + '">' + lbl + '</button>';
    });
    h += '</div>';
    if (P.period) h += '<p class="bt-sub" style="margin-top:10px">기간 ' + day(P.period[0]) + ' ~ ' + day(P.period[1]) +
                       ' (' + P.trading_days + '거래일) · 생성 ' + esc((D.generated || '').replace('T', ' ')) + '</p>';

    Object.keys(P.products).forEach(function (p) {
      var S = P.products[p], T = S.trades || {}, st = T.stats || {};
      var std = T.exit_source && T.exit_source !== '책';
      h += '<div class="bt-prod"><h2>' + esc(p) + '<span class="bt-tag' + (std ? ' std' : '') + '">매도: ' + esc(T.exit_source || '-') + '</span></h2>';
      h += '<p class="bt-sub">기간 보유(처음~끝) ' + pct(S.buy_hold, 1) + '</p>';

      // 거래 성적
      var a = st.win, b = st.f20_win;
      h += '<h3>거래 성적 — 매도 규칙의 효과</h3><div class="tablewrap"><table><thead><tr>' +
           '<th>방식</th><th>거래</th><th>승률</th><th>평균 수익률</th><th>평균 보유</th><th>비고</th></tr></thead><tbody>';
      // 표준 매도의 수치(+9%/−5%/10일)는 파이썬(shared/trades.STANDARD)에서 파생해 D.standard_exit_label 로 실려 온다 — 복붙 금지.
      var stdLabel = '표준 매도(' + (D.standard_exit_label || '표준 기준') + ')';
      h += '<tr><td>' + (std ? stdLabel : '책 매도 규칙') + '</td><td>' + (st.trades || 0) + '</td>' +
           '<td class="' + (a != null && b != null && a > b ? 'bt-best' : '') + '">' + win(a) + '</td><td>' + pct(st.avg) + '</td>' +
           '<td>' + (st.days != null ? st.days.toFixed(1) + '일' : '—') + '</td>' +
           '<td>' + (st.open ? '<span class="bt-warn">미청산 ' + st.open + '건(승률 제외)</span>' : '') + '</td></tr>';
      h += '<tr><td>같은 진입 · 20거래일 보유</td><td>' + (st.trades || 0) + '</td>' +
           '<td class="' + (a != null && b != null && b > a ? 'bt-best' : '') + '">' + win(b) + '</td><td>' + pct(st.f20_avg) + '</td><td>20일</td><td></td></tr>';
      var base20 = (S.baseline || {})[String(H[H.length - 1])];
      h += '<tr><td class="bt-muted">아무 날에나 · 20거래일 보유</td><td class="bt-muted">—</td><td class="bt-muted">' + win(base20 && base20.win) +
           '</td><td class="bt-muted">' + pct(base20 && base20.avg) + '</td><td class="bt-muted">20일</td><td class="bt-muted">비교 기준</td></tr>';
      h += '</tbody></table></div>';
      if (st.rule_hits && Object.keys(st.rule_hits).length) {
        h += '<p class="bt-sub" style="margin-top:6px">매도 발동: ' + Object.keys(st.rule_hits).map(function (k) {
          return esc(k) + ' ' + st.rule_hits[k] + '회'; }).join(' · ') + '</p>';
      }

      // 등급별
      h += '<h3>등급별 — 그날 판정 뒤 N거래일 수익률 (평균 · 승률)</h3><div class="tablewrap"><table><thead><tr><th>등급</th><th>일수</th><th>신호</th>';
      H.forEach(function (n) { h += '<th>' + n + '일 후</th>'; });
      h += '</tr></thead><tbody>';
      var order = (D.grades || []).concat([D.buy_or_confirm]);
      order.forEach(function (g) {
        var x = (S.grades || {})[g];
        if (!x || (!x.days && g !== D.buy_or_confirm)) return;
        h += '<tr><td>' + esc(g) + '</td><td>' + x.days + '</td><td>' + x.signals + '</td>';
        H.forEach(function (n) { h += '<td>' + f(x.fwd[String(n)]) + '</td>'; });
        h += '</tr>';
      });
      h += '<tr><td class="bt-muted">(아무 날)</td><td></td><td></td>';
      H.forEach(function (n) { h += '<td class="bt-muted">' + f((S.baseline || {})[String(n)]) + '</td>'; });
      h += '</tr></tbody></table></div>';

      // 거래 목록
      var tl = T.trades || [];
      if (tl.length) {
        h += '<details><summary>거래 목록 ' + tl.length + '건 — 언제 사서 무엇으로 얼마를 팔았나</summary><div class="tablewrap"><table><thead><tr>' +
             '<th>진입</th><th>청산</th><th>수익률</th><th>보유</th><th>매도 내역</th><th>같은 진입 20일</th></tr></thead><tbody>';
        tl.forEach(function (t) {
          var sells = (t.sells || []).map(function (s) {
            return day(s.date) + ' ' + Math.round(s.qty * 100) + '% (' + esc(s.rule) + ')'; }).join('<br>');
          h += '<tr><td>' + day(t.entry) + '</td><td>' + (t.closed ? day(t.exit) : '<span class="bt-warn">미청산</span>') + '</td>' +
               '<td class="' + (t.ret > 0 ? 'bt-best' : 'bt-warn') + '">' + pct(t.ret) + (t.closed ? '' : ' <span class="bt-muted">(평가)</span>') + '</td>' +
               '<td>' + t.days + '일</td><td>' + (sells || '<span class="bt-muted">—</span>') + '</td><td>' + pct(t.fixed20) + '</td></tr>';
        });
        h += '</tbody></table></div></details>';
      }
      h += '</div>';
    });

    // 가정·한계
    var man = [];
    Object.keys(P.manual || {}).forEach(function (p) {
      (P.manual[p] || []).forEach(function (m) { man.push('[' + esc(p) + ' ' + esc(m.section) + '] ' + esc(m.rule)); });
    });
    h += '<div class="note" style="margin-top:26px"><b>읽는 법·한계</b><ul style="margin:6px 0 0;padding-left:18px">' +
         '<li>매수 신호 = ✅ 매수 후보 + 🟡 확인 대기. 🟡 는 아래 <b>수동 조건이 모두 통과했다고 가정</b>한 낙관치다(과거 장중·개장 전 상태는 확인할 수 없다).</li>' +
         '<li>거래 성적: 한 상품에 포지션 하나 — 보유 중의 신호는 건너뛴다. 매도는 종가 판정 → 다음 날 시가 체결. 저자가 준 규칙만 쓰고 안전장치 손절은 넣지 않는다(미청산이 그 결과).</li>' +
         '<li>표본이 작으면(거래 수십 건 이하) 우연의 영향이 크다. 과거 성적은 미래를 보장하지 않는다.</li>';
    if (P.missing_symbols && P.missing_symbols.length) h += '<li class="bt-warn">시세를 못 받은 심볼: ' + esc(P.missing_symbols.join(', ')) + '</li>';
    h += '</ul>';
    if (man.length) h += '<details><summary>수동 조건 ' + man.length + '개</summary><ul style="margin:6px 0 0;padding-left:18px"><li>' + man.join('</li><li>') + '</li></ul></details>';
    h += '</div></div>';

    panel.innerHTML = h;
    panel.querySelectorAll('#btPick button').forEach(function (b) {
      b.addEventListener('click', function () { cur = b.dataset.p; render(); });
    });
  }
  render();
})();
