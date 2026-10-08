# etf-verdict 남은 작업 정밀 스펙 (#2 데이터/지표 만능화 · #3 무인 자동판정)

읽기 전용 분석 산출물. 코드/문서/트리/git 미변경. 근거는 모두 아래 파일 실측(라인 번호 포함).
작업 루트: `/Users/hyeyoung/claude-projects/etf-verdict/book-to-playbook` (venv `.venv`).

핵심 파일
- 수집 어댑터: `shared/md_feed.py`
- 평가기(원시함수): `checklist/cond.py`
- 트리 해석: `checklist/grade.py`
- 판정: `trading/judge.py`(Judge) → 화면 JSON `web/verdict_view.py`
- 원시함수 검사기: `checklist/verify_primitives.py`
- 계약 메모: `MIGRATION_NOTES.md` (④ jhts 분봉 계약, ⑤ 후속)

---

## 0. 한눈 요약 (지금 상태)

- **분봉 계약은 이미 OHLCV + UTC 로 열렸고 jhts 가 실제로 준다**(MIGRATION_NOTES ④-T, 133~141행).
  "jhts 분봉 미제공"은 **더 이상 블로커가 아니다** — `md.minute_bars()` 가 ES=F/NQ=F 등 최근 ~7거래일을
  OHLCV+UTC 로 주는 것을 실측 확인했다. 남은 데이터 한계는 **보관 기간(~7거래일)**과 **과거 심볼 미연결**뿐이다.
- 지표(ATR·VWAP·당일 고/저·시초가 등)는 전용 연산으로 만들지 않는다 — 기본 부품(세션 시작·sumsince·smooth·sqrt·순위)만 코드,
  지표는 조합 예시(`docs/action-grammar-draft.md` 9절, 트리 v3 와 함께).
- **gap(갭)은 신규 프리미티브가 필요 없다** — 기존 `px`/`lag`/`div` 로 이미 트리에 들어가 있다.
- **tree.json 이 삭제돼 있다**(`books/moneycopy/`·`books/trend/` 에 `tree.json` 없음, 후보만 `tree_candidates/{a,b}.json`).
  이게 #3 의 1차 블로커다(구간② 재생성). jhts 데이터는 **2차 블로커가 아니라 이미 대부분 해결**.

---

## 1. jhts 분봉/일봉 계약 (shared/md_feed.py)

### 1.1 md_feed 가 jhts 에 기대하는 것 (함수별 시그니처·반환·단위·tz)

| md_feed 함수 | jhts 호출 | jhts 반환 기대 | 단위·tz | 실패/미설치 |
|---|---|---|---|---|
| `history(symbol, start)` (31~42행) | `md.candles(symbol, start=start)` | `[Candle(date, open, high, low, close, volume)]` 오름차순, date=YYYYMMDD | 일봉, 날짜만(시각 없음) | `[]` (예외 시 stderr 1줄) |
| `histories(symbols, start)` (45~53행) | 위를 심볼마다 반복 | `{심볼: [Candle]}` | 동일 | 빈 심볼엔 수집요청(`_request`) |
| `minutes(symbol)` (66~95행) | `md.minute_bars(symbol)` | **리스트** `[{"dt":"2026-10-02T19:59:00Z"(ISO8601 UTC, 끝 Z), "open","high","low","close","vol"}, ...]` 오름차순 | 1분봉, **UTC** | `{}` (예외 시 stderr 1줄) |
| `sessions(market, start, end)` (98~106행) | `md.sessions(market, start, end)` | `[Session(.date, .open, .close(tz-aware), .is_half)]` | 거래소 현지 tz-aware datetime | `[]` |
| `market_of(symbol)` (109~116행) | `md.market_of(symbol)` | `"US"|"KR"|None` | — | `None` |

`md_feed.minutes()` 가 하는 **모양 변환만**(66~95행): `dt`(ISO8601 UTC) → `YYYYMMDDHHMM`(UTC 그대로,
변환 없음; 87행 슬라이싱 `dt[:4]+dt[5:7]+dt[8:10]+dt[11:13]+dt[14:16]`), `vol → volume`, OHLC 그대로.
반환 계약: `{YYYYMMDDHHMM(UTC): {open,high,low,close,volume}}`. 네트워크 코드는 이 파일에 **없어야 하고**
`import jhts` 는 파이프라인 전체에서 이 파일 하나만 허용(`orchestration/verify_code.py` 강제; md_feed.py 3~14행).

### 1.2 "jhts 가 줘야 할 것 vs 지금 주는 것" 표

