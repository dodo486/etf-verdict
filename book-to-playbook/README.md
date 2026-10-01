# book-to-playbook

트레이딩 책을 읽어 **① 저자 매매기법 플레이북 + ② 기계가 실행하는 체크리스트(조건 트리)**를 인터랙티브 웹으로 만들고,
**jhts 시세를 붙여 매일 자동 판정**까지 하는 파이프라인.

- 데모(공개 웹): `/trend/` — SPY·QQQ·IWM 추세추종 스윙 · `/moneycopy/` — TQQQ·SOXL·UPRO

## 한 줄 요약

**체크리스트 = 조건 트리(`books/<slug>/tree.json`).** 만드는 곳은 구간② 하나, 읽는 곳은 구간③ 하나다.
화면은 트리를 다시 해석하지 않고 ③이 낸 판정 결과만 그린다. 수집할 시세도 트리에서 나온다(수집 요청서 없음).

## 팀 구조 (폴더 = 조직도)

팀 코드는 **자기 팀 + shared/**만 import 한다 — 팀 사이 인터페이스는 산출물 파일(`books/<slug>/*.json`)이다.
경계는 `verify_teams.py` 가 매 발행마다 기계로 강제한다.

| 폴더 | 구간 | 하는 일 | 산출물(다음 팀의 입력) |
|---|---|---|---|
| `playbook/` | ① 책 원본 → 플레이북 | 원문 소절 인덱싱 · 플레이북 본문 무결 | `source_index.json` · `<slug>-playbook.html` 의 `#src` |
| `checklist/` | ② 플레이북 → 체크리스트 | 조건 트리 추출·검사·채택 · 화면 UI | **`books/<slug>/tree.json`** |
| `verdict/` | ③ 체크리스트 → 수집·판정 | 트리가 쓰는 심볼 수집(jhts) · 판정 · 백테스트 | `latest-verdict-<slug>.json` · `backtest-<slug>.json` |
| `shared/` | 공통층 | **트리의 뜻 한 벌**(cond 문법·tree_grade 판정·trades 체결) · **시세 창구 md_feed** · paths·pages·notify | — |
| `publish/` | 발행·서빙층 | 페이지 조립(정적 발행·로컬 서버 같은 함수) · 홈 | `PUBLIC/<slug>/index.html` |
| (루트) | 조립·감사 | `run.py`(러너) · `verify_structure.py`(구조·책 계약) · `verify_teams.py`(경계) | — |

트리의 뜻(문법·등급·체결)을 shared/ 에 한 벌만 두는 이유: ②가 트리를 검사할 때 본 동작과 ③이 판정할 때의 동작이
**같은 코드**여야 둘이 갈라지지 않는다.

```
책 원문 ──[① book_source]──▶ source_index.json (소절 키 = 체크리스트 ref 의 기준)
   │
   └─[① 플레이북 작성·원문 대조 감사]──▶ <slug>-playbook.html #src
                                  │
        [② 추출자 a·b(서로 모름) → 원문 사례 → 갈린 날 심판 → --adopt] ──▶ tree.json (체크리스트)
                                  │
   [③ cond.symbols_of(tree) → md_feed.histories(jhts, 없으면 수집 요청) → tree_grade → verdict_engine]
                                  │                                   └──▶ 알림 · latest-verdict-<slug>.json
                                  │
             [publish.assemble: 판정 + ui/*.js + 레일 + 원문 + 백테스트] ──▶ 공개 페이지 / 로컬 실시간
```

## 체크리스트 — 판정 여섯 칸 (`checklist/COND_DSL.md`)

| 칸 | 묻는 것 | 결과 |
|---|---|---|
| `filter` | 들어가도 되는 시장인가 | 거짓 → 🚫 진입 금지 |
| `avoid` | 사면 안 되는 자리인가 | 참 → ⛔ 보류 |
| `entry` | 살 자리인가 | 참 → ✅ 매수 후보 · 거짓 → ⚪ 관망 |
| `caution` | 사더라도 금액을 줄일까 | 걸린 규칙마다 금액 × scale (폭 미명시면 표시만) |
| `sizing` | 얼마나(비중)·나눠서(분할) | 총 투자금 대비 % · 차수별 비율(미명시면 null) |
| `exit` | 보유분을 언제 얼마나 팔까 | 걸리면 다음 날 시가 매도 · 내 포지션(로컬 파일) 기준 판정 |

시장 환경 점수·공격/균형/방어 모드·폭락 후 재진입처럼 **상품 여럿이 같이 보는 판단은 `defs` 에 한 번** 정의해
각 칸이 참조한다(화면 맨 위 '공통 조건'). 자동으로 알 수 없는 조건은 `manual` 로 남기고 사유 머리를 단다:
`저자 미명시:`(🟡가 정답) · `데이터 없음:`(jhts 수집 요청·데이터 연결 과제) · `연산 없음:`(원시 연산 추가 과제).

봉 단위(`tf`)는 시세 노드의 속성이다 — 일봉·분봉을 따로 다루지 않는다. 지금 연결된 데이터는 일봉이라 `1d` 만 허용된다.

## 검증층 — 검사기 3개 (발행 관문, `run.py`)

| # | 검사기 | 보는 것 |
|---|---|---|
| ① | `verify_structure` | 팀 경계 · 플레이북 본문 해시 · 책 계약(소절 인덱스·트리 문법·트리 ref 가 실제 소절·페이지 구획과 UI 사본) |
| ② | `verdict.verify_primitives` | 원시 연산·체결·금액 판정을 pandas 기준값·손계산과 대조 · 3값 논리 전수 · 인과성 · 문법. 책이 늘어도 크기 고정 |
| ③ | `checklist.verify_tree` | 체크리스트가 원문 뜻대로 **동작**하나 — 이중 추출을 실제 시세 3년으로 칸별 비교(갈린 칸은 심판 기록 필수) · 원문 사례 재현 · 발화 통계 · 비중 합 100% 초과 정지 · 수동 사유 분류 |

글자 대조 검사(창작·커버리지·규칙↔명세·의미검사)는 의미를 판정하지 못해 없앴다 — 숫자 '2'만 있으면 '2거래일 유지'가
1일로 판정돼도 통과했다. 지금 검사는 전부 **실행**으로 본다.

## 새 책 추가하는 법

1. **원문 자르기**(①): `book_sources.json` 에 원문 위치 → `python -m playbook.book_source --write` (소절 인덱스).
2. **플레이북**(①): 원문 소절마다 본문 + 요약 bullet. 저자 명시분만·원문 숫자·미명시 표기. 끝나면 **원문 대조 감사**
   (요약 bullet 에 원문에 없는 숫자·칸 배치가 섞이기 쉽다) → `python -m playbook.verify_source_integrity --accept --why "새 책"`.
3. **체크리스트**(②): 서로 모르는 추출자 a·b 가 플레이북만 보고 `tree_candidates/a.json`·`b.json`(매도는 `exit_a`·`exit_b`) +
   표현 못 한 규칙(`unexpressed`) → 다른 작성자가 원문만 보고 `scenarios.json` → `python -m checklist.verify_tree <slug> --dump 6`
   → 심판이 원문과 대조해 `tree_review.json` → `--adopt`(+`--adopt-exits`) → `python -m checklist.verify_tree <slug>` 통과.
4. **페이지**: `trend-playbook.html` 을 베이스로 `#src` 와 머리말만 교체(시트 패널은 `#verdict-data` + `#sheet-root` 골격 그대로).
5. **등록**: `books.json` 에 항목(slug/title/tickers/desc/live/engine). `python -m verify_structure` 의 책 계약이 통과해야 한다.
6. **배포**: `python run.py daily`.

수집 요청서는 없다 — 트리가 쓰는 심볼이 곧 수집 목록이고, jhts 에 없는 심볼은 수집 요청이 자동으로 남는다.

## 실행

```
python run.py daily        # 판정 → 백테스트 → 발행 → 검사 3종 → (통과 시) git 커밋·푸시
python run.py watch        # 저자가 말한 시각(예: 개장 10분 전)마다 기다렸다 판정 → 발행 (매일 밤 한 번 띄움)
python run.py publish      # 재판정 없이 발행만
python -m verdict.verdict_engine <slug> [--json] [--no-send]   # 오늘 판정
python -m verdict.backtest <slug> [--days 365] | --page        # 백테스트(로그 / 페이지 탭 데이터)
python -m publish.serve                                         # 로컬 실시간 서버(RUN.md)
```

환경: jhts 시세 패키지가 pip 설치가 아니면 `PYTHONPATH=<jhts 경로>` 를 줘야 시세가 들어온다(없으면 판정이 ❔).

## 구성 파일

| 파일 | 역할 |
|---|---|
| `SKILL.md` | 스킬 정의(트리거·새 책 절차) |
| `books.json` | 책 목록 매니페스트(SSOT) — 홈·레일·엔진 선택 |
| `books/<slug>/tree.json` | **체크리스트(조건 트리)** — 채택본 |
| `books/<slug>/tree_candidates/` · `scenarios.json` · `tree_review.json` | 이중 추출 후보 · 원문 사례 · 심판 기록 |
| `books/<slug>/source_index.json` | 원문 소절 인덱스(본문 없음 — 키·제목·줄범위·해시) |
| `books/<slug>/positions.json` | 내 포지션(커밋 안 함 — 로컬 화면에서만 매도·분할 판정) |
| `checklist/COND_DSL.md` | 조건 트리 작성 지침 |
| `checklist/verify_tree.py` | 트리 검사·채택 |
| `checklist/ui/*.js` · `checklist/inject_ui.py` | 화면 JS(책 무관 공유) · 페이지 주입 |
| `shared/cond.py` · `shared/tree_grade.py` · `shared/trades.py` | 트리 문법·평가기 · 판정(등급·금액·비중·포지션) · 체결(분할·매도) |
| `shared/md_feed.py` | **jhts 시세 창구 — 유일한 수집 입구**(없으면 수집 요청) |
| `verdict/verdict_engine.py` · `verdict/backtest.py` | 오늘 판정 · 과거 신호·거래 성적 |
| `publish/publish_pages.py` · `publish/serve.py` · `publish/build_home.py` | 페이지 조립·발행 · 로컬 실시간 서버 · 홈 |
| `playbook/book_source.py` · `playbook/verify_source_integrity.py` | 원문 소절 인덱스 · 플레이북 본문 무결 |
| `playbook/book_sources.json` · `playbook/source_baseline.json` | 원문 위치 · 본문 해시 기준(커밋 대상) |
| `SETUP.md` · `RUN.md` | 설치·스케줄 등록 · 로컬 서버/폰에서 보기 |
