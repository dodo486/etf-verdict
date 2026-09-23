# book-to-playbook

트레이딩 책을 읽어 **① 저자 매매기법 플레이북 + ② 정량화된 실전 매매시트**를 인터랙티브 웹으로 자동 생성하고, 가능하면 **시세를 실시간으로 붙여 매일 자동 판정**까지 하는 파이프라인.

- 데모(공개 웹): https://dodo486.github.io/etf-verdict/
  - `/etf/` — 미국 돈복사 ETF (야후 EOD + 한투 KIS 장중 자동판정)
  - `/supply/` — 외국인 매집 (한국 수급=무료 데이터 없어 수동 시트)

## 설계 원칙

**템플릿(고정) + 콘텐츠(책마다 교체)** 분리. LLM은 구조화된 데이터만 뽑고, HTML 조립·판정은 결정론적 코드가 한다(렉·누락 방지).

```
책 원문 ──[추출]──▶ 플레이북 마크다운 + 시트 스펙(JSON)
                          │
        템플릿 HTML  ◀────┘   ──[조립]──▶ 책별 웹페이지 (플레이북/시트 2탭)
                          │
   data_spec(JSON) ──[verdict_engine + datasources 어댑터]──▶ 시세 자동판정
                          │
             books.json ──[build_home]──▶ 책 선택 홈 + 사이드 레일
```

## 책 계약 (모든 책이 지켜야 하는 최소 형식)

검사기들은 첫 책(etf)의 생김새에 맞춰 자랐다. 두 번째 책(supply)에는 커버리지 블록도
규칙 JSON도 없으니 검사기가 "검사 대상 아님"으로 **통째로 건너뛰었다** — 책이 둘로
늘어난 시점에 검증층의 실효가 0이 된 것이다. 조용히 넘어간 검사는 안 돈 검사다.

그래서 방향을 뒤집는다. **검사기가 책에 맞추는 게 아니라, 책이 계약에 맞춘다.**
계약을 못 채우는 책은 검사를 건너뛰는 게 아니라 **등록이 안 된다.**

| 조항 | 내용 | 있어야 할 곳 |
|---|---|---|
| 계약 1 | 원문이 **소절 단위로 잘려** 있고 소절마다 고유 키가 있다 (`N-n` 형식, 그 외 `프롤로그`/`에필로그`) | `books/<slug>/source_index.json` |
| 계약 2 | 규칙은 **JSON 파일로 존재**하고 규칙마다 `ref`(소절 키)가 있다 | `books/<slug>/rules.json` |
| 계약 3 | 커버리지 맵이 소절 **전수**를 분류한다 (reflected / gap / mindset) | 책 HTML 의 `coverage-data` 블록 |
| 계약 4 | `data_spec` 항목에도 `ref` 가 있다 | `books/<slug>/data_spec.json` |

- **계약 2 보충**: HTML 안의 JS 리터럴(`const DATA = [...]`)은 **계약 위반**이다. 규칙이
  코드 안에 박혀 있으면 읽는 쪽이 책마다 달라진다 — 검사기가 etf 전용이 된 원인이 정확히
  그것이다. 규칙은 파일로 나와야 한다.
- **계약 4 보충**: `ref` 는 규칙과 수집요청을 짝지을 **유일한 열쇠**다. 없으면 "이 데이터를
  어느 규칙 때문에 받는가"를 사람 기억이 잇게 되고, 규칙이 바뀌어도 spec 은 그대로 남는다.

검사는 `verify_contract.py` 가 한다(미충족이면 exit 1). **지금은 실패가 정상이다** —
현재 etf 1/4, supply 0/4. 계약을 채우는 건 책 쪽 작업이지 검사 쪽 작업이 아니다.
**통과시키려고 검사를 느슨하게 만들지 말 것.**

### 책마다 **다른** 것은 코드가 아니라 설정으로 뺀다

앞으로 만드는 검사기는 어떤 책에서도 돈다. 책마다 갈리는 건 코드가 아니라 설정이다.

| 다른 것 | 설정 내용 | 그게 없는 책은 |
|---|---|---|
| 오귀속 검사의 **축** | etf = 종목↔장 매핑 `{TQQQ:3, SOXL:4, UPRO:5}` | 그 검사만 **'미적용'으로 보고**한다. **통과로 찍지 않는다** |
| 토큰 **단위 사전** | 공통 `%`·`배`·`개`·`일` + 책별 `억`·`만주`·`연속`·`단계` | 공통 사전만으로 돈다 |
| 시트 **단계 목록** | 규칙 JSON에서 자동 추출 | 계약 2 미충족이므로 등록 불가 |

'미적용'을 '통과'로 적는 순간 검증층은 또 거짓이 된다. 못 본 것은 못 봤다고 적는다.

## 구성 파일