| 항목 | jhts 가 줘야 할 것(계약) | 지금 실제 | 간극 |
|---|---|---|---|
| 일봉 OHLCV | `candles()` → OHLCV 캔들 | 준다(실측 SPY) | 없음 |
| 분봉 OHLCV | `minute_bars()` → OHLCV+UTC 리스트 | 준다(실측 SPY `T19:59:00Z`, ES=F `T20:59:00Z`) | **없음(④-T 교체 완료)** |
| 분봉 **보관 기간** | 길수록 과거 장중 자동판정↑ | 미국 심볼 **최근 ~7거래일만** | **보관기간 한계** — 과거 백테스트 장중 observe 는 그만큼만 자동, 나머지는 None→manual |
| 분봉 **tz** | UTC `YYYYMMDDHHMM` 고정 | UTC(미국 심볼 확인) | **KR 분봉 미검증** — KR 이 UTC 로 오거나 `minute_series` 에 tz 파라미터 추가 필요(⑤-3) |
| 세션 캘린더 | `sessions()` — 일봉 확정 경계용 | 제공(파이프라인은 `session_closes` 로 소비) | `md_feed.sessions`/`market_of` 는 **일봉 확정(settled) 경계에만** 쓰인다(분봉은 asof 키 비교라 캘린더 불필요) |

### 1.3 cond.py 가 이 데이터를 소비하는 경계 (계약 경계)

- `cond.minute_series(minutes, cal, field, asof)` (cond.py 366~391행): `minutes` = md_feed 가 준
  `{YYYYMMDDHHMM(UTC): {OHLCV} 또는 스칼라 종가}`. **dict 봉·스칼라 둘 다 받는다**(389행) — jhts 가
  종가만 주던 과거에도, OHLCV dict 를 주는 지금도 트리/평가기 무변경. 날짜별 'asof 이하 그날 마지막 분봉'의
  `field` 값. 그날 범위에 분봉 없으면 `None`(→ 장중 observe 는 manual).
- `cond.aggregate_5m(minutes)` (cond.py 394~417행): 1분봉 → 5분 OHLC 집계(첫 open·최고 high·최저 low·
  끝 close·합 volume). 버킷 키 `YYYYMMDDHH + (분 5내림)` 이라 **세션/날 경계를 절대 안 넘는다**(403행).
- `cond.Ctx.px(sym, field, tf)` (cond.py 312~329행): `tf="1d"` → 확정 일봉(settled, 장중 asof 면 오늘 미확정
  봉은 `_settled_dates` 로 가림), `tf="1m"` → `minute_series`, `tf="5m"` → `aggregate_5m` 후 `minute_series`.
- 소비 입구(수집): `grade.history(trees, start)` (checklist/grade.py) 가 `md_feed.histories` +
  `md_feed.minutes` 로 일봉·분봉을 모아 `History`(일봉 dict + `.minutes`)를 만든다.
- `series()` 메모키 = `(repr(node), s_sym, ctx.manual_as)` (cond.py 529행) — 신규 프리미티브는 이 키에
  이미 들어간다(별도 작업 불필요).

**계약 요점(절대 깨지면 안 되는 것):** 분봉 키는 **UTC `YYYYMMDDHHMM` 문자열**이어야 한다 — `minute_series`
가 asof 를 같은 포맷 문자열로 바꿔 **문자열 비교**로 자르기 때문(378~380행). tz 가 섞이면 조용히 잘못 자른다.

---

## 2. 계산기 부품 — 트리 v3 로 이관

지표별 전용 연산 설계(ATR·VWAP·세션 고저)는 폐기했다. 기본 부품 + 조합 예시 방식과 pandas 구현은
`docs/action-grammar-draft.md` 9절(트리 v3 작업 때 함께).

---

## 4. #3 무인 판정 체인 — 사람 개입 0 까지 남은 것

### 4.1 체인 현황 (tree → 데이터 → 판정)

```
tree.json(구간② 재생성)  →  md_feed(일봉 OK · 분봉 OHLCV OK, ~7일 보관)  →
grade.ProductEval(등급/금액/분할/매도)  →  trading.judge.Judge → web.verdict_view.render(JSON·알림)
```

- **1차 블로커 = tree.json 없음.** `books/moneycopy/`·`books/trend/` 에 `tree.json` 이 없다(후보만
  `tree_candidates/{a,b}.json`). `TreeGateway.load`(checklist/tree_gateway.py — 트리를 읽는 유일한 출입구)가 `None` 을 돌려주고
  `web.verdict_view.render` 는 "조건 트리 없음" 에러로 끝난다 → **판정 자체가 안 돌아간다.**
  (사용자 메모와 일치: tree.json 삭제·심판생성 전환, 재개 첫 일 = tree 재생성→파리티.)
- **2차 블로커(완화됨) = jhts 분봉.** OHLCV+UTC 로 이미 온다(④-T). 남은 건 **보관기간(~7일)**·**과거/KR 미연결**.
- **데이터 없음 → 조용한 실패 없음:** 시세 없는 심볼은 `md_feed` 가 수집요청을 남기고(`requested()`),
  판정은 ❔(unknown)로 **정직하게** 떨어진다(web/verdict_view.product_verdict·render 의 missing). 데이터 완전성 가드도 확정봉이
  워밍업보다 적으면 ❔ 로 보류(checklist/grade.py ProductEval.incomplete) — '모르고 매매' 방지.

