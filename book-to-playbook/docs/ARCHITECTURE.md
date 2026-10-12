# 아키텍처 — 구조의 정본

> 구조·원칙 설명은 이 파일 한 곳. README·HANDOFF 는 여기를 가리킨다. 할 일은 `docs/HANDOFF.md` 한 곳.
> 2026-10-08 리팩터(TreeGateway → 폴더 재편 → 검사 정리), 2026-10-09 리팩터(팀 폴더 → layer-first 재배치 → 2단 pub-sub),
> 2026-10-12 리팩터(만드는 곳 = 검증하는 곳 · 검사는 바뀔 때만)에서 사용자와 정한 원칙.

## 1. 구조 한눈에 — 폴더 이름이 곧 파이프라인

폴더 = 층(layer). 흐름은 **아래에서 위로 한 방향** — 아래는 위를 import 하지 않는다(소비·진입만 위에서 아래를 부른다).
**제작(authoring)이 왼쪽에서 tree.json 을 만들고(그 검증까지), 런타임이 그 tree 를 오른쪽으로 흘린다.**
**검사는 따로 폴더가 없다 — 검사하는 대상 옆에 `verify_*.py` 로 둔다**(그 층의 import 규칙을 그대로 따른다).
판정 엔진의 모양(시세 칸 → 노드 → 판때기)은 1-1, 라이브 배달은 1-2, 작업 순서와 트리를 읽는 길은 1-3.

```
 ┌─ authoring/ (사람·LLM — 트리를 바꿀 때만 돈다) ─────────────────┐
 │  ① transcribe/  책 ──▶ 전사(플레이북)                           │
 │  ② extract/     전사 ──▶ tree.json  (추출자 a·b · 심판 · 채점)  │
 └────────────────────────────┬───────────────────────────────────┘
                              │ books/<slug>/tree.json
                              ▼
 tree/     정적 — 트리의 언어 + 출입구 gateway: 열기 · 문법 검사 · 판때기 만들기(1-1)
           트리가 확정되면 결과도 고정 — 매일 돌지 않는다
 ═════════════════════════════│═════════ 여기부터 런타임(매일·틱마다) ═════════
 market/   시세 — md_feed(jhts 유일 창구) · store(시세 칸 + 확정 표시) · bus(틱 배달)
    │ 값
    ▼
 judge/    판정 — eval(계산기) · judge(판때기 채우기 → 등급 · '얼마나' · 시세 받기)
    │ Decision (등급 · 얼마나 · 조건 값)
    ├─▶ backtest/  과거 시뮬레이션(체결 · 돈)
    ├─▶ web/       화면 모양(판정 JSON · 설명 · 책 페이지 · ui/*.js) — 판정하지 않는다
    └─▶ entry/     serve(서버) · live(라이브 조립) · run(일일 · check) · notify(알림)

 shared/   경로 · 책 레지스트리(books.json) · 소절 키 규칙 — 모든 층이 쓴다
 검사      대상 옆 verify_*.py (5절) · books/<slug>/ 책 하나의 산출물 전부
```

층 방향(아래만 본다): `shared ← market ← tree ← judge ← backtest ← web ← entry`.
`authoring` 은 `shared · market · tree · judge` 만 본다. 두 단계(transcribe·extract)는 서로 import 하지 않는다.

