# 마이그레이션 노트 — "아침 판정" 폐기 → asof(관측 시점) 모델

브랜치 `refactor/asof-model`. 커밋/푸시 안 함(워킹트리만).

핵심: 하루 한 시점 고정 평가("아침 판정")를 **완전히 폐기**하고, 평가를 **사용자가 보는 그
순간(asof)** 기준으로 바꿨다. 종가 조건 = asof 이하 마지막 확정 일봉(고정), 장중 조건 = asof 이하
마지막 분봉(살아 있음). 데이터가 없으면 None(모름) → 장중 observe 는 manual(🟡)로 정직하게 떨어진다.

---

## ① 삭제한 심볼·파일·라인

`at`("저자가 말한 시각" 노드) 기계장치 전수 제거. 삭제·교체 목록(`shared/cond.py`):

| 삭제한 것 | 옛 위치(대략) | 대체 |
|---|---|---|
| `AT_KEYS` 상수 | cond.py:80 | 없음 |
| `AT_OFFSET_CAP` 상수 | cond.py:81 | 없음 |
| `px` 검증의 `at` 블록(close 한정·offset 정수·±1440 검사) | cond.py:140-149 | `tf` 는 "1d"/"1m" 만 허용 |
| `_op_of` 의 px 예외 목록에서 `"at"` | cond.py:105 | `("sym","tf")` 만 |
| `Ctx.px` 의 `at` 분기 + `at_series` 호출 | cond.py:259-278 | `px(sym, field, tf)` — tf="1m" 은 `minute_series` |
| `_MINUTE_TZ` 테이블 | cond.py:285 | 없음(분봉 키는 UTC 로 통일) |
| `_to_minute_key()` | cond.py:288-300 | 없음 |
| `_next_session()` | cond.py:303-308 | 없음 |
| `_session_of()` | cond.py:311-316 | 없음 |
| `at_series()` | cond.py:319-347 | `minute_series(minutes, cal, field, asof)` 로 대체 |
| `_at_nodes(tree)` | cond.py:864-869 | `_minute_nodes(tree)`(tf="1m" px 노드) |
| `at_offsets(tree)` | cond.py:885-887 | 없음(아침 고정 시각 개념 삭제) |
| `Ctx.sessions` / `Ctx.market` 필드·인자 | cond.py:233-234,241-242 | 없음(세션 달력 불필요) |
| `Ctx(now=...)` 인자·`Ctx.now` 필드 | cond.py:227,232 | `Ctx(asof=...)` / `Ctx.asof` 로 승격 |

`shared/tree_grade.py`:
- `History.sessions` · `History.market` 필드 삭제(분봉은 `History.minutes` 만 남음).
- `history()` 에서 `md_feed.sessions()` · `md_feed.market_of()` 수집 삭제(세션 달력 안 받음).
- `ProductEval(..., asof=None)` 추가 → Ctx 로 전달.
- `_view` 의 skip 집합에서 `"at"` 제거.

`run.py`:
- `watch()` 전면 재작성: 옛 "다음 정규장 개장 ± 저자 시각까지 대기" 로직(at_offsets·minute_symbols·
  `cond._next_session`·`md_feed.sessions`) 삭제 → **asof=지금 기준 `--every N`(기본 5)분 주기 재평가**
  (`--cycles K` 로 횟수 제한). 사용법 docstring 도 asof 로 수정.

`verdict/verdict_engine.py`:
- `render(slug, asof=None)` · `product_verdict(..., asof=None)` 추가(asof 단일 축을 호출부로 노출).
- 알림 꼬리말 "※ 종가 기준 판정" → "※ 관측 시점(asof) 기준 판정 …" 로 수정.

`verdict/verify_primitives.py`:
- `t_at()` → `t_asof()` 로 교체. `at_series`/`at` 노드/세션 지어넣기 테스트를 **`minute_series`(asof 슬라이싱)
  + `tf="1m"` 노드** 테스트로 전면 교체. `t_no_excluded_live()` 도 `now=`/`at` → `asof=`/`tf="1m"` 로 교체.
  main() 등록 이름 "저자 시각" → "관측 시점(asof)".

`checklist/COND_DSL.md`:
- `at` 문법 줄 삭제 → "장중(분봉) 값 = `{"px":"close","tf":"1m"}`" 로 교체.
- "저자가 말한 시각에 본다 — at · observe" 절 → "관측 시점(asof)에 본다 — 장중 조건은 observe" 로 재작성.
- "봉 단위(tf)" 절을 asof 축 설명으로 재작성(1d=확정 일봉, 1m=asof 이하 마지막 분봉).

`checklist/verify_tree.py` · `verdict/backtest.py`: "저자 시각" 서술을 asof/장중 observe 로 수정(동작 불변).

**신규 함수** `cond.minute_series(minutes, cal, field, asof=None)`: 날짜별 'asof 이하 그날 마지막 분봉'의
필드 값. `minutes = {YYYYMMDDHHMM(UTC): {o,h,l,c,v} 또는 종가}`. 그날 범위에 분봉 없으면 None.

