#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조건 트리(books/<slug>/tree.json) → 날짜별 판정 (책 무관). 트리의 '뜻'은 여기 한 벌뿐이다.

등급 (COND_DSL.md 1절, 조건 칸 셋):
  filter 거짓 → 🚫 진입 금지 · avoid 참 → ⛔ 보류 · entry 참 → ✅ 매수 후보 · entry 거짓 → ⚪ 관망
수동(manual) 조건은 '확인됨/안 됨' 두 번 평가한다:
  안 돼도 매수(비관) → ✅ · 확인돼야 매수(낙관만) → 🟡 확인 대기 · 데이터 부족으로 못 정함 → ❔ 판정 불가
  비관 = filter·entry 의 수동은 거짓, avoid 의 수동은 참 / 낙관 = 그 반대.
규칙 칸 셋:
  caution  걸린 규칙마다 그날 금액 × scale (null = 줄일 폭 저자 미명시)
  sizing   weight = 총 투자금 대비 비중(%) · tranches = 분할 매수(2차 이후는 포지션 값으로)
  exit     보유분의 매도 — 내 포지션이 있을 때만 평가(position_state)

판정은 봉이 끝난 직후(그날까지의 봉)로 낸다 — cond 연산이 전부 인과적이라 전체 이력을 한 번 계산해
날짜로 꺼내도 미래를 보지 않는다(verify_primitives 가 강제).
"""
import json
import os

from shared.paths import BASE
from shared import cond, md_feed

GRADES = {
    "buy": "✅ 매수 후보",
    "confirm": "🟡 확인 대기",
    "nofilter": "🚫 진입 금지",
    "avoid": "⛔ 보류",
    "wait": "⚪ 관망",
    "unknown": "❔ 판정 불가",
}
# 등급 판정 사다리의 '뜻'은 코드가 아니라 데이터(shared/grade_rules.json)에 있다 — 규칙을 바꾸면
# 거기 한 곳만 고친다. 파이썬(grade_key)과 화면(checklist-ui.gradeKey)이 같은 표를 읽는다.
# 판정 JSON 에도 실어보내(verdict_engine) 화면이 복붙 없이 받아 쓴다.
GRADE_RULES = json.load(
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "grade_rules.json"), encoding="utf-8"))
# 판정 전에 과거 시세를 며칠치(달력일) 미리 당겨올지 — '워밍업'. 트리가 쓰는 가장 긴 창
# (예: 52주 신고가 = 252거래일 ≈ 달력 365일)이 첫날부터 제대로 서도록 넉넉히 둔다.
# ★ 여기 한 곳이 정본이다 — 매일 판정(verdict_engine)·백테스트(backtest)·검증(verify_tree)이
#   모두 이 값을 가져다 쓴다. 과거엔 세 곳에 따로(500/400/500) 박혀 백테스트만 어긋났었다.
WARMUP_DAYS = 500


def tree_path(slug, name="tree.json"):
    return os.path.join(BASE, "books", slug, name)


def load_tree(slug, name="tree.json"):
    """트리 파일을 읽고 문법 검사까지 한다. 없으면 None, 문법 오류면 CondError."""
    p = tree_path(slug, name)
    if not os.path.exists(p):
        return None
    t = json.load(open(p, encoding="utf-8"))
    cond.validate_tree(t)
    return t


class History(dict):
    """{심볼: 일봉} + minutes{심볼: 분봉}. 장중(tf="1m") 값은 asof 축에서 분봉을 잘라 읽는다(cond.minute_series)."""
    minutes = {}


def history(trees, start):
    """트리(들)가 쓰는 모든 심볼의 일봉(+ 장중(tf="1m") 값에 쓰는 심볼의 분봉) — 수집 단계(md_feed)
    하나로 받는다. jhts 는 md_feed 에서만 만진다(팀 경계). 분봉이 연결되기 전에는 minutes 가 비어 있고
    장중 observe 조건은 None→manual 로 떨어진다(의도된 동작)."""
    syms, msyms = set(), set()
    for t in trees if isinstance(trees, list) else [trees]:
        syms |= cond.symbols_of(t)
        msyms |= cond.minute_symbols_of(t)
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

    def __init__(self, tree, prod, hist, cal, unobserved=None, asof=None):
        """unobserved="exclude" = 관측값이 없는 장중 조건(observe)을 빼고 판단한다(백테스트 비교용).
        asof = 관측 시각(UTC datetime) — 장중(tf="1m"/"5m") 조건을 이 시점 이하로 자르고, 일봉은 asof 이하
        확정(settled) 봉만 본다(미확정 그날 일봉은 None). None 이면 실제 지금(일봉은 마지막 확정봉)."""
        cfg = tree["products"][prod]
        defs = tree.get("defs") or {}
        self.tree, self.prod, self.cfg, self.defs, self.cal, self.hist = tree, prod, cfg, defs, list(cal), hist
        sc = session_closes(cond.symbols_of(tree), list(cal), asof)
        mk = lambda m: cond.Ctx(hist, cal, prod, cfg.get("index"), defs, manual_as=m, unobserved=unobserved,
                                asof=asof, session_close=sc)
        self.ctx = {True: mk(True), False: mk(False), None: mk(None)}
        neutral = {"filter": True, "entry": True, "avoid": False}      # 칸 전체가 빠지면 그 칸은 제약 없음

        def s(node, m, sec=None):
            out = cond.series(node, self.ctx[m])
            if sec is None:
                return [None if x is cond.EXCLUDED else x for x in out]
            return [neutral[sec] if x is cond.EXCLUDED else x for x in out]
        self.opt = {sec: s(cfg[sec], sec != "avoid", sec) for sec in cond.SECTIONS}
        self.pes = {sec: s(cfg[sec], sec == "avoid", sec) for sec in cond.SECTIONS}
        self.caution = [(r, [False if x is cond.EXCLUDED else x for x in cond.series(r["when"], self.ctx[None])])
                        for r in cfg.get("caution") or []]
        w = (cfg.get("sizing") or {}).get("weight")
        self.weight = {m: (s(w, m) if w is not None else None) for m in (None, True, False)}
        # 데이터 완전성 가드 — 이 상품 등급이 실제로 쓰는 가장 긴 워밍업(트리에서 파생, 하드코딩 아님).
        #   그보다 '확정 봉'이 적은 초기 구간의 1d 신호는 창이 덜 차 조용히 None/틀릴 수 있어 신뢰불가다
        #   → grade_key 가 '불완전 데이터(❔ 보류)'로 표시한다(✅/🚫 확신 금지). WARMUP_DAYS(fetch 버퍼)와 무관.
        self.warmup = cond.tree_warmup(tree, prod)
        # 심볼 확정봉 지도 — asof 장중이면 오늘 미확정 봉을 뺀 '마지막 확정 index'(없으면 전부 확정 = 항등).
        #   여러 심볼을 보면 가장 적게 확정된 심볼(지연된 feed)이 기준이다 — 하나라도 모자라면 불완전.
        self._confirmed = self._confirmed_index_map()

    def _confirmed_index_map(self):
        """날짜별 '이 상품 등급이 쓰는 모든 심볼이 확정한 봉 수 − 1'(= 확정 index). 어떤 심볼이 그 index 를
        아직 확정 못 했으면(지연된 feed·asof 장중 미확정) 그 심볼 기준으로 낮춘다. 확정봉이 하나도 없으면 -1.
        캘린더가 없거나 asof 가 없으면(라이브 지금) settled_map 이 no-op(None) → 날짜 index 그대로(항등)."""
        ctx = self.ctx[None]
        syms = sorted({ctx.bind(s) for s in cond.symbols_of(self.tree)
                       if not s.startswith("$")} | {self.prod}
                      | ({ctx.bind("$index")} if self.cfg.get("index") else set()))
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
        return [{"label": r["label"], "ref": r.get("ref"), "note": r.get("note"), "scale": r.get("scale"),
                 "value": ser[i], "manual": [n["manual"] for n in cond.manual_leaves(r["when"], self.defs)]}
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
                        for n in cond.labeled(self.cfg[sec], self.defs)]
        return out

    def top(self, i):
        """구역마다 맨 위 라벨 노드들의 그날 값(사유 문장용 — 안쪽 노드까지 늘어놓으면
        not 아래의 '거짓 = 정상' 노드가 '미충족'으로 읽힌다). 수동은 모름(None)."""
        out = {}
        for sec in cond.SECTIONS:
            out[sec] = [(n.get("label"), n.get("ref"), cond.series(n, self.ctx[None])[i])
                        for n in _top_labeled(self.cfg[sec], self.defs)]
        return out

    def view(self, node, i):
        """화면용 중첩 설명 — 노드 하나당 항목 하나(_view). 수동은 모름으로 둔 그날 값."""
        return _view(node, self.defs, self.ctx[None], i)

    def manual_items(self, i=None):
        """사람 확인이 필요한 조건 [(칸, 라벨, ref)] — i 를 주면 그날 관측된 observe 조건은 뺀다."""
        out = []
        for z, _l, _r, node in cond.zone_nodes(self.cfg):
            if z == "exit":
                continue
            for n in cond.manual_leaves(node, self.defs):
                if i is not None and "observe" in n and cond.series(n["observe"], self.ctx[None])[i] is not None:
                    continue
                out.append((z, n.get("label") or n["manual"], n.get("ref")))
        return out


LOGICAL = ("all", "any", "atleast", "not")


def product_specific(node, defs):
    """$self/$index/pos 를 쓰는 식은 상품마다 값이 달라진다 — 여러 상품이 '같이 보는' 판단이 아니다."""
    for n in cond.labeled_all(node, defs):
        if "px" in n and n.get("sym", "$self") in ("$self", "$index"):
            return True
        if "pos" in n:
            return True
    return False


# ------------------------------------------------------------------ 측정 증거(실제 값)
# 조건의 ●/○ 밑에 '무엇을 재서 그 값이 얼마였나'를 실어보낸다 — 사용자가 판정을 검증·신뢰할 수 있게.
# 엔진은 어차피 비교 양쪽 값을 계산해 참/거짓을 낸다(cond.series). 그 값을 버리지 않고 뷰에 담는 것뿐이다.
_PXF = {"close": "종가", "open": "시가", "high": "고가", "low": "저가", "volume": "거래량"}


def _meas_val(e, ctx, i):
    """값 표현식 하나를 그날 실제 숫자로 — 못 재면 None. 표시용이라 자리수만 줄인다(계산엔 안 쓴다)."""
    try:
        v = cond.series(e, ctx)[i]
    except Exception:
        return None
    if v is None or isinstance(v, bool):
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if v != v:                                   # NaN
        return None
    a = abs(v)
    return round(v, 1) if a >= 100 else round(v, 2) if a >= 1 else round(v, 3)


def _describe_operand(e, defs):
    """값 표현식 → 짧은 사람 설명(없으면 '' — 그럼 숫자만 보여준다). 복합식(산술 등)은 라벨이 설명하므로 생략."""
    if not isinstance(e, dict):
        return ""                                # 상수(기준값) — 숫자 자체로
    if "def" in e and e["def"] in defs and len([k for k in e if k not in cond.META]) == 1:
        return _describe_operand(defs[e["def"]], defs)
    try:
        op = cond._op_of(e)
    except cond.CondError:
        return ""
    if op == "px":
        sym = e.get("sym", "$self")
        base = _PXF.get(e["px"], e["px"])
        return base if sym in ("$self", "$index") else "%s %s" % (sym, base)
    if op in ("ma", "ema"):
        return "%d일선" % e[op][1] if op == "ma" else "%d일 지수이평" % e[op][1]
    if op in ("highest", "lowest", "sum", "stdev"):
        m = {"highest": "최고", "lowest": "최저", "sum": "합계", "stdev": "변동성"}
        return "%d일 %s" % (e[op][1], m[op])
    if op == "pct":
        return "전일 대비 변화율" if e["pct"][1] == 1 else "%d일 전 대비 변화율" % e["pct"][1]
    if op == "lag":
        inner = _describe_operand(e["lag"][0], defs)
        return ("%s " % inner if inner else "") + "%d일 전" % e["lag"][1]
    if op == "streak":
        return "연속 참 일수"
    if op == "count":
        return "최근 참 일수"
    if op == "barssince":
        return "마지막 참 이후 일수"
    if op == "rsi":
        return "RSI%d" % e["rsi"][1]
    if op == "pos":
        return {"ret": "수익률(%)", "days": "보유일", "maxret": "최고수익(%)",
                "minret": "최저수익(%)"}.get(e["pos"], "포지션")
    return ""                                    # add/sub/mul/div/case/valuewhen … 복합 → 숫자만


def _unit_of(e, defs):
    """값 표현식의 단위 힌트(%·일·배) — 모르면 '' (라벨이 단위를 말하므로 비워도 된다)."""
    if not isinstance(e, dict):
        return ""
    if "def" in e and e["def"] in defs and len([k for k in e if k not in cond.META]) == 1:
        return _unit_of(defs[e["def"]], defs)
    try:
        op = cond._op_of(e)
    except cond.CondError:
        return ""
    if op == "pct":
        return "%"
    if op in ("streak", "count", "barssince"):
        return "일"
    if op == "div":
        return "배"
    if op == "rsi":
        return ""
    if op == "pos":
        return "일" if e["pos"] == "days" else "%"
    return ""


def _inputs_of(e, ctx, i, defs, acc, seen):
    """복합식(산술)의 원시 측정 잎들을 [{d, v}]로 모은다 — '무슨 숫자로 계산했나'를 보여주려고.
    예: (고가 − 종가) ÷ 고가 → [{d:'고가', v:…}, {d:'종가', v:…}]. 중복 설명은 한 번만."""
    if not isinstance(e, dict):
        return
    if "def" in e and e["def"] in defs and len([k for k in e if k not in cond.META]) == 1:
        return _inputs_of(defs[e["def"]], ctx, i, defs, acc, seen)
    try:
        op = cond._op_of(e)
    except cond.CondError:
        return
    LEAF = ("px", "ma", "ema", "pct", "lag", "streak", "count", "barssince",
            "rsi", "highest", "lowest", "sum", "stdev", "pos")
    if op in LEAF:
        d = _describe_operand(e, defs)
        if d and d not in seen:
            seen.add(d)
            acc.append({"d": d, "v": _meas_val(e, ctx, i)})
        return
    if op in cond.ARITH:
        for sub in e[op]:
            _inputs_of(sub, ctx, i, defs, acc, seen)
    elif op == "abs":
        _inputs_of(e["abs"], ctx, i, defs, acc, seen)
    # case·valuewhen 등은 생략(라벨이 설명을 맡는다)


def _measure(node, defs, ctx, i, top=True):
    """표시되는 조건 하나가 '무엇을 재서 얼마였나' — [{op, lhs, lhsd, rhs, rhsd, unit, inputs?}, …].
    하위에 라벨 달린 조건이 있으면 멈춘다(그 조건이 자기 증거를 따로 보여준다)."""
    if not isinstance(node, dict):
        return []
    if "def" in node and node["def"] in defs and len([k for k in node if k not in cond.META]) == 1:
        return _measure(defs[node["def"]], defs, ctx, i, top)
    if not top and (node.get("label") or "manual" in node or "observe" in node):
        return []
    try:
        op = cond._op_of(node)
    except cond.CondError:
        return []
    if op in cond.CMP:
        a, b = node[op]
        lhsd = _describe_operand(a, defs)
        fact = {"op": op,
                "lhs": _meas_val(a, ctx, i), "lhsd": lhsd,
                "rhs": _meas_val(b, ctx, i), "rhsd": _describe_operand(b, defs),
                "unit": _unit_of(a, defs)}
        if not lhsd:                       # 복합식(산술) — 무슨 원시 숫자로 계산했는지 함께 보여준다
            ins = []
            _inputs_of(a, ctx, i, defs, ins, set())
            if ins:
                fact["inputs"] = ins
        return [fact]
    if op == "not":
        kids = [node["not"]]
    elif op in ("all", "any"):
        kids = node[op]
    elif op == "atleast":
        kids = node["of"]
    elif op == "observe":
        kids = [node["observe"]]
    else:
        return []
    facts = []
    for c in kids:
        facts += _measure(c, defs, ctx, i, top=False)
    return facts


def _view(node, defs, ctx, i, shared=False):
    """노드 하나 → 화면 항목 하나 {v, op?, n?, kids?, label?, ref?, manual?, note?, hidden?}.

    · 논리 노드(all/any/atleast/not)는 op 와 자식 항목 전부를 담는다 — 화면이 사람이 체크한 수동 조건으로
      같은 3값 논리를 다시 계산할 수 있게(not 아래 수동은 극성이 뒤집힌다 — cond 와 같은 규칙).
    · 그 밖의 노드는 그날 값(v)이 고정된 잎이다. 라벨이 없으면 hidden(화면에 안 보이지만 계산엔 쓴다),
      안쪽에 라벨 달린 노드가 있으면 참고용 kids(op 없음 — 다시 계산하지 않는다)로 붙인다.
    · 라벨 없는 정의 참조는 정의 본문으로, 라벨 달린 정의 참조는 op "ref"(값 = 유일한 자식)로.
    · 상품마다 값이 같은 정의(product_specific 아님) 안의 수동 조건은 shared=True — 화면에서 한 번 체크하면
      그 조건을 쓰는 모든 상품에 같은 답이 들어간다(같은 시장 사실이므로).
    v 는 수동 = 모름(None)으로 둔 그날 값이다."""
    if "def" in node and node["def"] in defs and not node.get("label")             and not [k for k in node if k not in cond.META and k != "def"]:
        body = defs[node["def"]]
        return _view(body, defs, ctx, i, shared or not product_specific(body, defs))
    skip = ("of", "sym", "tf", "else") + (("manual",) if "observe" in node else ())
    op = next((k for k in node if k not in cond.META and k not in skip), None)
    item = {"v": cond.series(node, ctx)[i]}
    for k in ("label", "ref", "note"):
        if node.get(k):
            item[k] = node[k]
    if op in ("manual", "observe"):
        item["manual"] = node["manual"]
        if shared:
            item["shared"] = True
        if op == "observe":
            item["observed"] = True              # v 가 있으면 관측값(자동), 없으면 사람 확인
            item["kids"] = [_view(node["observe"], defs, ctx, i, shared)]
    elif op in LOGICAL:
        kids = node[op] if op in ("all", "any") else (node["of"] if op == "atleast" else [node["not"]])
        kctx = ctx.flipped() if op == "not" else ctx
        item["op"] = op
        if op == "atleast":
            item["n"] = node["atleast"]
        item["kids"] = [_view(k, defs, kctx, i, shared) for k in kids]
    elif op == "def":
        body = defs[node["def"]]
        item["op"] = "ref"
        item["kids"] = [_view(body, defs, ctx, i, shared or not product_specific(body, defs))]
    else:
        inner = [_view(k, defs, ctx, i, shared) for k in _labeled_inside(node, defs)]
        if inner:
            item["kids"] = inner
        if not node.get("label"):
            item["hidden"] = True
    # 측정 증거 — 화면에 보이는 조건(라벨/수동/관측)에만 그날 실제 값을 붙인다.
    if node.get("label") or "manual" in node or "observe" in node:
        facts = _measure(node, defs, ctx, i)
        if facts:
            item["detail"] = facts
    return item


def _labeled_inside(node, defs):
    """잎 노드 안쪽의 가장 바깥 라벨 노드들(참고 표시용)."""
    out = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("label") or "manual" in n:
                out.append(n)
                return
            if "def" in n and n["def"] in defs:
                walk(defs[n["def"]])
                return
            for k, x in n.items():
                if k not in cond.META:
                    walk(x)
        elif isinstance(n, list):
            for x in n:
                walk(x)
    for k, x in node.items():
        if k not in cond.META:
            walk(x)
    return out


def _top_labeled(node, defs):
    """라벨 달린 가장 바깥 노드들. all/any/atleast 는 펼치고, not 아래는 들어가지 않는다."""
    if not isinstance(node, dict):
        return []
    if node.get("label"):
        return [node]
    if "def" in node and node["def"] in defs:
        return _top_labeled(defs[node["def"]], defs)
    kids = node.get("all") or node.get("any") or (node.get("of") if "atleast" in node else None) or []
    out = []
    for k in kids:
        out.extend(_top_labeled(k, defs))
    return out


def reason_of(key, ex, manual):
    """등급 사유 한 줄 — 무엇이 걸렸는지 라벨로."""
    def labels(sec, val):
        return [l for l, _, v in ex.get(sec, []) if l and v is val]
    if key == "nofilter":
        bad = labels("filter", False)
        return "필터 미충족: " + (" · ".join(bad[:3]) if bad else "전제 조건 거짓")
    if key == "avoid":
        hit = labels("avoid", True)
        return "회피 신호: " + (" · ".join(hit[:3]) if hit else "회피 조건 참")
    if key == "wait":
        return "진입 조건 미충족 — 매수 자리 아님"
    if key == "confirm":
        items = [l for s, l, _ in manual if s in ("filter", "entry")] + \
                ["(회피 아님) " + l for s, l, _ in manual if s == "avoid"]
        return "수동·장중 확인 시 매수: " + " · ".join(items[:4])
    if key == "buy":
        ok = labels("entry", True)
        return "필터 통과 · 회피 없음 · 진입: " + (" · ".join(ok[:3]) if ok else "조건 충족")
    return "데이터 부족으로 판정 불가"


def position_state(tree, prod, hist, cal, entry_date, cost, filled=1):
    """내 포지션(첫 매수일·평균 매입가·산 차수)의 오늘 매도·추가 매수 규칙 상태.
    → {ret, days, exit:[{label, ref, sell, v, view}], next_tranche:{label, ref, frac, v, view}|None}"""
    cfg, defs = tree["products"][prod], tree.get("defs") or {}
    later = [k for k, d in enumerate(cal) if d >= entry_date]
    if not later:
        return {"error": "첫 매수일 %s 이후 시세 없음" % entry_date}
    ctx = cond.Ctx(hist, cal, prod, cfg.get("index"), defs, manual_as=None, pos=(later[0], cost))
    i = len(cal) - 1
    out = {"ret": cond.series({"pos": "ret"}, ctx)[i], "days": cond.series({"pos": "days"}, ctx)[i],
           "exit": [{"label": r["label"], "ref": r.get("ref"), "sell": r["sell"],
                     "v": cond.series(r["when"], ctx)[i], "view": _view(r["when"], defs, ctx, i)}
                    for r in cfg.get("exit") or []]}
    trs = (cfg.get("sizing") or {}).get("tranches") or []
    nt = trs[filled] if 0 < filled < len(trs) else None
    out["next_tranche"] = None if nt is None else {
        "label": nt["label"], "ref": nt.get("ref"), "frac": nt["frac"],
        "v": cond.series(nt["when"], ctx)[i], "view": _view(nt["when"], defs, ctx, i)}
    return out
