---
name: book-to-playbook
description: 트레이딩 책을 읽어 실전 매매 플레이북 + 인터랙티브 매매시트 아티팩트로 자동 변환. "책 플레이북 만들어줘", "이 책 매매시트로", "book-to-playbook", 책 소스 경로와 함께 요청 시 사용.
---

# Book → Playbook + 매매시트

트레이딩 책 원문(텍스트)을 받아 ① 저자 매매기법 플레이북 ② 정량화된 실전 매매시트를
**2탭 인터랙티브 아티팩트**로 만든다. 원리: **템플릿(고정) + 콘텐츠(책마다 교체)** 분리.

## ⛔ 절대 규칙 — 원문은 고정, 구현을 고친다

**책 = 사양, 코드 = 구현.** 자동판정을 붙이다 보면 "구현이 보는 것"과 "책이 시킨 것"이
어긋나는 순간이 반드시 온다. 그때 **책 문구를 구현에 맞춰 고치지 말 것.**

선택지는 둘뿐이다.
1. **구현을 원문에 맞춘다** — 데이터를 구할 수 있으면 구한다.
2. **미구현/수동으로 남기고 그렇게 표시한다** — `source:"manual"` + `reason`.

원문 문구 수정은 선택지가 **아니다.** 고치는 순간 불일치는 사라진 게 아니라
**안 보이게** 되고, 커버리지 배지(✅반영/⚠미반영)까지 거짓이 된다.

> 실제 사고(2026-09-22, etf): 시트 라벨이 저자 2-6대로 "나스닥 **선물** 방향"인데
> 파이프라인은 지수 `^NDX`를 보고 있었다. 라벨을 "나스닥100 방향"으로 바꿔 구현에
> 맞췄다. 실제로는 `NQ=F`·`ES=F` 선물이 야후에서 그냥 받아졌다 —
> **구할 수 있는 걸 안 구하고 사양을 깎은 것.**

검사는 기계가 한다. `verify_source_integrity.py` 가 책마다 아래를 해시로 고정하고,
`run.py` 가 매 발행 끝에 자동 실행한다.

| 지키는 것 | 내용 |
|---|---|
| `#src` | 플레이북 마크다운(책 본문 전체) |
| 규칙 근거표 | "책의 표현 → 정량 정의" 표 |
| 체크 항목 라벨 | 스코어카드·진입·회피 체크박스의 규칙 문구 |

```
python verify_source_integrity.py            # 검사(다르면 exit 1)
python verify_source_integrity.py --accept   # 원문을 의도적으로 고쳤을 때만
python verify_source_integrity.py --show etf # 그 책의 라벨 목록
```

**새 책을 추가하면 처음 한 번 `--accept` 로 기준을 등록한다.** 기준값
(`source_baseline.json`)은 커밋 대상이다.

## ⛔ 절대 규칙 2 — 규칙마다 출처(ref)를 박는다

체크리스트의 **모든 규칙 항목은 출처 소절을 달아야 한다.**

```js
{t:'20일선 회복 후 2거래일 동안 다시 안 깸', ref:'3-2', src:'...'}
```

**왜 필수인가.** 토큰 대조로는 창작(저자가 말한 적 없는 규칙)을 못 잡는다. 실증:
SOXL 필터에 `20일선 회복 후 2거래일 동안 다시 안 깸`을 심어도 검사를 통과했다 —
'20일선'과 '2거래일'이 7-6("S&P500 20일선 2거래일 연속 이탈")에 함께 있기 때문이다.
사후 추론도 불가능했다(규칙 40개 중 유일 후보가 나온 건 1개뿐).
**출처는 추론하는 게 아니라 만들 때 적는 것이다.**

`verify_coverage.py` 가 넷을 본다.

1. ref 가 있는가
2. ref 소절이 실제로 존재하는가
3. 그 소절이 **이 종목의 장 또는 공통 장**인가 — 3장=TQQQ · 4장=SOXL · 5장=UPRO.
   다른 종목 장을 가리키면 오귀속으로 잡힌다(위 SOXL 사고가 여기서 걸린다)
4. 규칙의 수치 토큰이 그 소절 본문에 있는가

**새 책은 추출(STEP 1) 단계에서 규칙마다 ref 를 함께 산출한다.** 근거 소절을 못
대는 규칙은 시트에 넣지 않는다 — 그게 창작이다.


