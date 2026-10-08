# 목표#1 리팩토링 설계서 — 웹/표시 코드를 publish 로 모으기 + 서버 권위 통합

> 작성: 2026-10-08 · 읽기 전용 분석(코드/문서 수정·git 없음) · 작업 루트 `book-to-playbook/`, git 루트는 상위 `etf-verdict/`
> 검증 명령은 전부 venv `book-to-playbook/.venv` 로. 예: `./.venv/bin/python -m verify_teams`

---

## 0. 한 줄 요약

사장님 기획의도는 **"웹은 판정(tree.json/verdict JSON)만 받아 보여주기만"** 인데, 지금은
화면 JS 7개와 주입기(`inject_ui.py`)가 전부 **구간②(checklist, 트리 만드는 팀)** 폴더에 산다.
게다가 화면이 등급을 **직접 다시 계산**(`checklist-ui.js`의 `ev/and3/or3/gradeKey/gradeView`)한다.

- **이관(구조)**: `checklist/ui/*.js`(표시 7개) + `checklist/inject_ui.py` → `publish/`로 옮긴다.
  표시는 "트리 만들기"의 일이 아니라 "발행·서빙"의 일이다. `verify_teams`·`verify_structure`도 따라 고친다.
- **서버 권위(계산)**: 체크박스 토글 때 등급을 화면이 다시 내지 않고 **서버가** 내준다.
  `serve.py`에 수동답을 받는 엔드포인트를 더하고, `verdict_engine.render`가 그 답으로 등급을 해소한 뒤,
  `checklist-ui.js`의 평가기(`ev/gradeKey/...`)를 **삭제**한다.

이 둘은 **독립**이다(구조 이관은 지금 당장 가능, 서버 권위는 tree.json 재생성 뒤라야 테스트 가능).

---

## 1. 웹/표시 코드 전수 지도 (지금 어디 있고 무엇을 하나)

### 1-1. 화면 JS 7개 — 전부 `checklist/ui/` 에 있다 (= 구간② 폴더)

| 파일 | 하는 일 | 데이터 입력 | 성격 |
|---|---|---|---|
| `shared-ui.js` | 공용 부품 `window.BP`(esc·ZW/zw 칸이름표·소절 정규식). **가장 먼저** 주입돼 뒤 블록이 읽음 | `#verdict-data`(VD.zones) | **표시(공용 토대)** |
| `playbook-ui.js` | 플레이북 원문(`#src`) 렌더 + 소절별 반영 배지(VD.refs) + 목차·검색·원문보기 | `#src`, `#verdict-data`(refs), `#source-data` | **표시(end-user)** |
| `review-ui.js` | 좌우 분할 검수 · 소절↔체크리스트 점프 · 반영 현황 요약표 | `#verdict-data`(refs), `#src` | **표시(end-user)** — 아래 §2 판정 |
| `checklist-ui.js` | 탭전환 · 조건트리 여섯 칸 렌더 · **수동조건 체크 → 등급 재계산** · 비중/분할 계산 | `#verdict-data`(verdicts·grades·grade_rules·zones) | **표시 + (문제의) 계산기 복제** |
| `collect-ui.js` | 수집 현황(소스·신선도·라이브 폴링 여부 라벨) | `#verdict-data`(ts·source·live) | **표시(end-user)** — 아래 §2 판정 |
| `live-ui.js` | 라이브 모드: `/api/verdict` 폴링·`/events` SSE → `#verdict-data` 갈아끼우고 `window.__applyVerdict()` 재렌더 | `/api/verdict`, `/events` | **표시(end-user, 서버연동)** |
| `backtest-ui.js` | 백테스트 탭(1년/3년 성적·거래목록). `#backtest-data` 있을 때만 | `#backtest-data` | **표시(end-user)** — 단 주입 경로가 다름(§1-4) |

> 의존: 전부 `window.BP`(shared-ui)를 읽는다 → **shared-ui 가 항상 먼저 주입**돼야 한다(순서 불변식).
> `checklist-ui.js`는 `window.__applyVerdict` 를 노출, `live-ui.js`가 그걸 호출한다(재렌더 훅).

### 1-2. 주입기 `checklist/inject_ui.py` (= 구간② 폴더)

- 각 `ui/<name>.js` 를 **SSOT**로 두고, 책 HTML의 센티넬(`<!-- INJECT:name -->...<!-- /INJECT:name -->`) 안에
  `<script>`+파일내용 **사본**으로 inline 주입. 오프라인/아티팩트 자체완결 위해 `<script src>` 안 씀.
