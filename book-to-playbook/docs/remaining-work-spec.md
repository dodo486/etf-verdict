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
- **ATR·VWAP·세션리셋(당일 고/저)·세션 시각 프리미티브가 없다** — 이게 #2(b)의 실제 남은 구멍이다.
- **gap(갭)은 신규 프리미티브가 필요 없다** — 기존 `px`/`lag`/`div` 로 이미 트리에 들어가 있다(아래 2.3).
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

## 2. 추가할 프리미티브 정밀 명세 (cond.py 에 넣을 때 애매함 0)

> 공통 규칙(기존 원시함수와 일관): 입력은 값 표현식(또는 봉 필드). 출력은 **달력 길이 리스트**. **인과성** =
> index `i` 값은 `cal[i]` 이하 데이터만으로 결정(미래 참조 0 — `t_causal` 가 강제). 결측은 `None`.
> 하한 불확실은 `cond.AtLeast`. 세션 경계는 **분봉 키 앞 8자리(YYYYMMDD) = 거래일**로 판정(UTC 날짜).
> 등록: 신규 op 는 `validate()`(cond.py 166~262행) 분기 + `_series()`(cond.py 540행~) 분기 양쪽에 추가,
> `WINDOW`/`CMP`/`ARITH` 중 성격 맞는 집합 또는 신규 집합에 키 등록. 1d-순수 판정에 쓰이면 `_daily_axis`
> (cond.py 492~517행)·`_NON_DAILY`(489행) 에 분봉성 여부 반영.

### 2.1 ATR(기간 n) — Average True Range

- **정의:** True Range(그날) = `max(high−low, |high−prev_close|, |low−prev_close|)`. ATR(n) = TR 의 n기간 평균.
- **입력:** 봉 심볼(기본 `$self`)·기간 n(1 이상 정수). TR 은 high/low/close(전일 종가)를 함께 본다 — 기존
  `px`(close 단일 필드)로는 한 노드로 못 짠다 → **신규 프리미티브 필요**(확정).
- **출력:** 달력 길이 리스트. 첫 TR 은 prev_close 가 있는 index 1부터. ATR 은 스무딩 시드가 찰 때까지 `None`.
- **스무딩 권고: Wilder (기존 rsi 와 일관).** 근거 — cond.py 665~686행 rsi 가 이미 Wilder(첫 평균=처음 n개
  단순평균, 이후 `(prev*(n−1)+x)/n`, 결측 끼면 다시 쌓기)다. ATR 의 업계 표준도 Wilder(원저자 J. Welles
  Wilder 가 RSI·ATR 동시 제안). SMA·EMA 변형이 있으나 **Wilder 로 통일**해야 (a) 사용자가 "ATR" 로 적은 뜻과
  업계 기본이 맞고 (b) rsi 구현을 그대로 재사용해 결측 처리까지 일관. (SMA 를 쓰면 rsi 와 결측·시드 규칙이
  달라져 혼란.)
- **인과성:** TR·ATR 모두 asof 이하만. prev_close 는 `lag` 와 동일 규칙(index 0 은 TR None).
- **세션경계:** 일봉 기반이면 무관. 단, tf="1m"/"5m" 로 쓰이면 '전일 종가'가 아니라 '직전 분봉 close' 기준 TR
  이 되므로 **1차 구현은 일봉(1d) 전용으로 못박기**를 권고(분봉 TR 은 ⑤ 후속). → `_NON_DAILY` 비추가
  (1d-순수로 두어 일봉축 당김 혜택).
- **결측:** TR 입력(high/low/prev_close) 중 하나라도 None 이면 그 날 TR None → 스무딩 재시작(rsi 와 동일).
- **검사 1줄(`verify_primitives`):** 무작위 OHLC 시계열에서 손계산 TR + Wilder 스무딩과 전수 대조, 상수열 ATR→0,
  index 0·초기 구간 None, 인과성(앞을 잘라도 과거 날짜 동일) — `CAUSAL_NODES`(421행)에 `{"atr":[C,14]}` 추가.

