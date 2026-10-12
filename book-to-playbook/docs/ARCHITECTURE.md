# 아키텍처 — 구조의 정본

> 구조·원칙 설명은 이 파일 한 곳. README·HANDOFF 는 여기를 가리킨다. 할 일은 `docs/HANDOFF.md` 한 곳.
> 2026-10-08 리팩터(TreeGateway → 폴더 재편 → 검사 정리), 2026-10-09 리팩터(팀 폴더 → layer-first 재배치 → 2단 pub-sub),
> 2026-10-12 리팩터(만드는 곳 = 검증하는 곳 · 검사는 바뀔 때만)에서 사용자와 정한 원칙.

## 1. 구조 한눈에 — 폴더 이름이 곧 파이프라인

폴더 = 층(layer). 흐름은 **아래에서 위로 한 방향** — 아래는 위를 import 하지 않는다(소비·진입만 위에서 아래를 부른다).
**제작(authoring)이 왼쪽에서 tree.json 을 만들고(그 검증까지), 런타임이 그 tree 를 오른쪽으로 흘린다.**
**검사는 따로 폴더가 없다 — 검사하는 대상 옆에 `verify_*.py` 로 둔다**(그 층의 import 규칙을 그대로 따른다).
작업 순서(만들기 → 검증 → 사용)와 트리를 읽는 길은 1-2.

```
          books(설정·책마다 tree.json) · tree(언어)
                 │
  제작 ───────────┤─────────────── 런타임 파이프라인: 시세 → 신호 → 소비 ───────────────
                 │
authoring/   books/<slug>/tree.json 을 만들고 검증한다(전사·추출 a·b·심판 · 본문 해시·채점) — 런타임과 분리, 명령으로만 돈다
  │ 산출물 books/<slug>/*.json
  ▼
tree/         조건 트리의 언어(공개 토대) — gateway(읽는 유일 출입구) · tradeTool(문법/계산 validate·Ctx·series · 등급 수학 RuleSeries, 일봉 확정·asof)
  ▼
market/      시세 조달 — md_feed(jhts 어댑터, 유일한 시세 창구) · _dev_cache
  ▼
market/        라이브 틱 피더(pub-sub) — ① price_bus(시세 틱) · ② verdict_bus(판정) 두 단 버스. 시세를 '모름'(가격 아님, 트리거)
  ▼                               틱마다 전 책 심볼 합집합을 market 에서 '한 번' 조회해 fan-out(공유 시세·중복 조회 0)
judge/     ① 판단층 — 판단자 Judge(책)·ProductJudge(상품): 트리·시세 원본의 유일한 사용자 → Decision  (돈·잔고·화면 모름)
  │
  ├─▶ backtest   Judge.signals × 체결(판단자가 낸 조건 값·가격으로) × 성적(돈·vectorbt)
  ├─▶ entry/notify.py     텔레그램·데스크톱 알림
  └─▶ web    Decision → 화면 JSON·사유·view (판단 안 함 — 서버 권위) · ui/*.js

shared/   경로(paths)·인코딩·책 레지스트리(books.json) · 소절 키 규칙(sections) — 그 밖의 뜻은 두지 않는다
entry/    진입점 — serve(로컬 서버: 피더 구동 + SSE) · run(스케줄 daily·check) · live(2단 pub-sub 조립 뿌리)
검사      대상 옆 verify_*.py — 원문 authoring/transcribe/verify_source · 트리 authoring/extract/verify_tree · 페이지 web/verify_page
          · 연산 tree/verify_primitives · 설명 judge/verify_view · 체결 backtest/verify_trading · 코드 규칙 entry/verify_rules
books/<slug>/  책 하나의 산출물 전부(playbook.html · source · source_index · tree.json · 후보 · 사례 · 결과 · 로그)
```

