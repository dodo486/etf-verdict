# 이어받기 — 할 일의 정본 (여기 한 곳)

> 할 일은 이 파일에만 적는다(다른 곳에 TODO 파일을 만들지 않는다 — `entry.verify_rules` 가 막는다).
> 구조·원칙은 `docs/ARCHITECTURE.md`, 세션 규칙은 레포 맨 위 `CLAUDE.md`.
> 마지막 갱신 2026-10-12 · `main` 에 합침(작업 브랜치 work/v3-verbs 는 정리함).

## 0. 다음에 할 일 (한 줄)

**run3 — moneycopy 트리·사례를 v3 로 다시 뽑기(키스톤).** 코드는 3동사·조합 문법으로 바뀌었고, 지금 moneycopy
tree.json 은 지운 연산(pct·count·streak)·옛 `review` 키·옛 종목 모델(`$self`·`$index`·`names`·`across`) 때문에 **문법 검사에서 멈춘다 — 판정 화면·백테스트도 run3 전까지 안 돈다**
(사용자 확정: 트리는 다시 뽑는다). 종목 모델은 **트리 공통 + 해석기가 `$self`·`$index`(products.index) 채움**, `on` 은 저자가 상품을 짚은 규칙만(EXTRACTOR §2.5) — 이 모델로 뽑는다. 남은 v3 코드 일(새 기본 부품 등)은 3절.

## 1. 지금 상태

- `python -m entry.run check` — 정지 2건이 정상: `authoring.extract.verify_tree --quick`(trend 에 tree.json 없음 · moneycopy 트리 문법) ·
  `authoring.extract.verify_tree`(같은 이유 — run3 에서 사라진다). 나머지 6개 통과.
- 화면 머리글 ①안 산다 ②산다 ③판다 ④얼마나(트리가 다시 생기면 그대로 그린다).
- 전후 비교: 시세를 `ETF_DEV_CACHE=<캐시 폴더>` 로 고정하고 판정 JSON(`verdict_view.render`)·백테스트(`runner.run`)를 떠서 diff.

## 2. 2026-10-12 해결된 것 (main 에 합침)

