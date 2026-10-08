---
name: book-to-playbook
description: 트레이딩 책을 읽어 실전 매매 플레이북 + 기계가 실행하는 체크리스트(조건 트리) 웹페이지로 자동 변환하고 매일 자동 판정. "책 플레이북 만들어줘", "이 책 체크리스트로", "book-to-playbook", 책 소스 경로와 함께 요청 시 사용.
---

# Book → Playbook + 체크리스트(조건 트리) — 진행자 지침

이 문서는 전체를 돌리는 **진행자**의 지침이다(전 구간 공통만). 구간별 세부는 그 구간의 문서에 있다 —
체크리스트(구간②)는 `checklist/README.md`.

트레이딩 책 원문을 받아 ① 저자 매매기법 플레이북 ② 기계가 실행하는 체크리스트(`books/<slug>/tree.json`)를 2탭
웹페이지로 만들고, jhts 시세로 판정한다. 체크리스트를 **만드는 곳은 구간② 하나, 읽는 곳은 구간③ 하나**다. 상세는 `README.md`.

## ⛔ 절대 규칙 1 — 원문은 고정, 구현을 고친다

**책 = 사양, 코드 = 구현.** 구현이 원문을 못 따라가면 선택지는 둘뿐이다.
1. **구현을 원문에 맞춘다** — 데이터가 있으면 쓰고(jhts 에 없으면 수집 요청이 자동으로 남는다), 연산이 없으면 연산을 추가한다.
2. **못 따라간 것은 그렇다고 드러낸다** — 조용히 빼거나 다른 것으로 흉내 내지 않는다.

원문 문구를 구현에 맞춰 고치는 것은 선택지가 아니다. 플레이북 본문(`#src`)은 `verify_source_integrity` 가 해시로 지킨다.

> 실제 사고: 시트 라벨은 저자대로 "나스닥 **선물** 방향"인데 파이프라인은 지수(^NDX)를 봤다. 라벨을 구현에 맞춰
> 고쳤다 — 불일치가 사라진 게 아니라 안 보이게 됐다. 실제로는 선물(NQ=F)을 그냥 받을 수 있었다.

## ⛔ 절대 규칙 2 — 숫자를 지어내지 않는다

조건·숫자·대상을 지어내지 않는다. 저자가 안 준 것은 없는 대로 둔다. 구간별 정본에 세부가 있다 —
구간①(전사) = `playbook/PLAYBOOK.md`, 구간②(추출) = `checklist/EXTRACTOR.md`.

## ⛔ 절대 규칙 3 — 검사는 실행으로, 책이 계약에 맞춘다

검사는 글자가 아니라 실행으로 본다(목록은 `orchestration/run.py` CHECKS 하나 — 매 발행마다 돌고, `python -m orchestration.run check` 로 전부). 통과시키려고 검사를 느슨하게 만들지 않는다.
책 계약(`checklist.verify_tree --contract`): 원문 소절 인덱스 · 트리 문법(여섯 칸 전부) · 트리 ref 가 실제 소절. 책 페이지(`web.verify_view --pages`): 페이지 구획과 UI 사본.

## 새 책 절차

```
1) 원문 자르기   book_sources.json 에 원문 위치 → python -m playbook.book_source --write
                 (원문 전체는 리포에 넣지 않고 source_index.json 에 키·제목·줄범위·해시만 둔다)
2) 전사(구간①)  서브에이전트가 책 전체를 읽어 #src 로 **충실 전사**(저자 문장 그대로 · 요약·분류 금지 · 노이즈만 제거)
                 → 전사 대조 감사(별도 서브에이전트) → python -m playbook.verify_source_integrity --accept --why "새 책".
                 산출물 2개: 전사본(=구간② 입력) · 사람용 요약 뷰(비핵심·파생). 세부는 playbook/PLAYBOOK.md.
3) 페이지        books/trend/playbook.html 을 베이스로 #src·머리말(제목·상품 소개)만 교체.
                 시트 패널은 #verdict-data + #sheet-root 골격 그대로(UI 는 web/ui/*.js 가 주입된다).
4) 체크리스트    checklist/README.md 절차대로(추출자 a·b → 사례 작성자 → 심판 → verify_tree 통과)
5) 등록·배포     books.json 에 항목(slug/title/tickers/desc/live/engine.daily) → python -m orchestration.run daily
```

### 검사 실패 → 고칠 곳 (체크리스트 채점 `verify_tree` 는 `checklist/README.md`)

| 실패 | 뜻 | 고칠 곳 |
|---|---|---|
| verify_tree --contract · verify_view --pages | 소절 인덱스·트리 문법·ref · 페이지 구획·UI 사본 | 해당 산출물을 만든 단계를 다시(UI 사본은 `python -m web.inject_ui <페이지>`) |
| verify_code | 폴더 경계·주인 표 위반 | 위반 줄을 주인 파일의 공개 함수로(검사·표를 느슨하게 하지 않는다) |
| verify_source_integrity | 플레이북 본문이 바뀜 | 의도한 원문 대조 수정이면 `--accept --why`, 아니면 되돌린다 |
| verify_primitives · verify_trading | 원시 연산·체결 계산 오류 | `checklist/tradeTool.py`·`trading/trades.py`(책 쪽이 아니다) |

## 입력
- 정제된 텍스트(.md) 있음 → 바로 1)
- 스캔 PDF만 있음 → 먼저 이미지화→OCR→청킹(jhts 파이프라인 재사용) 후 1)

## 판정 운영
`python -m orchestration.run daily` — 책마다 `web.verdict_view`(판정 → 알림) → `web.backtest_page`(백테스트 탭 데이터) →
검사. `python -m orchestration.run watch [--every N]` 는 asof=지금으로 N분마다 재판정(장중 포함).
알림은 `telegram.env`(TELEGRAM_BOT_TOKEN/CHAT_ID)가 있으면 텔레그램, 없으면 데스크톱. 시세는 jhts 패키지(`PYTHONPATH`)에서만
온다. 스케줄 등록·내 포지션 파일은 `SETUP.md`.
