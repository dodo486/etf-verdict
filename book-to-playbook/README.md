# book-to-playbook

트레이딩 책을 읽어 **① 저자 매매기법 플레이북 + ② 정량화된 실전 매매시트**를 인터랙티브 웹으로 자동 생성하고, 가능하면 **시세를 실시간으로 붙여 매일 자동 판정**까지 하는 파이프라인.

- 데모(공개 웹): `/trend/` — SPY·QQQ·IWM 추세추종 스윙 (jhts EOD 자동판정)

## 팀 구조 (폴더 = 조직도)

파이프라인은 세 구간이고, 구간마다 팀 폴더가 하나다. 팀 코드는 **자기 팀 + shared/**만
import 할 수 있다 — 팀 사이 인터페이스는 코드가 아니라 산출물 파일(`books/<slug>/*.json`)이다.
이 경계는 `verify_teams.py` 가 매 발행마다 기계로 강제한다.

| 폴더 | 구간 | 하는 일 | 팀 산출물(다음 팀의 입력) |
|---|---|---|---|
| `playbook/` | ① 책 원본 → 플레이북 | 원문 소절 인덱싱 · 원문 무결/창작 검사 | `books/<slug>/source_index.json` |
| `checklist/` | ② 플레이북 → 체크리스트 | 규칙·UI 주입 · 커버리지 배지 검증 | `books/<slug>/rules.json` (+시트 HTML) |
| `verdict/` | ③ 체크리스트 → 수집·판정 | **jhts 시세수집팀** 데이터로 자동판정 | `latest-verdict.json` |
| `shared/` | 공통층 | paths·tokens·exempt·rules_io·pages·notify | — |
| `publish/` | 발행·서빙층 | 홈/책 조립 · GitHub Pages 발행 · 로컬 실시간 서버 | `PUBLIC/<slug>/index.html` |
| (루트) | 조립·감사 | `run.py`(러너) · `verify_contract.py`(계약) · `verify_teams.py`(경계) | — |

**구간③의 철칙**: 시세는 오롯이 jhts 시세수집팀(`jhts.marketdata`)에서 온다.
그 창구가 `shared/md_feed.py` **하나**다. 야후/KIS/스크래핑을 팀 안에서 직접 만드는 것은
`verify_teams.py` 가 import 수준에서 잡아 발행을 정지시킨다.

```
책 원문 ──[playbook 추출]──▶ 플레이북 마크다운 + source_index.json
                                  │
        템플릿 HTML  ◀── [checklist 조립: rules.json·ui/*.js 주입] ──▶ 책별 웹페이지 (플레이북/시트 2탭)
                                  │
   tree.json(조건 트리) ──[verdict: md_feed(jhts) → cond → tree_grade → verdict_engine]──▶ 자동판정
                                  │
             books.json ──[publish: build_home / publish_pages / serve]──▶ 홈 + 발행 + 실시간
```

## 검증층 — 검사기 3개 (발행 관문, `run.py publish`)

| # | 검사기 | 보는 것 | 방식 |
|---|---|---|---|
| ① | `verify_structure` | 형식·구조 — 팀 경계·원문 해시·책 계약·손 박은 체크박스 | 기존 4개 검사를 하나의 관문으로 |
| ② | `verdict.verify_primitives` | 조건 트리 원시함수가 계산을 맞게 하나 | pandas 기준값 대조·3값 논리 전수·인과성·문법·버그 유형 회귀. 책이 늘어도 크기 고정 |
| ③ | `checklist.verify_tree` | 규칙이 원문 뜻대로 **동작**하나 | 독립 추출 2개를 실제 시세 3년으로 비교(갈린 구역은 심판 기록 필수) · 원문 사례 재현 · 발화 통계 |

옛 검사(창작·커버리지·규칙↔명세·의미검사·자동가능)는 원문과 규칙의 **글자**를 대조했다 — 숫자 '2'만 있으면
'2거래일 유지'가 1일로 판정돼도 통과했고, 어휘 사전에 없는 새 조건은 '찾은 게 없으니 누락 없음'으로 통과했다.
그래서 관문에서 뺐다(파일은 화면 체크리스트가 rules.json 을 쓰는 동안 남아 있다).

### 규칙은 조건 트리로 (`books/<slug>/tree.json`, 문법: `checklist/COND_DSL.md`)

등급은 트리 하나에서만 나온다(`shared/tree_grade.py`). 트리를 만드는 절차 — 사람 없이:
1. 서로 문맥을 공유하지 않는 추출자 2명이 **플레이북(① 산출물)만 보고** `tree_candidates/a.json`·`b.json`
   (매도 규칙은 `exit_a.json`·`exit_b.json`)을 쓴다. 규칙의 출처는 플레이북이다 — 원문을 다시 읽어 ①의 일을
   ③에서 되풀이하지 않는다. 플레이북이 원문과 어긋나면 트리가 아니라 **플레이북을 고친다**(감사 → 수정 →
   `verify_source_integrity --accept --why`).
2. 다른 작성자가 **원문**만 보고 `scenarios.json`(원문 사례 → 합성 시세 → 기대값)을 쓴다 — 플레이북에서 뽑은
   트리를 원문 쪽에서 독립적으로 검증하는 장치다.
3. `python -m checklist.verify_tree <slug> --dump N` → 판정이 갈린 날의 수치를 심판이 원문과 대조해
   `tree_review.json` 에 승자(a·b·custom)와 근거를 남긴다. 사례가 틀렸으면 `scenario_overrides`, 원문 그대로라
   정상인 통계 경고는 `fire_ack` 에 사유를 남긴다.
4. `python -m checklist.verify_tree <slug> --adopt` → `tree.json`. 검사기 ③ 이 통과해야 발행된다.

## 설계 원칙

**템플릿(고정) + 콘텐츠(책마다 교체)** 분리. LLM은 구조화된 데이터만 뽑고, HTML 조립·판정은 결정론적 코드가 한다(렉·누락 방지).

## 책 계약 (모든 책이 지켜야 하는 최소 형식)

검사기들은 첫 책의 생김새에 맞춰 자랐다. 두 번째 책에는 커버리지 블록도
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
  코드 안에 박혀 있으면 읽는 쪽이 책마다 달라진다 — 검사기가 특정 책 전용이 된 원인이 정확히
  그것이다. 규칙은 파일로 나와야 한다.
- **계약 4 보충**: `ref` 는 규칙과 수집요청을 짝지을 **유일한 열쇠**다. 없으면 "이 데이터를
  어느 규칙 때문에 받는가"를 사람 기억이 잇게 되고, 규칙이 바뀌어도 spec 은 그대로 남는다.

검사는 `verify_contract.py` 가 한다(미충족이면 exit 1). 계약을 채우는 건 책 쪽 작업이지 검사 쪽 작업이 아니다.
**통과시키려고 검사를 느슨하게 만들지 말 것.**

### 책마다 **다른** 것은 코드가 아니라 설정으로 뺀다

앞으로 만드는 검사기는 어떤 책에서도 돈다. 책마다 갈리는 건 코드가 아니라 설정이다.

| 다른 것 | 설정 내용 | 그게 없는 책은 |
|---|---|---|
| 오귀속 검사의 **축** | `books.json verify.attribution_axis` (종목↔장 매핑) | 그 검사만 **'미적용'으로 보고**한다. **통과로 찍지 않는다** |
| 토큰 **단위 사전** | 공통 `%`·`배`·`개`·`일` + 책별 `억`·`만주`·`연속`·`단계` | 공통 사전만으로 돈다 |
| 시트 **단계 목록** | 규칙 JSON에서 자동 추출 | 계약 2 미충족이므로 등록 불가 |

'미적용'을 '통과'로 적는 순간 검증층은 또 거짓이 된다. 못 본 것은 못 봤다고 적는다.

## 구성 파일

| 파일 | 역할 |
|---|---|
| `SKILL.md` | OMC 스킬 정의(트리거·파이프라인) |
| `trend-playbook.html` | 디자인/구조 기준 템플릿 |
| `books.json` | 책 목록 매니페스트(SSOT). 홈·사이드레일·엔진 선택이 여기서 |
| `run.py` | **스케줄 러너**(OS 중립) — `daily` / `intraday` / `publish`. 모든 단계를 `python -m <팀>.<모듈>` 로 실행 |
| `verify_contract.py` | **책 계약 4조 검사**(모든 책) + 규칙 누출 검사. 못 채운 책은 등록 불가 |
| `verify_teams.py` | **팀 경계 검사** — 팀 간 import 금지 · jhts 단일창구 · 자가수집 네트워크 코드 금지 |
| `playbook/book_source.py` | 원문 → 소절 인덱스(`source_index.json`) 생성 |
| `playbook/verify_source_integrity.py` | **저자 원문 불변 검사**(모든 책). 매 발행마다 실행 |
| `playbook/verify_source_fabrication.py` | **구간① 창작 검사** — 저자-귀속 규칙이 실존 소절(`ref`)에 근거하나 |
| `checklist/inject_rules.py` | `rules.json` → 책 HTML 주입(사본 드리프트 게이트 포함) |
| `checklist/inject_ui.py` | 공유 UI(`checklist/ui/*.js`) → 책 HTML 주입 |
| `checklist/verify_coverage.py` | **커버리지 배지 검증** — ✅반영 주장이 사실인가 |
| `shared/md_feed.py` | **jhts 시세수집팀 어댑터 — 유일한 시세 창구** |
| `shared/cond.py` | **조건 트리 문법·평가기**(책 무관) — 원시 시계열 연산 조합 · 3값(참/거짓/모름) · 하한 · 수동 극성 |
| `shared/tree_grade.py` | 트리 → 날짜별 등급(✅/🟡/🚫/⛔/⚪/❔)·사유 |
| `verdict/verdict_engine.py` | 라이브 판정 — 등급은 tree_grade, 화면 표시 수치는 rules.json metric(metric_calc) |
| `verdict/metric_calc.py` | rules.json 의 metric 선언 → 화면 표시용 값 (등급엔 안 쓴다) |
| `verdict/backtest.py` | **신호 백테스트** — 트리로 매일 종가 기준 등급을 재현, 다음날 시가 진입 → 5·10·20일 수익률을 등급별로 |
| `verify_structure.py` · `verdict/verify_primitives.py` · `checklist/verify_tree.py` | 검사기 ①②③ (위 '검증층') |
| `verdict/verify_rules_vs_spec.py` | 체크리스트 ↔ 수집요청 대조(창작·누락) |
| `verdict/verify_auto_coverage.py` | '자동 가능한데 ✋직접으로 샌 것' 검사 |
| `shared/` | paths(경로·인코딩) · tokens(정량 토큰) · exempt(면제) · rules_io(규칙 읽기) · pages(페이지 찾기) · notify(알림 발신) |
| `publish/build_home.py` | books.json → 책 선택 홈 + 정적 책 조립 |
| `publish/publish_pages.py` | 판정 병합 → `PUBLIC/<slug>/index.html` |
| `publish/serve.py` | 로컬 실시간 서버(폴링/SSE) |
| `coverage_exempt.json` | 검사 면제 목록(분류·사유 필수 — 전 팀 공유) |
| `playbook/book_sources.json` | 책 원문 위치 설정(① 소유) |
| `playbook/source_baseline.json` | 원문 무결 검사의 기준 해시(① 소유, 커밋 대상) |
| `verdict/metric_registry.json` | metric type 의 자동/무데이터 분류(③ 소유 SSOT) |
| `ADAPTERS.md` | 구간③ 데이터 계층 · metric.type 카탈로그 · 새 책 붙이는 법 |
| `SETUP.md` | 설치·크레덴셜·스케줄 등록(launchd / 작업 스케줄러) |

## 새 책 추가하는 법

1. **추출**(①): 책 원문(정제 텍스트)을 서브에이전트로 완독 → 플레이북 마크다운(PART A) + 시트 스펙 JSON(PART B). 규칙: 저자 명시분만·원문 숫자·미명시 표기·지어내기 금지. `python -m playbook.book_source --write` 로 소절 인덱스 생성.
2. **조립**(②): `trend-playbook.html`을 베이스로 콘텐츠만 교체 → `<slug>-playbook.html`. 규칙은 `books/<slug>/rules.json` 으로(HTML 리터럴 금지).
3. **데이터 명세**(③): 그 책 규칙에 필요한 데이터를 `data_spec.json`으로. `verdict/metric_registry.json` 의 auto type 이면 자동판정이 붙고, 데이터가 없으면(한국 수급·업종·공매도잔고 등) `source:"manual"`로 정직하게 표시. 새 데이터가 필요하면 **jhts 시세수집팀에 요청**한다 — 여기서 직접 수집기를 만들지 않는다.
4. **등록**: `books.json`에 항목 추가(slug/title/tickers/desc/live). 등록의 조건은
   **계약 4조 충족**이다 — `python -m verify_contract` 가 그 책 줄에서 4조를 모두 ✅로
   찍어야 한다. 못 채우면 등록이 아니라 미완이다(검사를 건너뛰게 두지 않는다).
5. **배포**: `python -m publish.build_home`(정적) 또는 `python run.py publish`(라이브).

자세한 metric 규약은 `ADAPTERS.md` 참고.

## 실행

```
python run.py daily        # EOD 판정 → 발행
python run.py intraday     # 장중 판정 → 발행 (개장+31분)
python run.py publish      # 재판정 없이 발행만
python -m verdict.backtest <slug> [--days 365]   # 신호 백테스트 → logs/backtest-<slug>.json
python -m verdict.backtest <slug> --page         # 책 페이지 "📊 백테스트" 탭 데이터(1년·3년) → backtest-<slug>.json (daily 가 자동 실행, publish_pages 가 주입)
```

macOS·Windows 어느 쪽에서도 같은 명령으로 돈다. 설치 위치도 자유다
(경로는 `shared/paths.py`가 결정 — 하드코딩 없음). 스케줄 등록은 `SETUP.md` 참고.

개별 모듈은 `book-to-playbook/` 에서 `python -m <팀>.<모듈>` 로 돈다
(예: `python -m checklist.verify_coverage`, `python -m verdict.verdict_engine trend --json --no-send`).

## 크레덴셜 (커밋 안 됨)

- `telegram.env` — (선택) 텔레그램 알림 토큰. 없으면 데스크톱 알림으로 대체.
- 시세 크레덴셜은 이 리포에 없다 — 수집은 jhts 시세수집팀 몫이다.
- 위 파일과 `logs/`, 런타임 JSON은 `.gitignore` 처리.

## 한계 (정직하게)

- 자동 판정 가능한 데이터: jhts.marketdata 가 서빙하는 것(미국 주식/지수/VIX/금리 일봉·현재값·분봉).
- **자동 불가(근본적 manual)**: 한국 창구별/투자자별 수급, 업종 등락 집계, 공매도 순보유잔고(KRX 로그인), 호가/체결. 이런 데이터를 쓰는 책은 "읽고 수동 체크"까지만 자동화된다.
- 장중 자동판정은 재설계 대기 — 지금은 EOD 판정만 자동이고 장중 항목은 화면에 '대기'로 표시된다.