| 폴더(층) | 하는 일 | 주요 파일 |
|---|---|---|
| `shared/` | 경로·인코딩·책 레지스트리 · 소절 키 규칙 | `paths.py`(book_dir·book_file·books.json 레지스트리·live_slugs) · `sections.py`(원문·플레이북의 장/소절 표지 정규식 · marks) |
| `market/` | 시세 조달 — jhts 는 여기서만 · 틱 배달(시세 모르는 순수 부품) | `md_feed.py`(histories·minutes·sessions) · `_dev_cache.py` · `bus.py`(`Bus` 구독/발행 · `Poller` 틱 구동) · `feed.py`(`Feed`=Bus+run · `watch` 장중 루프) |
| `tree/` | 조건 트리(tree.json)의 언어 — **DSL 의 주인** | `gateway.py`(출입구) · `tradeTool.py`(문법·평가·RuleSeries·history — 모듈 수준 이름을 직접 import, +`grade_rules.json`) |
| `judge/` | 판단자 — 트리·시세 원본의 유일한 사용자 → 판정 데이터 (돈·화면 모름) | `judge.py`(**Judge** 책 하나: 트리 열기·시세 받기·라이브 decisions·백테스트 signals · `judge.tree`(비교·채점·원시 트리 보기가 출입구에 묻는 단 하나의 문) · **ProductJudge** 상품 하나: 등급·decide·설명·보유 status·체결용 conditions·price · Holding · Decision 그릇 · '얼마나' 절: 매도 정책 exit_policy·수량 변환 to_units·금액 정책 size_of — 라이브 화면·백테스트 공용) · `explain.py`(판단 근거 설명 — judge 만 부름) |
| `backtest/` | 판정을 받아 과거 시뮬레이션 | `{trades,portfolio,runner}.py`(체결 · 돈·수수료 · 러너, +`market_config.json`) · `verify_trading.py`(검사) |
| `web/` | 화면 모양(판정 안 함) | `verdict_view.py`(판정→화면 JSON·사유 문장) · `backtest_page.py` · `book_page.py` · `build_home.py` · `inject_*.py` · `raw_tree.py`(원시 트리 보기 — 소절마다 뽑힌 규칙 1:1, `Judge.cards`) · `ui/*.js` · `verify_page.py`(검사) |
| `entry/` | 진입점 | `serve.py`(로컬 서버·SSE) · `run.py`(스케줄 러너·CHECKS) · `live.py`(`LiveHub` — 2단 버스 조립) · `notify.py`(알림 — 텔레그램·데스크톱, books.json engine.daily) · `verify_rules.py`(코드 규칙 검사 — 전 층을 보므로 entry) |
| `authoring/` | 책 → 전사 → 트리를 **만드는** 쪽(런타임과 분리) · 두 단계는 서로 import 안 함 | **transcribe**(① 책 → 전사) `book_source.py` · `pages.py` · `verify_source.py`(본문 해시 검사) · `PLAYBOOK.md` · `book_sources.json` · `source_baseline.json` · **extract**(② 전사 → 트리) 지침 md(COND_DSL·EXTRACTOR·SCENARIO·JUDGE·README) · `compare.py`(심판 비교 도구 · '같은 뜻' 잣대) · `verify_tree.py`(트리 채점 · `--quick` 트리 계약) |

### 1-1. 라이브 2단 pub-sub — 책 N개가 시세 하나를 나눠 쓴다

```
market (jhts, pull)
   ▲ 틱마다 전 live 책 심볼 '합집합'을 한 번만 조회 (md_feed.histories 1회 — 공유 심볼 중복 0)
   │
market.bus price_bus (1개) ──틱 {ts, trees, hist}── fan-out ─┬──────────────┬──────────────┐
                                                      ▼              ▼              ▼
                                           signal(책A)     signal(책B)     signal(책N…)   (pricing 미래)
                                           = 구독+발행      = 구독+발행      = 구독+발행
                                                │ 판정 사실       │              │
                                                ▼ publish         ▼              ▼
                                           verdict_bus[책] (책마다 1개)
                                                ├──▶ web(화면 SSE push)
                                                └──▶ notify(알림) · (주문 미래)
```

- **책 추가 = `books.json` 한 줄 + `books/<slug>/tree.json`.** `entry/live.LiveHub._sync()` 가 live 책을 `price_bus` 구독자로 자동 등록한다(서버 재시작 불필요) — "책 등록 = 구독". signal 은 **코드 하나, 인스턴스 N개**(책마다 파일 안 만듦 — 원칙 12).
- **시세는 한 번**: 피더가 틱마다 전 책의 심볼 합집합을 `Judge.shared_prices([판단자들])` 로 1회 조회해 틱에 싣는다(피더는 시세 묶음을 열지 않고 넘기기만). 각 책 판단자는 그 공유 시세에서 자기 심볼만 읽어 혼자 받던 때와 **같은 판정**을 낸다(중복 조회 제거 — `verify`/A·B 로 동작 불변 증명).
- **버스는 가격을 모른다**(market/bus — 다른 층 import 0) — '언제 다시 판정하나'(트리거)만. '무엇을 계산할지'는 구독자(judge·web)가 정한다. 그래서 백테스트(과거 배치)는 버스를 안 거치고 같은 판단자 코드를 직접 돌린다(구독 밖).
- **의존성 주입**: judge·web 은 버스를 import 하지 않는다. 둘을 엮는 유일한 자리는 `entry/live.py`(조립 뿌리, entry 는 전 층 import 허용).
- **오늘 판정 = asof=now 한 점(Judge.decisions) · 백테스트 = 전 날짜(Judge.signals)** — 같은 판단자를 쓰임만 달리(원칙 5).

### 1-2. 작업 순서와 트리를 읽는 길 — 만드는 곳 = 검증하는 곳

세로는 **작업 순서**, 오른쪽은 그 단계가 **트리를 읽는 길**. 검증은 그것을 만드는 단계 안에 있고(폴더도 같다),
검사는 **대상이 바뀔 때만** 돈다 — 매일 돌지 않는다(daily·verdict·watch 에 검사 없음).

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
    entry/run daily·verdict · entry/live(watch·serve)                   Judge.open
      → judge/judge  Judge·ProductJudge (판정·백테스트 신호)
        ├▶ web  verdict_view · backtest_page (화면)
        ├▶ backtest runner · trades (체결·수익)
        └▶ entry/notify.py   알림
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 코드 검사 — 코드를 바꿀 때, 각 층 옆 verify_*.py              가짜 트리(synthetic)만
   tree/verify_primitives · judge/verify_view · backtest/verify_trading · entry/verify_rules
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
| 13 | **트리·시세 원본의 사용자는 판단자 하나** — 출입구(TreeGateway)·시세 받기·조건 평가는 `judge/judge`(+ 도구 tree)만 쓴다. 체결·화면·라이브·검사는 판단자에게 묻고 받은 값(판정·가격·조건 값·설명)만 쓴다(도구 단위 검사 tree.verify_primitives 만 예외) | 주인 표: 트리 출입구 사용·조건 평가·시세 원본 |

