#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""판단자(구간③) — 트리 원본과 시세 원본을 쓰는 유일한 곳. 책의 내용대로 판단하는 일은 여기 한 곳에서만 한다.

  · Judge         책 하나의 판단자 — 트리를 열고(TreeGateway 는 여기서만), 시세를 받고(history 는 여기서만 — 아래 '시세 받기' 절),
                  상품마다 ProductJudge 를 세운다. 라이브 판정(decisions)·백테스트 신호(signals)를 낸다.
  · ProductJudge  상품 하나의 판단자 — 트리에서 그 상품의 규칙만 골라 시세와 평가한다.
                  등급(grade·latest)·그날 판정(decide → Decision)·노드 하나의 그날 값(value·blank_value — 화면 설명
                  web/explain 의 값 함수)·보유분 상태(status)·체결 워크가 쓸 보유 조건 값(conditions)·가격(price — 체결가·수익률 계산용).
  · Holding       보유 하나의 상태(첫 매수 봉·평단·산 차수·체결 장부) — 값만. 평가는 ProductJudge 가 한다.
  · Decision · Amount · HoldingStatus   판정 사실을 담는 그릇(계산하지 않는다).
  · 시세 받기     history · history_back — 시세 원본을 받는 유일한 곳(market 은 트리를 모른다). 일봉 확정 경계는 market/store
                  (session_closes — Store.confirmed 와 같은 규칙)를 받아 계산기 Ctx 에 넘긴다
  · 등급         RuleSeries(날짜별 등급·금액·비중·워밍업 가드) · GRADES · GRADE_RULES(grade_rules.json 사다리)
                 — 식 계산은 계산기 judge/eval(Ctx·series), 문법은 tree/gateway
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
from datetime import datetime, timedelta

from market import md_feed
from market.store import session_closes
from shared.paths import positions_json
from tree.gateway import (
    Branch, BUY_SIDE, CondError, GATES, labeled, manual_leaves, manual_text, Qty, SELL, TreeGateway, WARMUP_DAYS)
from judge.eval import Ctx, series


# ================================================================ 시세 받기 — 판단자만(market 은 트리를 모른다)
def history(trees, start):
    """트리(들 — TreeGateway)가 쓰는 모든 심볼의 일봉 {심볼: 일봉} — 수집 단계(md_feed) 하나로 받는다.
    jhts 는 md_feed 에서만 만진다(팀 경계). 일봉 아닌 봉(tf 1m·5m)은 받지 않는다 — 그 조건은 모름(None)."""
    syms = set()
    for t in trees if isinstance(trees, list) else [trees]:
        syms |= t.symbols()
    return md_feed.histories(syms, start)


def since(extra_days=0):
    """시세를 받기 시작할 날(YYYYMMDD) — 지금부터 extra_days + 워밍업(WARMUP_DAYS)일 과거. 수집 시작일을 세는 한 곳
    (배치 history_back · 라이브 저장소 등록 store.need 가 같이 쓴다 — 각자 날짜 계산을 복붙하지 않는다)."""
    return (datetime.now() - timedelta(days=extra_days + WARMUP_DAYS)).strftime("%Y%m%d")


def history_back(trees, extra_days=0):
    """history 를 since(extra_days) 부터 받는다 — 백테스트(days)·재생(0)·검사(365*년 등)가 다 이걸로 부른다."""
    return history(trees, since(extra_days))


# ================================================================ 등급 — 등급의 뜻(트리 → 날짜별 등급·금액·비중)
# 트리의 '뜻'을 날짜별 등급으로 내는 곳은 여기 한 벌뿐이다.
#   등급 (동사 둘 — 사다리는 grade_rules.json):
#     안 산다 갈래 하나라도 참 → ⛔ 안 산다 · 산다 갈래 하나라도 참 → ✅ 산다 · 둘 다 아님 → ⚪ 관망
#   수동(manual) 조건은 '확인됨/안 됨' 두 번 평가한다:
#     안 돼도 산다(비관) → ✅ · 확인돼야 산다(낙관만) → 🟡 확인 대기 · 데이터 부족으로 못 정함 → ❔ 판정 불가
#     비관 = 산다의 수동은 거짓, 안 산다의 수동은 참 / 낙관 = 그 반대(BUY_SIDE).
#   얼마나·판다:
#     weight   산다 qty cash = 총 투자금 대비 비중(%) · tranches = 산다 qty budget 분할(2차 이후는 포지션 값으로)
#     sells    판다 — 보유분이 있을 때만 평가(구간③ trading)
#
#   판정은 봉이 끝난 직후(그날까지의 봉)로 낸다 — cond 연산이 전부 인과적이라 전체 이력을 한 번 계산해
#   날짜로 꺼내도 미래를 보지 않는다(judge.verify_eval 이 강제).
#
#   트리는 원본 dict 가 아니라 TreeGateway(tree/gateway.py — 트리를 읽는 유일한 출입구)로 받는다.
#   같은 뜻을 만드는 쪽(authoring.extract.verify_tree 의 사례·authoring.extract.compare 의 a/b 비교)과 읽는 쪽(구간③ 판정·백테스트)이 함께 쓴다 — 화면용 설명(view·
#   측정 증거)은 화면(web/explain)이 판단자가 낸 노드 값(ProductJudge.value)으로 빚는다 — 화면은 계산하지 않는다.
GRADES = {
    "buy": "✅ 산다",
    "confirm": "🟡 확인 대기",
    "avoid": "⛔ 안 산다",
    "wait": "⚪ 관망",
    "unknown": "❔ 판정 불가",
}
# 등급 판정 사다리의 '뜻'은 코드가 아니라 데이터(judge/grade_rules.json)에 있다 — 규칙을 바꾸면
# 거기 한 곳만 고친다. 등급을 내는 곳은 grade_key 하나 — 화면은 판정 JSON 의 key 를 그대로 그린다(서버 권위:
# 사람이 답한 수동도 서버가 Ctx answers 로 풀어 등급을 다시 낸다).
GRADE_RULES = json.load(
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "grade_rules.json"), encoding="utf-8"))


