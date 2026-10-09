# 아키텍처 — 구조의 정본

> 구조·원칙 설명은 이 파일 한 곳. README·HANDOFF 는 여기를 가리킨다. 할 일은 `docs/HANDOFF.md` 한 곳.
> 2026-10-08 리팩터(TreeGateway → 폴더 재편 → 검사 정리), 2026-10-09 리팩터(팀 폴더 → layer-first 재배치)에서 사용자와 정한 원칙.

## 1. 구조 한눈에

폴더 = 층(layer). 흐름은 아래에서 위로 한 방향 — 아래는 위를 import 하지 않는다. 소비·진입·검사만 위에서 아래를 부른다.

```
책 원문 ─▶ authoring/   ─▶ books/<slug>/playbook.html · tree.json  (만드는 쪽: 전사·추출·심판)
               │ 산출물 파일(books/<slug>/*.json)
               ▼
          dsl/          조건 트리의 언어 — tree_gateway(출입구) · tradeTool(Cond=문법·계산 · Grade=등급의 뜻)
               ▼
          signals/       tree + 시세 → Judge(판단) → Decision  (돈·잔고 모름)
               │
               ├─▶ consumers/backtest   signal_series × 계좌·체결 × 성적(돈)
               ├─▶ consumers/notify      텔레그램·데스크톱 알림
               └─▶ consumers/display     결과 JSON 을 화면 모양으로(판단 안 함) · ui/*.js
                        ▲
          feed/   라이브 틱 피더(트리거) ──┘ 틱마다 소비자 fan-out(SSE·watch·pricing)

market/   시세 창구(md_feed) · 개발 캐시 — jhts 는 여기서만
shared/   경로(paths)·인코딩·책 레지스트리(books.json) — 뜻은 두지 않는다
entry/    진입점 — run(스케줄 러너) · serve(로컬 서버) · watch(장중 루프)
verify/   검사만 — 코드 규칙·트리·원시함수·거래·화면·본문 해시
books/<slug>/  책 하나의 산출물 전부(playbook.html · source · source_index · tree.json · 후보 · 사례 · 결과 · 로그)
```

| 폴더(층) | 하는 일 | 주요 파일 |
|---|---|---|
| `shared/` | 경로·인코딩·책 레지스트리 | `paths.py`(book_dir·book_file·books.json 레지스트리) |
| `market/` | 시세 창구 — jhts 는 여기서만 | `md_feed.py` · `_dev_cache.py`(개발용 시세 캐시) |
| `dsl/` | 조건 트리(tree.json)의 언어 — **DSL 의 주인** | `tree_gateway.py`(출입구) · `tradeTool.py`(Cond·Grade, +`grade_rules.json`) |
| `signal/` | tree+시세 → 판정 데이터 | `judge.py`(Judge·Decision·Holding·signal_series·truncate) · `engine.py`(라이브 판정 엔진) · `commonTool.py`(공통 책 열기) |
| `feed/` | 라이브 틱 피더(트리거) | `__init__.py`(Feed — in-process pub-sub, SSE·watch 공통) |
| `consumers/` | 신호를 받아 쓰는 소비자 | **backtest** `{trades,portfolio,runner}.py`(체결 규약·매도 정책 · 돈·수수료 · 러너, +`market_config.json`) · **notify** `{telegram,desktop}.py` · **display** `verdict_view.py` · `condition_view.py` · `backtest_page.py` · `book_page.py` · `build_home.py` · `inject_*.py` · `ui/*.js` |
| `entry/` | 진입점 | `run.py`(스케줄 러너·CHECKS) · `serve.py`(로컬 서버) · `watch.py`(장중 루프) |
| `verify/` | 검사만 | `verify_code.py` · `verify_tree.py` · `verify_primitives.py` · `verify_trading.py` · `verify_view.py` · `verify_source_integrity.py` |
| `authoring/` | 책 → 플레이북 → 트리를 **만드는** 쪽 | **playbook** `book_source.py` · `pages.py` · `PLAYBOOK.md`(지침) · `book_sources.json` · `source_baseline.json` · **checklist** 지침 md(COND_DSL·EXTRACTOR·SCENARIO·JUDGE·README) |

## 2. 원칙

