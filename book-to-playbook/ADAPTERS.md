# 구간③ 데이터 계층 — jhts 창구 · metric 선언 · 판정

새 트레이딩 책을 넣으면, 그 책 규칙에 필요한 데이터가 기존 metric type 으로 **커버되면
시세 자동판정이 자동으로** 붙고, **안 되면 정직하게 "수동/데이터없음"** 으로 표시되게
만드는 계층. 전부 `verdict/` 팀 소속이다.

관련 파일:
- `verdict/md_feed.py` — **jhts 시세수집팀(jhts.marketdata) 어댑터. 유일한 시세 창구.**
  구간③의 누구도 시세를 직접 수집하지 않는다(야후/KIS/스크래핑 금지 — `verify_teams.py` 가 강제).
- `verdict/metric_calc.py` — metric 선언 `{type, symbol, ...}` → `{value, pass, text}` 평가기
- `verdict/metric_registry.json` — type 의 자동/무데이터 분류(SSOT). `verify_auto_coverage` 가 이걸로
  "자동 가능한데 ✋직접으로 샌 것"을 잡는다
- `verdict/verdict_engine.py` — `books/<slug>/rules.json` 선언을 읽어 판정을 만드는 범용 엔진
- `books/<slug>/data_spec.json` — 책 규칙을 수집요청으로 옮긴 명세 (`books/trend/` 참고)

---

## (a) 데이터 흐름

```
jhts.marketdata (시세수집팀 · 별도 프로젝트)
      │  candles / quote / index_rate / minute_closes / daily_features / breadth_*
      ▼
verdict/md_feed.py          ← 유일한 창구. 미설치/실패를 감싸 무크래시로 빈 값 반환
      ▼
verdict/metric_calc.py      ← 선언 {type, symbol, op, threshold} → {value, pass, text}
      ▼
verdict/verdict_engine.py   ← rules.json 의 SCORECARD/DATA 선언 → 종목별 등급·사유
```

**표준 평가 결과** (metric_calc.evaluate 반환):

| 키 | 뜻 |
|----|----|
| `value` | 대표 수치(있으면) |
| `pass` | bool 판정(문턱 있을 때) / 계산 불가·자동 불가면 `None` — **통과로 치지 않는다** |
| `text` | 사람이 읽는 근거 한 줄(실제 수치 포함) |

### 뱃지 매핑 (시트 렌더용 — metric_registry.json 기준)
| 분류 | 뱃지 |
|--------|------|
| auto_types & impl=true | 🤖 자동 |
| auto_types & impl=false | 🚧 미구현(데이터는 jhts 에 있음 — 해야 할 일, ✋직접 아님) |
| no_data_types | ✋ 직접(데이터 자체가 없음) |
| 미선언/미등록 | ❌ 미결선(발행 블로킹 — 선언하라) |

---

## (b) metric.type 카탈로그 (metric_calc.CALC 구현분)

| type | 뜻 | metric 필드 |
|------|----|-------------|
| `pct_change` | 전일 대비 등락률(%) | `symbol`, `op?`, `threshold?` |
| `point_change` | 전일 대비 포인트 변화 | `symbol` |
| `dxy_change` | 달러인덱스 등락(폴백 심볼 포함) | — |
| `above_ma` | 종가가 N일 이동평균 위인가 | `symbol`, `ma` |
| `hold_above_ma` | N일선 회복 후 며칠 더 지켰나 | `symbol`, `ma`, `days?` |
| `n_day_return` | 최근 N일 수익률(%) | `symbol`, `n` |
| `ma_distance` | 종가와 N일선의 이격도(%) | `symbol`, `ma?` |
| `upper_wick` | 윗꼬리 %(고점 대비 종가 하락폭) | `symbol` |
| `volume_ratio` | 거래량 / 기준거래량 배수 | `symbol`, `base?`(기본1=전일) |
| `count_up_days` | 최근 N거래일 중 상승일 개수 | `symbol`, `n?` |
| `gap_up` | 당일 시가의 전일종가 대비 갭(%) | `symbol` |
| `count_up` | 여러 심볼 중 상승 개수 | `symbols:[...]` |
| `count_above_ma` | 여러 심볼 중 N일선 위 개수 | `symbols:[...]`, `ma?` |
| `breadth_aligned` | 같은 방향 최대 개수 | `symbols:[...]` |
| `prev_low_break` | 전일 저점 이탈 종목 수 | `symbols:[...]` |
| `pullback_length` | 눌림 길이(거래일) | `symbol` |
| `breakout_hold` | 돌파 후 유지일 | `symbol` |
| `first_green_below_ma` | 20일선 아래 첫 양봉 | `symbol` |
| `defensive_only` | 방어(XLP·XLU·XLV) 강세 + 경기민감(XLK·XLF·XLI) 약세 동시(5일) | — |
| `cyclical_weak` | 금융·산업재 5일 약세 | — |
| `bad_rate_drop` | 나쁜 금리 하락(10년물↓ + S&P500 못오름 + XLF 약세) | — |

