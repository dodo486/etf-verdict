# book-to-playbook

트레이딩 책을 읽어 **① 저자 매매기법 플레이북 + ② 기계가 실행하는 체크리스트(조건 트리)**를 인터랙티브 웹으로 만들고,
**jhts 시세를 붙여 매일 자동 판정**까지 하는 파이프라인.

- 데모(공개 웹): `/trend/` — SPY·QQQ·IWM 추세추종 스윙 · `/moneycopy/` — TQQQ·SOXL·UPRO

## 한 줄 요약

**체크리스트 = 조건 트리(`books/<slug>/tree.json`).** 만드는 곳은 구간② 하나, 읽는 곳은 구간③ 하나다.
화면은 트리를 다시 해석하지 않고 ③이 낸 판정 결과만 그린다. 수집할 시세도 트리에서 나온다(수집 요청서 없음).

## 구조·원칙·검사

폴더 구조, 아키텍처 원칙, 검사 목록은 **`docs/ARCHITECTURE.md` 한 곳**에 있다. 할 일은 `docs/HANDOFF.md`.

## 체크리스트 — 규칙 목록 · 동사 셋 (`authoring/checklist/COND_DSL.md`)

트리는 **규칙 목록**이다(원문 판단 하나 = 규칙 하나). 규칙의 갈래는 동사 셋 중 하나를 한다:

| 동사 | 묻는 것 | 결과 |
|---|---|---|
| `안 산다` | 사면 안 되는 시장·자리인가 | 갈래 하나라도 참 → ⛔ 안 산다 |
| `산다` | 살 자리인가 · 얼마나(`qty` cash = 비중 % · budget = 분할 비율) | 참 → ✅ 산다 · 둘 다 아님 → ⚪ 관망 |
| `판다` | 보유분을 언제 얼마나 팔까(`qty` bought·held) | 걸리면 다음 봉 시가 매도 · 내 포지션(로컬 파일) 기준 판정 |

수동 조건 때문에 정해지지 않으면 🟡 확인 대기, 데이터가 모자라면 ❔ 판정 불가(사다리 정본 `dsl/grade_rules.json`).
여러 규칙이 같이 보는 측정(장전 점수·모드 등)은 **이름 하나로** 두고 `{"rule": 이름}` 으로 참조한다(화면은 on 없는 규칙을
'공통 시장 신호'로 한 번 모은다). 조건의 신원은 식이다 — 저자가 숫자를 안 준 조건도 식으로 쓰고 그 숫자 자리만
`"?"`(사람이 판단 — 🟡). 식으로 쓸 수 없는 것만 문장 수동: `저자 미명시: …(정성)` · `데이터 없음:`(수집·연결 과제) ·
`연산 없음:`(원시 연산 추가 과제). 문법 정본은 `authoring/checklist/COND_DSL.md`, 작성 규칙은 역할 문서.

봉 단위(`tf`: 1d·1m·5m)는 시세 노드의 속성이다 — 일봉·분봉을 따로 다루지 않는다. 데이터 연결 여부는 트리와 무관하다.

## 새 책 추가하는 법

1. **원문 자르기**(①): `book_sources.json` 에 원문 위치 → `python -m authoring.playbook.book_source --write` (소절 인덱스).
2. **플레이북**(①): 원문 소절마다 본문 + 요약 bullet. 저자 명시분만·원문 숫자·미명시 표기. 끝나면 **원문 대조 감사**
   (요약 bullet 에 원문에 없는 숫자·칸 배치가 섞이기 쉽다) → `python -m authoring.playbook.verify_source --accept --why "새 책"`.
3. **체크리스트**(②): 역할마다 지침 문서 하나 — 추출자 a·b(`authoring/checklist/EXTRACTOR.md`, 서로 모름)가 플레이북만 보고
   규칙 목록 `<a|b>.rules.json` → 트리 `<a|b>.json` → 사례 작성자(`authoring/checklist/SCENARIO.md`)가 원문만 보고 `scenarios.json`
   → 심판(`authoring/checklist/JUDGE.md`)이 비교 도구(`python -m authoring.checklist.compare <slug>`)로 다른 곳을 보고 원문과 대조해 최종 `tree.json`(규칙마다 `why`)을 직접 쓴다
   → `python -m authoring.checklist.verify_tree <slug>` 통과.
4. **페이지**: `books/trend/playbook.html` 을 베이스로 `#src` 와 머리말만 교체(시트 패널은 `#verdict-data` + `#sheet-root` 골격 그대로).
5. **등록**: `books.json` 에 항목(slug/title/tickers/desc/live/engine). `python -m entry.run check` 가 통과해야 한다.
6. **배포**: `python -m entry.run daily`.

수집 요청서는 없다 — 트리가 쓰는 심볼이 곧 수집 목록이고, jhts 에 없는 심볼은 수집 요청이 자동으로 남는다.

## 실행