- `REGIONS` dict = {이름 → ui 파일 경로}. 경로는 `_HERE/ui/<name>.js`(= checklist 기준).
  **backtest-ui 는 여기 등록돼 있지 않다** — 주입을 `publish_pages._inject_backtest()`가 따로 한다(§1-4).
- `inject(html)`(모든 구획 갱신) / `check(html)`(사본==파일 대조, 드리프트 검출) / `extract` 제공.
- 하위호환 꼬리: `inject(html, js)` 로 js 를 주면 `review-ui` 구획에만 쓴다(옛 시그니처).

### 1-3. HTML 주입 마커·앵커 (책 페이지 = `trend-playbook.html`, `moneycopy-playbook.html` 두 장)

- **데이터 블록**: `id="verdict-data"`(판정 JSON), `id="sheet-root"`(체크리스트 렌더 대상), `id="src"`(원문 md),
  `id="source-data"`(소절 원문, publish가 주입), `id="backtest-data"`(백테스트, publish가 주입).
- **UI 센티넬 주석**(순서대로): `INJECT:shared-ui` → `playbook-ui` → `checklist-ui` → `collect-ui` → `review-ui` → `live-ui`.
  (backtest 는 `checklist-ui` 앵커 바로 **앞**에 publish가 끼워넣음.)
- `verify_structure.PAGE_IDS = ('id="src"','id="verdict-data"','id="sheet-root"')` 가 세 id 존재를 검사.

### 1-4. publish 층 (= 발행·서빙, 소비자)

| 파일 | 하는 일 | 표시 코드와의 관계 |
|---|---|---|
| `publish/publish_pages.py` `assemble(slug, data)` | 책 HTML 한 장 조립: `#verdict-data` 주입 → **`checklist.inject_ui.inject(html)`** → `inject_nav` → `_inject_source` → `_inject_backtest` | **여기서 `checklist/`를 import** — 이관하면 이 import가 바뀜 |
| `publish/serve.py` | 로컬 서버. `GET /<slug>/` → assemble, `GET /api/verdict` → **엔진을 subprocess로** 돌려 JSON 반환(TTL캐시 ~8s), `/events` SSE | 서버 권위(§4)의 핵심 — 지금은 GET만 |
| `publish/build_home.py` `render_home` | 책 선택 셸(좌측 책목록 + iframe) HTML 생성 | 표시지만 책-무관 셸, 이관 대상 아님(이미 publish) |
| `publish/inject_nav.py` `inject(html, slug)` | 책 전환 사이드 레일 주입 | 표시지만 이미 publish, 이관 대상 아님 |

### 1-5. 검증기의 '표시' 관련 검사

- `verify_structure.book_contract(slug)`:
  - `from checklist.inject_ui import check as ui_check` → **UI 사본==파일 일치(드리프트)** 검사.
  - `PAGE_IDS` 세 id 존재 검사. tree.json 문법·ref↔소절 일치 검사.
- `inject_ui.check()`: 등록 구획 전부가 페이지에 있고 사본이 `ui/*.js`와 같은지. 빠진 구획도 실패로 본다.
- `verify_teams.py`:
  - 규칙1 = 팀폴더(playbook·checklist·verdict)는 다른 팀 import 금지. `publish`는 "조립자"라 팀 import 허용.
  - 규칙4 = `publish`도 네트워크 수집 금지(serve.py 만 `http`,`urllib` 예외 — `ALLOW`에 명시).
  - **핵심**: `inject_ui.py`가 `checklist`→`publish`로 가도 `publish`는 팀을 import해도 되므로 규칙1 위반 안 생김.
    반대로 `publish_pages`의 `import checklist.inject_ui` 는 이관 후 `publish` 내부 import가 되어 **더 깨끗**해진다.

---

## 2. 어느 게 '표시'(→이관)이고 어느 게 구간② 자체 도구인가

**결론: `checklist/ui/*.js` 7개 전부가 end-user 표시 코드다. 구간② 자체 도구는 하나도 없다.**
근거(코드 읽음):

- `review-ui.js` — "심판(트리) 검토용 내부 도구"가 아니다. **발행 페이지의 '나란히 검수' 모드**로,
  플레이북 원문 소절 ↔ 체크리스트 카드 점프 + 반영 현황 요약표를 그린다. DOM(`#splitbtn`,`#covRows`,`#content`)과
  판정 JSON(`VD.refs`)만 읽고 트리 파일은 직접 안 건드린다. 트리를 만드는 로직이 전혀 없다 → **표시**.