`op`/`threshold` 가 선언돼 있으면 그 방향·문턱으로 `pass` 를 정하고, 없으면 계산기
기본 판정(있을 때만)을 쓴다. **임계값을 저자가 안 준 지표는 문턱을 비워 둔다** —
숫자를 지어내는 대신 수치만 자동으로 채우고 판정은 사람이 한다.

장중 type(`above_open`, `higher_low`, `minute_high_hold` 등)은 레지스트리에 auto 로
등록돼 있지만 장중 엔진 재설계 대기라 `impl=false`(🚧)일 수 있다 — 현황은
`python -m verdict.verify_auto_coverage` 가 그대로 보여준다.

---

## (c) 새 책 붙이는 법

### 1. data_spec.json 작성
책 매매시트의 각 체크 항목이 **어떤 데이터를 필요로 하는지** JSON으로 기술한다.
항목마다 `ref`(소절 키)가 필수다(계약 4).

```json
{
  "book": "책 제목",
  "items": [
    {"item": "나스닥100 20일선 위", "ref": "2-2", "source": "auto",
     "metric": {"type": "above_ma", "symbol": "^NDX", "ma": 20}},
    {"item": "섹터 3개↑", "ref": "5-4", "source": "manual", "reason": "무료 업종 데이터 없음"}
  ]
}
```

### 2. 커버리지 확인
```bash
python -m verdict.verify_auto_coverage <slug>
```
🤖/🚧/✋/❌ 로 무엇이 자동/미구현/직접/미결선인지 즉시 보인다. ❌ 는 발행 블로킹.

### 3. 커버 안 되는 항목 처리

> **원문 문구를 손대서 맞추는 선택지는 없다.** 책이 A를 보라는데 데이터가 B밖에
> 없으면, A를 구하거나(jhts 에 요청 + metric type 추가) A를 `manual`로 남긴다.
> 라벨을 B로 바꿔 적는 것은 금지다 — `playbook/verify_source_integrity.py` 가 매 발행마다 검사한다.

- **기존 metric.type로 표현 가능** → data_spec만 고치면 끝.
- **새 계산이 필요한데 데이터는 jhts 에 있음** → `metric_calc.py` 에 계산기 추가 + `metric_registry.json` 에 등록. **원천 수집이 필요하면 jhts 시세수집팀에 요청한다 — 이 리포에 수집기를 만들지 않는다.**
- **데이터 자체가 없음** → `metric_registry.json` 의 `no_data_types` 에 등록하고 `source:"manual"`, `reason` 명시. 지어내지 않는다.

---

## (d) 데이터가 없어 근본적으로 manual 인 것

아래는 jhts 가 서빙하지 않고 무료 공개 소스도 없어 자동판정이 불가능하다. 정직하게 `manual`로 둔다.

- **한국 창구별/투자자별 수급** (기관·투자자별 순매수, 창구별 거래 평단·강도)
- **업종/섹터 등락 집계** (섹터 3개↑ 동반 등 한국 업종 단위)
- **공매도 순보유잔고** — KRX 로그인 소스만 존재
- **호가/체결강도·틱 데이터**
- **뉴스 감성·애널리스트 추정** (`news_sentiment`, `analyst_estimate`)

원칙: **커버 안 되는 데이터는 지어내지 말고 `manual`로 표시.** 자동으로 붙는 것만 자동판정, 나머지는 사용자가 직접 확인하도록 한다.