## ⛔ 절대 규칙 3 — 책이 계약에 맞춘다 (검사기가 책에 맞추는 게 아니라)

위의 두 검사(`verify_source_integrity.py` · `verify_coverage.py`)는 첫 책(etf)의
생김새를 전제로 쓰였다. 두 번째 책(supply)은 `coverage-data` 도 규칙 JSON도 없으니
검사기가 **"검사 대상 아님"으로 통째로 건너뛰었다.** 배지도 경고도 안 뜬다.
책이 둘로 늘어난 시점에 **검증층의 실효가 0이 된 것이다.**

검사기를 책마다 고치는 방향은 같은 사고를 책 수만큼 반복한다. 그래서 뒤집는다.
**책이 갖춰야 할 최소 형식을 계약으로 못박고, 못 채우는 책은 등록하지 않는다.**

| 조항 | 내용 | 있어야 할 곳 |
|---|---|---|
| 계약 1 | 원문이 **소절 단위로 잘려** 있고 소절마다 고유 키 (`N-n`, 그 외 `프롤로그`/`에필로그`) | `books/<slug>/source_index.json` |
| 계약 2 | 규칙은 **JSON 파일로 존재**하고 규칙마다 `ref`(소절 키) | `books/<slug>/rules.json` |
| 계약 3 | 커버리지 맵이 소절 **전수**를 분류 (reflected / gap / mindset) | 책 HTML 의 `coverage-data` |
| 계약 4 | `data_spec` 항목에도 `ref` — 규칙과 수집요청을 짝지을 **유일한 열쇠** | `books/<slug>/data_spec.json` |

**HTML 안의 JS 리터럴(`const DATA = [...]`)은 계약 2 위반이다.** 규칙이 코드 안에
있으면 읽는 쪽이 책마다 달라진다 — 검사기가 etf 전용이 된 원인이 바로 그것이다.
STEP 1 추출은 규칙을 **파일로** 내놓고, STEP 2 빌드는 그 파일을 읽어 렌더한다.

```
python verify_contract.py      # 책별·조항별 충족/미충족 표, 미충족 있으면 exit 1
```

지금은 **실패가 정상이다**(etf 1/4, supply 0/4). 그게 이 검사의 존재 이유다.
계약을 채우는 건 책 쪽 작업이지 검사 쪽 작업이 아니다 —
**통과시키려고 검사를 느슨하게 만들지 말 것.**

### 책마다 **다른** 것은 코드가 아니라 설정으로 뺀다

앞으로 만드는 검사기는 **어떤 책에서도 돈다.** 책마다 갈리는 것은 설정으로 뺀다.

| 다른 것 | 설정 내용 | 그게 없는 책은 |
|---|---|---|
| 오귀속 검사의 **축** | etf = 종목↔장 매핑 `{TQQQ:3, SOXL:4, UPRO:5}` | 그 검사만 **'미적용'으로 보고**. **통과로 찍지 않는다** |
| 토큰 **단위 사전** | 공통 `%`·`배`·`개`·`일` + 책별 `억`·`만주`·`연속`·`단계` | 공통 사전만으로 돈다 |
| 시트 **단계 목록** | 규칙 JSON에서 자동 추출 | 계약 2 미충족 → 등록 불가 |

'미적용'을 '통과'로 적는 순간 검증층은 다시 거짓이 된다. 못 본 것은 못 봤다고 적는다.

## 검증 게이트 자기수정 루프 (새 책 표준 절차)

새 책 하나를 "책 넣으면 완주"로 끌고 가는 표준 절차. **저작(1~4단계)은 LLM이 하고,
게이트(5단계)는 결정론적 검사기가 한다** — 이 분리를 절대 흐리지 않는다. 검사기를
느슨하게 만들어 통과시키는 것은 이 루프의 목적을 정면으로 배반한다.