```
python -m entry.run daily        # 판정 → 백테스트 탭 데이터 (검사는 돌지 않는다)
python -m entry.run check [--parity]   # 검사 전부(CHECKS) — 무언가 바꿨을 때(커밋 전). 요약 + 종료코드
python -m entry.run watch [--every N] # asof=지금 기준 N분(기본 5)마다 재판정(백테스트 제외) — 장중 조건은 분봉이 연결되면 살아난다
python -m consumers.display.verdict_view <slug> [--json] [--no-send]       # 오늘 판정(판정 JSON·알림)
python -m consumers.backtest.runner <slug> [--days 365]   # 백테스트(로그·JSON)
python -m consumers.display.backtest_page <slug>                            # 책 페이지 '백테스트' 탭 데이터
python -m entry.serve                                           # 로컬 실시간 서버(SETUP.md §7)
```

환경: jhts 시세 패키지가 pip 설치가 아니면 `PYTHONPATH=<jhts 경로>` 를 줘야 시세가 들어온다(없으면 판정이 ❔).
스케줄러로 돌릴 때는 `local.env`(커밋 안 함, `local.env.example` 참고)에 적어 두면 `entry.run` 이 읽는다.

## 구성 파일

| 파일 | 역할 |
|---|---|
| `SKILL.md` | 진행자 지침 — 전 구간 공통(트리거·절대 규칙·새 책 절차) |
| `authoring/checklist/README.md` | 구간② 진행 절차(역할 ↔ 지침 문서·원칙·실패 시) |
| `books.json` | 책 목록 매니페스트(SSOT) — 홈·레일·엔진 선택 |
| `books/<slug>/tree.json` | **체크리스트(조건 트리)** — 심판이 쓴 최종본 |
| `books/<slug>/tree_candidates/` · `scenarios.json` | 이중 추출 — 규칙 목록 `<a|b>.rules.json`·트리 `<a|b>.json` · 원문 사례 |
| `books/<slug>/source_index.json` | 원문 소절 인덱스(본문 없음 — 키·제목·줄범위·해시) |
| `books/<slug>/playbook.html` · `books/trend/source.md` | 플레이북 원본(책 페이지 HTML) · 데모 책 원문(자작) |
| `books/<slug>/positions.json` | 내 포지션(커밋 안 함 — 로컬 화면에서만 매도·분할 판정, 형식은 `SETUP.md`) |
| `books/<slug>/backtest.json` · `books/<slug>/logs/` | 런타임 산출물(커밋 안 함) — 백테스트 탭 데이터 · 책별 로그(판정 문장·백테스트·심판 덤프) |
| `shared/paths.py` | 경로 한 곳 — 책 산출물 경로(`book_dir`·`book_file`·`playbook_html`…)를 짓는 유일한 코드(`entry.verify_rules` 주인 표) |
| `authoring/checklist/EXTRACTOR.md` · `SCENARIO.md` · `JUDGE.md` | 추출자 · 사례 작성자 · 심판 지침(역할마다 하나 — 서브에이전트 프롬프트 정본) |
| `authoring/checklist/COND_DSL.md` | 트리 문법(트리를 쓰는 추출자·심판의 참고서) |
| `authoring/checklist/verify_tree.py` | 트리 채점(트리를 만들지 않음) · `--quick` 트리 계약(소절·트리 문법·ref) |
| `authoring/checklist/compare.py` | 심판 비교 도구(a·b 덤프) · '같은 뜻' 잣대(채점기도 이것으로) |
| 각 층의 `verify_*.py` | 검사 — 검사하는 대상 옆에 둔다(`dsl/verify_primitives` · `signals/verify_view` · `consumers/backtest/verify_trading` · `consumers/display/verify_page` · `entry/verify_rules` 등). 전부 한 번에 `python -m entry.run check` |
| `consumers/display/ui/*.js` · `consumers/display/inject_ui.py` | 화면 JS(책 무관 공유) · 페이지 주입 |
| `dsl/tree_gateway.py` · `tradeTool.py` | 구간② 공개 DSL — 트리 출입구 · Cond(문법·평가기) · Grade(등급의 뜻 — 등급·금액·비중·워밍업·시세 조달) |
| `signal/{judge,engine}.py` · `consumers/backtest/{trades,portfolio,runner}.py` · `consumers/notify/{telegram,desktop}.py` | ① 신호(판정기·라이브 엔진) · ② 백테스트 소비(체결·vectorbt 돈·러너) · ② 알림 소비 |
| `market/md_feed.py` | **jhts 시세 창구 — 유일한 수집 입구**(없으면 수집 요청) |
| `consumers/display/verdict_view.py` · `consumers/notify/{telegram,desktop}.py` | 판정 JSON·알림 문장(books.json engine.daily) · 알림 송신(텔레그램·데스크톱) |
| `consumers/display/book_page.py` · `entry/serve.py` · `consumers/display/build_home.py` · `consumers/display/backtest_page.py` | 페이지 조립 · 로컬 실시간 서버 · 홈 · 백테스트 탭 데이터 |
| `authoring/playbook/book_source.py` · `authoring/playbook/verify_source.py` · `authoring/playbook/pages.py` | 원문 소절 인덱스 · 플레이북 본문 무결 · 책 페이지 찾기·신선도 |
| `authoring/playbook/book_sources.json` · `authoring/playbook/source_baseline.json` | 원문 위치 · 본문 해시 기준(커밋 대상) |
| `SETUP.md` | 설치·스케줄 등록 · 로컬 서버/폰에서 보기 |
