#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""판단자(구간③) — 트리 원본과 시세 원본을 쓰는 유일한 곳. 책의 내용대로 판단하는 일은 여기 한 곳에서만 한다.

  · Judge         책 하나의 판단자 — 트리를 열고(TreeGateway 는 여기서만), 시세를 받고(tradeTool.history 는 여기서만),
                  상품마다 ProductJudge 를 세운다. 라이브 판정(decisions)·백테스트 신호(signals)를 낸다.
  · ProductJudge  상품 하나의 판단자 — 트리에서 그 상품의 규칙만 골라 시세와 평가한다.
                  등급(grade·latest)·그날 판정(decide → Decision)·조건 설명(views)·보유분 상태(status)·체결 워크가
                  쓸 보유 조건 값(conditions)·가격(price — 체결가·수익률 계산용).
  · Holding       보유 하나의 상태(첫 매수 봉·평단·산 차수·체결 장부) — 값만. 평가는 ProductJudge 가 한다.
  · Decision · Amount · HoldingStatus   판정 사실을 담는 그릇(계산하지 않는다).
  · 얼마나(판정의 '얼마나' — 라이브 화면·백테스트가 같이 쓴다, 아래 '얼마나' 절)
      exit_policy · NO_EXIT_NOTE   매도 정책(entry.verify_rules 주인 표 '매도 정책')
      to_units · Ledger · live_units   수량 변환(주인 표 '수량 변환')
      size_of · size_notes · SIZE_NOTES · tranches_of · unsized_note   금액 정책(주인 표 '금액 정책')