| 폴더(층) | 하는 일 | 주요 파일 |
|---|---|---|
| `shared/` | 경로·인코딩·책 레지스트리 · 소절 키 규칙 | `paths.py`(book_dir·book_file·books.json 레지스트리·live_slugs) · `sections.py`(원문·플레이북의 장/소절 표지 정규식 · marks) |
| `market/` | 시세 조달 — jhts 는 여기서만 · 시세 칸 · 틱 배달 | `md_feed.py`(histories·minutes·sessions) · `_dev_cache.py` · `store.py`(**Store** 시세 칸: need·load·refresh·prices·confirmed · 봉 확정 규칙 session_closes·settled_dates 한 곳) · `bus.py`(`Bus` 구독/발행 · `Poller` 틱 구동) · `verify_store.py`(검사) |
| `tree/` | 조건 트리(tree.json)의 언어 — **DSL 의 주인** | `gateway.py`(문법 validate·동사 VERBS·워밍업 warmup_of·공통 직렬화 `fmt` + 출입구 TreeGateway — 모듈 수준 이름을 직접 import) |
| `judge/` | 판단자 — 트리·시세 원본의 유일한 사용자 → 판정 데이터 (돈·화면 모름) | `judge.py`(**Judge** 책 하나: 트리 열기·시세 받기·라이브 decisions·백테스트 signals · `judge.tree`(비교·채점·원시 트리 보기가 출입구에 묻는 단 하나의 문) · **ProductJudge** 상품 하나: 등급·decide·설명·보유 status·체결용 conditions·price · Holding · Decision 그릇 · '얼마나' 절: 매도 정책 exit_policy·수량 변환 to_units·금액 정책 size_of — 라이브 화면·백테스트 공용 · 시세 받기 history·history_back·session_closes · 등급 RuleSeries·GRADES, +`grade_rules.json`) · `eval.py`(계산기 — 트리 식에 시세 값을 넣어 계산: Ctx·series) |
| `backtest/` | 판정을 받아 과거 시뮬레이션 | `{trades,portfolio,runner}.py`(체결 · 돈·수수료 · 러너, +`market_config.json`) · `verify_trading.py`(검사) |
| `web/` | 화면 모양(판정 안 함) | `verdict_view.py`(판정→화면 JSON·사유 문장) · `backtest_page.py` · `book_page.py` · `build_home.py` · `inject_*.py` · `explain.py`(판단 근거 설명 — 판단자의 값 함수 `ProductJudge.value`·`blank_value` 로만 값을 받는다, 계산 안 함) · `text.py`(식 → 글 낱말 한 벌 — explain·raw_tree 공용) · `raw_tree.py`(원시 트리 보기 — 소절마다 뽑힌 규칙 1:1, `Judge.cards`) · `ui/*.js` · `verify_page.py`(검사) |
| `entry/` | 진입점 | `serve.py`(로컬 서버·SSE — 판정은 허브 것을 그대로) · `run.py`(일일 배치 daily·검사 check · CHECKS) · `live.py`(**LiveHub** — 판단자·시세 칸·구독표를 엮어 바뀐 상품만 판정 → verdict_bus) · `notify.py`(알림 — 텔레그램·데스크톱, daily 가 책마다 부른다) · `verify_live.py`(라이브 허브 검사) · `verify_rules.py`(코드 규칙 검사 — 전 층을 보므로 entry) |
| `authoring/` | 책 → 전사 → 트리를 **만드는** 쪽(런타임과 분리) · 두 단계는 서로 import 안 함 | **transcribe**(① 책 → 전사) `book_source.py` · `pages.py` · `verify_source.py`(본문 해시 검사) · `PLAYBOOK.md` · `book_sources.json` · `source_baseline.json` · **extract**(② 전사 → 트리) 지침 md(COND_DSL·EXTRACTOR·SCENARIO·JUDGE·README) · `compare.py`(심판 비교 도구 · '같은 뜻' 잣대) · `verify_tree.py`(트리 채점 · `--quick` 트리 계약) |

### 1-1. 판정 엔진 — 시세 칸 → 노드 → 판때기

> 상태: ✅ 있음 · ⏳ 아직 없음. 아직 없는 것을 있는 것처럼 쓰지 않는다 — 단계가 끝나면 표시를 고친다.

판정 엔진은 세 가지로 이루어진다. **시세는 왼쪽에서 들어오고 등급은 오른쪽으로 나간다.**

| 무엇 | 몇 개 | 하는 일 | 어디 | 상태 |
|---|---|---|---|---|
| **시세 칸** | 심볼 × 봉 길이마다 1개 (TQQQ 일봉 · NVDA 일봉 …) | 과거 봉과 오늘 봉을 든다. 봉마다 `확정/진행 중` 표시. 같은 심볼은 어느 책이 쓰든 한 칸 | `market/store`(Store) | ✅ |
| **노드** | 서로 다른 식마다 1개 | 식 하나(예: `TQQQ 종가 > 20일 전`). 시세 칸에서 값을 읽어 계산. **같은 식은 노드 하나를 공유**(상품·책이 달라도 — 노드 풀이 정규 열쇠로 intern). 수동·`?`·pos 를 품은 노드는 상품마다 따로 | 모양 `tree/gateway`(Node·bind·노드 풀) · 계산 `judge/eval`(노드 id 로 값 기억) | ✅ |
| **판때기** | 책 × 상품마다 1개 | 그 상품의 동사(안 산다·산다·판다)와 '얼마나'(비중·분할) 식을 노드로 이은 배선도. 노드 값을 모아 **등급**을 낸다. 모양 `Board(product, index, gates{동사: 노드}, weight, tranches, sells, symbols, warmup)` | 만들기 `TreeGateway.board(상품)` · 채우기 `judge/judge`(RuleSeries) | ✅ |