_VALUES = (None, {})   # (시세 묶음, {(달력, asof): {nid: 시계열}}) — 가장 최근 시세 묶음 하나의 공유 값 기억


def shared_values(prices, days, asof):
    """같은 시세 묶음(객체 그대로)·달력·asof 의 문맥들이 같이 쓰는 값 기억 {nid: 시계열} — 수동·pos 없는 노드(Node.pure)의
    값은 이 셋으로만 정해지므로 상품·책·수동 가정이 달라도 한 번만 계산한다(eval.series 가 pure 노드만 넣고 꺼낸다).
    새 시세 묶음이 오면 통째로 새로 시작한다(지난 틱 값이 남지 않게 — 묶음 객체를 쥐고 있어 id 재사용도 없다)."""
    global _VALUES
    cur = _VALUES
    if cur[0] is not prices:
        cur = _VALUES = (prices, {})
    return cur[1].setdefault((tuple(days), asof), {})


class RuleSeries:
    """한 상품의 등급 동사(안 산다·산다)·비중을 전체 달력에 대해 한 번 계산해 둔다."""

    def __init__(self, tree, product, prices, days, asof=None, answers=None):
        """tree = 트리 출입구(TreeGateway) · product = 판정할 상품 — 그 상품의 판때기(tree.board)를 평가한다. asof = 관측 시각(UTC datetime) — 일봉은 asof 이하
        확정(settled) 봉만 본다(미확정 그날 일봉은 None). None 이면 실제 지금(일봉은 마지막 확정봉).
        answers = 사람이 답한 수동 {answer_key: 참/거짓} — 등급·금액·비중이 그 답으로 풀린다(서버 권위).
        None 이면 옛 동작 그대로."""
        self.tree, self.product, self.days, self.prices = tree, product, list(days), prices
        self.board = board = tree.board(product)
        self.index = board.index
        sc = session_closes(board.symbols, self.days, asof)
        shared, scope = shared_values(prices, self.days, asof), (None if asof is None else board.symbols)
        mk = lambda m: Ctx(prices, days, product, self.index, manual_as=m, asof=asof, session_close=sc, answers=answers,
                           shared=shared, scope=scope)
        self.ctx = {True: mk(True), False: mk(False), None: mk(None)}
        s = lambda node, m: series(node, self.ctx[m])
        self.opt = {do: s(board.gates[do], BUY_SIDE[do]) for do in GATES}
        self.pes = {do: s(board.gates[do], not BUY_SIDE[do]) for do in GATES}
        w = board.weight                              # 비중 식(Qty "cash") — None = 저자 미명시
        self.weight = {m: (s(w, m) if w is not None else None) for m in (None, True, False)}
        # 데이터 완전성 가드 — 이 상품 등급이 실제로 쓰는 가장 긴 워밍업(트리에서 파생, 하드코딩 아님).
        #   그보다 '확정 봉'이 적은 초기 구간의 1d 신호는 창이 덜 차 조용히 None/틀릴 수 있어 신뢰불가다
        #   → grade_key 가 '불완전 데이터(❔ 보류)'로 표시한다(✅/🚫 확신 금지). WARMUP_DAYS(fetch 버퍼)와 무관.
        self.warmup = board.warmup
        # 심볼 확정봉 지도 — asof 장중이면 오늘 미확정 봉을 뺀 '마지막 확정 index'(없으면 전부 확정 = 항등).
        #   여러 심볼을 보면 가장 적게 확정된 심볼(지연된 feed)이 기준이다 — 하나라도 모자라면 불완전.
        self._confirmed = self._confirmed_index_map()

    def _confirmed_index_map(self):
        """날짜별 '이 상품 등급이 쓰는 모든 심볼이 확정한 봉 수 − 1'(= 확정 index). 어떤 심볼이 그 index 를
        아직 확정 못 했으면(지연된 feed·asof 장중 미확정) 그 심볼 기준으로 낮춘다. 확정봉이 하나도 없으면 -1.
        캘린더가 없거나 asof 가 없으면(라이브 지금) settled_map 이 no-op(None) → 날짜 index 그대로(항등)."""
        ctx = self.ctx[None]
        syms = sorted(self.board.symbols)
        maps = [ctx.settled_map(s) for s in syms]
        out = []
        for day in range(len(self.days)):
            idxs = []
            for m in maps:
                idxs.append(day if m is None else m[day])   # None map = 가리지 않음(항등)
            out.append(-1 if any(x is None for x in idxs) else min(idxs))
        return out

    def incomplete(self, day):
        """그날(day) 1d 등급이 '불완전 데이터'인가 — 확정 봉이 필요 워밍업보다 적으면 True.
        확정 index(가장 늦은 심볼 기준)가 warmup 미만이면 가장 긴 창이 덜 차 신호가 신뢰불가다."""
        return self._confirmed[day] < self.warmup

    # ---------------------------------------------------------------- 등급
    def grade_key(self, day):
        # 데이터 완전성 가드 — 워밍업이 모자란 봉은 확신 판정을 내지 않고 '판정 불가(불완전 데이터)'로 둔다.
        #   (조용히 None 이 섞인 opt/pes 로 ✅/🚫 를 내면 모르고 매매하게 된다 — 정직성 원칙.)
        if self.incomplete(day):
            return "unknown"
        # grade_rules.json 을 위에서 아래로 본다 — when 의 모든 동사가 맞는 첫 규칙이 이긴다.
        # 값은 3값(True/False/None) — 'is' 로 정확히 맞춘다(None 은 True·False 어디에도 안 맞는다).
        views = {"opt": self.opt, "pes": self.pes}
        for rule in GRADE_RULES["rules"]:
            view = views[rule["view"]]
            if all(view[do][day] is want for do, want in rule["when"].items()):
                return rule["key"]
        return GRADE_RULES["default"]

    # ---------------------------------------------------------------- 비중
    def weight_of(self, day):
        """그날 비중(%) — 수동 때문에 모르면 (None, [가능한 값들]) 로 범위를 함께 돌려준다."""
        if self.weight[None] is None:
            return None, None
        v = self.weight[None][day]
        if v is not None:
            return v, None
        alt = sorted({x for x in (self.weight[True][day], self.weight[False][day]) if x is not None})
        return None, alt or None

    # ---------------------------------------------------------------- 설명
    def explain(self, day):
        """라벨 달린 노드의 그날 값 — 수동은 '모름'(None)으로 둔 평가. {동사: [(label, ref, 값)]}"""
        return {do: [(n.get("label"), n.get("ref"), series(n, self.ctx[None])[day])
                     for n in labeled(self.tree.gate(self.product, do))] for do in GATES}

    def top(self, day):
        """동사마다 맨 위 라벨 노드들의 그날 값(사유 문장용 — 안쪽 노드까지 늘어놓으면
        not 아래의 '거짓 = 정상' 노드가 '미충족'으로 읽힌다). 수동은 모름(None)."""
        return {do: [(n.get("label"), n.get("ref"), series(n, self.ctx[None])[day])
                     for n in _top_labeled(self.tree.gate(self.product, do))] for do in GATES}

    def manual_items(self, day=None):
        """사람 확인이 필요한 조건 [(동사, 라벨, ref)] — 판다(보유분)는 뺀다."""
        return [(z, n.get("label") or manual_text(n), n.get("ref"))
                for z, _l, _r, node in self.tree.expressions(self.product) if z != SELL for n in manual_leaves(node)]


