#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""판정기(구간③) — 한 상품의 한 시점 판정. 라이브 판정·백테스트·장중 재생·신호 파리티가 전부 여기를 지난다.

  · Judge     트리(TreeGateway) + 시세 이력(+ 보유 Holding) → Decision. 상품마다 Grade.ProductEval(dsl/tradeTool)을
              전체 달력에 한 번 세우고 시점(i)마다 꺼낸다(벡터 1회계산 — cond 연산이 인과적이라 미래를 보지 않는다).
              돈·잔고는 모른다(그건 계산기 portfolio 의 일). 등급은 grade(i) 하나 — 라이브는 latest()(달력 마지막 봉),
              백테스트는 signal_series 가 모든 i 에 같은 grade(i) 를 부른다.
  · Amount    그 시점의 '얼마나' 사실(비중·비중 범위) — Judge.amount(i) 하나로 낸다.
              라이브 화면(Decision.amount)과 백테스트 매수 크기(trades.size_of 가 정책을 입혀 씀)가 같은 값을 쓴다.
              돈은 없다 — 모름(비중 미명시·모름)을 금액에 어떻게 셀지는 정책 주인 trades.size_of 가 정한다.
  · Decision  그 시점의 판정 사실(등급·사유 재료·금액 Amount·수동 확인 목록·보유 규칙 상태). 화면용
              모양(view·사유 문장)은 웹 화면층(consumers/display/verdict_view)이 이 사실과 평가 문맥(eval)으로 빚는다.
  · Holding   보유 상태(첫 매수 봉·평균 매입가·산 차수). pos 값(ret·days·maxret·minret)을 cond 에 주입하는 문맥은
              Holding.ctx 한 곳에서 만든다 — 라이브 보유 화면(Judge.hold)과 백테스트 체결 워크(trades.build_trades) 공통.
