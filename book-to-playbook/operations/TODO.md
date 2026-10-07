# 구간④ (operations) 할 일

확정된 조건 트리를 '소비'하는 계산기(백테스트·장중·웹뷰어)의 남은 과제. 대부분 **구간② 안정화 →
`tree.json` 재생성**이 선행돼야 진행 가능(지금은 심판 전이라 트리 없음).

## 🔴 레거시 정리 — `observe` 노드 제거 (asof 이관 중 남은 것)

**이건 "아침 판정 → asof(관측 시점) 모델"로 이관하면서 아직 안 걷어낸 레거시다.**

- **배경:** `observe` 는 옛 `at`(개장 전/개장 N분 스냅샷) 기계장치를 걷어낼 때, "개장 전 선물 방향" 같은
  장중 관측 조건을 담아 옮기던 **임시 포장재**였다. asof 전환 뒤엔 중복 — 이제 맨 `tf:"1m"` 식이
  데이터 없으면 자동으로 None(모름)을 내기 때문이다.
- **현재 상태:** 지침·트리엔 observe 가 이미 0건. **엔진(`shared/cond.py`)에만 살아 있다.**
  (제거 시도했으나, 아래 이유로 구간④ 재개 때로 보류함 — 2026-10-07.)
- **그냥 못 지우는 이유:** run2 후보엔 observe 없는 **맨 장중 조건**(예: 개장 전 `ES=F` 선물 > 전일 종가)이
  있는데, 지금은 데이터가 없으면 🟡(사람 확인)가 아니라 ❔(보류)로 떨어지고 백테스트에서 EXCLUDED 도
  안 된다. **제대로 지우려면** 엔진이 "장중 데이터 없음 → None"을 observe 가 하던 대로
  **실전 🟡 / 백테스트 EXCLUDED 로 자동 처리**하는 트리거를 깔아야 한다. 이건:
  - 백테스트 `EXCLUDED`(빼고 판단) 의미 + 등급 로직(`shared/tree_grade.py`)을 건드리는 **구간④ 기능 변경**
  - **워밍업 None**(일봉 지표 준비 전)을 잘못 🟡/EXCLUDED 로 바꾸면 백테스트 오염 위험 → "장중축 데이터
    부재 None"만 콕 집는 표식 필요
  - `tree.json` 이 없어 **파리티(720/720)로 검증 불가** → 데이터 정직성상 지금 반쪽 변경은 안 함
- **할 일(구간④ 재개 때):** 실데이터 + 트리 생기면 → 엔진에 "장중 데이터 부재 None → 🟡/EXCLUDED"
  자동 트리거 설치 → `observe` 래퍼 전부 제거 → `verify_primitives` 불변식 + 백테스트 파리티로 등가성 증명.
- **영향 파일:** `shared/cond.py`, `shared/tree_grade.py`, `verdict/verify_primitives.py`,
  `checklist/verify_tree.py`, `operations/backtest.py`·`driver.py`, `checklist/ui/checklist-ui.js`,
  `COND_DSL.md`·`MIGRATION_NOTES.md`.

## 🟡 기능 (구간② tree.json 재생성 후)

- **웹뷰어 지표 통합:** 백테스트 탭에 vectorbt 지표(총수익·MaxDD·샤프·자산곡선·장중 결과)를
  `backtest-<slug>.json` + 탭에 채우기 (표시 코드는 이미 있음, 결과 JSON이 구버전 포맷이라 비어 있음).
- **신호 파리티 재검증:** 심판이 트리 재생성한 뒤 `python -m operations.verify_signal_parity`(venv)로
  새 `cond.py` 위 신호 파리티 실측.
- **장중 P&L 백테스트:** 분봉이 길게 들어오면 `replay.series → portfolio.run_product` 재사용
  (지금은 분봉 ~7일=1세션뿐이라 샤프 가짜 방지로 미룸).
- **신규 프리미티브:** VWAP·세션 리셋 집계(당일 고저) 등.

## 🟢 데이터 (선행조건)

- **jhts 실데이터 교체** + 작업용으로 임시로 쓴 **yfinance 흔적 완전 삭제**(MIGRATION_NOTES 삭제 체크리스트).