| 파일 | 역할 |
|---|---|
| `SKILL.md` | OMC 스킬 정의(트리거·파이프라인) |
| `templates/example-etf.html` | 디자인/구조 기준 템플릿 |
| `books.json` | 책 목록 매니페스트(SSOT). 홈·사이드레일이 여기서 생성 |
| `build_home.py` | books.json → 책 선택 홈 + 정적 책 조립 |
| `inject_nav.py` | 각 책에 사이드 책-전환 레일 주입 |
| `datasources.py` | 데이터 어댑터(Yahoo 무료 / KIS / Manual) + resolve 레지스트리 |
| `verdict_engine.py` | data_spec(JSON) → 항목별 자동/수동 판정 |
| `etf_data_spec.json` | ETF 규칙의 데이터 명세 예시 |
| `ADAPTERS.md` | 어댑터 인터페이스 · metric.type 카탈로그 · 새 책 붙이는 법 |
| `etf_daily_verdict.py` | ETF EOD 판정(야후) — 레거시, 검증됨 |
| `kis_intraday.py` | 자립 KIS 클라이언트(현재가·분봉·첫눌림). **TLS 검증 필수** |
| `etf_intraday_verdict.py` | 개장+31분 장중 판정(KIS) |
| `publish_pages.py` | 판정 병합 → `public/etf/index.html` |
| `verify_etf_migration.py` | 신규 엔진 ↔ 레거시 대조검증 |
| `verify_source_integrity.py` | **저자 원문 불변 검사**(모든 책). `run.py`가 매 발행마다 실행 |
| `verify_source_fabrication.py` | **구간① 창작 검사**(모든 책) — 플레이북의 저자-귀속 규칙이 실존 소절(`ref`)에 근거하나 · 그 정량 토큰이 원문 소절에 실제로 있나(없으면 창작) |
| `verify_coverage.py` | **커버리지 배지 검증**(모든 책) — 원문대로 구현됐나 · 규칙 출처(ref)가 맞나 · 원문에 없는 수치를 쓰지 않았나 |
| `verify_contract.py` | **책 계약 4조 검사**(모든 책) — 소절 키 · 규칙 `ref` · 커버리지 전수 · spec `ref`. 못 채운 책은 등록 불가 |
| `coverage_exempt.json` | 위 검사의 면제 목록(사유 필수) |
| `source_baseline.json` | 위 검사의 기준 해시(커밋 대상) |
| `paths.py` | **경로·인코딩 단일 기준점** (macOS/Windows 공용). BASE/PUBLIC/LOGS 결정, UTF-8 출력 고정 |
| `run.py` | **스케줄 러너**(OS 중립) — `daily` / `intraday` / `publish` |
| `run.sh` / `run_intraday.sh` / `run.cmd` | 얇은 OS 래퍼. 실제 동작은 전부 `run.py` |
| `SETUP.md` | 설치·크레덴셜·스케줄 등록(launchd / 작업 스케줄러) |

## 새 책 추가하는 법

1. **추출**: 책 원문(정제 텍스트)을 서브에이전트로 완독 → 플레이북 마크다운(PART A) + 시트 스펙 JSON(PART B). 규칙: 저자 명시분만·원문 숫자·미명시 표기·지어내기 금지.
2. **조립**: `templates/example-etf.html`을 베이스로 콘텐츠만 교체 → `<slug>-playbook.html`.
3. **데이터 명세**: 그 책 규칙에 필요한 데이터를 `data_spec.json`으로. `datasources.py`의 어댑터가 커버하면 자동판정이 붙고, 무료 소스가 없으면(한국 수급·업종·공매도잔고 등) `source:"manual"`로 정직하게 표시.
4. **등록**: `books.json`에 항목 추가(slug/title/tickers/desc/live). 등록의 조건은
   **계약 4조 충족**이다 — `python verify_contract.py` 가 그 책 줄에서 4조를 모두 ✅로
   찍어야 한다. 못 채우면 등록이 아니라 미완이다(검사를 건너뛰게 두지 않는다).
5. **배포**: `build_home.py`(정적) 또는 `publish_pages.py`(라이브) 실행.

자세한 어댑터/metric 규약은 `ADAPTERS.md` 참고.

## 실행

```
python run.py daily        # EOD 판정 → 발행
python run.py intraday     # 장중 판정 → 발행 (개장+31분)
python run.py publish      # 재판정 없이 발행만
```

macOS·Windows 어느 쪽에서도 같은 명령으로 돈다. 설치 위치도 자유다
(경로는 `paths.py`가 결정 — 하드코딩 없음). 스케줄 등록은 `SETUP.md` 참고.

## 크레덴셜 (커밋 안 됨)

- `kis.env` — 한투 Open API `KIS_APP_KEY` / `KIS_APP_SECRET` (미국주식 시세용, 주문 안 함)
- `telegram.env` — (선택) 텔레그램 알림 토큰
- 위 파일들과 `.kis_token.json`, `logs/`, `public/`(별도 배포 레포), 런타임 JSON은 `.gitignore` 처리.

## 한계 (정직하게)

- 무료로 자동 판정 가능한 데이터: 미국 주식/지수/VIX/금리(야후), 미국주식 실시간·분봉(KIS).
- **자동 불가(근본적 manual)**: 한국 창구별/투자자별 수급, 업종 등락 집계, 공매도 순보유잔고(KRX 로그인), 호가/체결. 이런 데이터를 쓰는 책은 "읽고 수동 체크"까지만 자동화된다.
- KIS 해외 무료 시세는 15분 지연일 수 있음(실시간은 유료 신청).
