# 데이터 소스 어댑터 프레임워크

새 트레이딩 책을 넣으면, 그 책 규칙에 필요한 데이터가 기존 어댑터로 **커버되면 시세 자동판정이 자동으로** 붙고, **안 되면 정직하게 "수동/데이터없음"** 으로 표시되게 만드는 레이어.

관련 파일:
- `datasources.py` — 어댑터 레이어(YahooAdapter / KisAdapter / ManualAdapter + 레지스트리)
- `verdict_engine.py` — data_spec(JSON)을 받아 각 항목을 자동 채우는 범용 판정 엔진
- `etf_data_spec.json` — ETF 책 규칙을 data_spec으로 옮긴 예시
- `verify_etf_migration.py` — 신규 엔진 결과 ↔ 레거시 `etf_daily_verdict.py` 대조검증

> 기존 파이프라인(`etf_daily_verdict.py` / `kis_intraday.py` / `etf_intraday_verdict.py` / `publish_pages.py`)의 **판정 로직은 건드리지 않는다.** 이 프레임워크는 그 옆에 추가된 범용 레이어다.
> (실행 방식만 OS 중립으로 바뀌었다 — `run.py` + `paths.py`. `SETUP.md` 참고.)

---

## (a) 어댑터 인터페이스

각 어댑터는 두 메서드만 구현한다.

```python
class SomeAdapter:
    source  = "yahoo"          # 결과 뱃지 식별자
    CADENCE = "eod"            # 기본 갱신 주기(eod|intraday|manual)

    def capabilities(self) -> set[str]:
        """지금 처리 가능한 metric.type 집합. 조건 불충족(예: 키 없음)이면 빈 집합."""

    def fetch(self, spec: dict) -> dict:
        """spec['metric']을 계산해 표준 결과 dict 반환."""
```

**표준 결과 dict** (fetch 반환):

| 키 | 뜻 |
|----|----|
| `ok` | bool 판정(임계값 있을 때) / 임계값 없으면 `None` |
| `value` | 대표 수치(있으면) |
| `label` | 사람이 읽는 한 줄(실제 수치 포함) |
| `status` | `"ok"` \| `"error"` \| `"manual"` |
| `source` | 어댑터 식별자(`yahoo`/`kis`/`manual`) |
| `reason` | status≠ok 일 때 사유 |

**레지스트리 & resolve** (`datasources.py`):

```python
ADAPTERS = [YahooAdapter(), KisAdapter(), ManualAdapter()]  # 우선순위 순

resolve(metric_spec)   # 그 metric.type을 처리 가능한 첫 어댑터. 없으면 ManualAdapter.
```

자동 소스(야후 EOD → KIS 장중)를 먼저 시도하고, **아무도 못 하면 항상 ManualAdapter로 폴백**한다. `source:"manual"`로 명시된 항목도 ManualAdapter가 처리한다.

### 뱃지 매핑 (아티팩트 렌더용)
| source | 뱃지 |
|--------|------|
| `yahoo` | 🤖 야후 EOD |
| `kis` | ⚡ KIS 장중 |
| `manual` | ✋ 직접 |

---

## (b) metric.type 카탈로그

| type | 뜻 | metric 필드 | 담당 어댑터 | cadence |
|------|----|-------------|-------------|---------|
| `above_ma` | 종가가 N일 이동평균 위인가 | `symbol`, `ma` | Yahoo | eod |
| `above_open` | 현재가가 당일 시가 위인가 | `symbol` | KIS | intraday |
| `pct_change` | 전일 대비 등락률(%) | `symbol`, `min?` | Yahoo | eod |
| `n_day_return` | 최근 N일 수익률(%) | `symbol`, `n`, `min?` | Yahoo | eod |
| `volume_ratio` | 거래량 / N일평균 배수 | `symbol`, `ref?`(기본20), `min?` | Yahoo | eod |
| `upper_wick` | 윗꼬리 %(고점 대비 종가 하락폭) | `symbol`, `min?` | Yahoo | eod |
| `higher_low` | 첫 눌림에서 저점 높임 여부 | `symbol` | KIS | intraday |
| `count_up` | 여러 심볼 중 상승 개수 | `symbols:[...]`, `min?` | Yahoo | eod |
| `ma_distance` | 종가와 N일선의 이격도(%) | `symbol`, `ma?`(기본5), `min?` | Yahoo | eod |
| `gap_up` | 당일 시가의 전일종가 대비 갭(%) | `symbol`, `min?` | Yahoo · KIS | eod · intraday |

