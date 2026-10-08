# book-to-playbook

트레이딩 책을 읽어 **① 저자 매매기법 플레이북 + ② 기계가 실행하는 체크리스트(조건 트리)**를 인터랙티브 웹으로 만들고,
**jhts 시세를 붙여 매일 자동 판정**까지 하는 파이프라인.

- 데모(공개 웹): `/trend/` — SPY·QQQ·IWM 추세추종 스윙 · `/moneycopy/` — TQQQ·SOXL·UPRO

## 한 줄 요약

**체크리스트 = 조건 트리(`books/<slug>/tree.json`).** 만드는 곳은 구간② 하나, 읽는 곳은 구간③ 하나다.
화면은 트리를 다시 해석하지 않고 ③이 낸 판정 결과만 그린다. 수집할 시세도 트리에서 나온다(수집 요청서 없음).

## 팀 구조 (폴더 = 조직도)

import 방향은 한 방향이다 — `shared ← playbook · checklist(공개 DSL) ← trading ← web` (orchestration 은 조립만).
구간②는 트리의 언어(공개 DSL: `tree_gateway`·`cond`·`grade`)를 내놓고, 구간③·화면은 그것만 import 한다.
경계와 '결정 하나 = 주인 하나'(주인 표)는 `orchestration/verify_code.py` 가 기계로 강제한다.

| 폴더 | 구간 | 하는 일 | 산출물 |
|---|---|---|---|
| `playbook/` | ① 책 원본 → 전사본 | 원문 소절 인덱싱 · 플레이북 본문 무결 | `books/<slug>/source_index.json` · `books/<slug>/playbook.html` 의 `#src` |
| `checklist/` | ② 전사본 → 체크리스트 | 조건 트리 추출·심판·검사 · 트리의 언어(출입구·문법·등급) | **`books/<slug>/tree.json`** |
| `trading/` | ③ 판정·백테스트·장중 | Judge(한 시점 판정)·Timeline(시간 축)·체결 워크·vectorbt 계산기·재생·알림 | (판정은 web 이 화면으로) · `books/<slug>/logs/backtest.json` |
| `web/` | 화면 | 판정 JSON·백테스트 탭 데이터 빚기 · 화면 JS 주입 · 페이지 조립 · 로컬 실시간 서버 · 홈 | (serve 가 매 요청 그림) · `books/<slug>/backtest.json` |
| `shared/` | 공통층 | **시세 창구 md_feed** · paths | — |
| `orchestration/` | 조립·감사 | `run.py`(러너 · 검사 목록 CHECKS 한 곳) · `verify_code.py`(폴더 경계·주인 표) — 전 구간 실행·검사 | — |

트리의 뜻(문법 cond·등급 grade)을 checklist/ 에 한 벌만 두고 ③이 그걸 import 하는 이유: ②가 트리를 검사할 때 본 동작과 ③이 판정할 때의 동작이
**같은 코드**여야 둘이 갈라지지 않는다.

```
책 원문 ──[① book_source]──▶ source_index.json (소절 키 = 체크리스트 ref 의 기준)
   │
   └─[① 플레이북 작성·원문 대조 감사]──▶ books/<slug>/playbook.html #src
                                  │
        [② 추출자 a·b(서로 모름) · 원문 사례 → 심판이 최종 트리를 씀(비교 도구 사용) → 채점] ──▶ tree.json (체크리스트)
                                  │
   [③ TreeGateway.symbols() → md_feed.histories(jhts, 없으면 수집 요청) → trading.Judge(checklist.grade)]
                                  │                                   └──▶ 알림(trading.notify)
                                  │
             [web: verdict_view(판정 JSON) · book_page(판정 + ui/*.js + 레일 + 원문 + 백테스트)] ──▶ web.serve(로컬 실시간)
```

## 체크리스트 — 판정 여섯 칸 (`checklist/COND_DSL.md`)

| 칸 | 묻는 것 | 결과 |
|---|---|---|
| `filter` | 들어가도 되는 시장인가 | 거짓 → 🚫 진입 금지 |
| `avoid` | 사면 안 되는 자리인가 | 참 → ⛔ 보류 |
| `entry` | 살 자리인가 | 참 → ✅ 매수 후보 · 거짓 → ⚪ 관망 |
| `caution` | 사더라도 금액을 줄일까 | 걸린 규칙마다 금액 × scale (폭 미명시면 표시만) |
| `sizing` | 얼마나(비중)·나눠서(분할) | 총 투자금 대비 % · 차수별 비율(미명시면 null) |
| `exit` | 보유분을 언제 얼마나 팔까 | 걸리면 다음 봉 시가 매도 · 내 포지션(로컬 파일) 기준 판정 |

