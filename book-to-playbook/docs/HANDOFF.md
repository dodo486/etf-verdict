# 이어받기 가이드 (리팩토링 진행 상황 · 남은 일)

> 2026-10-08 세션 핸드오프. 사장님 3대 기획의도에 맞춰 구조를 정리하는 중.
> 설계 정본: 같은 폴더의 `web-consolidation-plan.md`(웹 통합·서버권위) · `remaining-work-spec.md`(#2 데이터/지표·#3 무인판정).

## 사장님 3대 기획의도 (근본 기준)

1. **리팩토링** — 1폴더=1구간=1기능, 코드 독립 교체 쉽게. 웹은 판정(tree.json/verdict JSON)만 받아 **보여주기만**.
2. **만능툴** — 특정 책/특정 데이터에 안 묶임. 아무 타이밍(장중/마감/장후) + 일봉 고정 탈피(분봉·거래량·변동성·차트 등 책마다 보는 핵심지표 다 수용).
3. **무인 자동판정** — 사람 개입 없이 책 한 권을 데이터까지 알아서 판정.

### ★절대 원칙 (전 작업 공통)
- **특정 책에 맞게 코드를 그럴싸하게 고치지 않는다.** 버그를 만나면 "공통코드가 왜 이 책에선 안 먹히지?" 관점으로 **어떤 책이든 먹히는 상위 로직**을 고친다.
- 데이터 없으면 "없다"고 정직하게(지어내지 않음). 저자 미명시 숫자는 `"?"`(수동 판단).

## ✅ 이번 세션 완료 (origin/main 푸시됨)

| 커밋 | 내용 |
|---|---|
| `99563a1` | shared 소유자 분리 — pages→구간①(playbook), notify→구간③(verdict). 공용 핵심(cond·tree_grade·trades·md_feed·paths)은 shared 유지 |
| `e09a19c` | GitHub Pages(정적배포) 잔재 전면 제거 + 책-하드코딩 폴백 제거. 화면=로컬 서버(serve) 단일 모델 |
| `d548a71` | 화면 표시층(JS 7개 + inject_ui) checklist(구간②)→publish 이관. **구간②는 트리 생산만** |
| `7b2fed7` | 루트 조립·감사 코드(run·verify_structure·verify_teams)→`orchestration/` 층. **루트 .py = 0**. + stale 버그 수정(e09a19c 후유증) |

**현재 폴더 구조(1폴더=1구간/층 — 2026-10 구조 개편):**
`playbook/`(① 원문→전사본) · `checklist/`(② 전사본→tree.json + DSL: `tree_gateway`·`cond`·`grade`) ·
`trading/`(③ 판정·백테스트·장중: `judge`(Judge·Decision·Holding)·`timeline`·`trades`·`portfolio`·`backtest`·`replay`·`watch`·`notify`) ·
`web/`(화면: `verdict_view`·`condition_view`·`backtest_page`·`book_page`·`serve`·`ui/`) · `shared/`(시세 창구 `md_feed`·`paths`) · `orchestration/`(실행·감사)
import 방향: `shared ← playbook · checklist(공개 DSL) ← trading ← web` (`verify_code` 폴더 경계 규칙 1).
책 산출물은 전부 `books/<slug>/`(커밋: `playbook.html`·`source.md`·`source_index.json`·`tree.json`·`tree_candidates/`·`scenarios.json` / 런타임: `backtest.json`·`logs/`·`positions.json`) — 경로는 `shared/paths.py` 하나(`verify_code` 주인 표).
실행: `python -m orchestration.run <daily|verdict|watch>` · 검사 `python -m orchestration.run check`(목록 = run.py CHECKS 하나)
트리(`tree.json`) 읽기 = `checklist/tree_gateway.py` 의 **TreeGateway 하나**(형식 검사·탐색). 나머지 코드는 원본 키를 직접 읽지 않는다
(`verify_code` 주인 표 '트리 원본 키') — 트리 형식(여섯 칸 → rules 목록) 교체 시 TreeGateway + 문법(`checklist/cond.py`)만 고친다.
판정은 라이브·백테스트·재생 모두 `trading.judge.Judge` 하나를 지난다(라이브 = 달력 마지막 봉 `latest()`).

## 🔴 키스톤 — tree.json 재생성 (모든 게 이걸로 막힘)

`books/*/tree.json` 이 레포에 없다(구간② 개편으로 "심판이 그때그때 생성"). 이게 없어 판정·백테스트·서버·파리티검증이 전부 멈춤(`checklist.verify_tree --contract` 책계약 실패).

**순서(사장님 지시로 정정): 구간①(전사)부터 → 구간②(추출 a·b) → 심판 → verify_tree.**
- 옛 후보(tree_candidates)는 바뀐 `EXTRACTOR.md`(`9b7b47c`)·전사 재정의(`99c4048`) 이전 것이라 **폐기, 새로 뽑아야 함.**
- 절차 정본: `checklist/README.md`. 역할별 지침 = `playbook/PLAYBOOK.md`(전사) · `checklist/EXTRACTOR.md`(추출 a·b, 서로 모름) · `checklist/SCENARIO.md`(사례) · `checklist/JUDGE.md`(심판).
- **독립성이 검증 근거** — 추출 a·b는 서로/최종/사례 안 봄, 사례 작성자는 트리 안 봄. 각자 다른 서브에이전트.
- 게이트: `python -m checklist.verify_tree <slug>` exit 0.
- 원문 위치: `playbook/book_sources.json` (trend=`books/trend/source.md`, moneycopy=`~/jhts/hypotheses/sources/미국-돈복사-ETF-투자방법.md`).

## 🟡 키스톤 이후 (순서 있음 — 둘 다 cond.py 고쳐서 동시 금지)

1. **계산기 부품** — 지표별 전용 연산(ATR·VWAP 등)은 만들지 않는다. 기본 부품 + 조합 예시, pandas 구현 — 트리 v3 와 함께(`docs/action-grammar-draft.md` 9절).
2. **A 서버권위(적② 제거)** — 화면이 등급을 직접 재계산하는 중복(`web/ui/checklist-ui.js` 의 `ev/and3/or3/gradeKey/cautionOf`) 제거 — 끝나면 `orchestration/verify_code.py` 주인 표 '등급 사다리' 행의 TEMPORARY 허용 줄도 지운다. `cond.Ctx` 에 조건별 수동답 맵 추가 → `web.verdict_view.render(answers=)` → `web/serve.py` in-process → 마지막에 JS 평가기 삭제. **tree.json 재생성 뒤 파리티 검증(화면 등급==엔진 등급) 가능.** 상세 = `web-consolidation-plan.md` §4.


## 검증 명령 (venv = `book-to-playbook/.venv`)
```
python -m orchestration.run check            # 아래 전부(CHECKS 한 목록) — 요약 + 종료코드
python -m orchestration.verify_code           # 코드 규칙 — 폴더 경계 + 주인 표
python -m playbook.verify_source_integrity    # 플레이북 본문 해시
python -m checklist.verify_tree --contract    # 책 계약(tree.json 있어야 통과)
python -m web.verify_view --pages             # 책 페이지 구획·UI 사본
python -m checklist.verify_primitives         # 원시연산·등급 계산 검사
python -m trading.verify_trading              # 거래 시뮬레이터·실전 경로 (--parity = 신호 패리티)
python -m web.verify_view                     # 화면 설명 구조
python -m checklist.verify_tree <slug>        # 트리 동작 검사
```
