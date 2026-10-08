#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""등급의 뜻(구간② DSL) — 조건 트리(books/<slug>/tree.json) → 날짜별 등급·금액·비중 (책 무관). 트리의 '뜻'은 여기 한 벌뿐이다.

등급 (COND_DSL.md 1절, 조건 칸 셋):
  filter 거짓 → 🚫 진입 금지 · avoid 참 → ⛔ 보류 · entry 참 → ✅ 매수 후보 · entry 거짓 → ⚪ 관망
수동(manual) 조건은 '확인됨/안 됨' 두 번 평가한다:
  안 돼도 매수(비관) → ✅ · 확인돼야 매수(낙관만) → 🟡 확인 대기 · 데이터 부족으로 못 정함 → ❔ 판정 불가
  비관 = filter·entry 의 수동은 거짓, avoid 의 수동은 참 / 낙관 = 그 반대.
규칙 칸 셋:
  caution  걸린 규칙마다 그날 금액 × scale (null = 줄일 폭 저자 미명시)
  sizing   weight = 총 투자금 대비 비중(%) · tranches = 분할 매수(2차 이후는 포지션 값으로)
  exit     보유분의 매도 — 보유가 있을 때만 평가(구간③ trading)

판정은 봉이 끝난 직후(그날까지의 봉)로 낸다 — cond 연산이 전부 인과적이라 전체 이력을 한 번 계산해
날짜로 꺼내도 미래를 보지 않는다(verify_primitives 가 강제).