"""
from dataclasses import dataclass, field

from dsl.tradeTool import Cond
from dsl.tradeTool import Grade


class Holding:
    """보유 상태 — entry_i = 첫 매수 봉 index(없으면 None), cost = 평균 매입가(수 하나 또는 봉마다 평단 목록), filled = 산 차수,
    book = 날짜별 체결 장부 {"filled": {규칙 이름|None: 산 횟수}, "sold": 판 비율}(백테스트 체결 워크가 넣는다 — 없으면 모름)."""

    def __init__(self, entry_i, cost, filled=1, entry_date=None, book=None):
        self.entry_i, self.cost, self.filled, self.entry_date, self.book = entry_i, cost, filled, entry_date, book

    @classmethod
    def at(cls, cal, entry_date, cost, filled=1):
        """첫 매수일(YYYYMMDD) → 그날 이후 첫 봉. 그 뒤 시세가 없으면 entry_i=None."""
        later = [k for k, d in enumerate(cal) if d >= entry_date]
        return cls(later[0] if later else None, cost, filled, entry_date)

    def ctx(self, gw, prod, hist, cal, manual_as=None):
        """이 보유를 pos 로 주입한 평가 문맥 — cond 는 그 값을 '읽어' ret·days·maxret·minret·filled·sold 로 판다·분할 갈래만 평가한다."""
        pos = (self.entry_i, self.cost) if self.book is None else (self.entry_i, self.cost, self.book)
        return Cond.Ctx(hist, cal, prod, gw.index(prod), manual_as=manual_as, pos=pos)


@dataclass
class HoldingState:
    """보유 하나의 그 시점 규칙 상태 — sells = [(Rule, 값)](판다 갈래), next_tranche = (Rule, 값)|None. 시세가 없으면 error."""
    error: str = None
    ret: float = None
    days: float = None
    sells: list = field(default_factory=list)
    next_tranche: tuple = None
    ctx: object = None


@dataclass
class Amount:
    """그 시점의 '얼마나' 사실(돈 없음). weight = 그날 비중(%, 모르면 None)
    · weight_range = 수동 때문에 모를 때 가능한 값들 · weight_set = 저자가 비중을 줬나(식이 있나)."""
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
    top: dict = None                 # 동사(안 산다·산다)별 맨 위 라벨 노드의 그날 값(사유 재료)
    manual: list = None              # 사람 확인이 필요한 조건 [(동사, 라벨, ref)]
    amount: Amount = None            # 그날 '얼마나'(비중) — Judge.amount
    opt: dict = None
    pes: dict = None
    holdings: list = None            # [HoldingState]
    eval: object = None              # Grade.ProductEval — 화면층이 같은 문맥으로 view 를 빚는다

    @property
    def grade(self):
        return Grade.GRADES[self.key]


class Judge:
    """한 상품 판정기 — 생성 때 Grade.ProductEval 을 전체 달력에 한 번 세운다.
    asof = 관측 시각(UTC datetime, None 이면 지금)
    · answers = 사람이 답한 수동 {Cond.answer_key: 참/거짓}(라이브 화면의 수동 체크 — 서버가 그 답으로 등급을 낸다)."""

    def __init__(self, gw, prod, hist, cal=None, asof=None, answers=None):
        self.gw, self.prod, self.hist = gw, prod, hist
        self.cs = hist.get(prod) or []
        self.cal = [c.date for c in self.cs] if cal is None else cal
        self.pe = Grade.ProductEval(gw, prod, hist, self.cal, asof, answers)

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
        w, alt = self.pe.weight_of(i)
        return Amount(w, alt, self.pe.weight[None] is not None)   # 비중 식이 있나 — 평가기가 이미 세운 값으로(트리를 다시 묻지 않는다)

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
            opt={do: pe.opt[do][i] for do in Cond.GATES}, pes={do: pe.pes[do][i] for do in Cond.GATES},
            holdings=[self.hold(h, i) for h in holdings], eval=pe)

    def hold(self, h, i=None):
        """보유 하나의 i 번째 봉(기본 마지막) 판다·다음 분할 갈래 상태 — 수동은 모름(manual_as=None)."""
        if h.entry_i is None:
            return HoldingState(error="첫 매수일 %s 이후 시세 없음" % h.entry_date)
        i = len(self.cal) - 1 if i is None else i
        ctx = h.ctx(self.gw, self.prod, self.hist, self.cal)
        trs = self.gw.tranches(self.prod)
        nt = trs[h.filled] if 0 < h.filled < len(trs) else None
        return HoldingState(ret=Cond.series({"pos": "ret"}, ctx)[i], days=Cond.series({"pos": "days"}, ctx)[i],
                            sells=[(r, Cond.series(r.when, ctx)[i]) for r in self.gw.sells(self.prod)],
                            next_tranche=None if nt is None else (nt, Cond.series(nt.when, ctx)[i]), ctx=ctx)


def signal_series(gw, hist, start=None, prods=None):
    """전 상품·전 시점 신호 — 상품마다 Judge 를 전체 달력에 한 번 세우고 grade(i)/incomplete(i) 를 뽑는다
    (일봉 벡터 1회계산 — 라이브 latest() 와 같은 Judge.grade 경로). 백테스트가 이 신호 뒤에 집계·계산기를 붙인다.
    트리 연산은 전부 인과적이라(그날까지의 값만 씀) 전체 이력을 한 번 계산해 날짜로 꺼낸다. start(YYYYMMDD)을
    주면 그 이상 날만. → {prods, series:{prod:[{date,key,grade,close,incomplete}]}, judges:{prod:Judge}}."""
    prods = prods if prods is not None else gw.products()
    series, judges = {}, {}
    for p in prods:
        cs = hist.get(p) or []
        cal = [c.date for c in cs]
        j = Judge(gw, p, hist, cal)
        pts = []
        for i, d in enumerate(cal):
            if start is not None and d < start:
                continue
            k = j.grade(i)                            # 워밍업 부족이면 grade 가 ❔(불완전)로 내보낸다(incomplete 로 함께 표시)
            pts.append({"date": d, "key": k, "grade": Grade.GRADES[k], "close": cs[i].close, "incomplete": j.incomplete(i)})
        series[p], judges[p] = pts, j
    return {"prods": prods, "series": series, "judges": judges}


def truncate(full, upto):
    """full(Grade.History) 을 날짜 upto(YYYYMMDD) 이하로 자른 새 Grade.History (분봉 minutes 는 그대로 넘긴다).
    과거 세션의 '그 세션 마감 직후 라이브가 보유했을' 확정 일봉을 재현한다 — 신호 파리티(verify_trading --parity)가 쓰는 규약."""
    t = Grade.History({s: [c for c in (cs or []) if c.date <= upto] for s, cs in full.items()})
    t.minutes = getattr(full, "minutes", {})
    return t
