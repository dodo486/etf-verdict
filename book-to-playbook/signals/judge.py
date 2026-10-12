#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""판단자(구간③) — 트리 원본과 시세 원본을 쓰는 유일한 곳. 책의 내용대로 판단하는 일은 여기 한 곳에서만 한다.

  · Judge         책 하나의 판단자 — 트리를 열고(TreeGateway 는 여기서만), 시세를 받고(Grade.history 는 여기서만),
                  상품마다 ProductJudge 를 세운다. 라이브 판정(decisions)·백테스트 신호(signals)·원문 소절별 반영
                  현황(coverage)·트리 검사기의 질문(labels·body·why…)을 낸다.
  · ProductJudge  상품 하나의 판단자 — 그 상품 규칙(ProductRules)과 시세만 안다(책의 다른 상품·트리 파일은 모른다).
                  등급(grade·latest)·그날 판정(decide → Decision)·조건 설명(views)·보유분 상태(status)·체결 워크가
                  쓸 보유 조건 값(conditions)·가격(price — 체결가·수익률 계산용).
  · Holding       보유 하나의 상태(첫 매수 봉·평단·산 차수·체결 장부) — 값만. 평가는 ProductJudge 가 한다.
  · Decision · Amount · HoldingStatus   판정 사실을 담는 그릇(계산하지 않는다).