**판때기가 상품마다인 이유**: 등급은 상품에 붙는 결과다("TQQQ 를 살까?"). 다른 심볼(NVDA·^NDX)은 판단에 쓰는 **입력**일 뿐이라
판때기가 없다 — 어떤 책이 그 심볼을 상품으로 등록하면 그때 생긴다. 트리는 책마다 하나지만 `$self`·`$index` 자리에
상품마다 다른 티커가 들어가므로 판때기는 상품마다 따로 만든다(바인딩).

**예시** — 책 A, 상품 둘(TQQQ 지수 ^NDX · SOXL 지수 ^SOX):

```
 트리(책 A)                                   rules
   "추세 위"   산다    $self 종가 > $self 20일 전
   "지수 하락" 안 산다 $index 종가 < $index 5일 전
   "빅테크"    산다    NVDA·AAPL·MSFT·AMZN 중 2개 이상 상승
   "SOXL 과열" 안 산다 (on: SOXL) $self 종가 > 10일 전 × 1.3

        │ 서버 켤 때 한 번 컴파일 (트리 파일이 바뀐 책만 다시)
        ▼
 판때기 [A × TQQQ]                          판때기 [A × SOXL]
   안 산다 ─ n3 ^NDX 종가 < 5일 전             안 산다 ─ n4 ^SOX 종가 < 5일 전
                                                       └ n6 SOXL 과열        ← on:SOXL 이라 여기만
   산다   ─ n1 TQQQ 종가 > 20일 전            산다   ─ n2 SOXL 종가 > 20일 전
          └ n5 빅테크 2개↑ ◀─────── 공유 ──────────┘ n5
   필요 시세: TQQQ ^NDX NVDA AAPL MSFT AMZN     필요 시세: SOXL ^SOX NVDA AAPL MSFT AMZN
```

```
 시세 칸 (심볼마다)        노드 (식마다, 공유)          판때기 (책 × 상품마다)
 ┌───────────┐
 │ TQQQ 일봉 │──────────▶ n1 ─────────────────────────▶ [A×TQQQ] ─▶ 등급
 │ ^NDX 일봉 │──────────▶ n3 ─────────────────────────▶     ▲
 │ NVDA 일봉 │─┐                                            │
 │ AAPL 일봉 │─┼────────▶ n5 빅테크 2개↑ ─────────────────┤
 │ MSFT 일봉 │─┤                                            ▼
 │ AMZN 일봉 │─┘                                      [A×SOXL] ─▶ 등급
 │ SOXL 일봉 │──────────▶ n2 · n6 ─────────────────────────▲
 │ ^SOX 일봉 │──────────▶ n4 ──────────────────────────────┘
 └───────────┘
   구독표 ✅: 심볼 → (책, 상품)  (NVDA → [A×TQQQ, A×SOXL]) — entry/live 가 Judge.subscriptions 로 짓는다
```

**한 틱의 흐름** ✅ — 예: NVDA 만 새 값이 왔다.

1. 시세 칸 NVDA 의 오늘 봉만 바꾼다.
2. 구독표로 NVDA 를 보는 판때기(A×TQQQ · A×SOXL)만 깨운다 — 한 틱에 NVDA·AAPL 이 같이 바뀌어도 한 번.
   그 안에서 n5 는 두 판때기가 같이 쓰므로 한 번만 계산한다(노드 공유). 다른 책·상품은 손대지 않는다.
3. 깨운 판때기의 등급을 책마다 **이벤트 하나**로 판정 버스(verdict_bus)에 올린다. 바뀐 게 없는 틱은 계산도 발행도 없다.
   (⏳ 깨운 판때기는 아직 전 기간을 다시 계산한다 — '오늘 칸만'은 아래 표의 남은 일)
4. 화면·알림·(나중) 주문은 버스에서 받기만 한다.

**흐름 보장**