| 커밋 | 내용 |
|---|---|
| 종목 모델 정정 | **`products.index` + `$self`·`$index` 되살림** — on+sym 반영(2c9a90e)이 상품마다 달라지는 대상을 구체 티커로만 쓰게 해 같은 판단이 상품 수만큼 복제됨(후보 a 규칙 142개·이름 조건 73개). 트리는 공통 한 번, 상품은 해석기가 `products` 를 돌며 채움. `$s`·`names`·`across` 폐지는 유지(atleast·of). 동치 확인: 공통 규칙 하나 == 옛 기준 날마다 동일 |
| 판단자 정리 | **판단자 층 정리**(동작 불변 — 합성 트리 3년 판정·비중·거래 동일) — `ProductRules`·`TreeGateway.product` 삭제(`ProductJudge`·`RuleSeries` 가 트리+상품으로 출입구에 직접), `Judge` 의 트리 질문 전달 15개 → `judge.tree` 하나. **소절 반영 배지(coverage) 삭제**(기능 제거 — 원시 트리 보기가 대신) |
| 원시 트리 | **원시 트리 보기**(브랜치에서 옮김) — 플레이북 소절 헤딩의 '🌲 규칙' 토글로 그 소절에서 뽑힌 규칙을 판정 로직 없이 1:1(`web/raw_tree.py`). 트리는 판단자에게 묻는다 — 출입구 질문 `cards()`(규칙 카드, 적힌 그대로) 추가(브랜치의 뒷문 `whole()`·원본 키 직접 접근은 쓰지 않음) |
| on+sym | **종목 모델 `on`(어느 상품) + `sym`(구체 티커) 둘로**(브랜치 `cleanup/symbol-model` 을 지금 구조로 옮김) — `$self`·`$index`·`$s`·`names`·`products.index`·`across` 폐지(형식 검사가 거부, 평가기·출입구·설명·화면·검사에서 지원 삭제). 동치 확인: 같은 뜻을 옛/새 표기로 쓴 합성 트리가 실제 시세 3년치 판정·비중·백테스트 거래까지 동일 |
| (문서) | entry 설명 바로잡음(없는 watch.py → live.py · watch 루프는 market/feed.watch) · README 옛 `signal/{judge,engine}.py` 경로 |
| `d11a164` | **verify/ 폴더 폐지** — 검사는 대상 옆 `verify_*.py`(동작 불변): 트리 `authoring/extract/verify_tree` · 원문 `authoring/transcribe/verify_source` · 페이지 `web/verify_page` · 연산 `tree/verify_primitives` · 설명 `judge/verify_view` · 체결 `backtest/verify_trading` · 코드 규칙 `entry/verify_rules` |
| `43ebea0` | **검사는 바뀔 때만** — daily·verdict·watch 에서 검사 제거, `--no-verify-tree` 폐지. 바꿨으면 커밋 전 `run check` |
| `fba5686` | **만드는 곳 = 검증하는 곳**(동작 불변) — 트리 채점 → `authoring/extract/score.py`(+`--quick` 트리 계약) · 본문 해시 → `authoring/transcribe/` · 책 페이지 검사 → `web/book_page.py` · `verify/` 는 코드 검사만 |
| `d25526f` | 심판 비교 도구를 `authoring/extract/compare.py` 로(채점과 '같은 뜻' 잣대 한 벌) — authoring 층 import 에 signals |
| `d9b5d63` | 검사 픽스처를 v3 규칙 트리로(출입구 `rule`·`synthetic`) — 깨져 있던 원시함수·거래·화면 검사 복구 |
| `40deda9` | **6칸 잔재의 꼬인 참조 정리**(판정·백테스트 불변) — v3→v2→Qty 왕복 번역·뒷문(raw_*)·조심/defs 경로 삭제, 칸 극성 표 하나 |
| `b78fdb0` | **6칸 → 3동사** — 평가기·출입구(gate·weight·sells·skips)·판정 JSON(gates·size·sells·verbs)·화면·등급 글자(✅ 산다·⛔ 안 산다), 🚫·`grade_rules` 출력 삭제 |
| `195187c` | **verify_tree v3** — 규칙 단위 a·b 비교 + `why`, 사례 = 그날 결과, 같은 식 두 벌·같은 이름 다른 식·skip 머리·"?" 심볼·옛 키 정지 |
| `3ca66ed` | 지운 전용 지표 연산(ma·ema·stdev·rsi) 흔적 삭제 + 주인 표 '지운 연산'(되살림 정지) |
| `03c6ac7` | 책 페이지 백테스트 탭이 옛 `web/ui/` 경로 때문에 영영 안 붙던 버그 — 총수익·MDD·샤프·자산곡선이 이제 보인다 |
| `9781828` | `observe` 레거시(관측·수동 노드·백테스트 제외 모드 EXCLUDED) 삭제 |
| `f24c4c1` | 전용 연산 `pct`·`count`·`streak` 삭제 → 조합(변화율 = (s÷lag−1)×100 · sum(case) · barssince(not c)) — 지침 갱신 |
| `7090c7b` | 트리 형식 검사 강화(모르는 키·옛 키·동사별 qty 종류 거부) + 판다 `repeat` 구현 |
| `9865ddd` | **`pos filled`·`sold` 가 minret 으로 계산되던 조용한 버그** — 백테스트 체결 장부로 구현 |

## 3. 남은 일 (순서대로)

### 6. run3 — tree.json 다시 만들기 (키스톤)
- 순서: 구간① 전사 → 구간② 추출 a·b(서로·최종·사례 안 봄, 각자 다른 서브에이전트) → 사례 작성자(트리 안 봄, `SCENARIO.md` —
  기대값 = 그날 결과) → 심판(`JUDGE.md` — 규칙마다 `why`, `review` 없음) → `python -m authoring.extract.verify_tree <slug>` exit 0.
  옛 후보·`scenarios.json`·`tree.json` 의 `review` 는 다시 뽑으면 없어진다(손으로 고치지 않는다).
- 원문 위치 `authoring/transcribe/book_sources.json`(trend = `books/trend/source.md`, moneycopy = `~/jhts/hypotheses/sources/미국-돈복사-ETF-투자방법.md`).
- 끝나면 사용자 승인 후 `main` 에 합치기.

### 5-남음. 트리 v3 코드 반영의 나머지 (초안 `docs/action-grammar-draft.md` 9절·5절)
- **새 기본 부품**: 세션 시작 · `sumsince` · `smooth`(EMA 2/(n+1)·Wilder 1/n) · `sqrt` · 순위(후보 종목 중) — 후보: 세션 경과
  시간(개장 캘린더 `md_feed.sessions().open`). **pandas 로 다시 구현**(지금 평가기(tradeTool)는 순수 파이썬 반복문).