다른 층(체결·화면·라이브 버스·검사)은 트리·시세 원본을 만지지 않고 여기에 묻는다 — 받은 값(판정·가격·조건 값·
규칙 설명)만 쓴다. 시세 묶음(prices)은 다른 층에선 열어 보지 않는 봉투다(받아서 다시 넘기기만). entry.verify_rules 가 강제한다.
"""
import json
import os
from dataclasses import dataclass, field

from shared.paths import positions_json
from dsl.tradeTool import Cond, Grade
from dsl.tree_gateway import TreeGateway
from signals import explain


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
        return Grade.GRADES[self.key]


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


# ================================================================ 상품 하나
class ProductJudge:
    """상품 하나의 판단자 — 생성 때 그 상품 규칙을 달력 전체로 한 번 계산해 둔다(Grade.RuleSeries).
    rules = ProductRules(TreeGateway.product) · prices = 시세 묶음(Judge 가 받은 것) · days = 판정 달력(생략 = 이 상품 봉 날짜)
    · asof = 관측 시각(UTC datetime, None 이면 지금) · answers = 사람이 답한 수동 {Cond.answer_key: 참/거짓}."""

    def __init__(self, rules, prices, days=None, asof=None, answers=None):
        self._rules, self.product = rules, rules.product
        self._prices = prices
        self._bars = prices.get(self.product) or []
        self.days = [c.date for c in self._bars] if days is None else list(days)
        self._series = Grade.RuleSeries(rules, prices, self.days, asof, answers)

    # ------------------------------------------------------------ 상품·가격
    @property
    def note(self):
        return self._rules.note

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
        return self._rules.weight()

    def tranches(self):
        """분할 차수 갈래(산다 qty budget)."""
        return self._rules.tranches()

    def sells(self):
        """판다 갈래."""
        return self._rules.sells()

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
            return Cond.series(self._rules.gate(do), self._series.ctx[None])[day]
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
            opt={do: s.opt[do][day] for do in Cond.GATES}, pes={do: s.pes[do][day] for do in Cond.GATES},
            views={do: explain.view(self._rules.gate(do), s.ctx[None], day) for do in Cond.GATES},
            holdings=[self.status(h, day) for h in holdings])

    def static_views(self):
        """시세 없이 보이는 등급 조건 설명(값 없음) — 시세가 없는 상품의 체크리스트 구조."""
        return {do: explain.static_view(self._rules.gate(do)) for do in Cond.GATES}

    def describe(self, branch):
        """갈래 하나(비중·분할·판다)의 값 없는 설명."""
        return explain.static_view(branch.when)

    def view(self, node, day):
        """조건 하나의 그날 설명(값·측정 증거) — 수동은 모름."""
        return explain.view(node, self._series.ctx[None], day)

    # ------------------------------------------------------------ 보유
    def _context(self, holding, manual_as=None):
        pos = ((holding.entry_day, holding.cost) if holding.book is None
               else (holding.entry_day, holding.cost, holding.book))
        return Cond.Ctx(self._prices, self.days, self.product, manual_as=manual_as, pos=pos)

    def conditions(self, holding, sells, tranches, manual_as=False):
        """이 보유 상태로 판다 갈래·분할 차수 조건의 날짜별 값 — 백테스트 체결 워크가 체결을 정하는 데 쓴다.
        manual 은 '매매가 안 나가는 쪽'(manual_as=False)이 기본. → ([판다마다 값 목록], [분할마다 값 목록|None])."""
        ctx = self._context(holding, manual_as)
        return ([Cond.series(r.when, ctx) for r in sells],
                [Cond.series(t.when, ctx) if t.when is not None else None for t in tranches])

    def status(self, holding, day=None):
        """보유 하나의 그날(기본 마지막) 판다·다음 분할 상태 — 수동은 모름(manual_as=None)."""
        if holding.entry_day is None:
            return HoldingStatus(error="첫 매수일 %s 이후 시세 없음" % holding.entry_date)
        day = len(self.days) - 1 if day is None else day
        ctx = self._context(holding)
        trs = self.tranches()
        nt = trs[holding.filled] if 0 < holding.filled < len(trs) else None
        return HoldingStatus(
            ret=Cond.series({"pos": "ret"}, ctx)[day], days=Cond.series({"pos": "days"}, ctx)[day],
            sells=[(r, Cond.series(r.when, ctx)[day], explain.view(r.when, ctx, day)) for r in self.sells()],
            next_tranche=None if nt is None else (nt, Cond.series(nt.when, ctx)[day], explain.view(nt.when, ctx, day)))

    # ------------------------------------------------------------ 검사기용(구간② — 조건 하나를 이 상품 시세로)
    def evaluate(self, node, manual_as=None, holding=None):
        """조건·값 식 하나의 날짜별 값(이 상품 문맥) — 트리 검사기가 a·b 비교·발화 통계·사례 채점에 쓴다."""
        ctx = self._context(holding, manual_as) if holding is not None else self._series.ctx[manual_as]
        return Cond.series(node, ctx)

    def explain(self, day):
        """등급 동사별 라벨 노드의 그날 값 {동사: [(label, ref, 값)]}(검사기 덤프용)."""
        return self._series.explain(day)

    def gate(self, do):
        """등급 동사 하나의 조건 묶음(펼친 식) — 검사기가 라벨 노드를 훑는 데 쓴다."""
        return self._rules.gate(do)


# ================================================================ 책 하나
class Judge:
    """책 하나의 판단자 — 트리 원본(TreeGateway)·시세 원본(Grade.history)을 쓰는 유일한 곳.
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
        return Grade.history_back(self._tree, extra_days)

    @staticmethod
    def shared_prices(judges, extra_days=0):
        """여러 책이 같이 쓰는 시세를 한 번에(심볼 합집합 1회 조회) — 라이브 버스의 공유 시세."""
        judges = [j for j in judges if j]
        return Grade.history_back([j._tree for j in judges], extra_days) if judges else Grade.History({})

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
        """시세를 날짜 day(YYYYMMDD) 이하로 자른 새 묶음(분봉은 그대로) — 그날 마감 직후 라이브가 가졌을 시세(패리티 검사)."""
        t = Grade.History({s: [c for c in (bars or []) if c.date <= day] for s, bars in prices.items()})
        t.minutes = getattr(prices, "minutes", {})
        return t

    # ------------------------------------------------------------ 상품
    def products(self):
        return self._tree.products()

    def has(self, product):
        return self._tree.has(product)

    def product(self, product, prices, days=None, asof=None, answers=None):
        """상품 하나의 판단자."""
        return ProductJudge(self._tree.product(product), prices, days, asof, answers)

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
                pts.append({"date": d, "key": k, "grade": Grade.GRADES[k], "close": close[i], "incomplete": pj.incomplete(i)})
            out[p] = (pj, pts)
        return out

    # ------------------------------------------------------------ 원문 소절별 반영 현황(플레이북 배지)
    def coverage(self):
        """{소절: {auto, manual, verbs[], prods[], skipped?[{rule, reason}]}} — 트리에 ref 로 달린 라벨 노드·규칙을 센다."""
        out = {}

        def add(ref, do, prod, manual):
            if not ref:
                return
            r = out.setdefault(ref, {"auto": 0, "manual": 0, "verbs": [], "prods": []})
            r["manual" if manual else "auto"] += 1
            if do not in r["verbs"]:
                r["verbs"].append(do)
            if prod not in r["prods"]:
                r["prods"].append(prod)

        for p in self.products():
            rules = self._tree.product(p)
            for do, label, ref, node in rules.expressions():
                if label:
                    add(ref, do, p, bool(Cond.manual_leaves(node)))
                for n in Cond.labeled(node):
                    add(n.get("ref"), do, p, bool(Cond.manual_leaves(n)))
            for t in rules.tranches():
                if t.when is None:
                    add(t.ref, Cond.BUY, p, False)
            w = rules.weight()
            if w.qty.x is None and w.ref:
                add(w.ref, Cond.BUY, p, False)
        for u in self._tree.skips():
            if u.get("ref"):
                r = out.setdefault(u["ref"], {"auto": 0, "manual": 0, "verbs": [], "prods": []})
                r.setdefault("skipped", []).append({"rule": u.get("rule"), "reason": u.get("reason")})
        return out

    # ------------------------------------------------------------ 트리 검사기의 질문(구간② — 시세 없이 트리만)
    def gate(self, product, do):
        return self._tree.gate(product, do)

    def weight(self, product):
        return self._tree.weight(product)

    def tranches(self, product):
        return self._tree.tranches(product)

    def sells(self, product):
        return self._tree.sells(product)

    def expressions(self, product):
        return self._tree.expressions(product)

    def symbols(self, products=None):
        return self._tree.symbols(products)

    def refs(self):
        return self._tree.refs()

    def skips(self):
        return self._tree.skips()

    def labels(self):
        return self._tree.labels()

    def body(self, label, expand=True):
        return self._tree.body(label, expand)

    def value(self, label, expand=True):
        return self._tree.value(label, expand)

    def why(self, label):
        return self._tree.why(label)

    def conditions(self):
        return self._tree.conditions()

    def cards(self):
        """규칙 카드(적힌 그대로) — 원시 트리 보기(화면)용."""
        return self._tree.cards()