| 보장 | 어떻게 | 상태 |
|---|---|---|
| 판때기는 최초 1회 | `TreeGateway.board` 가 상품마다 한 번 만들어 둔다. `Judge.open` 은 트리 파일(경로·수정 시각·크기)이 그대로면 같은 판단자를 돌려준다 — 바뀐 책·새 책만 다시. 파일로 저장하지 않는다(진실은 tree.json 하나) | ✅ |
| 중복 계산 없음 | 같은 식은 노드 하나(규칙 엔진 Rete 의 노드 공유). 같은 시세 묶음·달력·asof 에서 수동·pos 없는 노드 값은 상품·책·수동 가정이 달라도 한 번 계산(`judge.shared_values`) | ✅ |
| 내 시세 + 프록시 시세 | 판때기의 필요 시세 = 자기($self) + 지수($index) + 트리에 적힌 티커(`Board.symbols`) — 전부 구독표에 오른다. 아직 안 온 시세는 그 칸의 마지막 확정 봉 | ✅ |
| 틱당 한 번만 깨움 | `store.refresh()` 가 이번 틱에 바뀐 심볼 집합을 돌려주고, 허브가 그걸 보는 상품을 모아 한 번만 판정 · 책마다 발행 하나 (`entry/verify_live` 가 증명) | ✅ |
| 과거 재계산 없음 | 노드가 과거 칸 결과를 기억 — 오늘 칸만 계산. 지금은 깨운 판때기만 전 기간을 다시 계산한다(일봉 기준 수 ms) | ⏳ |
| 서로 참조 없음 · 한 방향 | 판때기끼리 부르지 않는다(rule 참조는 컴파일 때 펼쳐 끝). 시세 → 노드 → 판때기 → 버스 → 소비자. 사람이 답한 수동 조건·내 포지션도 아래쪽 입력으로 넣는다(화면이 판정을 거꾸로 부르지 않는다) | ✅ (수동 답 = `LiveHub.judge_with` · 포지션 = 파일 표식이 바뀌면 다시) |
| 백테스트 = 라이브 | 같은 판때기에 과거 봉을 하루씩 흘린다(버스 안 거침). 포지션은 그날 체결 결과를 다음 날 입력으로 | ✅ 같은 판단자 |

봉의 확정 표시는 `market/store` 의 한 규칙(`session_closes`·`settled_dates`) — 판단자의 장중 asof 재현도 같은 함수를 쓴다.

업계 대응: 시세 칸·구독표 = LEAN SubscriptionManager · Nautilus Cache+MessageBus / 판때기 컴파일 = Backtrader `__init__` 지표 그래프 ·
Pine 스크립트 컴파일 / 노드 공유 = Rete / 봉의 확정 표시 = Pine `barstate.isconfirmed`.

### 1-2. 라이브 — 시세 칸 하나를 책 N개가 나눠 쓴다

```
 [서버 켤 때 한 번]  entry/live.LiveHub
   books.json(live:true) ─▶ Judge.open(책) ─▶ 판때기(상품마다, 1-1)
                          └▶ 구독표 {심볼 → (책, 상품)} ─▶ store.need(전 심볼) ─▶ store.load() (과거 봉 한 번)

 [틱] Poller(interval 초)
   store.refresh() ─▶ 바뀐 심볼 ─▶ 구독표 ─▶ 그 심볼을 보는 상품만 Judge.decisions(products=…)
                                              │ 책마다 이벤트 하나 (바뀐 게 없으면 없음)
                                              ▼
                                       verdict_bus[책] ──▶ 화면 소비자(_format → 최신 top) ──▶ serve (GET · SSE push)
 [아래쪽 입력]  수동 답 POST ─▶ LiveHub.judge_with(책, 답)  (허브의 판단자 + 저장소 시세 — 다시 받지 않음)
              내 포지션(positions.json) ─▶ 파일이 바뀌면 그 책 전 상품 다시
```

- **책 추가 = `books.json` 한 줄 + `books/<slug>/tree.json`.** 허브가 틱마다 `_sync` 로 맞춘다 — 새 책·트리가 바뀐 책만 다시
  열고(컴파일 캐시) 구독표를 다시 짓는다(서버 재시작 불필요). 판정 코드는 **하나, 인스턴스 N개**(책마다 파일 안 만듦 — 원칙 12).