## 3. 변경 규율

- **리팩터와 기능은 커밋 분리, 리팩터 먼저.** 리팩터는 **동작 불변을 전후 비교로 증명**한다(고정 픽스처 + 시세 캐시
  `ETF_DEV_CACHE` 로 판정 JSON·백테스트·검사 출력 diff).
- **동작 변경은 따로 커밋**하고 전후 수치를 보고한다.
- **쓸모없어진 것(죽은 코드·옛 문서·옛 산출물)은 같은 작업에서 지운다.** 호환용 별칭을 남기지 않는다.
- **책 데이터(후보·tree.json)는 손으로 고치지 않는다** — 공통 로직을 고친 뒤 다시 뽑는다. 심판 몫은 심판이.
- 트리 JSON 은 `python -m tree.tradeTool fmt <파일>` 압축 형식.

## 4. 주인 표 (`entry/verify_rules.py` OWNERS — 주인 밖에 보이면 정지)

| 결정 | 주인 |
|---|---|
| tree.json 원본 키 | `tree/gateway.py` |
| 책 산출물 경로 | `shared/paths.py` |
| 매도 정책(책에 매도 규칙이 없을 때 = 매수 신호만 평가) | `judge/judge.py` `exit_policy` |
| 금액 정책(비중 × 분할, 모름 처리) | `judge/judge.py` `size_of` (사실은 `ProductJudge.amount` 한 경로) |
| 수량 변환('얼마나' → 물량, 매수·매도 공통) | `judge/judge.py` `to_units` |
| 동사·등급 이름표(안 산다·산다·판다 · 등급 글자) | `tree/tradeTool.py`(VERBS·GRADES) · `grade_rules.json` |
| 등급 사다리(날짜별 등급 계산) | `tree/tradeTool.py`(RuleSeries.grade_key) — 화면은 다시 계산하지 않음(수동 답은 `POST /api/verdict`) |
| 트리 출입구 사용(TreeGateway) | `judge/judge.py` (+ 도구 `tree/`) |
| 조건 평가(series·Ctx·RuleSeries — 책 내용대로 판단) | `judge/judge.py` · `judge/explain.py` (+ 도구 `tree/`) |
| 시세 원본(받기·캔들 필드) | `judge/judge.py` (+ 도구 `tree/tradeTool.py` · 창구 `market/`) |
| 지운 연산(ma·ema·stdev·rsi·pct·count·streak — `tradeTool.GONE_OPS`) | 어디서도 쓰지 않는다 |
| 할 일 목록 | `docs/HANDOFF.md` (다른 곳에 TODO 파일 금지) |

새로 '한 곳에서만 정할 것'이 생기면 여기와 OWNERS 에 한 줄씩.

## 5. 검사

`python -m entry.run check` 하나로 전부. 목록은 `entry/run.py` 의 `CHECKS` 한 곳.
검사는 **대상이 바뀔 때** 돈다(코드·트리·원문·페이지를 바꾼 뒤, 커밋 전) — 매일 돌지 않는다(daily·verdict·watch 에는 없음).
트리 검사는 트리뿐 아니라 트리를 실행하는 엔진 코드(tree·judge)가 바뀌어도 다시 돌아야 해서 목록을 나누지 않고 전부 돈다.
선택(opt) = `run check --parity` 일 때만.

| 검사 | 보는 것 |
|---|---|
| `entry.verify_rules` | 폴더 경계(import 방향·jhts 단일 창구·자가수집 0) + 주인 표 |
| `authoring.transcribe.verify_source` | 플레이북 본문(`#src`) 해시 |
| `authoring.extract.verify_tree --quick` | 트리 계약 — 소절 인덱스 · 트리 문법 · ref 가 실제 소절 |
| `web.verify_page` | 책 페이지 구획 · UI 사본 == `web/ui/*.js` |
| `tree.verify_primitives` | 원시 연산·등급·금액·수동 답(pandas 기준값·손계산) · 3값 논리 · 인과성 · 문법 · 출입구 계약 |
| `backtest.verify_trading` | 체결 워크·수량 변환·금액·매도 정책 · 실전 경로. `--parity` = 판정 == 백테스트(opt) |
| `judge.verify_view` | 화면 설명 구조 |
| `authoring.extract.verify_tree` | 체크리스트가 원문 뜻대로 동작하나 — a·b 비교(식) · 원문 사례 · 심판 기록 · 발화 통계 |

검사는 전부 **실행**으로 본다(글자 대조 검사는 의미를 판정하지 못해 없앴다).