def _top_labeled(node):
    """라벨 달린 가장 바깥 노드들. all/any/atleast 는 펼치고, not 아래는 들어가지 않는다."""
    if not isinstance(node, dict):
        return []
    if node.get("label"):
        return [node]
    kids = node.get("all") or node.get("any") or (node.get("of") if "atleast" in node else None) or []
    out = []
    for k in kids:
        out.extend(_top_labeled(k))
    return out


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
    """보유 하나의 그날 상태 — sells = [(Branch, 값)] 판다 갈래, next_tranche = (Branch, 값)|None. 시세가 없으면 error.
    holding = 그 보유(Holding) — 화면이 갈래 설명의 값을 ProductJudge.value(노드, 날, holding)로 묻는다."""
    error: str = None
    ret: float = None
    days: float = None
    sells: list = field(default_factory=list)
    next_tranche: tuple = None
    holding: object = None


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
    """상품 하나의 판단자 — 생성 때 그 상품 규칙을 달력 전체로 한 번 계산해 둔다(RuleSeries).
    tree = 트리 출입구 · product = 상품 · prices = 시세 묶음(Judge 가 받은 것) · days = 판정 달력(생략 = 이 상품 봉 날짜)
    · asof = 관측 시각(UTC datetime, None 이면 지금) · answers = 사람이 답한 수동 {tree.gateway.answer_key: 참/거짓}."""

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
            return series(self._series.board.gates[do], self._series.ctx[None])[day]
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
            holdings=[self.status(h, day) for h in holdings])

    def value(self, node, day, holding=None):
        """트리에서 온 노드 하나의 그날 값(이 상품 문맥 — 수동은 모름, 사람이 답했으면 그 답) · holding = 보유(판다·분할 갈래의
        pos 값). 화면 설명(web/explain)의 값 함수 — 화면은 계산하지 않고 이것만 묻는다."""
        return self.evaluate(node, holding=holding)[day]

    def blank_value(self, node):
        """시세·포지션 없이(빈 문맥 하루) 노드 하나의 값 — 값 없는 규칙 설명(web/explain.static_view)의 값 함수."""
        return series(node, Ctx({}, ["0"], "$none", self.index, manual_as=None, pos=(0, 1.0)))[0]

    # ------------------------------------------------------------ 보유
    def _context(self, holding, manual_as=None):
        pos = ((holding.entry_day, holding.cost) if holding.book is None
               else (holding.entry_day, holding.cost, holding.book))
        return Ctx(self._prices, self.days, self.product, self.index, manual_as=manual_as, pos=pos,
                   shared=shared_values(self._prices, self.days, None))

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
            holding=holding, ret=series({"pos": "ret"}, ctx)[day], days=series({"pos": "days"}, ctx)[day],
            sells=[(r, series(r.when, ctx)[day]) for r in self.sells()],
            next_tranche=None if nt is None else (nt, series(nt.when, ctx)[day]))

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
_OPENED = {}   # (판단자 클래스, slug) → ((트리 경로, 수정 시각 ns, 크기), Judge) — Judge.open 의 컴파일 캐시