- **시세는 한 번**: 같은 심볼은 책이 몇 권이든 시세 칸 하나. 적재는 시작 때 한 번, 틱마다는 최근 창만 다시 받아 합친다.
- **버스는 가격을 모른다**(market/bus — 다른 층 import 0) — '언제'(Poller)와 '누구에게'(verdict_bus)만. 판단자·화면은 버스를
  import 하지 않는다. 엮는 유일한 자리는 `entry/live.py`(조립 뿌리, entry 는 전 층 import 허용).
- **일일 배치**(`run daily`)는 허브 없이 책마다 `entry.notify`(판정 한 번 → 알림) + `web.backtest_page` 를 돈다.
- **오늘 판정 = 마지막 봉 한 점(Judge.decisions) · 백테스트 = 전 날짜(Judge.signals)** — 같은 판단자·같은 판때기(원칙 5).
  틱을 하루씩 흘린 판정 == 일괄 판정 · 재생 == 신호는 `entry/verify_live` 가 증명한다.

### 1-3. 작업 순서와 트리를 읽는 길 — 만드는 곳 = 검증하는 곳

세로는 **작업 순서**, 오른쪽은 그 단계가 **트리를 읽는 길**. 검증은 그것을 만드는 단계 안에 있고(폴더도 같다),
검사는 **대상이 바뀔 때만** 돈다 — 매일 돌지 않는다(daily 에 검사 없음).

```
 작업 순서(위 → 아래)                                              트리를 읽는 길
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 0. 원문 (구간①, authoring/transcribe) — 원문을 바꿀 때
    book_source(소절 인덱스) → 전사 → verify_source(본문 해시 고정)         트리 안 읽음
──────────────────────────────────────────────────────────────────────────────────
 1. 트리 만들기 + 검증 (구간②, authoring/extract) — 트리를 바꿀 때
    ① 추출자 a·b ─▶ tree_candidates/a.json · b.json (서로 모름)        서브에이전트가 씀
    ② 사례 작성자 ─▶ scenarios.json                                   트리 안 읽음
    ③ 심판  compare <slug> 6 → logs/disagree.json (a·b 다른 곳)         Judge.read
            원문과 대조해 tree.json (규칙마다 why)                      심판이 씀
    ④ 채점  verify_tree <slug> — 정지 0 까지 ③으로                      Judge.open/read
            ('같은 뜻' 잣대는 compare 한 벌) · verify_tree --quick 트리 계약
──────────────────────────────────────────────────────────────────────────────────
 2. 페이지 (web) — 페이지·UI 를 바꿀 때
    playbook.html 골격 · verify_page(구획·UI 사본 검사)                  트리 안 읽음
──────────────────────────────────────────────────────────────────────────────────
 3. 사용 (구간③, 런타임) — 매일·장중, 검사 없음
    entry/run daily(notify) · entry/serve → entry/live(허브)             Judge.open
      → judge/judge  Judge·ProductJudge (판정·백테스트 신호)
        ├▶ web  verdict_view · backtest_page (화면)
        ├▶ backtest runner · trades (체결·수익)
        └▶ entry/notify.py   알림
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 코드 검사 — 코드를 바꿀 때, 각 층 옆 verify_*.py              가짜 트리(synthetic)만
   tree/verify_gateway · judge/verify_eval · web/verify_view · backtest/verify_trading · entry/verify_rules
 전부 한 번에: python -m entry.run check  (무언가 바꿨으면 커밋 전 — 엔진 tree·judge 를 바꿔도 트리 검사까지)
```

트리를 읽는 길은 단계와 상관없이 하나다(원칙 13):

```
 tree.json · 후보 ──▶ tree/gateway.TreeGateway ──▶ judge/judge.Judge ──▶ 비교·채점·계약 / 화면·백테스트·라이브
                      (키 배치를 아는 유일한 파일)        (트리 객체를 받는 유일한 곳)
```

트리 파일 모양이 바뀌면 고칠 곳은 `tree/gateway.py` 하나. 새 질문이 필요하면 출입구에 하나(판단자는 `ProductJudge`가 출입구에 직접 묻고, 도구는 `judge.tree` 로 묻는다 — 전달 층 없음).

## 2. 원칙