```
1) 자르기    원문 → 소절 단위 + 고유 키 (N-n · 프롤로그 · 에필로그)
             → #src(플레이북 마크다운) / books/<slug>/source_index.json
             (book_source.py --write 가 소절키·제목·줄범위·해시·정량토큰을 산출)
2) 추출      각 소절 → 저자 매매규칙, books/<slug>/rules.json (t=라벨).
             규칙마다 ref(소절 키). 라벨의 정량 토큰은 그 ref 소절 원문에서 나온
             토큰이어야 한다(창작 금지). 근거 소절을 못 대는 규칙은 넣지 않는다.
             ── 분해 원칙: 한 소절이 독립적으로 체크되는 조건을 여럿 담으면,
                시트 규칙도 조건 수만큼 쪼갠다. AND 한 줄로 퉁치지 않는다.
                (예: 4-4 "단타=5일선 / 스윙=20일선" 두 체제 → 규칙 둘로.
                 합치면 어느 조건이 깨졌는지 안 보이고, 한 규칙에 metric 여럿이
                 숨어 ③ 검증이 느슨해진다. 판정이 '택1'이면 병렬로 두고 선택을 분리.)
             ── 같은 말 묶기(분해의 짝): 서로 다른 소절의 규칙이라도 **사실상 같은
                판정**이면 하나로 합친다. 부모 규칙 하나 + `subs:[...]`(합쳐진 저자
                조건들, 각자 ref·bkey 보존) + xref(각 sub 소절 bullet → 이 부모).
                · "같은 말"인가는 **의미로 판단한다**(추출자가 책을 읽고). 엔진키나
                  지표가 있어야만 묶는 게 아니다 — manual 규칙도 의미가 같으면 묶는다.
                · **지표(metric)가 달라도 관찰 현상이 같으면 흡수한다.** 예: '고점 대비
                  4% 밀림(upper_wick)'과 '거래량 급증+종가 밀림(volume_ratio)'은 둘 다
                  "위에서 털림/매물"이라 **한 부모**로 합치고, 각 지표는 subs 로 분해해
                  보존한다. **지표가 다르다는 것은 별개 top-level 규칙으로 둘 이유가 아니다**
                  — 분해(지표별 subs)와 묶기(같은 현상 한 부모)는 한 쌍이다. 판별 질문:
                  "체크하는 사람이 이걸 하나의 상황으로 보나?" 예면 한 부모, subs 로 지표 분해.
                · 부모 라벨은 그 책의 저자 표현으로 쓴다. **고정 주제 목록(카테고리)을
                  코드/스키마에 박지 않는다.** 책마다 다르며, 묶는 판단은 데이터의 몫.
                · 하위 저자 조건은 subs 로 전부 보존(누락 0). 렌더는 **한 체크박스 안에
                  전부 몰아넣어(생략 없이)** 보여준다(부모 라벨 + 하위 조건 크램) — 렌더
                  코드는 주제를 모르고 subs 유무만 본다(책무관 SSOT). 각 sub 는 자기
                  지표(k)·출처(src)를 달고, 부모 `k` 는 `a|b` 로 이어 **하나라도 걸리면**
                  부모가 걸리게 한다.
                · 개수 기반 판정(예: 5신호 중 2개↑)만 예외 — `groupNeed` 를 달면 하위
                  각각을 on/off 로 펴서 센다(이때만 하위줄 표시). 이것도 subs 모델의
                  인스턴스다. 특정 소절 전용 패널을 따로 만들지 않는다(두더지잡기).
3) 분류      모든 소절 전수 → reflected / gap / mindset
             → 책 HTML 의 coverage-data 블록(#src 소절 키 전부를 map 에 담는다)
4) 수집요청  각 규칙/조건(부모·subs) → **metric type 을 선언한다**(`mtype` 또는 data_spec.metric.type).
             ── **자동/직접은 사람이 정하지 않는다 — `metric_registry.json` 이 파생한다:**
                · type ∈ auto_types & impl=true  → 🤖 자동(jhts 데이터 O + 판정 로직 O)
                · type ∈ auto_types & impl=false → 🚧 미구현(jhts 데이터는 O, 로직만 X — **✋직접 아님, 해야 할 일**)
                · type ∈ no_data_types           → ✋ 직접(데이터 자체가 없음: 뉴스감성·애널추정·한국수급·뉴스시각)
                · 선언 없음/미등록 type          → ❌ 미결선(블로킹 — 반드시 선언)
             ── 핵심: "jhts 시세수집팀에 요청하면 나오는 데이터"를 ✋직접으로 두는 것은 **금지**.
                그건 미구현(🚧)이지 직접이 아니다. 데이터가 새로 생기면(예: 심볼 추가) auto_types 로,
                무료 소스가 정말 없을 때만 no_data_types 로. **엔진(판정)은 jhts.marketdata(수집)에 위임**한다.
5) 게이트    6검사를 --json 으로 그 책 slug 기준 실행:
             verify_source_integrity · verify_source_fabrication · verify_coverage
             · verify_contract · verify_rules_vs_spec · **verify_auto_coverage**(자동가능한데 직접으로 샌 것 차단)
6) 수리      실패를 읽고 산출물을 고쳐 재실행 (아래 수리 매핑):
7) 수렴      그 책의 blocking(코드1) = 0 까지. 남는 건 전부 '수동/미구현'으로 표시된
             warning(코드2) 뿐이어야 한다. **미결선(❌)은 blocking, 미구현(🚧)은 warning.**
```

