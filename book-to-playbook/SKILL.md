---
name: book-to-playbook
description: 트레이딩 책을 읽어 실전 매매 플레이북 + 인터랙티브 매매시트 아티팩트로 자동 변환. "책 플레이북 만들어줘", "이 책 매매시트로", "book-to-playbook", 책 소스 경로와 함께 요청 시 사용.
---

# Book → Playbook + 매매시트

트레이딩 책 원문(텍스트)을 받아 ① 저자 매매기법 플레이북 ② 정량화된 실전 매매시트를
**2탭 인터랙티브 아티팩트**로 만든다. 원리: **템플릿(고정) + 콘텐츠(책마다 교체)** 분리.

## 입력
- 정제된 텍스트(.md) 있음 → 바로 STEP 1
- 스캔 PDF만 있음 → 먼저 이미지화→OCR→청킹(jhts/jhts2 파이프라인 재사용) 후 STEP 1

## 파이프라인

### STEP 1. 추출 (서브에이전트, opus)
책 전체를 청크로 **처음부터 끝까지** 읽어 아래를 산출. **절대규칙: 저자 명시분만·원문 숫자 그대로·미명시는 "저자 미명시" 표기·지어내기 금지·개인 일화/이름 제외.**
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
- `logs/` — 판정 로그