시장 환경 점수·공격/균형/방어 모드·폭락 후 재진입처럼 **상품 여럿이 같이 보는 판단은 `defs` 에 한 번** 정의해
각 칸이 참조한다(화면 맨 위 '공통 조건'). 조건의 신원은 식이다 — 저자가 숫자를 안 준 조건도 식으로 쓰고 그 숫자 자리만
`"?"`(사람이 판단 — 🟡). 식으로 쓸 수 없는 것만 문장 수동: `저자 미명시: …(정성)` · `데이터 없음:`(수집·연결 과제) ·
`연산 없음:`(원시 연산 추가 과제). 문법 정본은 `checklist/COND_DSL.md`, 작성 규칙은 역할 문서.

봉 단위(`tf`: 1d·1m·5m)는 시세 노드의 속성이다 — 일봉·분봉을 따로 다루지 않는다. 데이터 연결 여부는 트리와 무관하다.

## 검증층 — 검사 목록 하나 (`orchestration/run.py` 의 CHECKS, `python -m orchestration.run check`)

| 검사 | 태그 | 보는 것 |
|---|---|---|
| `orchestration.verify_code` | gate | 코드 규칙 — 폴더 경계(import 방향·jhts 단일 창구·자가수집 0) · **주인 표**(트리 원본 키·책 산출물 경로·매도 정책·칸/등급 이름표·등급 사다리 — 주인 밖에 보이면 정지) |
| `playbook.verify_source_integrity` | gate | 플레이북 본문(`#src`) 해시 |
| `checklist.verify_tree --contract` | gate | 책 계약 — 소절 인덱스 · 트리 문법(여섯 칸 전부) · 트리 ref 가 실제 소절 |
| `web.verify_view --pages` | gate | 책 페이지 — `#src`·`#verdict-data`·`#sheet-root` · 공유 UI 구획 사본 == `web/ui/*.js` |
| `checklist.verify_primitives` | tree | 원시 연산·등급·금액을 pandas 기준값·손계산과 대조 · 3값 논리 전수 · 인과성 · 문법 · 출입구 계약. 책이 늘어도 크기 고정 |
| `trading.verify_trading` | tree | 거래 시뮬레이터(체결 워크) · 실전 경로 불변식. `--parity` = 신호 패리티(백테스트 == 실시간, 시세 필요 — 태그 opt) |
| `web.verify_view` | tree | 화면 설명 구조(condition_view) |
| `checklist.verify_tree` | tree | 체크리스트가 원문 뜻대로 **동작**하나 — 이중 추출을 실제 시세 3년으로 칸별 비교(갈린 칸은 심판 기록 필수) · 원문 사례 재현 · 발화 통계 · 비중 합 100% 초과 정지 · 수동 사유 분류 |

태그: gate = 항상(daily·verdict 포함) · tree = `--no-verify-tree` 면 생략 · opt = `run check --parity` 일 때만.
종료코드 0 통과 · 1 정지 · 2 경고(tree 태그만 — gate 는 2 도 정지).

글자 대조 검사(창작·커버리지·규칙↔명세·의미검사)는 의미를 판정하지 못해 없앴다 — 숫자 '2'만 있으면 '2거래일 유지'가
1일로 판정돼도 통과했다. 지금 검사는 전부 **실행**으로 본다.

## 새 책 추가하는 법

1. **원문 자르기**(①): `book_sources.json` 에 원문 위치 → `python -m playbook.book_source --write` (소절 인덱스).
2. **플레이북**(①): 원문 소절마다 본문 + 요약 bullet. 저자 명시분만·원문 숫자·미명시 표기. 끝나면 **원문 대조 감사**
   (요약 bullet 에 원문에 없는 숫자·칸 배치가 섞이기 쉽다) → `python -m playbook.verify_source_integrity --accept --why "새 책"`.
3. **체크리스트**(②): 역할마다 지침 문서 하나 — 추출자 a·b(`checklist/EXTRACTOR.md`, 서로 모름)가 플레이북만 보고
   규칙 목록 `<a|b>.rules.json` → 트리 `<a|b>.json` → 사례 작성자(`checklist/SCENARIO.md`)가 원문만 보고 `scenarios.json`
   → 심판(`checklist/JUDGE.md`)이 비교 도구(`--dump`)로 다른 곳을 보고 원문과 대조해 최종 `tree.json`(`review` 포함)을 직접 쓴다
   → `python -m checklist.verify_tree <slug>` 통과.
4. **페이지**: `books/trend/playbook.html` 을 베이스로 `#src` 와 머리말만 교체(시트 패널은 `#verdict-data` + `#sheet-root` 골격 그대로).
5. **등록**: `books.json` 에 항목(slug/title/tickers/desc/live/engine). `python -m orchestration.run check --no-verify-tree`(코드 규칙·본문 해시·책 계약·책 페이지)가 통과해야 한다.
6. **배포**: `python -m orchestration.run daily`.

수집 요청서는 없다 — 트리가 쓰는 심볼이 곧 수집 목록이고, jhts 에 없는 심볼은 수집 요청이 자동으로 남는다.