`min`이 있으면 그 임계값으로 `ok`(True/False)를 매기고, 없으면 `ok=None`(수치만 노출).

> **임계값을 저자가 안 준 지표는 `min`을 비워 둔다.** 예: 2-7 "5일선과 얼마나 벌어졌는지",
> 7-3 "갭상승 날" — 둘 다 %가 원문에 없다. 숫자를 지어내는 대신 수치만 자동으로 채우고
> 판정은 사람이 하게 한다(시트에서는 체크박스 + 자동 수치 표기로 구현).
`min` 방향: `pct_change`는 초과(`>`), 나머지는 이상(`>=`).

---

## (c) 새 책 붙이는 법

### 1. data_spec.json 작성
책 매매시트의 각 체크 항목이 **어떤 데이터를 필요로 하는지** JSON으로 기술한다.

```json
{
  "book": "책 제목",
  "items": [
    {"item": "나스닥100 20일선 위", "source": "auto",
     "metric": {"type": "above_ma", "symbol": "^NDX", "ma": 20}, "cadence": "eod"},
    {"item": "엔비디아 시초가 위", "source": "auto",
     "metric": {"type": "above_open", "symbol": "NVDA"}, "cadence": "intraday"},
    {"item": "섹터 3개↑", "source": "manual", "reason": "무료 업종 데이터 없음"}
  ]
}
```

item 필드:
- `item` — 체크 항목 이름(표시용)
- `source` — `auto`(어댑터가 채움) 또는 `manual`(직접 확인). 생략하면 metric 유무로 추정.
- `metric` — `{type, ...}`. auto일 때 필수.
- `cadence` — `eod`/`intraday`/`manual`. 생략하면 어댑터 기본.
- `reason` — manual일 때 사유.

### 2. 커버리지 확인
```bash
python3 verdict_engine.py my_book_spec.json
```
출력 상단에 `자동 N/총 · 수동 M`. 각 줄 뱃지(🤖/⚡/✋)로 무엇이 자동/수동인지 즉시 보인다.

### 3. 커버 안 되는 항목 처리

> **원문 문구를 손대서 맞추는 선택지는 없다.** 책이 A를 보라는데 어댑터가 B밖에
> 못 주면, A를 구하거나(새 metric.type 추가) A를 `manual`로 남긴다. 라벨을 B로
> 바꿔 적는 것은 금지다 — `verify_source_integrity.py` 가 매 발행마다 검사한다.

- **기존 metric.type로 표현 가능** → data_spec만 고치면 끝.
- **새 계산 방식이 필요** → 해당 어댑터에 metric.type 하나 추가(카탈로그 + `fetch` 분기 + `HANDLES` 집합).
- **무료로 원천 데이터 자체가 없음** → `source:"manual"`, `reason` 명시. 지어내지 않는다.

---

## (d) 무료로 안 되는 데이터 = 근본적으로 manual

아래는 무료 공개 소스로 **원천 데이터 자체가 없어** 자동판정이 불가능하다. 정직하게 `manual`로 둔다.

- **한국 창구별/투자자별 수급** (외국인·기관 순매수, 창구별 매집·평단·매집강도) — 무료 API 없음
- **업종/섹터 등락 집계** (섹터 3개↑ 동반 등) — 무료로 섹터 단위 집계 없음
- **공매도 순보유잔고** — KRX 로그인 소스만 존재(무료 공개 없음)
- **달러인덱스 EOD** — 무료 심볼 폴백(DX-Y.NYB / DX=F)이 불안정 → 신뢰 필요 시 manual
- **호가/체결강도·틱 데이터** — 무료로 불가

원칙: **커버 안 되는 데이터는 지어내지 말고 `manual`로 표시.** 자동으로 붙는 것만 자동판정, 나머지는 사용자가 직접 확인하도록 한다.
