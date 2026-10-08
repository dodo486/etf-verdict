#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""판정기(구간③) — 한 상품의 한 시점 판정. 라이브 판정·백테스트·장중 재생·신호 파리티가 전부 여기를 지난다.

  · Judge     트리(TreeGateway) + 시세 이력(+ 보유 Holding) → Decision. 상품마다 Grade.ProductEval(checklist/grade)을
              전체 달력에 한 번 세우고 시점(i)마다 꺼낸다(벡터 1회계산 — cond 연산이 인과적이라 미래를 보지 않는다).
              돈·잔고는 모른다(그건 계산기 portfolio 의 일). 등급은 grade(i) 하나 — 라이브는 latest()(달력 마지막 봉),
              백테스트는 Timeline 이 모든 i 에 같은 grade(i) 를 부른다.
  · Amount    그 시점의 '얼마나' 사실(조심 배수·폭 미명시·확인 필요 조심·비중·비중 범위) — Judge.amount(i) 하나로 낸다.
              라이브 화면(Decision.amount)과 백테스트 매수 크기(trades.size_of 가 정책을 입혀 씀)가 같은 값을 쓴다.
              돈은 없다 — 모름(폭 미명시·확인 필요·비중 모름)을 금액에 어떻게 셀지는 정책 주인 trades.size_of 가 정한다.
  · Decision  그 시점의 판정 사실(등급·사유 재료·금액 Amount·조심 규칙·수동 확인 목록·보유 규칙 상태). 화면용
              모양(view·사유 문장)은 웹 화면층(web/verdict_view)이 이 사실과 평가 문맥(eval)으로 빚는다.
  · Holding   보유 상태(첫 매수 봉·평균 매입가·산 차수). pos 값(ret·days·maxret·minret)을 cond 에 주입하는 문맥은
              Holding.ctx 한 곳에서 만든다 — 라이브 보유 화면(Judge.hold)과 백테스트 체결 워크(trades.build_trades) 공통.