**상수 변경** `TIMEFRAMES = ("1d",)` → `("1d", "1m")`.

---

## ② at 트리조건 → asof observe 재표현 매핑

모든 `{"px":"close","sym":X,"at":{"open_offset_min":m}}` → `{"px":"close","sym":X,"tf":"1m"}`
(같은 observe 래퍼 안에서). 아침 "개장 m분 전 스냅샷"이 아니라 **asof 시점의 그 심볼 장중 분봉 값**을 본다.

| 책 | 조건(원문) | 옛 at | 새 표현 |
|---|---|---|---|
| trend | 개장 전 S&P500 선물 방향(1-1) — `env_stable` def 및 IWM.filter 인라인 | ES=F `at -1` | ES=F `tf:"1m"` observe |
| trend | 개장 전 나스닥 선물 방향(1-1) — 위 2곳 | NQ=F `at -1` | NQ=F `tf:"1m"` observe |
| moneycopy | 개장 10분 전 S&P500 선물 버팀(2-6 점수표) — `점수_SP선물` def + 각 상품 caution(시장_3점) 인라인 | ES=F `at -10` | ES=F `tf:"1m"` observe |

- trend tree.json: at 4개 → tf:"1m" 4개. moneycopy tree.json: at 7개(def 1 + 상품 caution 인라인 6) → tf:"1m" 7개.
- 후보·심판 파일도 같은 규칙으로 이행(이중 추출 게이트가 돌아가야 하므로):
  `trend/tree_candidates/a.json·b.json`(각 2개), `moneycopy/tree_candidates/a.json·b.json`·`tree_review.json`.
- 트리의 `note`·`manual` 문구 중 "개장 직전/개장 10분 전 1분봉" → "asof(관측 시점) 장중 분봉"으로 수정
  (사용자 노출 문구). 저자 원문 라벨("개장 전 선물 방향 안정" 등)은 **그대로 둠** — 조건 자체의 서술이지
  아침 고정 기계장치가 아니다.

재표현 결과(의도된 동작):
- **분봉이 asof 기준 있으면 자동 판정**(지금 jhts 가 ES=F/NQ=F 분봉을 최근 ~7거래일 주므로, 당일 선물
  방향 observe 가 실제로 자동으로 풀린다 — 데모에서 trend '아침 환경 안정'이 🟢 로 뜬다).
- **분봉이 없는 과거·미연결 심볼은 None → manual(🟡)** 로 떨어진다(옛 폴백과 동일, 아침 고정만 제거).

---

## ③ 설계 가정(사용자/상위 검토용)

1. **asof = 단일 관측 축.** `Ctx.now` 를 `Ctx.asof`(UTC datetime) 로 승격. 라이브 = 실제 지금 또는 지정
   시각, 백테스트 = 재생되는 각 시점. `render(asof=)` / `ProductEval(asof=)` 로 호출부에 노출.
2. **분봉 귀속일이 바뀐다(핵심 의미 변화).** 옛 at 모델은 "판정일 d 의 다음 개장 분봉"을 **d 의 값**으로
   썼다(아침 고정). asof 모델은 분봉을 **그 분봉 자신의 거래일(키 앞 8자리)** 에 귀속한다. 그래서 과거
   재생 시 선물 값이 하루 뒤로 이동한다 — 이것이 asof 모델의 정의상 올바른 동작이다.
3. **tf="1m" 은 종가뿐 아니라 OHLCV 봉도 받는다.** `minute_series` 는 분봉 값이 dict 면 `field` 를 꺼내고,
   스칼라면 종가로 본다 — 현재 `{키:종가}` 계약과 목표 OHLCV 계약 둘 다 무변경으로 지원.
4. **세션 캘린더 의존 제거.** 개장/마감 시각을 코드가 몰라도 된다(asof 슬라이싱은 분봉 키의 UTC 시각만
   비교). `md_feed.sessions()`/`market_of()` 는 더 호출하지 않는다(파이프라인에서 미사용 — ⑤ 참고).
5. **분봉 키 시간대 = UTC 로 통일.** 옛 `_MINUTE_TZ`(US=UTC, KR=KST) 표 삭제. jhts 분봉 키는 UTC
   `YYYYMMDDHHMM` 로 받는다고 가정(현재 ES=F 샘플이 UTC 임을 확인). KR 분봉이 들어오면 jhts 가 UTC 키로
   주거나, 그때 `minute_series` 한 곳에서 tz 를 받도록 확장(후속).
6. **단일 일봉 달력 유지.** `cal` 은 상품 일봉 날짜 그대로. 분봉은 그 날짜들에 asof 로 매핑만 한다 —
   분봉 다축 달력(그날 분봉 구간 전체를 독립 축으로)은 이번 범위 밖(⑤).
