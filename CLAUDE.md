# etf-verdict — 작업 규칙 (모든 세션 공통)

트레이딩 책 → 전사본 → 체크리스트(DSL, `books/<slug>/tree.json`) → 판정·백테스트·화면. 코드는 `book-to-playbook/`.

- **구조·원칙의 정본**: `book-to-playbook/docs/ARCHITECTURE.md` — 작업 전에 읽는다.
- **할 일의 정본**: `book-to-playbook/docs/HANDOFF.md` 한 곳(다른 곳에 TODO 를 만들지 않는다).
- **검사**: `python -m orchestration.run check` (book-to-playbook 에서). 실행 환경: `PYTHONPATH=<jhts 경로>`(jhts-marketdata 미설치 시 시세가 빈다), `PYTHONIOENCODING=utf-8`.

## 꼭 지킬 것

1. **결정 하나 = 주인 하나.** 같은 결정을 두 곳에 두지 않는다. 새로 '한 곳에서만 정할 것'이 생기면
   `orchestration/verify_code.py` 주인 표(`OWNERS`)에 한 줄 추가.
2. **특정 책에 맞추지 않는다.** 일반 부품 + 조합. 사례마다 칸·지표·필드를 덧대지 않는다.
3. **숫자를 지어내지 않는다, 모르면 드러낸다.** 저자가 안 준 숫자는 `"?"`. 대신 채우는 기본값 금지.
4. **tree.json 은 `TreeGateway` 로만 읽는다.** 화면(web)은 엔진 결과를 그리기만 한다.
5. **책 데이터(후보·tree.json)는 손으로 고치지 않는다** — 공통 로직을 고친 뒤 다시 뽑는다.
6. **리팩터와 기능은 커밋 분리, 리팩터 먼저.** 리팩터는 전후 비교로 동작 불변을 증명. 한 작업 = 커밋 하나.
7. **쓸모없어진 것은 같은 작업에서 지운다**(호환 별칭 남기지 않음).
8. 사용자에게는 한국어로, 쉬운 말로 보고한다.