"""
from dataclasses import dataclass, field

from checklist.tradeTool import Cond
from checklist.tradeTool import Grade


class Holding:
    """보유 상태 — entry_i = 첫 매수 봉 index(없으면 None), cost = 평균 매입가(수 하나 또는 봉마다 평단 목록), filled = 산 차수."""

    def __init__(self, entry_i, cost, filled=1, entry_date=None):
        self.entry_i, self.cost, self.filled, self.entry_date = entry_i, cost, filled, entry_date

    @classmethod
    def at(cls, cal, entry_date, cost, filled=1):
        """첫 매수일(YYYYMMDD) → 그날 이후 첫 봉. 그 뒤 시세가 없으면 entry_i=None."""
        later = [k for k, d in enumerate(cal) if d >= entry_date]
        return cls(later[0] if later else None, cost, filled, entry_date)

    def ctx(self, gw, prod, hist, cal, manual_as=None):
        """이 보유를 pos 로 주입한 평가 문맥 — cond 는 그 값을 '읽어' ret·days·maxret·minret 로 exit·분할 규칙만 평가한다."""
        return Cond.Ctx(hist, cal, prod, gw.index(prod), gw.defs(), manual_as=manual_as, pos=(self.entry_i, self.cost))


@dataclass
class HoldingState:
    """보유 하나의 그 시점 규칙 상태 — exits = [(Rule, 값)], next_tranche = (Rule, 값)|None. 시세가 없으면 error."""
    error: str = None
    ret: float = None
    days: float = None
    exits: list = field(default_factory=list)
    next_tranche: tuple = None
    ctx: object = None


@dataclass
class Amount:
    """그 시점의 '얼마나' 사실(돈 없음). factor = 걸린 조심 규칙 배수(Qty "order")의 곱 · unspecified = 걸렸지만 폭을
    저자가 안 준 조심 라벨 · unknown = 걸렸는지 모르는(수동·데이터 없음) 조심 라벨 · weight = 그날 비중(%, 모르면 None)
    · weight_range = 수동 때문에 모를 때 가능한 값들 · weight_set = 저자가 비중을 줬나(식이 있나)."""
    factor: float = 1.0
    unspecified: list = field(default_factory=list)
    unknown: list = field(default_factory=list)
    weight: float = None
    weight_range: list = None
    weight_set: bool = False


@dataclass
class Decision:
    """한 상품·한 시점의 판정 사실(돈·잔고 없음). has_data=False 면 그 상품 시세가 없다(key="unknown")."""
    prod: str
    key: str
    has_data: bool = True
    i: int = None
    date: str = None
    close: float = None
    prev_close: float = None
    incomplete: bool = False
    confirmed: int = None            # 확정 봉 수(가장 늦은 심볼 기준)
    warmup: int = None               # 필요 워밍업(트리에서 파생)
    top: dict = None                 # 구역별 맨 위 라벨 노드의 그날 값(사유 재료)
    manual: list = None              # 사람 확인이 필요한 조건 [(칸, 라벨, ref)]
    amount: Amount = None            # 그날 '얼마나'(조심 배수·비중) — Judge.amount
    caution: list = None             # [(caution_state 항목, Rule)]
    opt: dict = None
    pes: dict = None
    holdings: list = None            # [HoldingState]
    eval: object = None              # Grade.ProductEval — 화면층이 같은 문맥으로 view 를 빚는다

    @property
    def grade(self):
        return Grade.GRADES[self.key]


class Judge:
    """한 상품 판정기 — 생성 때 Grade.ProductEval 을 전체 달력에 한 번 세운다.
    asof = 관측 시각(UTC datetime, None 이면 지금) · unobserved 가 "exclude" 면 관측 못 한 장중 조건을 빼고 판단(백테스트 전용)
    · answers = 사람이 답한 수동 {Cond.answer_key: 참/거짓}(라이브 화면의 수동 체크 — 서버가 그 답으로 등급을 낸다)."""

    def __init__(self, gw, prod, hist, cal=None, asof=None, unobserved=None, answers=None):
        self.gw, self.prod, self.hist = gw, prod, hist
        self.cs = hist.get(prod) or []
        self.cal = [c.date for c in self.cs] if cal is None else cal
        self.pe = Grade.ProductEval(gw, prod, hist, self.cal, unobserved, asof, answers)

    @property
    def warmup(self):
        return self.pe.warmup

    def grade(self, i):
        """i 번째 봉의 등급 키 — 라이브·백테스트·재생이 같이 쓰는 단 하나의 등급 경로."""
        return self.pe.grade_key(i)

    def incomplete(self, i):
        return self.pe.incomplete(i)

    def manual_items(self, i=None):
        return self.pe.manual_items(i)

    def amount(self, i):
        """i 번째 봉의 Amount — 라이브 Decision 과 백테스트 매수 크기가 같이 쓰는 단 하나의 '얼마나' 경로."""
        f, unspec, unknown = self.pe.amount_factor(i)
        w, alt = self.pe.weight_of(i)
        return Amount(f, unspec, unknown, w, alt, self.gw.sizing(self.prod).qty.x is not None)

    def latest(self):
        """(등급 키, 종가) — 달력 마지막 봉(라이브 '지금'). 시세가 없으면 ("unknown", None)."""
        if not self.cs:
            return "unknown", None
        return self.grade(len(self.cal) - 1), self.cs[-1].close

    def decide(self, i=None, holdings=()):
        """i 번째 봉(기본 = 마지막 봉)의 Decision. holdings = [Holding] 이면 각 보유의 규칙 상태도 담는다."""
        if not self.cs:
            return Decision(self.prod, "unknown", has_data=False)
        pe = self.pe
        i = len(self.cal) - 1 if i is None else i
        return Decision(
            self.prod, self.grade(i), i=i, date=self.cal[i], close=self.cs[i].close,
            prev_close=self.cs[i - 1].close if i >= 1 else None,
            incomplete=pe.incomplete(i), confirmed=pe._confirmed[i] + 1, warmup=pe.warmup,
            top=pe.top(i), manual=pe.manual_items(i), amount=self.amount(i),
            caution=list(zip(pe.caution_state(i), self.gw.cautions(self.prod))),
            opt={sec: pe.opt[sec][i] for sec in Cond.SECTIONS}, pes={sec: pe.pes[sec][i] for sec in Cond.SECTIONS},
            holdings=[self.hold(h, i) for h in holdings], eval=pe)

    def hold(self, h, i=None):
        """보유 하나의 i 번째 봉(기본 마지막) 매도·다음 분할 규칙 상태 — 수동은 모름(manual_as=None)."""
        if h.entry_i is None:
            return HoldingState(error="첫 매수일 %s 이후 시세 없음" % h.entry_date)
        i = len(self.cal) - 1 if i is None else i
        ctx = h.ctx(self.gw, self.prod, self.hist, self.cal)
        trs = self.gw.tranches(self.prod)
        nt = trs[h.filled] if 0 < h.filled < len(trs) else None
        return HoldingState(ret=Cond.series({"pos": "ret"}, ctx)[i], days=Cond.series({"pos": "days"}, ctx)[i],
                            exits=[(r, Cond.series(r.when, ctx)[i]) for r in self.gw.exit_rules(self.prod)],
                            next_tranche=None if nt is None else (nt, Cond.series(nt.when, ctx)[i]), ctx=ctx)