다른 층(체결·화면·라이브 버스·검사)은 트리·시세 원본을 만지지 않고 여기에 묻는다 — 받은 값(판정·가격·조건 값·
규칙 설명)만 쓴다. 시세 묶음(prices)은 다른 층에선 열어 보지 않는 봉투다(받아서 다시 넘기기만). entry.verify_rules 가 강제한다.
"""
import json
import os
from collections import namedtuple
from dataclasses import dataclass, field

from shared.paths import positions_json
from tree.tradeTool import CondError, Ctx, GATES, GRADES, history_back, RuleSeries, series
from tree.gateway import Branch, Qty, TreeGateway
from judge import explain


# ================================================================ 결과 그릇
@dataclass
class Amount:
    """그 시점의 '얼마나' 사실(돈 없음). weight = 그날 비중(%, 모르면 None)
    · weight_range = 수동 때문에 모를 때 가능한 값들 · weight_set = 저자가 비중을 줬나(식이 있나)."""
    weight: float = None
    weight_range: list = None
    weight_set: bool = False


@dataclass
class HoldingStatus:
    """보유 하나의 그날 상태 — sells = [(Branch, 값, 설명)] 판다 갈래, next_tranche = (Branch, 값, 설명)|None. 시세가 없으면 error."""
    error: str = None
    ret: float = None
    days: float = None
    sells: list = field(default_factory=list)
    next_tranche: tuple = None


@dataclass
class Decision:
    """한 상품·한 날의 판정 사실(돈·잔고 없음). has_data=False 면 그 상품 시세가 없다(key="unknown")."""
    product: str
    key: str
    has_data: bool = True
    day: int = None
    date: str = None
    close: float = None
    prev_close: float = None
    incomplete: bool = False
    confirmed: int = None            # 확정 봉 수(가장 늦은 심볼 기준)
    warmup: int = None               # 필요 워밍업(트리에서 파생)
    top: dict = None                 # 동사(안 산다·산다)별 맨 위 라벨 노드의 그날 값(사유 재료)
    manual: list = None              # 사람 확인이 필요한 조건 [(동사, 라벨, ref)]
    amount: Amount = None            # 그날 '얼마나'(비중)
    opt: dict = None                 # 등급 동사의 낙관(수동 = 유리) 값
    pes: dict = None                 # 등급 동사의 비관(수동 = 불리) 값
    views: dict = None               # 등급 동사별 조건 설명(그날 값·측정 증거) — 화면이 그대로 그린다
    holdings: list = None            # [HoldingStatus]

    @property
    def grade(self):
        return GRADES[self.key]


class Holding:
    """보유 하나의 상태(값만) — entry_day = 첫 매수 봉 index(없으면 None), cost = 평균 매입가(수 하나 또는 봉마다 평단 목록),
    filled = 산 차수, book = 날짜별 체결 장부 {"filled": {규칙 이름|None: 산 횟수}, "sold": 판 비율}(백테스트 체결 워크가
    넣는다 — 없으면 pos filled·sold 는 모름)."""

    def __init__(self, entry_day, cost, filled=1, entry_date=None, book=None):
        self.entry_day, self.cost, self.filled, self.entry_date, self.book = entry_day, cost, filled, entry_date, book

    @classmethod
    def at(cls, days, entry_date, cost, filled=1):
        """첫 매수일(YYYYMMDD) → 그날 이후 첫 봉. 그 뒤 시세가 없으면 entry_day=None."""
        later = [k for k, d in enumerate(days) if d >= entry_date]
        return cls(later[0] if later else None, cost, filled, entry_date)


# ================================================================ 얼마나 — 매도 정책 · 수량 변환 · 금액 정책
# 판정의 '얼마나'(비중·분할·매도 비율)를 물량으로 — 라이브 화면(web)과 백테스트 체결 워크(backtest)가 여기를 같이 쓴다.
#   · exit_policy : 매도 정책 "book"(책 매도 규칙으로 청산 시뮬레이션) | "none"(책에 매도 규칙 없음 — 대체 규칙을
#                   지어내지 않고 매수 신호 뒤 N거래일 보유 수익률로만 평가, 표시 문구 NO_EXIT_NOTE). 모두 이걸 묻는다.
#   · to_units    : 정규화된 '얼마나'(출입구 Qty(of, x) — cash·budget·bought·held)를 물량으로 바꾸는 단 하나의
#                   함수. 매수(분할 차수)·매도(산/남은 물량의 비율)·비중이 전부 여기를 지난다. 장부 = Ledger.
#                   live_units = 라이브 오늘 물량(화면이 basis 를 다시 해석하지 않게).
#   · size_of     : 그날의 '얼마나' 사실(Amount — 라이브 화면과 같은 ProductJudge.amount 한 경로)을 그날 장부
#                   Ledger(budget = 비중)로. 매수 물량 = to_units(분할 차수 Qty, 그 장부) = 분할 비율 × 비중(%)/100.
#                   모름은 지어내지 않는다(SIZE_NOTES 로 횟수를 결과에 드러낸다):
#                     · 비중 저자 미명시(산다 qty cash 없음) → 상품 예산 100% 기준(배수 1)
#                     · 비중 식은 있으나 그날 값 모름(저자 미명시 숫자 "?"·수동) → 상품 예산 100% 기준(배수 1)
#                     · 금액 사실이 없음(그 봉의 판정 없음) → 배수 1
#   · size_notes  : 위 횟수(체결 집계의 size_counts)를 결과에 보일 문구로.
#   · tranches_of : 분할 매수 차수. 분할이 없거나 저자가 비율을 안 줬으면("?") 전량 한 번(비율을 지어내지 않는다).
#   · unsized_note: 분할 비율·매도 비율 '저자 미명시'를 백테스트가 어떻게 계산했는지 결과에 표시할 문구.
FULL = [Branch("전량", qty=Qty("budget", 1.0))]    # 한 번에 전량 — 분할이 없거나 비율 미명시일 때
NO_EXIT_NOTE = "책에 매도 규칙 없음 — 매수 신호만 평가"   # 매도 정책 "none" 의 표시 문구(백테스트 탭·판정 화면이 받아 쓴다)


def exit_policy(sells):
    """매도 정책 — 이 함수 하나가 주인이다(밖은 이걸 묻는다). "book" = 책의 매도 규칙으로 청산까지 시뮬레이션.
    "none" = 책에 매도 규칙이 없다 → 대체 매도 규칙을 지어내지 않고, 거래 시뮬레이션 없이 매수 신호 뒤
    N거래일 보유 수익률(backtest 의 HORIZONS)로만 평가한다(화면 문구 NO_EXIT_NOTE)."""
    return "book" if sells else "none"


def tranches_of(trs):
    """시뮬레이션에 쓰는 분할 — 없거나 저자가 비율을 안 줬으면("?") 전량 한 번으로
    계산한다(비율을 지어내지 않는다 — 결과에 unsized_note 로 표시)."""
    return FULL if (not trs or trs[0].qty.x is None) else trs


def unsized_note(trs, sells):
    """저자가 비율을 안 준 수량 자리를 백테스트가 어떻게 계산했는지 — 없으면 None."""
    out = ["분할 비율 저자 미명시 — 전량 한 번 매수로 계산"] if trs and trs[0].qty.x is None else []
    out += ["매도 비율 저자 미명시 「%s」 — 팔지 않은 것으로 계산" % r.label for r in sells if r.qty.x is None]
    return " · ".join(out) or None


class Ledger(namedtuple("Ledger", "budget bought held")):
    """수량 변환의 그 시점 장부(물량 단위 = 시작자본 1.0). budget = 오늘 이 상품에 배정된 물량(비중) ·
    bought = 지금까지 산 물량 · held = 지금 남은 물량."""
    __slots__ = ()

    def __new__(cls, budget=1.0, bought=0.0, held=0.0):
        return super().__new__(cls, budget, bought, held)


def to_units(q, led):
    """정규화된 '얼마나'(출입구 Qty(of, x)) → 물량 — 매수·매도·비중이 전부 지나는 단 하나의 변환
    (entry.verify_rules 주인 표 '수량 변환'). led = 그 시점 장부(Ledger).
      cash   x → x/100            총 투자금의 x %          (비중)
      budget x → x × led.budget   이 상품 배정 금액의 x    (분할 차수)
      bought x → x × led.bought   지금까지 산 물량의 x     (매도)
      held   x → x × led.held     지금 남은 물량의 x(1=전량)(매도)
    x None(저자 미명시) → None — 지어내지 않는다(호출자 정책: 매도는 팔지 않음 · 비중은 size_of)."""
    if q.x is None:
        return None
    return {"cash": lambda: q.x / 100.0, "budget": lambda: q.x * led.budget,
            "bought": lambda: q.x * led.bought, "held": lambda: q.x * led.held}[q.of]()


def live_units(a, q=None):
    """라이브 화면의 오늘 물량(시작자본 1.0 기준) — q(분할 차수 Qty) 생략이면 이 상품 오늘 배정 전체.
    비중을 모르면(미명시·그날 값 모름) None(화면은 금액을 '—'로 — 백테스트 정책으로 채우지 않는다)."""
    if not a.weight_set or a.weight is None:
        return None
    led = Ledger(budget=to_units(Qty("cash", a.weight), Ledger()))
    return to_units(q or Qty("budget", 1.0), led)


def sell_text(q, repeat=False):
    """매도 수량(Qty)의 사람 문장 — 화면이 basis 를 다시 해석하지 않게 여기서 빚는다. repeat = 다시 맞을 때마다."""
    again = " · 다시 맞을 때마다" if repeat else ""
    if q.x is None:
        return ("산 물량의 " if q.of == "bought" else "남은 물량의 ") + "? (비율 저자 미명시)" + again
    if q.of == "held" and q.x == 1:
        return "남은 전량" + again
    if not isinstance(q.x, (int, float)):
        return ("산 물량의 " if q.of == "bought" else "남은 물량의 ") + "식으로 정한 비율" + again
    return ("산 물량의 " if q.of == "bought" else "남은 물량의 ") + "%d%%" % round(q.x * 100) + again


# 결과에 남기는 모름의 종류 → 문구(%d = 매수 결정 횟수). 판단 근거는 위 '얼마나' 절의 size_of.
SIZE_NOTES = (("weight_unset", "비중 저자 미명시 — 상품 예산 100%% 기준(%d회)"),
              ("weight_unknown", "비중 그날 값 모름 %d회 — 상품 예산 100%% 기준"),
              ("no_facts", "금액 사실 없음 %d회 — 배수 1"))


def size_of(a):
    """그날의 Amount(ProductJudge.amount) → (오늘 장부 Ledger(budget=비중), 모름 표시 집합).
    물량 계산은 to_units 하나 — 여기는 모름을 어떻게 채울지(정책, 위 '얼마나' 절)만 정한다:
    모름은 줄이지도 늘리지도 않고(상품 예산 100%) 표시 집합으로 센다."""
    if a is None:
        return Ledger(), {"no_facts"}
    flags = set()
    budget = to_units(Qty("cash", a.weight), Ledger()) if a.weight_set else None
    if budget is None:
        flags.add("weight_unknown" if a.weight_set else "weight_unset")
        budget = 1.0
    return Ledger(budget=budget), flags


def size_notes(counts):
    """체결 집계(backtest.trades._parity_stats)의 size_counts 횟수 → 결과에 보일 문구 목록(모름이 없으면 [])."""
    return [txt % counts[k] for k, txt in SIZE_NOTES if counts.get(k)]


# ================================================================ 상품 하나
class ProductJudge:
    """상품 하나의 판단자 — 생성 때 그 상품 규칙을 달력 전체로 한 번 계산해 둔다(tradeTool.RuleSeries).
    tree = 트리 출입구 · product = 상품 · prices = 시세 묶음(Judge 가 받은 것) · days = 판정 달력(생략 = 이 상품 봉 날짜)
    · asof = 관측 시각(UTC datetime, None 이면 지금) · answers = 사람이 답한 수동 {tradeTool.answer_key: 참/거짓}."""

    def __init__(self, tree, product, prices, days=None, asof=None, answers=None):
        self._tree, self.product = tree, product
        self._prices = prices
        self._bars = prices.get(self.product) or []
        self.days = [c.date for c in self._bars] if days is None else list(days)
        self._series = RuleSeries(tree, product, prices, self.days, asof, answers)

    # ------------------------------------------------------------ 상품·가격
    @property
    def index(self):
        return self._tree.index(self.product)

    @property
    def note(self):
        return self._tree.note(self.product)

    @property
    def has_data(self):
        return bool(self._bars)

    @property
    def warmup(self):
        return self._series.warmup

    def price(self, field):
        """이 상품의 날짜별 가격(open·high·low·close·volume) — 판정 달력(days) 길이, 없는 날은 None.
        체결가·수익률 계산(백테스트)·화면의 종가가 이걸 쓴다(시세 원본을 직접 열지 않는다)."""
        by = {c.date: getattr(c, field) for c in self._bars}
        return [by.get(d) for d in self.days]

    # ------------------------------------------------------------ 갈래 목록(Branch 값 — 라벨·소절·메모·조건·얼마나)
    def weight(self):
        """비중 갈래(산다 qty cash) — 없으면 qty.x None."""
        return self._tree.weight(self.product)

    def tranches(self):
        """분할 차수 갈래(산다 qty budget)."""
        return self._tree.tranches(self.product)

    def sells(self):
        """판다 갈래."""
        return self._tree.sells(self.product)

    # ------------------------------------------------------------ 등급·얼마나
    def grade(self, day):
        """그날의 등급 키 — 라이브·백테스트·재생이 같이 쓰는 단 하나의 등급 경로."""
        return self._series.grade_key(day)

    def incomplete(self, day):
        return self._series.incomplete(day)

    def manual_items(self, day=None):
        return self._series.manual_items(day)

    def amount(self, day):
        """그날의 Amount — 라이브 Decision 과 백테스트 매수 크기가 같이 쓰는 단 하나의 '얼마나' 경로."""
        w, alt = self._series.weight_of(day)
        return Amount(w, alt, self._series.weight[None] is not None)

    def latest(self):
        """(등급 키, 종가) — 달력 마지막 봉(라이브 '지금'). 시세가 없으면 ("unknown", None)."""
        if not self._bars:
            return "unknown", None
        return self.grade(len(self.days) - 1), self._bars[-1].close

    def gate_value(self, do, day, view=None):
        """등급 동사 하나의 그날 값 — view None = 수동 모름 · "opt" = 수동이 유리하게 · "pes" = 불리하게(검사·사례 채점용)."""
        if view is None:
            return series(self._tree.gate(self.product, do), self._series.ctx[None])[day]
        return (self._series.opt if view == "opt" else self._series.pes)[do][day]

    def weight_at(self, day):
        """그날 비중(%, 모르면 None)과 수동 때문에 모를 때 가능한 값들."""
        return self._series.weight_of(day)

    # ------------------------------------------------------------ 그날 판정
    def decide(self, day=None, holdings=()):
        """그날(기본 = 마지막 봉)의 Decision. holdings = [Holding] 이면 각 보유의 상태도 담는다."""
        if not self._bars:
            return Decision(self.product, "unknown", has_data=False)
        s = self._series
        day = len(self.days) - 1 if day is None else day
        close = self.price("close")
        return Decision(
            self.product, self.grade(day), day=day, date=self.days[day], close=close[day],
            prev_close=close[day - 1] if day >= 1 else None,
            incomplete=s.incomplete(day), confirmed=s._confirmed[day] + 1, warmup=s.warmup,
            top=s.top(day), manual=s.manual_items(day), amount=self.amount(day),
            opt={do: s.opt[do][day] for do in GATES}, pes={do: s.pes[do][day] for do in GATES},
            views={do: explain.view(self._tree.gate(self.product, do), s.ctx[None], day) for do in GATES},
            holdings=[self.status(h, day) for h in holdings])

    def static_views(self):
        """시세 없이 보이는 등급 조건 설명(값 없음) — 시세가 없는 상품의 체크리스트 구조."""
        return {do: explain.static_view(self._tree.gate(self.product, do), self.index) for do in GATES}

    def describe(self, branch):
        """갈래 하나(비중·분할·판다)의 값 없는 설명."""
        return explain.static_view(branch.when, self.index)

    def view(self, node, day):
        """조건 하나의 그날 설명(값·측정 증거) — 수동은 모름."""
        return explain.view(node, self._series.ctx[None], day)

    # ------------------------------------------------------------ 보유
    def _context(self, holding, manual_as=None):
        pos = ((holding.entry_day, holding.cost) if holding.book is None
               else (holding.entry_day, holding.cost, holding.book))
        return Ctx(self._prices, self.days, self.product, self.index, manual_as=manual_as, pos=pos)

    def conditions(self, holding, sells, tranches, manual_as=False):
        """이 보유 상태로 판다 갈래·분할 차수 조건의 날짜별 값 — 백테스트 체결 워크가 체결을 정하는 데 쓴다.
        manual 은 '매매가 안 나가는 쪽'(manual_as=False)이 기본. → ([판다마다 값 목록], [분할마다 값 목록|None])."""
        ctx = self._context(holding, manual_as)
        return ([series(r.when, ctx) for r in sells],
                [series(t.when, ctx) if t.when is not None else None for t in tranches])

    def status(self, holding, day=None):
        """보유 하나의 그날(기본 마지막) 판다·다음 분할 상태 — 수동은 모름(manual_as=None)."""
        if holding.entry_day is None:
            return HoldingStatus(error="첫 매수일 %s 이후 시세 없음" % holding.entry_date)
        day = len(self.days) - 1 if day is None else day
        ctx = self._context(holding)
        trs = self.tranches()
        nt = trs[holding.filled] if 0 < holding.filled < len(trs) else None
        return HoldingStatus(
            ret=series({"pos": "ret"}, ctx)[day], days=series({"pos": "days"}, ctx)[day],
            sells=[(r, series(r.when, ctx)[day], explain.view(r.when, ctx, day)) for r in self.sells()],
            next_tranche=None if nt is None else (nt, series(nt.when, ctx)[day], explain.view(nt.when, ctx, day)))

    # ------------------------------------------------------------ 검사기용(구간② — 조건 하나를 이 상품 시세로)
    def evaluate(self, node, manual_as=None, holding=None):
        """조건·값 식 하나의 날짜별 값(이 상품 문맥) — 트리 검사기가 a·b 비교·발화 통계·사례 채점에 쓴다."""
        ctx = self._context(holding, manual_as) if holding is not None else self._series.ctx[manual_as]
        return series(node, ctx)

    def explain(self, day):
        """등급 동사별 라벨 노드의 그날 값 {동사: [(label, ref, 값)]}(검사기 덤프용)."""
        return self._series.explain(day)

    def gate(self, do):
        """등급 동사 하나의 조건 묶음(펼친 식) — 검사기가 라벨 노드를 훑는 데 쓴다."""
        return self._tree.gate(self.product, do)


# ================================================================ 책 하나
class Judge:
    """책 하나의 판단자 — 트리 원본(TreeGateway)·시세 원본(tradeTool.history)을 쓰는 유일한 곳.
    Judge.open(slug) 으로 열고, prices() 로 시세를 받아(또는 여러 책 공유 조회를 넘겨받아) 판정을 낸다."""

    def __init__(self, slug, tree):
        self.slug, self._tree = slug, tree

    def __bool__(self):
        return bool(self._tree)

    # ------------------------------------------------------------ 열기
    @classmethod
    def open(cls, slug):
        """책의 최종 트리(books/<slug>/tree.json)를 열어 형식 검사까지. 없으면 None, 형식이 틀리면 CondError."""
        tree = TreeGateway.load(slug)
        return None if tree is None else cls(slug, tree)

    @classmethod
    def read(cls, slug, which=None):
        """책의 트리를 형식 검사 없이 연다 — which = None(최종) · "a"·"b"(추출자 후보). 없으면 빈 판단자(거짓)."""
        return cls(slug, TreeGateway.read(slug, which))

    @classmethod
    def of(cls, data, slug="합성"):
        """트리 dict(검사용 합성 트리)로 연다 — 형식 검사까지."""
        return cls(slug, TreeGateway.of(data))

    def validate(self):
        return self._tree.validate()

    # ------------------------------------------------------------ 시세
    def prices(self, extra_days=0):
        """이 책이 쓰는 시세(워밍업 포함, extra_days 만큼 더 과거까지)."""
        return history_back(self._tree, extra_days)

    @staticmethod
    def shared_prices(judges, extra_days=0):
        """여러 책이 같이 쓰는 시세를 한 번에(심볼 합집합 1회 조회) — 라이브 버스의 공유 시세."""
        judges = [j for j in judges if j]
        return history_back([j._tree for j in judges], extra_days) if judges else {}

    @staticmethod
    def missing(prices):
        """시세가 하나도 없는 심볼 목록."""
        return sorted(s for s, bars in prices.items() if not bars)

    @staticmethod
    def recent(prices, symbol, day, n):
        """심볼 하나의 day(YYYYMMDD) 이하 마지막 n봉 [[날짜, 시, 고, 저, 종, 거래량]] — 검사기 덤프(사람이 보는 근거)."""
        bars = [c for c in prices.get(symbol) or [] if c.date <= day][-n:]
        return [[c.date, c.open, c.high, c.low, c.close, c.volume] for c in bars]

    @staticmethod
    def until(prices, day):
        """시세를 날짜 day(YYYYMMDD) 이하로 자른 새 묶음 — 그날 마감 직후 라이브가 가졌을 시세(패리티 검사)."""
        return {s: [c for c in (bars or []) if c.date <= day] for s, bars in prices.items()}

    # ------------------------------------------------------------ 상품
    def products(self):
        return self._tree.products()

    def has(self, product):
        return self._tree.has(product)

    def product(self, product, prices, days=None, asof=None, answers=None):
        """상품 하나의 판단자."""
        if not self._tree.has(product):
            raise CondError("트리에 없는 상품 %r" % product)
        return ProductJudge(self._tree, product, prices, days, asof, answers)

    # ------------------------------------------------------------ 라이브 · 백테스트
    def positions(self):
        """내 포지션(books/<slug>/positions.json — 커밋 안 하는 개인 파일) → {상품: [포지션]}."""
        p = positions_json(self.slug)
        if not os.path.exists(p):
            return {}
        out = {}
        for x in (json.load(open(p, encoding="utf-8")).get("positions") or []):
            out.setdefault(x["prod"], []).append(x)
        return out

    def decisions(self, prices, asof=None, answers=None):
        """라이브 판정 — 상품마다 마지막 봉 Decision(내 포지션 상태 포함).
        → [(상품, Decision, ProductJudge, [내 포지션])] — 화면은 ProductJudge 에 규칙 설명을 묻는다."""
        my_positions = self.positions()
        out = []
        for p in self.products():
            pj = self.product(p, prices, asof=asof, answers=answers)
            mine = my_positions.get(p, [])
            holdings = [Holding.at(pj.days, str(x["entry_date"]), float(x["entry_px"]), int(x.get("filled", 1))) for x in mine]
            out.append((p, pj.decide(holdings=holdings), pj, mine))
        return out

    def signals(self, prices, start=None):
        """백테스트 신호 — 상품마다 전 날짜 등급(라이브 latest() 와 같은 grade 경로). start(YYYYMMDD)를 주면 그 이상 날만.
        → {product: (ProductJudge, [{date, key, grade, close, incomplete}])}."""
        out = {}
        for p in self.products():
            pj = self.product(p, prices)
            close = pj.price("close")
            pts = []
            for i, d in enumerate(pj.days):
                if start is not None and d < start:
                    continue
                k = pj.grade(i)                    # 워밍업 부족이면 ❔(불완전)로 — incomplete 로 함께 표시
                pts.append({"date": d, "key": k, "grade": GRADES[k], "close": close[i], "incomplete": pj.incomplete(i)})
            out[p] = (pj, pts)
        return out

    # ------------------------------------------------------------ 트리 질문(구간② 비교·채점·원시 트리 보기 — 시세 없이 트리만)
    @property
    def tree(self):
        """트리 출입구(TreeGateway) — 비교 도구·채점기·원시 트리 보기가 규칙·식을 직접 묻는 단 하나의 문. 판정은 여기로 안 낸다."""
        return self._tree