### 4.2 "사람 개입 0" 을 막는 수동 조건 목록 (tree_candidates 기준)

두 후보 트리(`a.json`·`b.json`)의 manual 잎을 전수 분류. 각 조건은 🟡(확인 대기)로 떨어져 **사람 개입**이 된다.

**(가) "연산 없음" — 프리미티브로 자동화 가능 (기본 부품 조합이 해결):**

| 수동 문구(요약) | 출처 | 필요 프리미티브 |
|---|---|---|
| 장중 첫 눌림 저점 지킴 (a 117행 / b) | a.json `장중 첫 눌림 저점 지킴` | 세션 시작·minsince/maxsince 조합 + 분봉 비교 |
| 세션 첫 30분 고점·저점 (a 173행 / b) | a.json `첫 30분 저점 지킴` | **세션 시작·maxsince/minsince 조합 + 개장 캘린더**(첫 30분 구간) |
| 장 시작 후 경과 시간/30분 이내 (a 119행 / b) | a.json `장 시작 후 30분 이내` | **세션 시각(개장 캘린더) — 기본 부품 '세션 경과 시간' 후보** |
| 20일선 회복 후 첫 눌림 저점 (a 229행) | a.json `기준지수 회복 후 첫 눌림` | 세션 시작·minsince 조합 + barssince(기존) 조합 |
| 장중 당일 시초가 위(장 30분 뒤) (b) | b.json | 세션리셋 + 개장 캘린더 |
| 뉴스 후 첫 30분 고점 (b) | b.json | 세션리셋 + 개장 캘린더 + (뉴스 시점은 아래 '나') |

→ **기본 부품 조합(당일 고/저·VWAP·ATR — v3 초안 9절)** 로 상당수가 자동화되나, **'장 시작 후 N분/첫 30분 구간'은 개장
시각(개장 캘린더)**이 더 필요하다. 현재 cond 는 **마감 시각만**(`session_close`) 받는다(cond.py 286행).
→ 완전 자동화하려면 `session_close` 와 짝으로 **개장 시각 맵**을 `md_feed.sessions`(이미 `.open` 제공,
md_feed.py 100행)에서 끌어와 Ctx 에 넣고, '세션 경과 분' 프리미티브를 추가해야 한다(v3 초안 9절 기본 부품 후보).

**(나) "데이터 없음" — 프리미티브로는 못 풀고 새 데이터 소스 필요:**

| 수동 문구(요약) | 출처 | 필요 데이터 소스 |
|---|---|---|
| 빅테크 실적 발표 일정/전 | a 702행 / b | **실적 캘린더 피드** |
| 반도체/뉴스가 가격보다 먼저 (뉴스 시점) | a 281행 / b | **뉴스 타임스탬프 피드** |
| S&P500 상승 종목 폭(breadth) | b.json | **지수 구성종목 등락 데이터** |
| 계좌 실현수익 확정일·직전 손절 시점 | b.json | **개인 계좌 매매 기록**(positions.json 류 확장) |

→ 이들은 **데이터 자체가 없어** 프리미티브로 자동화 불가. jhts 또는 외부 소스가 해당 데이터를 주기 전에는
영구히 🟡(manual) 이거나, **서버권위 수동응답 맵(작업 A)**으로 '사람이 한 번 답하면 저장·재사용' 하는 길뿐.

**(다) "저자 미명시" — 정성 판단 (자동화 대상 아님):**

- b.json: "20일선 스윙으로 정했는지(정성)", "무엇을 '시장의 확인'으로 세는지(정성)", "1차 매수 기준 유지(정성)".
- 저자가 숫자/규칙을 안 준 순수 주관 → 프리미티브·데이터로 풀 수 없다. **작업 A(서버권위 맵)**로 사람이 정한
  값을 저장해 재사용하는 게 유일한 '개입 감축' 경로.

### 4.3 "사람 개입 0" 도달 조건 (우선순위)

1. **tree.json 재생성**(구간②) — 없으면 판정 자체가 불가(1차·필수).
2. **작업 A(서버권위 manual_answers 맵)** — (나)·(다) 의 사람 1회 답을 저장·재사용해 매 판정의 반복 개입 제거.
3. **기본 부품(v3 초안 9절)** + **개장 캘린더/세션 경과 분** — (가) 전부를 데이터로 자동화.
4. **외부 데이터 소스**(실적/뉴스/breadth/계좌 기록) — (나) 를 진짜로 자동화하려면 필요(장기).
   그 전엔 (나)·(다) 는 A 로 '개입 1회화'까지가 현실적 상한.

---