### 2.2 VWAP — 세션 리셋 거래량가중평균가 (장중 전용)

- **정의:** 세션(당일) 시가부터 누적. 분봉 전형가 TP=`(high+low+close)/3`, VWAP = `Σ(TP·volume) / Σ(volume)`
  (당일 시작부터 asof 이하까지 누적).
- **입력:** 봉 심볼(기본 `$self`), tf="1m"(또는 "5m"). **인자 n 없음** — 창이 아니라 '당일 세션 누적'.
- **출력:** 달력 길이 리스트. 각 날짜 index 는 'asof 이하 그날 분봉'만으로 누적한 VWAP(그날 분봉 없으면 None).
  — `minute_series` 와 같은 '그날 asof 이하' 스코프를 쓰되, **마지막 봉 하나가 아니라 그날 처음~asof 누적**이라
  `minute_series` 를 그대로 못 쓴다 → **신규 집계 경로 필요**(아래 구현 메모).
- **세션 경계 판정:** '당일 시가부터'의 '당일' = **분봉 키 앞 8자리(YYYYMMDD) = 거래일**로 가른다
  (`aggregate_5m` 와 같은 규칙 — 거래소 캘린더·`session_closes` **불필요**. 분봉 키 UTC 날짜가 곧 세션일).
  미 정규장이 한 UTC 날짜 안에서 닫힌다는 전제(MIGRATION_NOTES: 13:30~20:00 UTC)와 일치. **주의:** KR·선물
  야간처럼 세션이 UTC 자정을 넘으면 이 전제가 깨진다 → 1차는 미국 정규장 전제로 못박고 ⑤ 후속(세션 경계를
  `session_close` 캘린더로 일반화).
- **인과성:** asof 이하 분봉만 누적(자명). asof 이후 분봉·다른 날 분봉 미사용.
- **결측:** 어떤 분봉의 TP·volume 이 None 이면 그 봉만 제외하고 누적(0 으로 채우지 않음). volume 합이 0/None 이면
  그 날 VWAP None(0 나눗셈 금지 — `div` 규칙 cond.py 588행과 일관).
- **구현 메모:** `minute_series` 를 '그날 asof 이하 마지막 1봉' 대신 '그날 asof 이하 전 봉 순회 누적'으로 한
  함수 더(예: `minute_vwap(minutes, cal, asof)`) — 평가기 다른 부분 무변경(MIGRATION_NOTES ⑤-1 이 예고한
  "`minute_series` 한 곳만 확장" 지점과 동일 성격). `px` 와 별도 op `{"vwap":{...}}` 로 둘지, `px` 의
  `field:"vwap"` 가상필드로 둘지 — **별도 op 권고**(px 필드는 OHLCV 원시값만, 집계는 op 로 분리해 1d 혼입 차단).
- **검사 1줄:** 손계산 분봉 몇 개의 Σ(TP·vol)/Σvol 과 대조 + 세션 경계(전날 분봉 안 섞임) + asof 자르기
  (`t_settled_mtf` 의 5분봉 집계 테스트 648~660행과 같은 분봉 픽스처 재사용) + volume 0 → None.

### 2.3 gap(갭) — 신규 프리미티브 **불필요** (기존으로 표현)

- **정의:** 오늘 시가 vs 전일 종가. 비율(%) = `(open/prev_close − 1)·100`.
- **판단:** 기존 `{"px":"open"}`, `{"lag":[{"px":"close"},1]}`, `div`/`sub`/`mul` 로 **이미 표현된다**.
  근거 — `books/moneycopy/tree_candidates/a.json`:
  - 241행 `P_gap_up`: `{"gt":[{"px":"open"},{"lag":[{"px":"close"},1]}]}` (갭상승 불리언)
  - 168~172행 `상품 갭상승`: `{"ge":[{"mul":[100,{"sub":[{"div":[{"px":"open"},{"lag":[{"px":"close"},1]}]},1]}]}, "?"]}` (갭 %)