- 검사기 남은 것(JUDGE 5절 중 기계로 아직 못 보는 것): 판정 같은 조건의 포함관계(시세 없이 논리로) · 효과 없는 규칙(결과를
  바꾼 날 0일) · 원문 소절 누락(어느 규칙 ref 에도 없는 판단 소절) · 충실성(식 되는데 skip) · 결정 쪼개짐/흩어짐 · `ref` 형식(`·`).
- 산다(분할)의 `repeat`("~할 때마다 더 산다")는 연산 없음으로 거부 중 — 원문이 요구하면 체결 워크에 구현.
- 라이브 보유 화면의 `pos filled`·`sold` 는 모름(positions.json 에 차수별 체결 기록이 없다) — 필요하면 positions.json 형식 확장.
- 장중 데이터가 없을 때 조건은 모름(None)이다 — 분봉 없음을 자동으로 수동(🟡)/백테스트 제외로 돌리는 처리가 필요하면 새 기능으로
  (옛 `observe` 는 지웠다).
- 초안 문서는 위가 끝나면 지침(`COND_DSL`·`EXTRACTOR`·`JUDGE`·`SCENARIO`)으로 옮기고 지운다(초안 머리말 규칙).

### 그 뒤
- **화면 JS 의 소절 키 정규식 사본** — `web/ui/shared-ui.js` REF_RE·REF_HEAD_RE 가 `shared/sections` 와 같은 키를 따로 적는다
  (JS 라 import 불가). 서버가 판정 JSON 에 키 패턴을 실어 보내면 한 벌.
- **트리 출입구 강제의 빈틈** — 주인 표 '트리 원본 키'는 `r["rules"]`·`.get("then")` 꼴만 잡는다. `"then" in r`·흔한 키
  (`when`·`qty`)·`book_file(slug, "tree.json")` 직접 열기는 안 잡힌다(지금 위반은 0). 출입구 밖에서 `"tree.json"`·`"tree_candidates"`
  를 파일 열기에 넘기면 정지하는 줄을 주인 표에. (후보 파일 이름은 출입구 `gateway.FILES` 한 곳으로 모음 — `Judge.read(slug, "a")`)
- **백테스트 계산기 버그** — `portfolio` 가 1 unit = 시작자본 고정이라 손실 뒤 다음 진입이 남은 현금보다 클 수 있다
  (옛 표준 매도 사본에서 SOXL −162% 관측). 잔고 기준 사이징으로.
- **장중 손익 백테스트**(분봉 ~7일뿐이라 보류 — 되살릴 땐 통일 신호 경로 위에 재구현) · tree 재생성 뒤
  `python -m backtest.verify_trading --parity` 실측.
- **무인 판정을 막는 수동 조건** — (가) 연산으로 풀 것 = v3 기본 부품 조합 · (나) 데이터가 없는 것 = 실적 캘린더 · 뉴스 시각 ·
  지수 구성종목 등락(breadth) · 개인 매매 기록 — 외부 소스 생기기 전엔 서버 권위 수동 답으로 '1회 답'까지 · (다) 정성 판단 = 수동 답.
- **이번 범위 밖**(트리 v3 에서 `skip` "연산 없음"으로 드러남): 계좌 전체 기준 · 종목 간 돈 이동 · 지난 매매 이력.

## 4. 참고 문서 (할 일 없음)

| 문서 | 내용 |
|---|---|
| `docs/ARCHITECTURE.md` | 구조(1-2 작업 순서·트리를 읽는 길)·원칙·변경 규율·검사 |
| `docs/action-grammar-draft.md` | 트리 v3 설계(모양 확정 — 남은 세부는 3절 5-남음) |
| `authoring/extract/README.md` 외 지침 | 구간② 절차·역할 |
| `market/md_feed.py` docstring | jhts 일봉·분봉 계약(어댑터가 기대하는 것·반환 계약) |

## 5. 검증 명령

```
python -m entry.run check            # 전부(CHECKS 한 목록) — 바꿨으면 커밋 전. 요약 + 종료코드
python -m entry.verify_rules               # 코드 규칙 — 폴더 경계 + 주인 표
python -m authoring.extract.verify_tree <slug>        # 트리 채점
python -m authoring.extract.verify_tree --quick   # 트리 계약(소절·트리 문법·ref)
python -m web.verify_page         # 책 페이지 구획·UI 사본
python -m authoring.extract.compare <slug> 6   # 심판 비교 도구(a·b 덤프)
python -m entry.serve  → http://localhost:8799/<slug>/?tree=a   # 소절별 원시 트리(🌲 규칙)를 후보 a(·b)로 보기
python -m backtest.verify_trading --parity     # 판정 = 백테스트 일치(시세 필요)
```