트리는 원본 dict 가 아니라 TreeGateway(checklist/tree_gateway.py — 트리를 읽는 유일한 출입구)로 받는다.
같은 뜻을 만드는 쪽(verify_tree 의 사례·a/b 비교)과 읽는 쪽(구간③ 판정·백테스트)이 함께 쓴다 — 화면용 설명(view·
측정 증거·사유 문장)은 웹 화면층(web/condition_view.py)이 이 평가 문맥을 받아 빚는다.
"""
import json
import os

from checklist import cond
from shared import md_feed

GRADES = {
    "buy": "✅ 매수 후보",
    "confirm": "🟡 확인 대기",
    "nofilter": "🚫 진입 금지",
    "avoid": "⛔ 보류",
    "wait": "⚪ 관망",
    "unknown": "❔ 판정 불가",
}
# 등급 판정 사다리의 '뜻'은 코드가 아니라 데이터(checklist/grade_rules.json)에 있다 — 규칙을 바꾸면
# 거기 한 곳만 고친다. 파이썬(grade_key)과 화면(checklist-ui.gradeKey)이 같은 표를 읽는다.
# 판정 JSON 에도 실어보내(web/verdict_view) 화면이 복붙 없이 받아 쓴다.
GRADE_RULES = json.load(
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "grade_rules.json"), encoding="utf-8"))
# 판정 전에 과거 시세를 며칠치(달력일) 미리 당겨올지 — '워밍업'. 트리가 쓰는 가장 긴 창
# (예: 52주 신고가 = 252거래일 ≈ 달력 365일)이 첫날부터 제대로 서도록 넉넉히 둔다.
# ★ 여기 한 곳이 정본이다 — 매일 판정(web/verdict_view)·백테스트(trading/backtest)·검증(verify_tree)이
#   모두 이 값을 가져다 쓴다. 과거엔 세 곳에 따로(500/400/500) 박혀 백테스트만 어긋났었다.
WARMUP_DAYS = 500


class History(dict):
    """{심볼: 일봉} + minutes{심볼: 분봉}. 장중(tf="1m") 값은 asof 축에서 분봉을 잘라 읽는다(cond.minute_series)."""
    minutes = {}


def history(trees, start):
    """트리(들 — TreeGateway)가 쓰는 모든 심볼의 일봉(+ 장중(tf="1m") 값에 쓰는 심볼의 분봉) — 수집 단계(md_feed)
    하나로 받는다. jhts 는 md_feed 에서만 만진다(팀 경계). 분봉이 연결되기 전에는 minutes 가 비어 있고
    장중 observe 조건은 None→manual 로 떨어진다(의도된 동작)."""
    syms, msyms = set(), set()
    for t in trees if isinstance(trees, list) else [trees]:
        syms |= t.symbols()
        msyms |= t.minute_symbols()
    h = History(md_feed.histories(syms, start))
    h.minutes = {s: md_feed.minutes(s) for s in sorted(msyms)}
    return h


def session_closes(symbols, cal, asof):
    """일봉 확정(settled) 경계 — {심볼: {YYYYMMDD: 그날 정규장 마감(UTC datetime)}}. cond.Ctx 가 장중 asof 에서
    '마감이 asof 이후'인 일봉(아직 미확정)을 가리는 데 쓴다. 경계는 하드코딩이 아니라 거래소 캘린더
    (md_feed.sessions)에서 읽는다. asof 가 없으면(라이브 '지금' = 늘 마지막 확정봉) 가릴 것이 없으므로 빈 dict.
    캘린더가 비면(jhts 미설치·조회 실패) 해당 심볼은 빠진다 → cond 가 '가리지 않음'으로 떨어진다(캘린더 없다고
    일봉을 조용히 전부 지우지 않게). 시장(US/KR)이 같은 심볼은 캘린더를 한 번만 조회해 공유한다."""
    import datetime as _dt
    if asof is None or not cal:
        return {}
    start, end = min(cal), max(cal)
    by_market = {}      # market → {YYYYMMDD: 마감 UTC}
    out = {}
    for sym in sorted(set(symbols)):
        mkt = md_feed.market_of(sym)
        if mkt is None:
            continue
        if mkt not in by_market:
            by_market[mkt] = {s.date: s.close.astimezone(_dt.timezone.utc)
                              for s in md_feed.sessions(mkt, start, end) if s.close is not None}
        closes = by_market[mkt]
        if closes:
            out[sym] = closes
    return out


class ProductEval:
    """한 상품의 여섯 칸을 전체 달력에 대해 한 번 계산해 둔다."""

    def __init__(self, gw, prod, hist, cal, unobserved=None, asof=None):
        """gw = TreeGateway. unobserved="exclude" = 관측값이 없는 장중 조건(observe)을 빼고 판단한다(백테스트 비교용).
        asof = 관측 시각(UTC datetime) — 장중(tf="1m"/"5m") 조건을 이 시점 이하로 자르고, 일봉은 asof 이하
        확정(settled) 봉만 본다(미확정 그날 일봉은 None). None 이면 실제 지금(일봉은 마지막 확정봉)."""
        defs, index = gw.defs(), gw.index(prod)
        self.gw, self.prod, self.index, self.defs, self.cal, self.hist = gw, prod, index, defs, list(cal), hist
        sc = session_closes(gw.symbols(), list(cal), asof)
        mk = lambda m: cond.Ctx(hist, cal, prod, index, defs, manual_as=m, unobserved=unobserved,
                                asof=asof, session_close=sc)
        self.ctx = {True: mk(True), False: mk(False), None: mk(None)}
        neutral = {"filter": True, "entry": True, "avoid": False}      # 칸 전체가 빠지면 그 칸은 제약 없음

        def s(node, m, sec=None):
            out = cond.series(node, self.ctx[m])
            if sec is None:
                return [None if x is cond.EXCLUDED else x for x in out]
            return [neutral[sec] if x is cond.EXCLUDED else x for x in out]
        self.opt = {sec: s(gw.section(prod, sec), sec != "avoid", sec) for sec in cond.SECTIONS}
        self.pes = {sec: s(gw.section(prod, sec), sec == "avoid", sec) for sec in cond.SECTIONS}
        self.caution = [(r, [False if x is cond.EXCLUDED else x for x in cond.series(r.when, self.ctx[None])])
                        for r in gw.cautions(prod)]
        w = gw.sizing(prod).qty.x                # 비중 식(Qty "cash") — None = 저자 미명시
        self.weight = {m: (s(w, m) if w is not None else None) for m in (None, True, False)}
        # 데이터 완전성 가드 — 이 상품 등급이 실제로 쓰는 가장 긴 워밍업(트리에서 파생, 하드코딩 아님).
        #   그보다 '확정 봉'이 적은 초기 구간의 1d 신호는 창이 덜 차 조용히 None/틀릴 수 있어 신뢰불가다
        #   → grade_key 가 '불완전 데이터(❔ 보류)'로 표시한다(✅/🚫 확신 금지). WARMUP_DAYS(fetch 버퍼)와 무관.
        self.warmup = gw.warmup(prod)
        # 심볼 확정봉 지도 — asof 장중이면 오늘 미확정 봉을 뺀 '마지막 확정 index'(없으면 전부 확정 = 항등).
        #   여러 심볼을 보면 가장 적게 확정된 심볼(지연된 feed)이 기준이다 — 하나라도 모자라면 불완전.
        self._confirmed = self._confirmed_index_map()

    def _confirmed_index_map(self):
        """날짜별 '이 상품 등급이 쓰는 모든 심볼이 확정한 봉 수 − 1'(= 확정 index). 어떤 심볼이 그 index 를
        아직 확정 못 했으면(지연된 feed·asof 장중 미확정) 그 심볼 기준으로 낮춘다. 확정봉이 하나도 없으면 -1.
        캘린더가 없거나 asof 가 없으면(라이브 지금) settled_map 이 no-op(None) → 날짜 index 그대로(항등)."""
        ctx = self.ctx[None]
        syms = sorted({ctx.bind(s) for s in self.gw.symbols()
                       if not s.startswith("$")} | {self.prod}
                      | ({ctx.bind("$index")} if self.index else set()))
        maps = [ctx.settled_map(s) for s in syms]
        out = []
        for i in range(len(self.cal)):
            idxs = []
            for m in maps:
                idxs.append(i if m is None else m[i])   # None map = 가리지 않음(항등)
            out.append(-1 if any(x is None for x in idxs) else min(idxs))
        return out

    def incomplete(self, i):
        """i 번째 봉의 1d 등급이 '불완전 데이터'인가 — 확정 봉이 필요 워밍업보다 적으면 True.
        확정 index(가장 늦은 심볼 기준)가 warmup 미만이면 가장 긴 창이 덜 차 신호가 신뢰불가다."""
        return self._confirmed[i] < self.warmup

    # ---------------------------------------------------------------- 등급
    def grade_key(self, i):
        # 데이터 완전성 가드 — 워밍업이 모자란 봉은 확신 판정을 내지 않고 '판정 불가(불완전 데이터)'로 둔다.
        #   (조용히 None 이 섞인 opt/pes 로 ✅/🚫 를 내면 모르고 매매하게 된다 — 정직성 원칙.)
        if self.incomplete(i):
            return "unknown"
        # grade_rules.json 을 위에서 아래로 본다 — when 의 모든 칸이 맞는 첫 규칙이 이긴다.
        # 값은 3값(True/False/None) — 'is' 로 정확히 맞춘다(None 은 True·False 어디에도 안 맞는다).
        views = {"opt": self.opt, "pes": self.pes}
        for rule in GRADE_RULES["rules"]:
            view = views[rule["view"]]
            if all(view[sec][i] is want for sec, want in rule["when"].items()):
                return rule["key"]
        return GRADE_RULES["default"]

    # ---------------------------------------------------------------- 금액
    def caution_state(self, i):
        """[{label, ref, note, scale, value, manual}] — value 는 수동 = 모름으로 둔 평가."""
        return [{"label": r.label, "ref": r.ref, "note": r.note, "scale": r.qty.x,
                 "value": ser[i], "manual": [cond.manual_text(n) for n in cond.manual_leaves(r.when, self.defs)]}
                for r, ser in self.caution]

    def weight_of(self, i):
        """그날 비중(%) — 수동 때문에 모르면 (None, [가능한 값들]) 로 범위를 함께 돌려준다."""
        if self.weight[None] is None:
            return None, None
        v = self.weight[None][i]
        if v is not None:
            return v, None
        alt = sorted({x for x in (self.weight[True][i], self.weight[False][i]) if x is not None})
        return None, alt or None

    def amount_factor(self, i):
        """(금액 배수, 폭 미명시로 걸린 규칙, 확인이 필요한 규칙) — 걸린 caution 의 scale 곱."""
        f, unspecified, unknown = 1.0, [], []
        for st in self.caution_state(i):
            if st["value"] is True:
                if st["scale"] is None:
                    unspecified.append(st["label"])
                else:
                    f *= st["scale"]
            elif st["value"] is None:
                unknown.append(st["label"])
        return f, unspecified, unknown

    # ---------------------------------------------------------------- 설명
    def explain(self, i):
        """라벨 달린 노드의 그날 값 — 수동은 '모름'(None)으로 둔 평가. {구역: [(label, ref, 값)]}"""
        out = {}
        for sec in cond.SECTIONS:
            out[sec] = [(n.get("label"), n.get("ref"), cond.series(n, self.ctx[None])[i])
                        for n in cond.labeled(self.gw.section(self.prod, sec), self.defs)]
        return out

    def top(self, i):
        """구역마다 맨 위 라벨 노드들의 그날 값(사유 문장용 — 안쪽 노드까지 늘어놓으면
        not 아래의 '거짓 = 정상' 노드가 '미충족'으로 읽힌다). 수동은 모름(None)."""
        out = {}
        for sec in cond.SECTIONS:
            out[sec] = [(n.get("label"), n.get("ref"), cond.series(n, self.ctx[None])[i])
                        for n in _top_labeled(self.gw.section(self.prod, sec), self.defs)]
        return out

    def manual_items(self, i=None):
        """사람 확인이 필요한 조건 [(칸, 라벨, ref)] — i 를 주면 그날 관측된 observe 조건은 뺀다."""
        out = []
        for z, _l, _r, node in self.gw.expressions(self.prod):
            if z == "exit":
                continue
            for n in cond.manual_leaves(node, self.defs):
                if i is not None and "observe" in n and cond.series(n["observe"], self.ctx[None])[i] is not None:
                    continue
                out.append((z, n.get("label") or cond.manual_text(n), n.get("ref")))
        return out


def _top_labeled(node, defs):
    """라벨 달린 가장 바깥 노드들. all/any/atleast 는 펼치고, not 아래는 들어가지 않는다."""
    if not isinstance(node, dict):
        return []
    if node.get("label"):
        return [node]
    if "def" in node and node["def"] in defs:
        # 참조 자리 META(label·ref·note)를 def 본문 위에 덮는다 — cond.labeled 와 같은 규칙(자리의 원문 출처 보존)
        site = {k: v for k, v in node.items() if k in ("label", "ref", "note")}
        body = defs[node["def"]]
        return _top_labeled(dict(body, **site) if site and isinstance(body, dict) else body, defs)
    kids = node.get("all") or node.get("any") or (node.get("of") if "atleast" in node else None) or []
    out = []
    for k in kids:
        out.extend(_top_labeled(k, defs))
    return out
