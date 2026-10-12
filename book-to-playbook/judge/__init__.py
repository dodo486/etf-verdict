# -*- coding: utf-8 -*-
"""judge 층 — tree+시세 → 판정 데이터. 돈·체결은 backtest, 화면 모양은 web 이 빚는다.

  · judge.py       판단자 — Judge(책 하나: 트리·시세 원본의 유일한 사용자 · 라이브 판정·백테스트 신호 · judge.tree = 비교·채점 도구가 트리에 묻는 문)
                   · ProductJudge(상품 하나: 등급·그날 판정·노드 값(value — 화면 설명의 값 함수)·보유 상태·체결용 조건 값·가격) · Holding · Decision 그릇
                   · '얼마나'(매도 정책 exit_policy · 수량 변환 to_units · 금액 정책 size_of — 라이브 화면·백테스트 공용)
                   · 등급(RuleSeries · GRADES) · 시세 받기(history · history_back · session_closes — 시세 원본은 여기서만)
  · eval.py        계산기 — 트리 식에 시세 값을 넣어 계산(Ctx · series). 부르는 곳은 judge(판단자·설명)뿐
  · grade_rules.json 등급 사다리(데이터 — 읽는 곳은 judge.py 의 RuleSeries.grade_key 하나)
  · verify_eval.py 검사 — 원시 연산·3값·인과성·확정봉·등급·금액·수동 답(pandas 기준값·손계산 대조, judge 를 바꾸면)

경계: judge 는 shared · market · tree 만 import 한다(트리의 뜻은 tree 공개 모듈로). 백테스트·화면은 모른다.
경계는 entry/verify_rules.py 가 강제한다.
"""