| # | 원칙 | 지키는 장치 |
|---|---|---|
| 1 | **단방향 파이프라인** — shared ← market ← tree ← judge ← backtest ← web (entry 는 전부 · 검사는 대상 옆 verify_*.py 로 그 층 규칙을 따름, authoring 은 judge 까지 — 심판 비교 도구가 후보 트리를 판단자로 평가). 층 사이 약속은 코드가 아니라 **산출물 파일**. 아래는 위를 import 하지 않는다 | `entry.verify_rules` 폴더 경계 |
| 2 | **산출물을 만든 쪽이 읽는 창구도 책임** — tree.json 키는 `TreeGateway` 만 안다. 소비자는 질문만 | 주인 표: 트리 원본 키 |
| 3 | **결정 하나 = 주인 하나** — 같은 결정을 두 곳에 두지 않는다. 새로 '한 곳에서만 정할 것'이 생기면 주인 표에 한 줄 | 주인 표(`entry.verify_rules.OWNERS`) |
| 4 | **뜻 / 판단 / 실행 / 표시 분리** — 뜻 = `tree` · 판단 = `judge`(`Judge`, 돈·잔고 모름) · 실행 = `backtest`(계좌·체결, 갈아끼울 수 있음) · 표시 = `web`(판단 안 함) · 트리거 = `market/bus`(언제, 가격 모름) | 폴더 경계 + 주인 표 |
| 5 | **판단 엔진은 하나, 쓰임은 조합만 다름** — 오늘 판정 = 백테스트의 마지막 하루. 실전 주문도 같은 `Judge` | `Judge` 단일 경로 · `backtest.verify_trading --parity` |
| 6 | **서버 권위** — 화면은 엔진 결과를 그리기만. 다시 계산하지 않는다 | 주인 표: 등급 사다리 |
| 7 | **특수 기능보다 일반 부품 + 조합** — 사례마다 칸·지표를 덧대지 않는다. 조합으로 안 되면 **부품을 넓힌다**. `연산 없음`이 쌓이면 확장 신호 | 최소 문법 + 주인 표 |
| 8 | **같은 것은 표현도 하나** — 같은 식 = 같은 조건, 같은 것은 라벨 하나 | 검사기(같은 식 두 벌 등) |
| 9 | **모르면 드러낸다** — 대신 채우는 기본값 없음. `"?"` · 3값 논리 · "미명시"를 결과에 표시 | 검사기 + 결과 표시 |
| 10 | **데이터는 한 곳** — 책 산출물은 `books/<slug>/`, 경로는 `shared/paths.py` 하나 | 주인 표: 책 산출물 경로 |
| 11 | **기본 계산은 검증된 라이브러리(pandas), 도메인 뜻만 직접** | — |
| 12 | **특정 책에 맞추지 않는다** — 버그를 만나면 "공통 코드가 왜 이 책에선 안 먹히나"로 상위 로직을 고친다 | 리뷰 |
| 13 | **트리·시세 원본의 사용자는 판단자 하나** — 출입구(TreeGateway)·시세 받기·조건 평가는 `judge/judge`(+ 도구 tree)만 쓴다. 체결·화면·라이브·검사는 판단자에게 묻고 받은 값(판정·가격·조건 값·설명)만 쓴다(도구 단위 검사 tree.verify_gateway·judge.verify_eval 만 예외) | 주인 표: 트리 출입구 사용·조건 평가·시세 원본 |

## 3. 변경 규율

- **리팩터와 기능은 커밋 분리, 리팩터 먼저.** 리팩터는 **동작 불변을 전후 비교로 증명**한다(고정 픽스처 + 시세 캐시
  `ETF_DEV_CACHE` 로 판정 JSON·백테스트·검사 출력 diff).
- **동작 변경은 따로 커밋**하고 전후 수치를 보고한다.
- **쓸모없어진 것(죽은 코드·옛 문서·옛 산출물)은 같은 작업에서 지운다.** 호환용 별칭을 남기지 않는다.
- **책 데이터(후보·tree.json)는 손으로 고치지 않는다** — 공통 로직을 고친 뒤 다시 뽑는다. 심판 몫은 심판이.
- 트리 JSON 은 `python -m tree.gateway fmt <파일>` 압축 형식.

## 4. 주인 표 (`entry/verify_rules.py` OWNERS — 주인 밖에 보이면 정지)

