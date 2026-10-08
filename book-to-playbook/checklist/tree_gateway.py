#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TreeGateway — 조건 트리(books/<slug>/tree.json)를 읽는 유일한 출입구 (구간② 소유, 책 무관).

왜 있나
  트리의 키 배치(products·defs·여섯 칸·규칙의 sell/scale/frac…)를 아는 코드가 판정·백테스트·검사기 곳곳에
  흩어져 있었다. 형식이 바뀌면(여섯 칸 → rules 목록 하나) 그 전부를 고쳐야 했다. 이제 원본 키를 만지는 코드는
  이 파일 하나다 — 나머지는 여기에 '질문'만 한다. 형식이 바뀌면 이 파일(+ 문법 shared/cond.py)만 고친다.
  직접 접근은 orchestration/verify_teams 규칙 6 이 막는다.

무엇을 하나 / 안 하나
  · 찾아서 건네주기(탐색·조회)와 파일 형식 검사(최상위·상품·규칙 목록의 모양)만 한다.
  · 식의 뜻·평가·노드 문법은 shared/cond.py, 등급·금액은 shared/tree_grade.py, 체결은 shared/trades.py.
  · shared 는 이 파일을 import 하지 않는다(공통층이 맨 아래) — 호출자가 TreeGateway 를 인자로 넘긴다.
  · 규칙은 Rule(읽기 전용 값)로 건넨다 — 형식이 바뀌어도 같은 속성(label·ref·note·when·sell·scale·frac·weight)을 준다.
