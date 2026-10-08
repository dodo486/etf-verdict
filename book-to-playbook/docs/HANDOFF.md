# 이어받기 — 할 일의 정본 (여기 한 곳)

> 할 일은 이 파일에만 적는다(다른 곳에 TODO 파일을 만들지 않는다 — `verify_code` 가 막는다).
> 구조·원칙은 `docs/ARCHITECTURE.md`, 세션 규칙은 레포 맨 위 `CLAUDE.md`.
> 마지막 갱신 2026-10-08 · 작업 브랜치 `work/pre-run3`(origin 푸시됨, `main` 에는 아직 안 합침).

## 0. 다음에 할 일 (한 줄)

**트리 v3 확정 → 코드 반영(5) → run3(6).** 초안 = `docs/action-grammar-draft.md`(미확정 — 사용자 검토 중).

## 1. 지금 상태

- tree.json 이 없다 → 판정 화면·백테스트는 tree 가 생겨야 돈다. `python -m orchestration.run check` 는 이 2건
  (`verify_tree --contract`·`verify_tree` 의 "tree.json 없음")만 정지하고 나머지 6개 통과가 정상.
- 검증용 픽스처: run2 후보 `books/moneycopy/tree_candidates/a.json` 을 잠깐 `tree.json` 으로 복사해 돌린다(커밋 금지).
  시세는 `ETF_DEV_CACHE=<캐시 폴더>` 로 고정하면 전후 비교가 같은 값으로 된다.

## 2. 2026-10-08 해결된 것