| # | 원칙 | 지키는 장치 |
|---|---|---|
| 1 | **단방향 파이프라인** — shared ← market ← dsl ← signal·feed ← consumers (entry·verify 는 전부, authoring 은 dsl 까지). 층 사이 약속은 코드가 아니라 **산출물 파일**. 아래는 위를 import 하지 않는다 | `verify_code` 폴더 경계 |
| 2 | **산출물을 만든 쪽이 읽는 창구도 책임** — tree.json 키는 `TreeGateway` 만 안다. 소비자는 질문만 | 주인 표: 트리 원본 키 |
| 3 | **결정 하나 = 주인 하나** — 같은 결정을 두 곳에 두지 않는다. 새로 '한 곳에서만 정할 것'이 생기면 주인 표에 한 줄 | 주인 표(`verify_code.OWNERS`) |
| 4 | **뜻 / 판단 / 실행 / 표시 분리** — 뜻 = `dsl` · 판단 = `signal`(`Judge`, 돈·잔고 모름) · 실행 = `consumers/backtest`(계좌·체결, 갈아끼울 수 있음) · 표시 = `consumers/display`(판단 안 함) | 폴더 경계 + 주인 표 |
| 5 | **판단 엔진은 하나, 쓰임은 조합만 다름** — 오늘 판정 = 백테스트의 마지막 하루. 실전 주문도 같은 `Judge` | `Judge` 단일 경로 · `verify_trading --parity` |
| 6 | **서버 권위** — 화면은 엔진 결과를 그리기만. 다시 계산하지 않는다 | 주인 표: 등급 사다리 |
| 7 | **특수 기능보다 일반 부품 + 조합** — 사례마다 칸·지표를 덧대지 않는다. 조합으로 안 되면 **부품을 넓힌다**. `연산 없음`이 쌓이면 확장 신호 | 최소 문법 + 주인 표 |
| 8 | **같은 것은 표현도 하나** — 같은 식 = 같은 조건, 같은 것은 라벨 하나 | 검사기(같은 식 두 벌 등) |
| 9 | **모르면 드러낸다** — 대신 채우는 기본값 없음. `"?"` · 3값 논리 · "미명시"를 결과에 표시 | 검사기 + 결과 표시 |
| 10 | **데이터는 한 곳** — 책 산출물은 `books/<slug>/`, 경로는 `shared/paths.py` 하나 | 주인 표: 책 산출물 경로 |
| 11 | **기본 계산은 검증된 라이브러리(pandas), 도메인 뜻만 직접** | — |
| 12 | **특정 책에 맞추지 않는다** — 버그를 만나면 "공통 코드가 왜 이 책에선 안 먹히나"로 상위 로직을 고친다 | 리뷰 |

## 3. 변경 규율

- **리팩터와 기능은 커밋 분리, 리팩터 먼저.** 리팩터는 **동작 불변을 전후 비교로 증명**한다(고정 픽스처 + 시세 캐시
  `ETF_DEV_CACHE` 로 판정 JSON·백테스트·검사 출력 diff).
- **동작 변경은 따로 커밋**하고 전후 수치를 보고한다.
- **쓸모없어진 것(죽은 코드·옛 문서·옛 산출물)은 같은 작업에서 지운다.** 호환용 별칭을 남기지 않는다.
- **책 데이터(후보·tree.json)는 손으로 고치지 않는다** — 공통 로직을 고친 뒤 다시 뽑는다. 심판 몫은 심판이.
- 트리 JSON 은 `python -m dsl.tradeTool fmt <파일>` 압축 형식.

## 4. 주인 표 (`verify/verify_code.py` OWNERS — 주인 밖에 보이면 정지)

| 결정 | 주인 |
|---|---|
| tree.json 원본 키 | `dsl/tree_gateway.py` |
| 책 산출물 경로 | `shared/paths.py` |
| 매도 정책(책에 매도 규칙이 없을 때 = 매수 신호만 평가) | `consumers/backtest/trades.py` `exit_policy` |
| 금액 정책(비중 × 분할 × 조심 배수, 모름 처리) | `consumers/backtest/trades.py` `size_of` (사실은 `Judge.amount` 한 경로) |
| 수량 변환('얼마나' → 물량, 매수·매도 공통) | `consumers/backtest/trades.py` `to_units` |
| 칸·등급 이름표 | `dsl/tradeTool.py`(Cond·Grade) · `grade_rules.json` |
| 등급 사다리(등급·금액 배수 계산) | `dsl/tradeTool.py`(Grade) — 화면은 다시 계산하지 않음(수동 답은 `POST /api/verdict`) |
| 할 일 목록 | `docs/HANDOFF.md` (다른 곳에 TODO 파일 금지) |

새로 '한 곳에서만 정할 것'이 생기면 여기와 OWNERS 에 한 줄씩.

## 5. 검사

`python -m entry.run check` 하나로 전부. 목록은 `entry/run.py` 의 `CHECKS` 한 곳.
태그: gate = 항상(daily·verdict 포함) · tree = `--no-verify-tree` 면 생략 · opt = `run check --parity` 일 때만.

| 검사 | 태그 | 보는 것 |
|---|---|---|
| `verify.verify_code` | gate | 폴더 경계(import 방향·jhts 단일 창구·자가수집 0) + 주인 표 |
| `verify.verify_source_integrity` | gate | 플레이북 본문(`#src`) 해시 |
| `verify.verify_tree --contract` | gate | 책 계약 — 소절 인덱스 · 트리 문법 · ref 가 실제 소절 |
| `verify.verify_view --pages` | gate | 책 페이지 구획 · UI 사본 == `consumers/display/ui/*.js` |
| `verify.verify_primitives` | tree | 원시 연산·등급·금액·수동 답(pandas 기준값·손계산) · 3값 논리 · 인과성 · 문법 · 출입구 계약 |
| `verify.verify_trading` | tree | 체결 워크·수량 변환·금액·매도 정책 · 실전 경로. `--parity` = 판정 == 백테스트(opt) |
| `verify.verify_view` | tree | 화면 설명 구조 |
| `verify.verify_tree` | tree | 체크리스트가 원문 뜻대로 동작하나 — a·b 비교(식) · 원문 사례 · 심판 기록 · 발화 통계 |

검사는 전부 **실행**으로 본다(글자 대조 검사는 의미를 판정하지 못해 없앴다).