- `collect-ui.js` — "수집을 수행"하지 않는다. `#verdict-data`의 `ts/source/live`만 읽어 **신선도 라벨을 그린다**.
  라이브 서버 연결 여부를 사용자에게 보여주는 표시 위젯 → **표시**.
- 나머지(shared/playbook/checklist/live/backtest)도 전부 DOM+판정 JSON만 소비하는 그리기 코드.

→ 7개 모두 `publish/ui/` 로 옮긴다. 애매함 없음. (구간②에 남길 JS 없음.)

---

## 3. 구체 이관 계획 (구조) — checklist/ui/*.js + inject_ui.py → publish/

목표 배치:
- `checklist/ui/*.js`  →  `publish/ui/*.js`
- `checklist/inject_ui.py`  →  `publish/inject_ui.py`

### 3-1. 바뀌는 것 (파일별)

1. **`inject_ui.py`**: `_HERE` 가 publish 폴더가 되므로 `REGIONS` 의 `os.path.join(_HERE,"ui",...)` 는 자동으로
   `publish/ui/*.js` 를 가리킨다 — 경로 문자열 수정 불필요(상대 구조 유지). 모듈 docstring의 "이 팀(checklist/)의
   소유물" 문구만 "발행층(publish/)" 로 바꾸면 됨(기능 무관).
2. **`publish/publish_pages.py`**:
   - `from checklist.inject_ui import inject as _inject_ui` → `from publish.inject_ui import inject as _inject_ui`.
   - `_inject_backtest()` 의 `ui_p = os.path.join(BASE,"checklist","ui","backtest-ui.js")`
     → `os.path.join(BASE,"publish","ui","backtest-ui.js")`.
3. **`verify_structure.py`**: `from checklist.inject_ui import check as ui_check`
   → `from publish.inject_ui import check as ui_check`.
4. **`verify_teams.py`**: 표면상 수정 불필요(아래 §3-3에서 왜 안전한지). 단 주석의 팀 설명에 "UI는 publish 소유"를
   한 줄 반영하면 의도가 분명(선택).
5. **문서**: `checklist/README.md`·`checklist/inject_ui.py` docstring·`publish/` 설명이 "UI는 checklist 소유"라고
   말하는 곳(문구만) 갱신. `MIGRATION_NOTES.md` 에 이관 기록(선택).

### 3-2. 그대로 두는 것
- 책 HTML의 센티넬 주석(`INJECT:*`)·데이터 id — **변경 없음**(주입기 경로만 바뀌지 마커 이름은 그대로).
- `inject_nav.py`·`build_home.py` — 이미 publish, 무관.
- `checklist/cond.py`·`checklist/grade.py` — **읽기만**(이번 구조 이관에서 손 안 댐).

### 3-3. 왜 `verify_teams` 가 안 깨지나 (중요)
- 규칙1은 `checklist`가 **다른 팀**을 import할 때만 위반. `inject_ui.py` 는 다른 팀을 import하지 않는다
  (stdlib `os/re/sys`만). 그래서 checklist→publish 로 **옮겨도** 위반이 새로 생기지 않는다.
- `publish_pages.py` 는 지금 `import checklist`(publish→checklist)인데 규칙1은 "팀 폴더"에만 적용되고
  `publish`는 LAYERS 중 "조립자"라 팀 import가 허용된다 → **지금도 합법, 이관 후엔 `import publish` 라 더 깨끗**.
- 결론: 구조 이관은 팀 경계 규칙을 **느슨하게 만들지 않고 오히려 정합성을 높인다**.

### 3-4. 깨질 수 있는 것 (주의)
- 혹시 다른 곳에서 `checklist/ui/` 또는 `checklist.inject_ui` 경로를 **문자열/import로 더 참조**하는 데가 없는지
  이관 직전 `grep -rn "checklist/ui\|checklist.inject_ui\|checklist\\\\ui"` 로 전수 확인(현재까지 확인된 참조:
  publish_pages·verify_structure 둘뿐).
- `git mv` 로 옮겨 히스토리 보존. 옮긴 뒤 `__init__.py` 유무 확인(ui/ 는 .js뿐이라 패키지 아님 — 무관).

### 3-5. 단계별 순서 + 각 단계 검증 (venv=.venv)
1. 전수 grep으로 참조처 확정(위 §3-4). → 통과 기준: 참조 2곳만.
2. `git mv checklist/inject_ui.py publish/inject_ui.py` ; `git mv checklist/ui publish/ui`.
3. `publish_pages.py`·`verify_structure.py` 의 import·경로 2+1곳 수정.
4. 검증:
   - `./.venv/bin/python -m verify_teams` → "팀 경계 통과" 기대.
   - `./.venv/bin/python -m verify_structure` → ⚠ 단 **tree.json 없음**으로 책 계약은 지금도 실패할 수 있음(§5).
     UI 드리프트 라인만 통과(사본==파일)면 이관 자체는 성공으로 본다.
   - (서버 뜨면) `./.venv/bin/python -m publish.serve` 로 `/trend/` 열어 탭/렌더 육안 확인.
