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

## ⛔ 절대 규칙 2 — 숫자를 지어내지 않는다 (플레이북에서도)

- **플레이북 요약 bullet 은 원문에 없는 숫자·칸 배치가 섞이기 쉽다.** 실제로 분할 비율 25~30/30/40~45%,
  '비중 키우는 자리'를 '진입'으로 적은 것, 없는 조건("SPY·QQQ가 먼저")이 섞여 있었다. 플레이북을 쓴 뒤 반드시
  원문과 한 줄씩 대조 감사한다. 어긋나면 **트리가 아니라 플레이북을 고친다**(`--accept --why`).

## ⛔ 절대 규칙 3 — 검사는 실행으로, 책이 계약에 맞춘다

검사는 글자가 아니라 실행으로 본다(검사기 3개, `run.py` 가 매 발행마다 돈다). 통과시키려고 검사를 느슨하게 만들지 않는다.
책 계약(`verify_structure`): 원문 소절 인덱스 · 트리 문법(여섯 칸 전부) · 트리 ref 가 실제 소절 · 페이지 구획과 UI 사본.

## 새 책 절차

```
1) 원문 자르기   book_sources.json 에 원문 위치 → python -m playbook.book_source --write
                 (원문은 저작권물 — 리포에 복사하지 않는다. source_index.json 엔 키·제목·줄범위·해시만)
2) 플레이북      서브에이전트가 책 전체를 읽어 #src 마크다운: ## 0. 핵심 원칙 + 장별 ## N. / ### N-n. 소절
                 (본문 + 요약 bullet). 저자 명시분만 · 원문 숫자 그대로 · 미명시는 "(저자 미명시)" · 개인 일화 제외.
                 → 원문 대조 감사(별도 서브에이전트) → python -m playbook.verify_source_integrity --accept --why "새 책"
3) 페이지        trend-playbook.html 을 베이스로 #src·머리말(제목·상품 소개)만 교체.
                 시트 패널은 #verdict-data + #sheet-root 골격 그대로(UI 는 checklist/ui/*.js 가 주입된다).
4) 체크리스트    checklist/README.md 절차대로(추출자 a·b → 사례 작성자 → 심판 → verify_tree 통과)
5) 등록·배포     books.json 에 항목(slug/title/tickers/desc/live/engine.daily) → python run.py daily
```

### 검사 실패 → 고칠 곳 (체크리스트 채점 `verify_tree` 는 `checklist/README.md`)

| 실패 | 뜻 | 고칠 곳 |
|---|---|---|
| verify_structure 책 계약 | 소절 인덱스·트리 문법·ref·페이지 구획 | 해당 산출물을 만든 단계를 다시 |
| verify_source_integrity | 플레이북 본문이 바뀜 | 의도한 원문 대조 수정이면 `--accept --why`, 아니면 되돌린다 |
| verify_primitives | 원시 연산·체결 계산 오류 | `shared/cond.py`·`trades.py`(책 쪽이 아니다) |

## 입력
- 정제된 텍스트(.md) 있음 → 바로 1)
- 스캔 PDF만 있음 → 먼저 이미지화→OCR→청킹(jhts 파이프라인 재사용) 후 1)

## 판정 운영
`python run.py daily` — 책마다 `verdict.verdict_engine`(알림 + latest-verdict JSON) → `verdict.backtest --page` → 발행 →
검사 3종 → 통과 시 git 커밋·푸시. `python run.py watch [--every N]` 는 asof=지금으로 N분마다 재판정(장중 포함).
알림은 `telegram.env`(TELEGRAM_BOT_TOKEN/CHAT_ID)가 있으면 텔레그램, 없으면 데스크톱. 시세는 jhts 패키지(`PYTHONPATH`)에서만
온다. 스케줄 등록·내 포지션 파일은 `SETUP.md`.