## 실행

```
python -m orchestration.run daily        # 판정 → 백테스트 탭 데이터 → 검사
python -m orchestration.run check [--no-verify-tree] [--parity]   # 검사만 전부(CHECKS) — 요약 + 종료코드
python -m orchestration.run watch [--every N] # asof=지금 기준 N분(기본 5)마다 재판정(백테스트 제외) — 장중 조건은 분봉이 연결되면 살아난다
python -m web.verdict_view <slug> [--json] [--no-send]       # 오늘 판정(판정 JSON·알림)
python -m trading.backtest <slug> [--days 365] [--engine vectorbt | --intraday]   # 백테스트(로그)
python -m web.backtest_page <slug>                            # 책 페이지 '백테스트' 탭 데이터
python -m web.serve                                           # 로컬 실시간 서버(RUN.md)
```

환경: jhts 시세 패키지가 pip 설치가 아니면 `PYTHONPATH=<jhts 경로>` 를 줘야 시세가 들어온다(없으면 판정이 ❔).
스케줄러로 돌릴 때는 `local.env`(커밋 안 함, `local.env.example` 참고)에 적어 두면 `orchestration.run` 이 읽는다.

## 구성 파일

| 파일 | 역할 |
|---|---|
| `SKILL.md` | 진행자 지침 — 전 구간 공통(트리거·절대 규칙·새 책 절차) |
| `checklist/README.md` | 구간② 진행 절차(역할 ↔ 지침 문서·원칙·실패 시) |
| `books.json` | 책 목록 매니페스트(SSOT) — 홈·레일·엔진 선택 |
| `books/<slug>/tree.json` | **체크리스트(조건 트리)** — 심판이 쓴 최종본 |
| `books/<slug>/tree_candidates/` · `scenarios.json` | 이중 추출 — 규칙 목록 `<a|b>.rules.json`·트리 `<a|b>.json` · 원문 사례 |
| `books/<slug>/source_index.json` | 원문 소절 인덱스(본문 없음 — 키·제목·줄범위·해시) |
| `books/<slug>/playbook.html` · `books/trend/source.md` | 플레이북 원본(책 페이지 HTML) · 데모 책 원문(자작) |
| `books/<slug>/positions.json` | 내 포지션(커밋 안 함 — 로컬 화면에서만 매도·분할 판정, 형식은 `SETUP.md`) |
| `books/<slug>/backtest.json` · `books/<slug>/logs/` | 런타임 산출물(커밋 안 함) — 백테스트 탭 데이터 · 책별 로그(판정 문장·백테스트·심판 덤프) |
| `shared/paths.py` | 경로 한 곳 — 책 산출물 경로(`book_dir`·`book_file`·`playbook_html`…)를 짓는 유일한 코드(`verify_code` 주인 표) |
| `checklist/EXTRACTOR.md` · `SCENARIO.md` · `JUDGE.md` | 추출자 · 사례 작성자 · 심판 지침(역할마다 하나 — 서브에이전트 프롬프트 정본) |
| `checklist/COND_DSL.md` | 트리 문법(트리를 쓰는 추출자·심판의 참고서) |
| `checklist/verify_tree.py` | 트리 검사(트리를 만들지 않음) |
| `web/ui/*.js` · `web/inject_ui.py` | 화면 JS(책 무관 공유) · 페이지 주입 |
| `checklist/tree_gateway.py` · `cond.py` · `grade.py` | 구간② 공개 DSL — 트리 출입구 · 문법·평가기 · 등급의 뜻(등급·금액·비중·워밍업) |
| `trading/judge.py` · `timeline.py` · `trades.py` · `portfolio.py` · `backtest.py` | 판정기(Judge·Decision·Holding) · 시간 축 · 체결 워크(분할·매도) · vectorbt 계산기 · 백테스트 |
| `shared/md_feed.py` | **jhts 시세 창구 — 유일한 수집 입구**(없으면 수집 요청) |
| `web/verdict_view.py` · `trading/notify.py` | 판정 JSON·알림 문장(books.json engine.daily) · 알림 송신(텔레그램·데스크톱) |
| `web/book_page.py` · `web/serve.py` · `web/build_home.py` · `web/backtest_page.py` | 페이지 조립 · 로컬 실시간 서버 · 홈 · 백테스트 탭 데이터 |
| `playbook/book_source.py` · `playbook/verify_source_integrity.py` · `playbook/pages.py` | 원문 소절 인덱스 · 플레이북 본문 무결 · 책 페이지 찾기·신선도 |
| `playbook/book_sources.json` · `playbook/source_baseline.json` | 원문 위치 · 본문 해시 기준(커밋 대상) |
| `SETUP.md` · `RUN.md` | 설치·스케줄 등록 · 로컬 서버/폰에서 보기 |