- **권고:** 신규 op 추가하지 않는다(사장님 '하드코딩/중복 금지' 원칙과 일치 — 조합으로 충분). 자주 쓰여 가독성이
  문제면 **`defs` 의 정의 한 줄**로 재사용(코드 변경 0). 프리미티브 작업 범위에서 **제외**.
- **검사:** 불필요(기존 `pct`/`div`/`lag` 검사가 커버).

### 2.4 세션리셋 집계 — 당일 고/저 (장중 전용)

- **정의:** asof 이하 '오늘 세션' 분봉들의 high 최대 / low 최소(당일 고가·당일 저가). "첫 눌림 저점",
  "첫 30분 고점·저점" 류 수동 조건(아래 4장)이 이걸로 자동화된다.
- **입력:** 봉 심볼(기본 `$self`), tf="1m"/"5m", 집계 종류(high-max | low-min). **인자 n 없음**(당일 누적).
- **출력:** 달력 길이 리스트. 각 날짜 = 그날 asof 이하 분봉의 high 최대/low 최소(그날 분봉 없으면 None).
- **세션 경계:** VWAP 과 동일 — 분봉 키 앞 8자리(거래일). 캘린더 불필요.
- **인과성·결측:** asof 이하만; None 봉 제외하고 집계, 전무면 None.
- **'첫 30분' 류:** '당일 고/저' 는 위로 된다. 그러나 **'장 시작 후 N분(세션 시각)'**·**'첫 30분 구간'**은 세션
  **개장 시각**을 알아야 한다 → `md_feed.sessions`(개장 시각) 또는 `session_close` 와 짝인 **개장 캘린더**가
  필요(현재 cond 는 마감만 `session_close` 로 받는다, cond.py 286·331행). **권고:** '당일 고/저'(세션리셋
  집계)만 1차에 넣고, '세션 경과 시간/첫 N분 구간'은 **개장 캘린더 의존**이라 별도 후속으로 분리(4장 참조).
- **구현 메모:** VWAP 과 같은 '그날 asof 이하 전 봉 순회' 경로 재사용(high max / low min 만 다름). 별도 op
  (예: `{"session_high":{...}}`/`{"session_low":{...}}`) 권고.
- **검사 1줄:** 손계산 당일 고/저 대조 + 전날 분봉 안 섞임(세션 경계) + asof 자르기 + 분봉 전무 None.

---

## 3. 구현 순서와 충돌 지점 (둘 다 cond.py 를 고친다)

**두 작업이 모두 `checklist/cond.py` 를 고치므로 동시 진행 시 충돌한다.**

| 작업 | cond.py 건드리는 영역(함수) | 성격 |
|---|---|---|
| **B. 프리미티브(ATR/VWAP/세션리셋)** | `validate()`(166~262), `_series()`(540~, op 분기 추가), 상수 집합(`WINDOW`/신규), `_NON_DAILY`(489)·`_daily_axis`(492)·`Ctx.px`(312) 분봉 경로 | 평가 로직에 **새 op 추가**(append 성격) |
| **A. 서버권위(manual_answers 맵)** | `Ctx.__init__`(269~290, `manual_as` 옆에 `manual_answers` 맵 필드 추가), `_series()` 의 `manual`/`observe`/`is_unknown` 분기(548·799·802행 — manual 값을 맵에서 조회) | **기존 수동 평가 분기 개편**(수정 성격) |

**충돌 핵심:** 둘 다 `_series()` 본문을 건드린다. A 는 `manual`/`observe`/is_unknown 분기(548·799~804행)를,
B 는 그 아래 op 분기들을 **추가**한다. 같은 함수 동시 편집 → 머지 충돌.

**권고 순서: A(서버권위) 먼저, B(프리미티브) 나중.** 근거:
1. A 는 **구조 변경**(Ctx 생성자 시그니처 + manual/observe 평가 의미)이라 뒤에 오면 B 가 추가한 op 분기와
   더 크게 엉킨다. 구조를 먼저 안정화.