5. 문구/문서 갱신(§3-1-5). 커밋은 사장님 지시 후에만.

---

## 4. 서버 권위(A) 통합 스케치 — 화면 재계산 제거

### 4-1. 현재 (왜 화면이 다시 계산하나)
- 서버는 `GET /api/verdict` 에서 엔진을 **subprocess**로 돌려 판정 JSON을 준다(~1초). 토글마다 이걸 치면 느리다.
- 그래서 `checklist-ui.js` 가 `grade_rules`(데이터)와 **평가기(ev/and3/or3)를 JS로 복제**해, 체크박스 토글 즉시
  등급을 다시 낸다. 이 평가기가 `checklist/cond.py` 3값 평가기의 **복제**(사장님이 지적한 결합도의 핵심).
- 단 **'사다리'(grade_rules.json)는 데이터**라 이미 VD로 실려와 복붙 아님. 복제는 **평가기 로직**뿐.

### 4-2. 목표: 서버가 '체크한 답까지 반영한 완성 판정'을 내려주고, 화면은 그리기만

세 군데를 손댄다(순서 = 시스템 안 깨지게 **서버 먼저 → JS 삭제 마지막**):

**(a) `checklist/cond.Ctx` — 조건별 수동답 맵 추가 (기존 균일 `manual_as` 와 공존)**
- 지금 `manual_as` 는 수동 조건 전부를 True/False/None 하나로 균일 적용(opt/pes 두 벌).
- 추가할 것: `manual_answers={수동키: True/False}` 같은 선택 인자. 평가 시 그 키에 답이 있으면 그 값을,
  없으면 기존 `manual_as` 를 쓴다. **극성(not 아래 뒤집힘) 규칙은 그대로** 태워야 화면 `ev` 와 일치.
- 수동키는 화면 `mkey(it,path)` 와 **동일 규칙**이어야 한다: `(shared?'*':path.split('.')[0]) + '|' + (mkey||manual)`.
  → 엔진이 view를 낼 때 각 수동 노드에 이 키를 실어주거나(권장: `_view` 가 `mkey` 를 이미 낸다), 서버가
    같은 공식으로 재구성. **키 규칙 불일치 = 등급 갈라짐**이므로 여기가 가장 조심할 곳.
- `checklist/grade.py` 는 **건드리지 않는다**(사장님 제약). `grade_key` 는 이미 `opt/pes`로 등급을 내므로,
  답을 반영한 opt/pes를 만들 수 있으면 등급 해소는 기존 코드를 그대로 탄다.
  → 구현 위치는 `verdict_engine`(구간③)에서 Ctx에 답을 넣어 ProductEval을 다시 돌리는 얇은 경로.

**(b) `verdict_engine.render(slug, asof=None, answers=None)` — 답으로 등급 해소**
- `answers`(수동키→불리언)를 받아 ProductEval/Ctx에 흘려, 답 반영된 `key`(등급)·zones 표시값을 낸다.
- `answers=None`(기본)이면 지금과 100% 동일 출력(하위호환). → 알림/CLI/첫 렌더 경로 안 깨짐.
- grade_rules 데이터로 등급 해소(이미 그 구조). grade는 호출만 하고 수정 안 함.

**(c) `publish/serve.py` — in-process 평가 + 답 전달**
- 지금 subprocess(~1초)를 토글 지연의 원인. 토글 응답용으로 **in-process** 경로를 추가:
  `from verdict.verdict_engine import render` 를 직접 호출(serve는 publish라 verdict import 가능 —
  verify_teams 규칙상 publish는 조립자, 팀 import 허용).
  - 단 **네트워크 규칙4 주의**: serve.py는 `http`,`urllib`만 ALLOW. `verdict_engine` 자체는 네트워크 안 씀
    (시세는 shared/md_feed 창구). import 추가는 규칙 위반 아님.
- 새 엔드포인트(안): `POST /api/verdict` (body=answers JSON) 또는 `GET /api/verdict?...&ans=<base64json>`.
  답을 render에 넘겨 완성 판정을 반환. 기존 무답 GET은 그대로(캐시).
