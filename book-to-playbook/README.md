# book-to-playbook

트레이딩 책을 읽어 **① 저자 매매기법 플레이북 + ② 기계가 실행하는 체크리스트(조건 트리)**를 인터랙티브 웹으로 만들고,
**jhts 시세를 붙여 매일 자동 판정**까지 하는 파이프라인.

- 데모(공개 웹): `/trend/` — SPY·QQQ·IWM 추세추종 스윙 · `/moneycopy/` — TQQQ·SOXL·UPRO

## 한 줄 요약

**체크리스트 = 조건 트리(`books/<slug>/tree.json`).** 만드는 곳은 구간② 하나, 읽는 곳은 구간③ 하나다.
화면은 트리를 다시 해석하지 않고 ③이 낸 판정 결과만 그린다. 수집할 시세도 트리에서 나온다(수집 요청서 없음).

## 구조·원칙·검사

폴더 구조, 아키텍처 원칙, 검사 목록은 **`docs/ARCHITECTURE.md` 한 곳**에 있다. 할 일은 `docs/HANDOFF.md`.

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
python -m trading.backtest <slug> [--days 365]   # 백테스트(로그·JSON)
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
| `checklist/tree_gateway.py` · `tradeTool.py` | 구간② 공개 DSL — 트리 출입구 · Cond(문법·평가기) · Grade(등급의 뜻 — 등급·금액·비중·워밍업·시세 조달) |
| `trading/judge.py` · `trades.py` · `portfolio.py` · `backtest.py` | 판정기(Judge·Decision·Holding·signal_series·truncate) · 체결 워크(분할·매도) · vectorbt 계산기 · 백테스트 |
| `shared/md_feed.py` | **jhts 시세 창구 — 유일한 수집 입구**(없으면 수집 요청) |
| `web/verdict_view.py` · `trading/notify.py` | 판정 JSON·알림 문장(books.json engine.daily) · 알림 송신(텔레그램·데스크톱) |
| `web/book_page.py` · `web/serve.py` · `web/build_home.py` · `web/backtest_page.py` | 페이지 조립 · 로컬 실시간 서버 · 홈 · 백테스트 탭 데이터 |
| `playbook/book_source.py` · `playbook/verify_source_integrity.py` · `playbook/pages.py` | 원문 소절 인덱스 · 플레이북 본문 무결 · 책 페이지 찾기·신선도 |
| `playbook/book_sources.json` · `playbook/source_baseline.json` | 원문 위치 · 본문 해시 기준(커밋 대상) |
| `SETUP.md` · `RUN.md` | 설치·스케줄 등록 · 로컬 서버/폰에서 보기 |