class Judge:
    """책 하나의 판단자 — 트리 원본(TreeGateway)·시세 원본(history)을 쓰는 유일한 곳.
    Judge.open(slug) 으로 열고, prices() 로 시세를 받아(또는 여러 책 공유 조회를 넘겨받아) 판정을 낸다."""

    def __init__(self, slug, tree):
        self.slug, self._tree = slug, tree

    def __bool__(self):
        return bool(self._tree)

    # ------------------------------------------------------------ 열기
    @classmethod
    def open(cls, slug):
        """책의 최종 트리(books/<slug>/tree.json)를 열어 형식 검사까지. 없으면 None, 형식이 틀리면 CondError.
        한 번 연 책은 트리 파일(경로·수정 시각·크기)이 그대로면 같은 판단자를 돌려준다 — 컴파일(판때기)은 트리가 바뀐
        책만 다시(라이브가 틱마다 불러도 다시 읽지 않는다)."""
        path = TreeGateway.path(slug)
        try:
            st = os.stat(path)
        except OSError:
            _OPENED.pop((cls, slug), None)
            return None
        stamp = (path, st.st_mtime_ns, st.st_size)
        hit = _OPENED.get((cls, slug))
        if hit is not None and hit[0] == stamp:
            return hit[1]
        tree = TreeGateway.load(slug)
        if tree is None:
            return None
        judge = cls(slug, tree)
        _OPENED[(cls, slug)] = (stamp, judge)
        return judge

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
        """여러 책이 같이 쓰는 시세를 한 번에(심볼 합집합 1회 조회) — 배치용(심판 비교 등). 라이브는 시세 칸(market/store)을 쓴다."""
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

    def subscriptions(self):
        """구독표의 재료 — {상품: 그 상품 판정이 읽는 심볼들}(판때기 필요 심볼 + 상품 자신 — 판정 달력이 상품 봉이라).
        라이브는 이 심볼 중 하나라도 바뀐 상품만 다시 판정한다(entry/live)."""
        return {p: self._tree.board(p).symbols | {p} for p in self.products()}

    def decisions(self, prices, asof=None, answers=None, products=None):
        """라이브 판정 — 상품마다 마지막 봉 Decision(내 포지션 상태 포함). products = 판정할 상품만(생략 = 전부, 순서는 트리 순).
        → [(상품, Decision, ProductJudge, [내 포지션])] — 화면은 ProductJudge 에 규칙 설명을 묻는다."""
        my_positions = self.positions()
        out = []
        for p in self.products():
            if products is not None and p not in products:
                continue
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