2. B 는 **순수 append**(새 op 는 기존 분기와 독립) — A 가 끝난 cond.py 위에 깔끔히 얹힌다.
3. A 는 #3(무인 판정)의 '사람 개입 지점'을 줄이는 핵심이고(4장), B 는 그 남은 manual 중 일부를 데이터로
   자동화한다 — A 가 먼저 서 있어야 B 가 "무엇을 자동화하면 manual 이 실제로 줄어드는지" 검증 기준이 선다.

**직렬 진행이 어려우면:** A 는 `Ctx.__init__`+manual/observe 분기(cond.py 269~290·799~804행)에,
B 는 신규 op 분기(cond.py 613행 이후 append)에만 손대도록 **영역을 물리적으로 분리**하면 한 파일이라도 충돌
최소화 가능. 단 `validate()`·상수 집합은 둘 다 건드릴 수 있으니 거기만 순서를 둔다.

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

**(가) "연산 없음" — 프리미티브로 자동화 가능 (2장이 해결):**

| 수동 문구(요약) | 출처 | 필요 프리미티브 |
|---|---|---|
| 장중 첫 눌림 저점 지킴 (a 117행 / b) | a.json `장중 첫 눌림 저점 지킴` | 세션리셋 당일 고/저(2.4) + 분봉 비교 |
| 세션 첫 30분 고점·저점 (a 173행 / b) | a.json `첫 30분 저점 지킴` | **세션리셋 당일 고/저(2.4) + 개장 캘린더**(첫 30분 구간) |
| 장 시작 후 경과 시간/30분 이내 (a 119행 / b) | a.json `장 시작 후 30분 이내` | **세션 시각(개장 캘린더) — 2.4 에 미포함, 별도 후속** |
| 20일선 회복 후 첫 눌림 저점 (a 229행) | a.json `기준지수 회복 후 첫 눌림` | 세션리셋 당일 저(2.4) + barssince(기존) 조합 |
| 장중 당일 시초가 위(장 30분 뒤) (b) | b.json | 세션리셋 + 개장 캘린더 |
| 뉴스 후 첫 30분 고점 (b) | b.json | 세션리셋 + 개장 캘린더 + (뉴스 시점은 아래 '나') |

→ **당일 고/저(2.4)·VWAP(2.2)·ATR(2.1)** 로 상당수가 자동화되나, **'장 시작 후 N분/첫 30분 구간'은 개장
시각(개장 캘린더)**이 더 필요하다. 현재 cond 는 **마감 시각만**(`session_close`) 받는다(cond.py 286행).
→ 완전 자동화하려면 `session_close` 와 짝으로 **개장 시각 맵**을 `md_feed.sessions`(이미 `.open` 제공,
md_feed.py 100행)에서 끌어와 Ctx 에 넣고, '세션 경과 분' 프리미티브를 추가해야 한다(2.4 의 후속 분리 항목).

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
3. **작업 B 프리미티브(2장)** + **개장 캘린더/세션 경과 분**(2.4 후속) — (가) 전부를 데이터로 자동화.
4. **외부 데이터 소스**(실적/뉴스/breadth/계좌 기록) — (나) 를 진짜로 자동화하려면 필요(장기).
   그 전엔 (나)·(다) 는 A 로 '개입 1회화'까지가 현실적 상한.

---

## 5. 검사기 훅 정리 (verify_primitives.py)

- 신규 프리미티브(ATR/VWAP/세션리셋)는 `main()`(877행)의 테스트 목록에 함수 추가 + 관련 기존 테스트에 노드 추가:
  - 수치/스무딩: `t_numeric`(77행)에 ATR Wilder 대조 추가.
  - 인과성: `CAUSAL_NODES`(421행)에 신규 노드 추가(앞을 잘라도 과거 날짜 동일 자동검증).
  - 분봉/세션: `t_asof`(516행)·`t_settled_mtf`(578행)의 분봉 픽스처(648~660행) 재사용해 VWAP·당일 고/저
    세션 경계·asof 자르기 전수.
  - 문법: `t_syntax`(448행)에 신규 op 의 잘못된 인자(음수 n·모르는 필드) 거부 케이스 추가.
- gap 은 신규 테스트 불필요(기존 `pct`/`div`/`lag` 커버).