| 결정 | 주인 |
|---|---|
| tree.json 원본 키 | `tree/gateway.py` |
| 책 산출물 경로 | `shared/paths.py` |
| 매도 정책(책에 매도 규칙이 없을 때 = 매수 신호만 평가) | `judge/judge.py` `exit_policy` |
| 금액 정책(비중 × 분할, 모름 처리) | `judge/judge.py` `size_of` (사실은 `ProductJudge.amount` 한 경로) |
| 수량 변환('얼마나' → 물량, 매수·매도 공통) | `judge/judge.py` `to_units` |
| 동사·등급 이름표(안 산다·산다·판다 · 등급 글자) | `tree/gateway.py`(VERBS) · `judge/judge.py`(GRADES) · `judge/grade_rules.json` |
| 등급 사다리(날짜별 등급 계산) | `judge/judge.py`(RuleSeries.grade_key) — 화면은 다시 계산하지 않음(수동 답은 `POST /api/verdict`) |
| 트리 출입구 사용(TreeGateway) | `judge/judge.py` (+ 도구 `tree/`) |
| 조건 평가(series·Ctx·RuleSeries — 책 내용대로 판단) | `judge/judge.py` · 계산기 `judge/eval.py` (+ 문법 `tree/gateway.py`) — 화면 설명(web/explain)은 판단자가 낸 값만 받는다 |
| 시세 원본(받기·캔들 필드) | `judge/judge.py` (+ 계산기 `judge/eval.py` · 창구 `market/`) |
| 지운 연산(ma·ema·stdev·rsi·pct·count·streak — `tree.gateway.GONE_OPS`) | 어디서도 쓰지 않는다 |
| 소절 키 규칙(원문·플레이북의 장/소절 표지) | `shared/sections.py` |
| 식 → 글 낱말(종가·보유일·k일 전…) | `web/text.py` — 판단 설명(explain)·원시 트리 보기(raw_tree) 공용 |
| 할 일 목록 | `docs/HANDOFF.md` (다른 곳에 TODO 파일 금지) |

새로 '한 곳에서만 정할 것'이 생기면 여기와 OWNERS 에 한 줄씩.

## 5. 검사

`python -m entry.run check` 하나로 전부. 목록은 `entry/run.py` 의 `CHECKS` 한 곳.
검사는 **대상이 바뀔 때** 돈다(코드·트리·원문·페이지를 바꾼 뒤, 커밋 전) — 매일 돌지 않는다(daily 에는 없음).
트리 검사는 트리뿐 아니라 트리를 실행하는 엔진 코드(tree·judge)가 바뀌어도 다시 돌아야 해서 목록을 나누지 않고 전부 돈다.
선택(opt) = `run check --parity` 일 때만.

| 검사 | 보는 것 |
|---|---|
| `entry.verify_rules` | 폴더 경계(import 방향·jhts 단일 창구·자가수집 0) + 주인 표 |
| `authoring.transcribe.verify_source` | 플레이북 본문(`#src`) 해시 |
| `authoring.extract.verify_tree --quick` | 트리 계약 — 소절 인덱스 · 트리 문법 · ref 가 실제 소절 |
| `web.verify_page` | 책 페이지 구획 · UI 사본 == `web/ui/*.js` |
| `tree.verify_gateway` | 트리 문법 · 출입구 계약 |
| `judge.verify_eval` | 원시 연산·등급·금액·수동 답(pandas 기준값·손계산) · 3값 논리 · 인과성 · 확정봉 |
| `backtest.verify_trading` | 체결 워크·수량 변환·금액·매도 정책 · 실전 경로. `--parity` = 판정 == 백테스트(opt) |
| `web.verify_view` | 화면 설명 구조 |
| `market.verify_store` | 시세 칸 — 한 번 적재 · 바뀐 심볼만 · 스냅샷 동일성 · 확정 표시(가짜 시세·캘린더) |
| `entry.verify_live` | 라이브 허브 — 하루씩 흘린 틱 판정 == 일괄 판정 · 바뀐 상품만 · 무변화 무발행 · 책마다 발행 하나 · 재생 == 신호 |
| `authoring.extract.verify_tree` | 체크리스트가 원문 뜻대로 동작하나 — a·b 비교(식) · 원문 사례 · 심판 기록 · 발화 통계 |

검사는 전부 **실행**으로 본다(글자 대조 검사는 의미를 판정하지 못해 없앴다).