### 수리 매핑 — 어느 검사 실패 → 어느 산출물을 고치나

| 검사 실패 | 실패 뜻 | 고칠 산출물 |
|---|---|---|
| `verify_source_fabrication` **창작** (orphan/ungrounded) | 규칙 ref 가 없거나·없는 소절을 가리키거나·규칙 토큰이 그 소절 원문 토큰에 없음 | `rules.json` — 올바른 ref 를 찾아 달거나, **근거가 없으면 그 규칙을 삭제**(창작이었던 것). 원문은 손대지 않는다 |
| `verify_coverage` **미분류/거짓배지** | 소절이 map 에 없거나·reflected 주장의 토큰이 시트 구현 범위에 없음 | `coverage-data` — 분류를 채우거나, reflected→gap 로 배지 정정 |
| `verify_rules_vs_spec` **위반** | 규칙 ref 에 짝지을 spec 항목이 없거나(nospec)·규칙 토큰을 spec 이 못 담거나(cond)·spec 파라미터가 원문에 없음(param, 창작) | `data_spec.json` — 규칙 ref 마다 spec 항목을 만들고 규칙 토큰을 담는다 |
| `verify_contract` **미충족** | 계약 1~4 중 형식이 빔 | 해당 산출물을 계약 형식으로 채운다(source_index / rules.json+ref / coverage-data / data_spec+ref) · HTML 안 규칙 리터럴(누출)은 `id="rules"` JSON 안으로 이동 |
| `verify_source_integrity` **실패** | 저자 원문(#src·def_table·labels·rule_data)이 바뀜 | **원문을 되돌린다.** 절대 원문을 고쳐 검사에 맞추지 않는다. 의도한 신규 등록만 `--accept` 로 기준 갱신 |
| `verify_auto_coverage` **미결선(❌)** | 조건이 자동/무데이터를 안 밝힘 | `rules.json` 조건에 `mtype` 선언 — jhts 데이터 있으면 auto_types, 없으면 no_data_types |
| `verify_auto_coverage` **미구현(🚧)** | jhts 데이터는 있는데 판정 로직 미작성(✋직접 위장 금지) | 엔진에 그 metric type 계산 구현 + `metric_registry.json` 에서 `impl:true` 로. 데이터 없으면 no_data 로 재선언 |

**절대원칙(재확인).** 책 = 사양, 코드 = 구현. **통과하려고 #src/원문을 고치지 않는다.**
어긋나면 ①구현을 원문에 맞추거나 ②`source:"manual"` + `reason` 으로 미구현/수동 표시.
그 둘뿐이다.

### 책별 게이트 규칙 — 전역 종료코드가 아니라 그 slug 의 --json 결과로 판정

`run.py` 의 전역 종료코드는 **다른 책**의 실패로도 빨개진다(예: etf 에 무관한 고아 규칙
4개가 있으면 전역이 빨갛다). 그러니 새 책을 게이트할 때는 **전역 exit 이 아니라 각
검사의 `--json` 결과에서 그 slug 의 값만** 본다:

```
python verify_source_fabrication.py --json   # {slug:{claims,orphans,ungrounded,fabrications}}
python verify_contract.py --json             # {slug:{reflected,gap,mindset,rules,ref_missing,spec_items,leaks,...}}
python verify_rules_vs_spec.py --json        # {slug: 위반수|null}
```

그 slug 에 대해 blocking = 0 의 정의:
- fabrication: `fabrications == 0` **이고** `claims > 0` (규칙이 실제로 근거를 대고 있음.
  값이 null 이면 '검사 불가' — 통과 아님)
- contract: `leaks == 0` 이고 계약 1~4 충족(값이 null 이 아님)
- rules_vs_spec: 위반수 `== 0` (null 은 '검사 불가' — 통과 아님)
- coverage / source_integrity: 그 책 항목에 미해결·불일치 0

null(검사 불가)은 통과가 아니다. 계약 구조를 못 채운 것이다.

## 입력
- 정제된 텍스트(.md) 있음 → 바로 STEP 1
- 스캔 PDF만 있음 → 먼저 이미지화→OCR→청킹(jhts/jhts2 파이프라인 재사용) 후 STEP 1

## 파이프라인

### STEP 1. 추출 (서브에이전트, opus)
책 전체를 청크로 **처음부터 끝까지** 읽어 아래를 산출. **절대규칙: 저자 명시분만·원문 숫자 그대로·미명시는 "저자 미명시" 표기·지어내기 금지·개인 일화/이름 제외.**
여기서 뽑은 문구는 이후 **절대 수정 대상이 아니다**(위 절대 규칙 참고). 자동판정이
그 문구를 못 따라가면 문구가 아니라 판정을 고치거나 수동으로 남긴다.
산출 = 하나의 `*_raw.md`:
- **PART A 플레이북 마크다운**: `## 0. 핵심 원칙` + 장별 `## N. …` / `### N-n. …` 불릿 + `## A. 부록 숫자표` + `## B. 커버리지 검증`
- **PART B 매매시트 스펙 JSON**:
  ```json
  {"definitions":[{"vague":"","precise":"","source":"저자|운영"}],
   "scorecard":{"title":"","total":100,"items":[{"label":"","points":25,"detail":""}]},
   "entry_checklist":[{"group":"","need":2,"filter":[],"conditions":[],"avoid":[],"note":""}],
   "exit_rules":[{"stage":"","trigger":"","action":""}],
   "position":{"desc":"","splits":[{"label":"","pct":25,"cond":""}]},
   "routine":[]}
  ```

### STEP 2. 빌드 (서브에이전트 or 직접)
`templates/example-etf.html`을 베이스로 CSS·탭·마크다운 렌더러(`script id="src"`)·시트 컴포넌트를
그대로 재사용하고 콘텐츠만 교체:
- 플레이북 탭: PART A 마크다운을 `#src`에 그대로 삽입(`## 0.`부터)
- 시트 탭 STEP1~6: PART B JSON을 표/스코어카드/진입체크리스트/청산표/분할계산기/루틴으로 렌더
- `[저자]`/`[운영]` 태그 유지, 자체완결(외부 리소스 금지)

### STEP 3. 게시
Artifact 도구로 HTML 게시(같은 책은 같은 file_path→같은 URL 재배포).

## 데일리 자동판정 엔진 (선택, 미국 ETF 전용)
`etf_daily_verdict.py` — STEP1의 정량규칙을 코드로 옮겨 매일 자동 판정.
- 무인증 Yahoo chart API(urllib)로 지표 계산 → 필터/스코어카드/회피 → 상품별 verdict
- 장중 3항목(시초가 지지·첫 눌림·30분 판별)은 자동 불가 → "장중 확인"으로 표시
- 전송: `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`(telegram.env) 있으면 텔레그램, 없으면 macOS 알림
- 스케줄: `~/Library/LaunchAgents/com.hyeyoung.etf-verdict.plist` (화~토 08:00 KST)
- 수동 실행: `python3 etf_daily_verdict.py [--json] [--no-send]`

**주의**: 한국 수급(창구별 외국인/기관) 기반 책은 무료 데이터로 자동화 불가 → KRX/증권사 소스 필요(supply-signal 프로젝트 영역).

## 파일
- `SKILL.md` — 이 문서
- `templates/example-etf.html` — 디자인/구조 기준 템플릿(ETF 완성본)
- `etf_daily_verdict.py` / `run.sh` / `telegram.env.example` — 데일리 엔진
- `verify_contract.py` — 책 계약 4조 검사(절대 규칙 3). 못 채운 책은 등록 불가
- `verify_source_fabrication.py` — 구간① 창작 검사. 플레이북이 책에 없는 저자 주장을 지어내지 않았나(정량 토큰이 ref 소절 원문에 근거하나)
- `logs/` — 판정 로그