7. **moneycopy SOXL.sizing·UPRO.sizing 심판 추가.** asof 귀속일 변화로 a·b 두 추출의 **동등한** 장전
   스코어카드 인코딩이 최근 분봉 구간 2일에서만 갈렸다(옛엔 0일 → 심판 불필요였음). 채택 트리(a 동작)와
   같으므로 `tree_review.json` 에 `winner:"a"` + 사유를 추가해 이중 추출 게이트를 통과시켰다. TQQQ.sizing 은
   이미 custom 심판이 있어 무관.

---

## ④ jhts 분봉 데이터 계약 초안

현재(`md_feed.minutes(symbol)` → `md.minute_closes`):
```
{ "YYYYMMDDHHMM(UTC)": 종가(float) }    # 종가만. 미국 심볼 최근 ~7거래일.
```

목표(OHLCV·tz 명시):
```
minutes(symbol) -> { "YYYYMMDDHHMM(UTC)": {"open":f,"high":f,"low":f,"close":f,"volume":f} }
```
- **키 = UTC 분(YYYYMMDDHHMM).** asof 슬라이싱이 분봉 키를 UTC asof 와 문자열 비교하므로 UTC 고정이 필수.
  KR 분봉도 UTC 키로 준다(또는 계약에 tz 필드를 두고 `minute_series` 가 받도록 확장 — 후속).
- **값 = OHLCV dict.** `cond.minute_series` 는 이미 dict/스칼라 둘 다 받으므로, jhts 가 종가만 주던 것을
  OHLCV dict 로 바꿔도 트리·평가기 변경 없이 그날 분봉의 high/low/open/volume 까지 tf="1m" 로 읽힌다.
- **보관 기간**이 늘면 장중 observe 의 과거 자동 판정 구간(백테스트 반영)도 그만큼 자동으로 는다.
- **md_feed 는 jhts 세션 함수(sessions/market_of)를 더는 호출하지 않으므로**, jhts 쪽에서 세션 API
  유지 여부는 이 파이프라인과 무관해짐.

### ④-T  [TEMP] yfinance 임시 분봉 제공자 — jhts OHLCV 연결 시 통째 삭제

jhts 분봉이 아직 OHLCV 로 안 와서, 위 목표 계약을 **임시로 yfinance** 가 채운다. 흔적0 격리:
  · yfinance 를 import 하는 파일은 **단 하나**: `shared/_temp_yf_minutes.py`(신규).
  · 스왑 포인트는 **1곳**: `shared/md_feed.py` 의 `minutes()`(TEMP 두 줄 — 원래 jhts 경로는 바로 아래 주석).
  · 계약 형태는 위 목표(④)와 동일: `{YYYYMMDDHHMM(UTC): {open,high,low,close,volume}}`.
  · 정직한 한계: yfinance 1분봉은 최근 ~7일만. 그 밖·실패·빈결과 → `{}`(→ 모름 → observe 는 manual 🟡).
    가짜로 안 채운다. (과거 asof 는 여전히 None 으로 정직하게 떨어짐을 실측 확인.)

**삭제 체크리스트(jhts 분봉 OHLCV 연결 시):**
1. `shared/_temp_yf_minutes.py` 파일 통째 삭제.
2. `shared/md_feed.py` 의 `minutes()` 를 jhts 경로로 되돌림(TEMP 두 줄 삭제 → 바로 아래 주석 블록 복원).
3. `pip uninstall yfinance`(및 함께 설치된 curl_cffi·lxml·peewee 등 전이 의존 — 필요 시).
4. `grep -rn "yfinance\|_temp_yf" .`(`.venv` 제외) 가 **0건**인지 확인.

- `md_feed.minutes` 의 docstring 은 이미 OHLCV 계약(위 목표)으로 갱신됨(TEMP 제공자가 그 형태로 채움).

---

## ⑤ 후속으로 남긴 것

1. **분봉 다축 달력.** 지금은 분봉을 일봉 달력 날짜에 "asof 이하 마지막 1봉"으로 접어 넣는다. 그날의 분봉
   구간 전체를 독립 축으로 돌리는 창·시간 연산(분봉 ma 등)은 데이터 계약(④) 확정 후. `cond.minute_series`
   한 곳만 확장하면 된다(평가기 다른 부분 무변경).
2. **OHLCV 분봉 수집.** jhts `minute_closes`(종가) → OHLCV dict 로 확장(④). 평가기는 준비됨.
3. **분봉 tz 일반화.** KR 등 비-UTC 분봉이 오면 `minute_series` 에 tz 파라미터 추가(현재 UTC 가정).
4. **`md_feed.sessions`/`market_of` 정리.** 이 파이프라인에서 호출부가 사라졌다 — md_feed 에 함수는 남아
   있으나 미사용. jhts 다른 소비자가 없으면 다음 청소 때 제거 가능(이번 범위에선 어댑터 축소를 피해 보존).
5. **발화 통계 경고 61건.** 전부 기존부터 있던 '데이터 부족(판정 불가 N일)' 경고(재추출 대상, 비차단).
   asof 전환으로 늘지 않았다.
