# jhts 시세 계약 (참고 문서 — 할 일은 docs/HANDOFF.md)

> md_feed 가 jhts 에 기대하는 것 vs 지금 주는 것. 남은 작업·우선순위는 여기 적지 않는다.

## 0. 한눈 요약 (지금 상태)

- **분봉 계약은 이미 OHLCV + UTC 로 열렸고 jhts 가 실제로 준다**(MIGRATION_NOTES ④-T, 133~141행).
  "jhts 분봉 미제공"은 **더 이상 블로커가 아니다** — `md.minute_bars()` 가 ES=F/NQ=F 등 최근 ~7거래일을
  OHLCV+UTC 로 주는 것을 실측 확인했다. 남은 데이터 한계는 **보관 기간(~7거래일)**과 **과거 심볼 미연결**뿐이다.
- **gap(갭)은 신규 프리미티브가 필요 없다** — 기존 `px`/`lag`/`div` 로 이미 트리에 들어가 있다.

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
