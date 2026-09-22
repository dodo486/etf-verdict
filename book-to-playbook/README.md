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
| `verify_coverage.py` | **커버리지 배지 검증**(모든 책) — 원문대로 구현됐나 · 규칙 출처(ref)가 맞나 · 원문에 없는 수치를 쓰지 않았나 |
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
4. **등록**: `books.json`에 항목 추가(slug/title/tickers/desc/live).
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