| 커밋 | 내용 |
|---|---|
| `9a1dedc` | **TreeGateway** — tree.json 을 읽는 유일한 출입구(`checklist/tree_gateway.py`) |
| `fdbc361` | 창 길이·lag 가 `"?"` 인 식에서 판정 화면이 죽던 버그 |
| `005355b` | shared 분리 — DSL(문법·등급)은 `checklist/`, shared 는 시세 창구·경로만 |
| `423cbdc` | 구간② a·b 비교는 규칙 식으로만(매매 시뮬레이션 비교 제거) |
| `5caf628` | **trading/**(판정·백테스트·장중: Judge·Decision·Holding·Timeline) + **web/**(화면 가공 전부) |
| `feadb10` | 책 산출물을 `books/<slug>/` 한 곳으로 |
| `5fb6577` | 검사 정리 — `verify_code`(폴더 경계 + 주인 표) · `run check` 하나 |
| `091fb09` | 지표별 전용 연산 계획(ATR·VWAP) 폐기 — 기본 부품 + 조합 예시로 |
| `fa1c4e6` | `CLAUDE.md` · `docs/ARCHITECTURE.md` · 트리 v3 초안 |
| `9df494a` | **표준 매도 폐지** — 매도 규칙 없는 책은 매수 신호 후 N일 보유 수익률로만(`trades.exit_policy`) |
| `ea289b5` | **백테스트가 '얼마나' 반영** — 비중 × 분할 × 조심 배수, 수량 변환은 `trades.to_units` 하나(매수·매도 공통). 모름은 ×1·예산 100% + 횟수 표시 |
| `a09b200` | **서버 권위** — 화면 JS 등급 재계산 삭제, 수동 체크는 `POST /api/verdict` 로 서버가 판정 |
| 마지막 커밋 | 할 일 문서 통합(이 파일) — `checklist/TODO.md`·`trading/TODO.md`·`docs/web-consolidation-plan.md` 흡수·삭제 |

## 3. 남은 일 (순서대로)

### 5. 트리 v3 코드 반영 — 초안 `docs/action-grammar-draft.md` 확정 뒤
- 칸 6개 → `rules` 하나(동사 안 산다·산다·판다, `qty {of, x}`, `"?"` 통일, `{"rule": 이름}`, 갈래, `skip`·`why`).
  바꿀 곳은 `TreeGateway` 와 DSL(`checklist/`) 안 — 소비자는 이미 출입구 API·`Qty`·`to_units` 를 쓴다.
- **계산기 부품 정리(초안 9절)**: `pct`·`rsi`·`count`·`streak`(·`ma` 검토) 삭제, `ema`→`smooth`, `stdev`→`sqrt`,
  새 기본 부품(세션 시작·`sumsince`·`smooth`·`sqrt`·순위, 후보: 세션 경과 시간 — 개장 캘린더 `md_feed.sessions().open`).
  **pandas 로 다시 구현.** 지울 흔적 목록은 초안 9절. 주인 표에 '지운 연산 이름 금지' 줄 추가.
- 검사기 추가: 같은 식 두 벌 · 같은 값 다른 규칙 · 매일 결과 같음 · 효과 없는 규칙 · 원문 소절 누락 · `ref` 형식(`·`).
- 지침 갱신: `COND_DSL`·`EXTRACTOR`(산출물 한 파일 — `--lint` 불필요)·`JUDGE`(판례 = 갈린 곳 → 사용자 승인 후 지침)·`SCENARIO`(기대값 = 그날 결과).
- 옛 TODO 가 여기로 모였다: 매도 비율 `"?"`(③) · 이름 심볼 `names`(⑥) · 판례(⑧) · 누적 상한(`pos sold`) ·
  규칙 목록 형식(`not`·항목 참조 = `{"rule"}`) · 세션 연산(기본 부품 조합) · verify_tree 읽기 쉬운 보기(v3 로 불필요해질 것).

### 6. run3 — tree.json 다시 만들기 (키스톤)
- 순서: 구간① 전사 → 구간② 추출 a·b(서로·최종·사례 안 봄, 각자 다른 서브에이전트) → 사례 작성자(트리 안 봄) → 심판 →
  `python -m checklist.verify_tree <slug>` exit 0. 옛 후보·`scenarios.json` 은 폐기하고 새로.
- 절차 정본 `checklist/README.md`, 역할 지침 `playbook/PLAYBOOK.md` · `checklist/EXTRACTOR.md` · `SCENARIO.md` · `JUDGE.md`.
- 원문 위치 `playbook/book_sources.json`(trend = `books/trend/source.md`, moneycopy = `~/jhts/hypotheses/sources/미국-돈복사-ETF-투자방법.md`).
- 끝나면 `main` 에 합치기(사용자 승인).

### 그 뒤
- **`observe` 레거시 제거** — 엔진(`checklist/cond.py`)에만 남은 옛 포장재. 제대로 지우려면 "장중 데이터 없음 None →
  실전 🟡 / 백테스트 EXCLUDED" 자동 처리를 먼저 깔아야 한다(워밍업 None 과 구별하는 표식 필요). tree 생긴 뒤 파리티로 증명.
  영향: `cond`·`grade`·`verify_primitives`·`verify_tree`·`trading/backtest`·`timeline`·`COND_DSL`.
- **백테스트 계산기 버그** — `portfolio` 가 1 unit = 시작자본 고정이라 손실 뒤 다음 진입이 남은 현금보다 클 수 있다
  (옛 표준 매도 사본에서 SOXL −162% 관측). 잔고 기준 사이징으로.
- **판정 JSON 의 `grade_rules` 빼기** — 서버 권위 뒤 화면이 안 쓴다(다음 출력 변경 때).
- **웹 백테스트 탭 지표 채우기**(총수익·MDD·샤프·자산곡선 — 표시 코드는 있음) · **장중 손익 백테스트**(분봉이 길게 쌓이면
  `replay → portfolio.run_product`, 지금은 분봉 ~7일이라 보류) · tree 재생성 뒤 `python -m trading.verify_trading --parity` 실측.
- **무인 판정을 막는 수동 조건** — (가) 연산으로 풀 것 = v3 기본 부품 조합 · (나) 데이터가 없는 것 = 실적 캘린더 · 뉴스 시각 ·
  지수 구성종목 등락(breadth) · 개인 매매 기록 — 외부 소스 생기기 전엔 서버 권위 수동 답으로 '1회 답'까지 · (다) 정성 판단 = 수동 답.
- **jhts 실데이터 교체 + yfinance 임시 흔적 삭제**(`MIGRATION_NOTES.md` 체크리스트).
- **이번 범위 밖**(트리 v3 에서 `skip` "연산 없음"으로 드러남): 계좌 전체 기준 · 종목 간 돈 이동 · 지난 매매 이력.

## 4. 참고 문서 (할 일 없음)

| 문서 | 내용 |
|---|---|
| `docs/ARCHITECTURE.md` | 구조·원칙 12개·변경 규율·검사 |
| `docs/action-grammar-draft.md` | 트리 v3 초안(미확정) |
| `docs/data-contract.md` | jhts 일봉·분봉 계약(md_feed 가 기대하는 것 vs 주는 것) |
| `checklist/README.md` 외 지침 | 구간② 절차·역할 |
| `MIGRATION_NOTES.md` | 옛 이관 기록 |

## 5. 검증 명령

```
python -m orchestration.run check            # 전부(CHECKS 한 목록) — 요약 + 종료코드
python -m orchestration.verify_code           # 코드 규칙 — 폴더 경계 + 주인 표
python -m checklist.verify_tree <slug>        # 트리 동작 (--contract = 책 계약)
python -m trading.verify_trading --parity     # 판정 = 백테스트 일치(시세 필요)
```