"""
import json
import os

from shared import cond
from shared.paths import BASE

TREE_TOP = ("version", "defs", "products", "source", "note", "unexpressed", "review")
# review = 심판의 판정 근거(구간② 검사기만 읽는다 — 판정·체결엔 안 쓴다): sections{"상품.칸": {winner a|b|custom, why, cases}},
#   exits{상품: {winner, why}}, scenario_overrides{사례 이름: 사유}, fire_ack{경고문: 사유}. 최종 트리와 한 파일 — 심판만 쓴다.
PRODUCT_KEYS = ("index", "note", "exit_note") + cond.ZONES
EXIT_KEYS = ("label", "ref", "note", "when", "sell")
CAUTION_KEYS = ("label", "ref", "note", "when", "scale")
SIZING_KEYS = ("label", "ref", "note", "weight", "tranches")
TRANCHE_KEYS = ("label", "ref", "note", "frac", "when")
EMPTY_ZONE = {"filter": {"all": []}, "entry": {"all": []}, "avoid": {"any": []},
              "caution": [], "sizing": {"weight": None, "tranches": []}, "exit": []}


def empty_product(**zones):
    """여섯 칸이 전부 빈 상품 하나(검사기·합성 트리용) — 준 칸만 덮는다."""
    return dict(EMPTY_ZONE, **zones)


def synthetic(products, **top):
    """합성 트리 dict(검사기용) — products = {상품: 상품 dict}. 형식이 바뀌면 이것과 empty_product 만 고친다."""
    return dict(top, products=products)


class Rule:
    """규칙 하나(조심 · 비중 · 분할 차수 · 매도)의 읽기 전용 값. 없는 필드는 None — when None = 조건 없음(1차 분할)."""
    __slots__ = ("label", "ref", "note", "when", "sell", "scale", "frac", "weight", "_raw")

    def __init__(self, raw):
        self._raw = raw
        for k in self.__slots__[:-1]:
            setattr(self, k, raw.get(k))

    def shown(self, *keys):
        """원본에 적힌 필드만 {키: 값} — 적지 않은 키는 빠진다(판정 JSON 모양 그대로)."""
        return {k: self._raw[k] for k in keys if k in self._raw}

    def raw(self):
        """원본 그대로 — 심판 덤프·식 지문 전용(판정·체결은 속성을 쓴다)."""
        return self._raw

    def with_when(self, when):
        """when 만 바꾼 사본(def 를 펼친 비교용)."""
        return Rule(dict(self._raw, when=when))


class TreeGateway:
    """트리 하나. load/read/open/of 로 만들고 질문으로 읽는다(원본 dict 는 밖으로 내지 않는다 — raw_* 덤프 전용 제외)."""

    def __init__(self, data):
        self._d = data

    def __bool__(self):
        return bool(self._d)          # 빈 파일({})은 없는 것과 같게 — 옛 dict 진리값 그대로

    # ---------------------------------------------------------------- 읽기
    @staticmethod
    def path(slug, name="tree.json"):
        return os.path.join(BASE, "books", slug, name)

    @classmethod
    def open(cls, path):
        """검사 없이 읽는다 — 파일 없음·JSON 오류는 OSError·ValueError 그대로."""
        return cls(json.load(open(path, encoding="utf-8")))

    @classmethod
    def read(cls, slug, name="tree.json"):
        """검사 없이 읽는다(후보 a·b 등) — 없으면 None."""
        p = cls.path(slug, name)
        return cls.open(p) if os.path.exists(p) else None

    @classmethod
    def load(cls, slug, name="tree.json"):
        """트리 파일을 읽고 형식 검사까지 한다. 없으면 None, 문법 오류면 CondError."""
        t = cls.read(slug, name)
        if t is not None:
            t.validate()
        return t

    @classmethod
    def of(cls, data):
        """dict → 검사를 통과한 출입구(합성 트리·검사기용). 문법 오류면 CondError."""
        t = cls(data)
        t.validate()
        return t

    @staticmethod
    def as_rules(raw):
        """트리 형식의 규칙 dict 목록(표준 매도 exit_defaults·전량 한 번 등) → [Rule]."""
        return [Rule(r) for r in raw]

    # ---------------------------------------------------------------- 형식 검사
    def validate(self):
        """트리 파일 전체 검사. 상품마다 여섯 칸을 다 명시해야 한다(빠진 칸을 조용히 기본값으로 채우지 않는다).
        노드 하나의 문법은 cond.validate."""
        tree = self._d
        if not isinstance(tree, dict):
            raise cond.CondError("트리 파일은 객체여야 한다")
        bad = set(tree) - set(TREE_TOP)
        if bad:
            raise cond.CondError("모르는 최상위 키: %s" % sorted(bad))
        defs = tree.get("defs") or {}
        for name, d in defs.items():
            cond.validate(d, defs, "defs.%s" % name)
            if cond._uses_pos(d, defs):
                raise cond.CondError("defs.%s: pos 는 정의에 쓰지 않는다(매도·분할 규칙 안에 직접)" % name)
        prods = tree.get("products")
        if not isinstance(prods, dict) or not prods:
            raise cond.CondError("products 가 비어 있다")
        for p, cfg in prods.items():
            if not isinstance(cfg, dict):
                raise cond.CondError("products.%s: 객체여야 한다" % p)
            bad = set(cfg) - set(PRODUCT_KEYS)
            if bad:
                raise cond.CondError("products.%s: 모르는 키 %s" % (p, sorted(bad)))
            for z in cond.ZONES:
                if z not in cfg:
                    raise cond.CondError("products.%s.%s: 칸이 없다(조건이 없으면 %s 로 명시)"
                                         % (p, z, json.dumps(EMPTY_ZONE[z], ensure_ascii=False)))
            for sec in cond.SECTIONS:
                cond.validate(cfg[sec], defs, "products.%s.%s" % (p, sec))
                if cond._uses_pos(cfg[sec], defs):
                    raise cond.CondError("products.%s.%s: pos 는 매도·분할 규칙 안에서만 쓴다" % (p, sec))
            _validate_caution(cfg["caution"], defs, "products.%s.caution" % p)
            _validate_sizing(cfg["sizing"], defs, "products.%s.sizing" % p)
            _validate_exits(cfg["exit"], defs, "products.%s.exit" % p)
        return True

    # ---------------------------------------------------------------- 책·상품
    def _p(self, prod):
        return self._d["products"][prod]

    def products(self):
        """상품 목록(트리에 적힌 순서)."""
        return list(self._d["products"])

    def has(self, prod):
        return prod in self._d["products"]

    def index(self, prod):
        """상품의 기준 지수 심볼($index) — 없으면 None."""
        return self._p(prod).get("index")

    def note(self, prod):
        return self._p(prod).get("note")

    def book(self, default=None):
        """트리가 말하는 책 이름(source.book) — 키가 없으면 default."""
        return (self._d.get("source") or {}).get("book", default)

    def defs(self):
        """{정의 이름: 노드} — {"def": 이름} 참조를 푸는 표(노드 문법 함수에 그대로 넘긴다)."""
        return self._d.get("defs") or {}

    def unexpressed(self):
        """트리로 못 옮긴 규칙 [{rule, ref, reason}]."""
        return self._d.get("unexpressed") or []

    # ---------------------------------------------------------------- 칸·규칙
    def section(self, prod, sec):
        """조건 칸(filter/entry/avoid) 하나의 식."""
        return self._p(prod)[sec]

    def cautions(self, prod):
        """조심 규칙 [Rule(label, ref, note, when, scale)]."""
        return [Rule(r) for r in self._p(prod).get("caution") or []]

    def sizing(self, prod):
        """비중 Rule(label, ref, note, weight) — weight None = 저자 미명시."""
        return Rule(self._p(prod).get("sizing") or {})

    def tranches(self, prod):
        """분할 차수 [Rule(label, ref, note, frac, when)] — 1차는 when None."""
        return [Rule(t) for t in (self._p(prod).get("sizing") or {}).get("tranches") or []]

    def exit_rules(self, prod):
        """책의 매도 규칙 [Rule(label, ref, note, when, sell)] — 없으면 [](표준 기본값은 trades.exits_of 가 붙인다)."""
        return [Rule(r) for r in self._p(prod).get("exit") or []]

    def expressions(self, prod):
        """상품 하나의 모든 식 [(칸, 라벨, ref, 식)] — 조건 칸은 칸 전체, 규칙 칸은 규칙마다."""
        cfg = self._p(prod)
        out = [(sec, None, None, cfg[sec]) for sec in cond.SECTIONS if sec in cfg]
        for r in cfg.get("caution") or []:
            out.append(("caution", r.get("label"), r.get("ref"), r["when"]))
        sz = cfg.get("sizing") or {}
        if sz.get("weight") is not None:
            out.append(("sizing", sz.get("label"), sz.get("ref"), sz["weight"]))
        for t in sz.get("tranches") or []:
            if "when" in t:
                out.append(("sizing", t.get("label"), t.get("ref"), t["when"]))
        for r in cfg.get("exit") or []:
            out.append(("exit", r.get("label"), r.get("ref"), r["when"]))
        return out

    def scenario_node(self, prod, sec, rule=None):
        """원문 사례가 가리키는 식 — 조건 칸은 칸 전체, caution 은 rule 라벨의 when(라벨 없으면 '어느 조심이든'),
        sizing 은 weight. 가리킬 곳이 없거나 모호하면 None."""
        if not self.has(prod):
            return None
        cfg = self._p(prod)
        if sec in cond.SECTIONS:
            return cfg[sec]
        if sec == "caution":
            if not rule:                    # 규칙을 모르고 쓴 사례 = '어느 조심이든 걸려 금액을 줄이나'
                return {"any": [r["when"] for r in cfg["caution"]]}
            hit = [r for r in cfg["caution"] if r["label"] == rule]
            return hit[0]["when"] if len(hit) == 1 else None
        if sec == "sizing":
            return cfg["sizing"].get("weight")
        return None

    # ---------------------------------------------------------------- 트리 전체 훑기
    def _all_nodes(self):
        """defs 본문 + 모든 상품의 식."""
        nodes = list(self.defs().values())
        for p in self._d["products"]:
            nodes.extend(n for _z, _l, _r, n in self.expressions(p))
        return nodes

    def symbols(self, prods=None):
        """트리가 참조하는 실제 심볼 전부(상품·지수·defs·여섯 칸 전부) — 수집 단계의 단일 입력.
        prods 를 주면 그 상품들(+ defs 전부)만."""
        out = set()

        def walk(n):
            if isinstance(n, dict):
                if "px" in n:
                    s = n.get("sym", "$self")
                    if not s.startswith("$"):
                        out.add(s)
                if "across" in n and isinstance(n["across"], dict):
                    out.update(n["across"].get("syms") or [])
                for k, x in n.items():
                    if k not in cond.META:
                        walk(x)
            elif isinstance(n, list):
                for x in n:
                    walk(x)

        walk(self._d.get("defs") or {})
        for p in (self._d["products"] if prods is None else prods):
            out.add(p)
            if self.index(p):
                out.add(self.index(p))
            for _z, _l, _r, node in self.expressions(p):
                walk(node)
        return out

    def minute_symbols(self):
        """장중 봉(tf="1m"/"5m") 값을 쓰는 심볼 — 수집 단계가 이 심볼들의 1분봉을 같이 받는다(5분봉은 세션 안 집계).
        $self·$index 잎은 어느 상품의 것인지 가리지 않고 모든 상품(지수)을 넣는다."""
        defs = self.defs()
        out = set()
        for n in (n for node in self._all_nodes() for n in cond.labeled_all(node, defs)):
            if not ("px" in n and n.get("tf") in ("1m", "5m")):
                continue
            s = n.get("sym", "$self")
            if s.startswith("$"):
                out.update(self.index(p) if s == "$index" else p for p in self._d["products"])
            else:
                out.add(s)
        out.discard(None)
        return out

    def timeframes(self):
        """트리가 실제로 쓰는 tf 집합(모든 px 잎, defs 펼침)."""
        defs = self.defs()
        return {n.get("tf", "1d") for node in self._all_nodes() for n in cond.labeled_all(node, defs)
                if isinstance(n, dict) and "px" in n}

    def warmup(self, prod=None):
        """상품 하나(prod)의 등급(조건 칸 filter/entry/avoid)이 요구하는 가장 긴 워밍업(거래일 수).
        prod=None 이면 모든 상품에 걸친 최댓값. 규칙 칸(caution/sizing/exit)은 등급과 무관해 넣지 않는다."""
        defs = self.defs()
        mx = 0
        for p in [prod] if prod is not None else self._d["products"]:
            for sec in cond.SECTIONS:
                mx = max(mx, cond.warmup_of(self._p(p)[sec], defs))
        return mx

    def refs(self):
        """트리에 달린 원문 소절 ref 전부(라벨 노드·규칙·비중·분할) — ref 유효성 검사용."""
        defs = self.defs()
        out = set()
        for node in self._all_nodes():
            out.update(x.get("ref") for x in cond.labeled_all(node, defs) if x.get("ref"))
        for p in self._d["products"]:
            cfg = self._p(p)
            out.update(r.get("ref") for r in cfg["caution"] + cfg["exit"] if r.get("ref"))
            sz = cfg["sizing"]
            out.update(t.get("ref") for t in sz["tranches"] + [sz] if t.get("ref"))
        return out

    def def_users(self):
        """{정의 이름: 그 정의를 참조하는 상품 집합} — 칸 안에서 {"def": 이름} 을 직접·간접으로 쓰는 상품."""
        defs = self.defs()
        users = {}

        def walk(n, p, seen):
            if isinstance(n, dict):
                if "def" in n and n["def"] in defs and n["def"] not in seen:
                    users.setdefault(n["def"], set()).add(p)
                    walk(defs[n["def"]], p, seen | {n["def"]})
                for k, x in n.items():
                    if k not in cond.META:
                        walk(x, p, seen)
            elif isinstance(n, list):
                for x in n:
                    walk(x, p, seen)

        for p in self._d["products"]:
            for _z, _l, _r, node in self.expressions(p):
                walk(node, p, set())
        return users

    # ---------------------------------------------------------------- 심판 기록(review) — 구간② 검사기만 읽는다
    def _review(self):
        return self._d.get("review") or {}

    def review_sections(self):
        """{"상품.칸": {winner, why, …}}."""
        return self._review().get("sections") or {}

    def review_exits(self):
        """{상품: {winner, why}}."""
        return self._review().get("exits") or {}

    def scenario_overrides(self):
        """{사례 이름: '시나리오가 틀렸다' 사유}."""
        return self._review().get("scenario_overrides") or {}

    def fire_ack(self):
        """{경고문: '원문 그대로라 정상' 사유}."""
        return self._review().get("fire_ack") or {}

    # ---------------------------------------------------------------- 원본 그대로(심판 덤프·식 지문·전수 훑기 전용)
    def raw_defs(self):
        """defs 원본(없으면 None) — 심판 덤프용."""
        return self._d.get("defs")

    def raw_product(self, prod):
        """상품 원본 — 식 지문·이름 대조처럼 상품 전체를 훑는 검사용."""
        return self._p(prod)

    def raw_zone(self, prod, zone):
        """칸 원본(없으면 None) — 심판 덤프·칸 지문용."""
        return self._p(prod).get(zone)

    def whole(self):
        """트리 원본 전체 — 형식과 무관한 전수 훑기(이름 없는 수동 찾기 등) 전용."""
        return self._d


# ------------------------------------------------------------------ 규칙 목록 형식 검사
def _rule_list(rules, keys, path, need):
    """규칙 목록 형식 검사 — (경로, 규칙) 을 차례로 돌려준다."""
    if not isinstance(rules, list):
        raise cond.CondError("%s: 목록이어야 한다" % path)
    out = []
    for k, r in enumerate(rules):
        pp = "%s[%d]" % (path, k)
        if not isinstance(r, dict):
            raise cond.CondError("%s: 객체여야 한다" % pp)
        bad = set(r) - set(keys)
        if bad:
            raise cond.CondError("%s: 모르는 키 %s" % (pp, sorted(bad)))
        if any(x not in r or r[x] in (None, "") for x in need):
            raise cond.CondError("%s: %s 이 필요하다" % (pp, "·".join(need)))
        out.append((pp, r))
    return out


def _frac_or_null(f):
    """수량 자리(scale·frac·sell 비율) — 0 초과 1 이하의 수, 또는 null(저자 미명시)."""
    return f is None or (isinstance(f, (int, float)) and not isinstance(f, bool) and 0 < f <= 1)


def _validate_exits(rules, defs, path):
    """매도 규칙 목록: [{label, ref, when, sell}] — sell = "all" | {"initial": f} | {"remaining": f}.
    f = 0<f<=1, 또는 null(줄일 비율 저자 미명시 — caution.scale·tranches.frac 과 같은 규칙)."""
    for pp, r in _rule_list(rules, EXIT_KEYS, path, ("label", "when", "sell")):
        cond.validate(r["when"], defs, pp + ".when")
        sell = r["sell"]
        ok = sell == "all" or (isinstance(sell, dict) and len(sell) == 1
                               and next(iter(sell)) in ("initial", "remaining")
                               and _frac_or_null(next(iter(sell.values()))))
        if not ok:
            raise cond.CondError("%s.sell: \"all\" 또는 {\"initial\"|\"remaining\": 0~1|null} 이어야 한다" % pp)


def _validate_caution(rules, defs, path):
    """조심 규칙 목록: [{label, ref, when, scale}] — scale = 0<f<=1(그날 금액에 곱함) | null(저자 미명시)."""
    for pp, r in _rule_list(rules, CAUTION_KEYS, path, ("label", "when")):
        cond.validate(r["when"], defs, pp + ".when")
        if cond._uses_pos(r["when"], defs):
            raise cond.CondError("%s.when: pos 는 매도·분할 규칙 안에서만 쓴다" % pp)
        if "scale" not in r:
            raise cond.CondError("%s: scale 을 명시한다(폭을 저자가 안 줬으면 null)" % pp)
        if not _frac_or_null(r["scale"]):
            raise cond.CondError("%s.scale: 0 초과 1 이하의 수 또는 null" % pp)


def _validate_sizing(sz, defs, path):
    """비중·분할: {weight: 숫자식|null, tranches: [{label, frac, when?}]} — 1차는 when 없음, frac 합 1."""
    if not isinstance(sz, dict):
        raise cond.CondError("%s: 객체여야 한다" % path)
    bad = set(sz) - set(SIZING_KEYS)
    if bad:
        raise cond.CondError("%s: 모르는 키 %s" % (path, sorted(bad)))
    if "weight" not in sz or "tranches" not in sz:
        raise cond.CondError("%s: weight·tranches 를 명시한다(저자가 안 줬으면 null·[])" % path)
    if sz["weight"] is not None:
        cond.validate(sz["weight"], defs, path + ".weight")
        if cond._uses_pos(sz["weight"], defs):
            raise cond.CondError("%s.weight: pos 를 쓸 수 없다" % path)
    trs = _rule_list(sz["tranches"], TRANCHE_KEYS, path + ".tranches", ("label",))
    if trs and len({t.get("frac") is None for _, t in trs}) > 1:
        raise cond.CondError("%s.tranches: frac 은 전부 숫자이거나 전부 null(저자 미명시)이어야 한다" % path)
    for k, (pp, t) in enumerate(trs):
        if "frac" not in t:
            raise cond.CondError("%s: frac 을 명시한다(저자가 비율을 안 줬으면 null)" % pp)
        if not _frac_or_null(t["frac"]):
            raise cond.CondError("%s.frac: 0 초과 1 이하 또는 null" % pp)
        if k == 0 and "when" in t:
            raise cond.CondError("%s: 1차는 when 없이 매수 신호 날 산다" % pp)
        if k > 0:
            if "when" not in t:
                raise cond.CondError("%s: 2차 이후는 when 이 필요하다" % pp)
            cond.validate(t["when"], defs, pp + ".when")
    if trs and trs[0][1]["frac"] is not None and abs(sum(t["frac"] for _, t in trs) - 1) > 1e-6:
        raise cond.CondError("%s.tranches: frac 합이 1 이어야 한다(%g)" % (path, sum(t["frac"] for _, t in trs)))