- **주의**: in-process 로 바꾸면 매 요청 import/계산이 메인 스레드에서 돈다 — 시세 창구 과호출 막는 TTL캐시는
  무답 경로엔 유지하고, 답-포함 요청은 캐시 키에 answers 해시를 포함(또는 캐시 안 함)해야 섞이지 않음.

**(d) `checklist-ui.js` — 평가기 삭제 (마지막)**
- 삭제 대상: `and3/or3/ev/mkey(계산용)/gradeKey/gradeView/zoneFill/selfCheck/canGrade/GRADE_RULES`.
- 토글 핸들러(`bind`)는 '답을 서버에 보내고 받은 판정으로 `render()`' 로 바뀐다(live-ui의 applyData 재사용).
- 남는 것: 그리기(`node/renderProduct/renderSizing/evLine/MARK...`)와 서버 판정(VD) 표시.
- selfCheck('화면 계산이 엔진과 다름' 경고)는 더 이상 화면이 계산 안 하므로 **불필요 → 제거**.

### 4-3. 순서 (안 깨지게)
1. (a) Ctx에 `manual_answers` 추가 — 기본 None이면 기존과 동일. 단위검증: `verify_primitives`.
2. (b) `render(..., answers=)` 추가 — answers=None 동일 출력. `verdict_engine` CLI/JSON 회귀 확인.
3. (c) serve에 답-포함 엔드포인트 + in-process 경로. 로컬 서버로 토글 왕복 수동 테스트(지연<100ms 목표).
4. (d) 마지막에 `checklist-ui.js` 평가기 삭제 + 토글→서버 왕복으로 교체. inject_ui `--check` 로 드리프트 0.
5. 전구간 검증: `verify_teams`·`verify_structure`·`verify_primitives`·`checklist.verify_tree`.

### 4-4. 트레이드오프
- 장점: 복제 평가기 제거(단일 진실 = cond.py), 사장님 "웹은 보여주기만" 달성.
- 비용: 토글마다 서버 왕복(네트워크 1홉). in-process+경량이면 체감 즉시성 유지 가능. **오프라인 아티팩트에선
  토글이 서버 없이는 안 됨** — 지금도 live-ui가 '서버 없으면 값 없음' 정책이라 일관됨(정적 스냅샷 폐지와 같은 선).

---

## 5. 의존성 / 순서 — tree.json 재생성에 얼마나 묶이나

- **현재 레포에 `books/*/tree.json` 이 없다**(확인: `books/trend/`·`books/moneycopy/` 에 tree.json 없음,
  tree_candidates/*.json 만 존재). 메모리 스냅샷의 "구간2 끝난 뒤 재개, 재개 첫 일 = tree 재생성→파리티"와 일치.
- 영향:
  - **§3 구조 이관**: tree.json **없어도 가능**. `verify_teams` 는 tree 무관으로 지금 돌릴 수 있고,
    `inject_ui --check`(사본==파일)도 tree 무관. 단 `verify_structure` 의 '책 계약'은 tree.json이 없으면
    실패 라인을 낸다 — 이관 성공 판정은 **UI 드리프트 라인 통과**로 보고, 책 계약 실패는 §5 블로커로 분리 기록.
  - **§4 서버 권위**: 실제 등급이 바뀌는지 **end-to-end 테스트는 tree.json 재생성 뒤**라야 가능
    (render가 돌려면 tree가 있어야 함). (a)(b) 단위 로직은 작은 합성 tree로 선검증 가능하나, 파리티(화면=엔진)
    확인은 실제 트리 필요.
- **권장 순서**:
  1. **지금**: §3 구조 이관(표시 코드 publish로) — tree 무관, 즉시 가능·검증 가능.
  2. **tree.json 재생성 후**: §4 서버 권위 통합 + 파리티 검증(화면 등급 == 엔진 등급).
  - 둘은 독립이므로 1을 먼저 끝내 커밋 가능 상태로 두고, 2는 tree 재생성에 맞춰 착수.

---

## 부록: 이관 전 전수 grep 체크리스트
```
grep -rn "checklist/ui"            # HTML/py 문자열 참조
grep -rn "checklist.inject_ui"     # import 참조 (publish_pages, verify_structure 기대)
grep -rn "checklist\\\\ui"         # 윈도 경로 표기(있다면)
ls book-to-playbook/books/*/tree.json   # 재생성 여부(§5 게이트)
```
검증(모두 venv):
```
./.venv/bin/python -m verify_teams
./.venv/bin/python -m verify_structure
./.venv/bin/python -m checklist.verify_primitives
./.venv/bin/python -m checklist.verify_tree   # tree.json 있을 때
```
