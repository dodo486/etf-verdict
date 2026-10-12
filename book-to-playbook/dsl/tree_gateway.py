#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TreeGateway — 조건 트리(books/<slug>/tree.json)를 읽는 유일한 출입구 (구간② 소유, 책 무관).

왜 있나
  트리의 키 배치를 아는 코드가 판정·백테스트·검사기 곳곳에 흩어지지 않게, 원본 키를 만지는 코드는 이 파일 하나다.
  나머지(판정 엔진·백테스트·화면)는 여기에 '질문'만 한다. 직접 접근은 entry/verify_rules 주인 표가 막는다.

트리 v3 (규칙 목록)
  파일은 `rules` 목록(원문 판단 하나 = 규칙 하나, 동사 셋 안 산다·산다·판다 — 정본 Cond.VERBS). 소비자는 동사로 묻는다:
    · gate(안 산다)·gate(산다) — 그 동사 갈래의 any 묶음(등급용, 포지션 쓰는 갈래 제외)
    · weight — 산다 + qty cash(비중) · tranches — 산다 + qty budget(분할) · sells — 판다
  수량은 트리의 qty {of, x} 를 그대로 Qty(of, x) 로 건넨다("?" → None). 물량 변환은 consumers/backtest/trades.to_units.
  `{"rule": "이름"}` 참조는 건네기 전에 **펼친다** — 평가기(Cond)는 평범한 식만 본다.
  트리는 상품을 모르는 공통 로직이다. 상품마다 달라지는 것은 해석기(판단자)가 채운다:
    · 시세 잎 sym = 역할 `$self`(판정 중인 상품) · `$index`(그 상품의 지수 — products 의 index) · 또는 구체 티커(^VIX 등)
    · 규칙·노드 `on` = 저자가 상품을 이름으로 짚은 규칙의 대상 상품 필터(생략 = 전 상품)
  ($s·이름 심볼 names·across 는 폐지 — 여러 종목 중 N개는 atleast·of. 형식 검사가 거부한다.)
  `{"pos": "filled", "rule": 이름}`(그 규칙으로 산 횟수)은 그대로 건넨다 — 값은 체결 장부(trades)가 낸다.
"""
import json
import os
from collections import namedtuple

from dsl.tradeTool import Cond
from shared.paths import book_file

BLOCK, BUY, SELL = Cond.BLOCK, Cond.BUY, Cond.SELL
# 트리 v3 파일 형식(COND_DSL 1·5절) — 여기 밖의 키는 거부한다(옛 양식·오타를 조용히 무시하지 않는다).
TOP_KEYS = ("version", "products", "rules", "note")
PRODUCT_KEYS = ("index", "ref", "note")
# 책 폴더 안의 트리 파일 — 어느 트리(최종 None · 추출자 후보 "a"·"b")가 어느 파일인지는 여기 한 곳.
FILES = {None: "tree.json", "a": "tree_candidates/a.json", "b": "tree_candidates/b.json"}
RULE_KEYS = ("label", "ref", "note", "on", "value", "then", "skip", "why")
BRANCH_KEYS = ("when", "do", "qty", "repeat")
QTY_OF = {BUY: ("cash", "budget"), SELL: ("bought", "held")}   # 동사마다 쓸 수 있는 qty 종류(안 산다는 qty 없음)


def rule(label, do, when=None, qty=None, repeat=False, **meta):
    """합성 트리(검사용)의 행동 규칙 하나 — 갈래 하나짜리. qty = (of, x) 또는 None. meta = ref·note·on 등."""
    br = {"do": do}
    if when is not None:
        br["when"] = when
    if qty is not None:
        br["qty"] = {"of": qty[0], "x": qty[1]}
    if repeat:
        br["repeat"] = True
    return dict(meta, label=label, then=[br])


def synthetic(products, *rules, **top):
    """합성 트리(검사용, v3). products = 상품 티커 목록 또는 {상품: 기준지수 | None}. 규칙이 없으면 skip 하나를 둔다
    (v3 는 빈 rules 를 거부한다)."""
    items = products.items() if isinstance(products, dict) else [(p, None) for p in products]
    prods = {p: ({"index": ix} if ix else {}) for p, ix in items}
    return dict(top, version=3, products=prods,
                rules=list(rules) or [{"label": "(합성 — 규칙 없음)", "skip": "연산 없음: 합성 트리"}])


class Qty(namedtuple("Qty", "of x")):
    """'얼마나' — 정규화된 수량 (트리 v3 qty {of, x}). x = 수 · 식 · None(저자 미명시).
      of = "cash"(총 투자금의 x %) · "budget"(배정 금액의 x · 분할) · "bought"(산 물량의 x) · "held"(남은 물량의 x, 1=전량)"""
    __slots__ = ()


class Card(namedtuple("Card", "label ref note on value branches skip why")):
    """규칙 하나를 **적힌 그대로**(펼치지 않음 — {"rule"} 참조 그대로, 갈래의 "$value" 만 그 규칙 value 로) — 원시 트리 보기용.
    ref = 원문 소절 글자("·" 로 여럿) · on = 대상 상품 목록(None = 전부) · value = 이름 조건·측정(없으면 None)
    · branches = [CardBranch] · skip = 못 옮긴 사유(없으면 None) · why = 심판 기록."""
    __slots__ = ()


class CardBranch(namedtuple("CardBranch", "do when qty repeat")):
    """규칙 카드의 갈래 하나 — do = 동사 · when = 조건(적힌 그대로) · qty = Qty(of, x — x 는 적힌 그대로, "?" 포함) | None."""
    __slots__ = ()


class Branch:
    """갈래 하나(분할 차수·매도·비중)의 읽기 전용 값. 없는 필드는 None. qty = Qty(얼마나).
    repeat = 조건이 다시 맞을 때마다(판다 갈래만 — 기본은 한 번)."""
    __slots__ = ("label", "ref", "note", "when", "qty", "allprod", "repeat")

    def __init__(self, label=None, ref=None, note=None, when=None, qty=None, allprod=None, repeat=False):
        self.label, self.ref, self.note, self.when, self.qty = label, ref, note, when, qty
        self.allprod = allprod                   # 공통(on 없음) 규칙이면 True — 화면이 공통 섹션으로 모은다
        self.repeat = repeat


def _num(x):
    """'?' → None(저자 미명시), 그 외는 그대로."""
    return None if x in ("?", None) else x


def _qty(q, default=None, expand=lambda x: x):
    """트리 qty {of, x} → Qty(of, x) — x "?" 는 None, 식이면 펼친 식(expand). qty 가 없으면 default."""
    return Qty(q.get("of"), _num(expand(q.get("x")))) if q else default


class TreeGateway:
    """트리 하나(v3 규칙 목록). load/read/open/of 로 만들고 질문으로 읽는다.
    갈래를 do 동사로 골라 건네고, {"rule"} 참조는 펼쳐 건넨다."""

    def __init__(self, data):
        self._d = data or {}
        self._by_label = {r.get("label"): r for r in self._d.get("rules", []) if isinstance(r, dict)}

    def __bool__(self):
        return bool(self._d)

    # ---------------------------------------------------------------- 읽기
    @staticmethod
    def path(slug, which=None):
        """트리 파일 경로 — which = None(최종 tree.json) · "a"·"b"(추출자 후보). 모르는 이름이면 CondError."""
        if which not in FILES:
            raise Cond.CondError("모르는 트리 %r (허용 %s)" % (which, " · ".join(str(k) for k in FILES)))
        return book_file(slug, FILES[which])

    @classmethod
    def open(cls, path):
        return cls(json.load(open(path, encoding="utf-8")))

    @classmethod
    def read(cls, slug, which=None):
        p = cls.path(slug, which)
        return cls.open(p) if os.path.exists(p) else None

    @classmethod
    def load(cls, slug, which=None):
        t = cls.read(slug, which)
        if t is not None:
            t.validate()
        return t

    @classmethod
    def of(cls, data):
        t = cls(data)
        t.validate()
        return t

    # ---------------------------------------------------------------- 펼치기 ({"rule"} 참조)
    def _expand(self, node, seen=()):
        """조건식을 평가기가 바로 먹을 모양으로 — {"rule"} 펼침(pos 의 rule 은 장부 열쇠라 그대로)."""
        if isinstance(node, list):
            return [self._expand(x, seen) for x in node]
        if not isinstance(node, dict):
            return node
        if "pos" in node:                        # 포지션 값 — {"pos": "filled", "rule": 이름} 의 rule 은 참조가 아니라 장부 열쇠
            return dict(node)
        # bare {"rule": "이름"} → 그 규칙의 value(없으면 첫 갈래 when)
        if "rule" in node and set(node) - set(Cond.META) == {"rule"}:
            name = node["rule"]
            if name in seen:
                return {"manual": "연산 없음: 순환 참조 %s" % name}
            r = self._by_label.get(name)
            if not r:
                return {"manual": "연산 없음: 미해결 참조 %s" % name}
            tgt = r.get("value")
            if tgt is None and r.get("then"):
                tgt = r["then"][0].get("when")
            exp = self._expand(tgt if tgt is not None else {"all": []}, seen + (name,))
            # 참조한 규칙의 이름을 펼친 노드에 실어 화면이 "전고점 돌파" 로 보이게 한다(펼치며 이름을 떨구지 않음).
            if isinstance(exp, dict) and not exp.get("label"):
                exp = dict(exp, label=name)
                if node.get("ref") or r.get("ref"):
                    exp["ref"] = node.get("ref") or r.get("ref")
            return exp
        return {k: (v if k in Cond.META else self._expand(v, seen)) for k, v in node.items()}

    def _sub_value(self, node, val):
        """갈래의 `"$value"` 를 그 규칙의 value(이미 펼친 노드)로 치환."""
        if node == "$value":
            return val
        if isinstance(node, list):
            return [self._sub_value(x, val) for x in node]
        if isinstance(node, dict):
            return {k: (v if k in Cond.META else self._sub_value(v, val)) for k, v in node.items()}
        return node

    def _x_of(self, r):
        """규칙 r 의 qty.x 를 평가기가 먹을 모양으로 — 식이면 {"rule"} 참조를 펼치고 "$value" 를 r 의 value 로."""
        def ex(x):
            if not isinstance(x, (dict, list)):
                return x
            x = self._expand(x)
            return self._sub_value(x, self._expand(r["value"])) if "value" in r else x
        return ex

    def _on(self, r):
        """규칙의 대상 상품(생략 = None → 전부)."""
        on = r.get("on")
        return set(on) if on else None

    def _when_of(self, r, t):
        """규칙 r 의 갈래 t 의 when 을 평가기가 먹을 모양으로 — {"rule"} 펼치고 `"$value"` 를 r 의 value 로 치환."""
        w = t.get("when")
        if w is None:
            return None
        w = self._expand(w)
        if "value" in r:
            w = self._sub_value(w, self._expand(r["value"]))
        return w

    def _rules_for(self, prod):
        """이 상품에 적용되는 행동 규칙 (on 생략 = 전부)."""
        for r in self._d.get("rules", []):
            if "then" not in r:
                continue
            on = self._on(r)
            if on is None or prod in on:
                yield r

    # ---------------------------------------------------------------- 형식 검사 (v3, 느슨)
    def validate(self):
        tree = self._d
        if not isinstance(tree, dict):
            raise Cond.CondError("트리 파일은 객체여야 한다")
        if tree.get("version") != 3:
            raise Cond.CondError("version 3 트리만 읽는다 (받은 값 %r)" % tree.get("version"))
        if not isinstance(tree.get("products"), dict) or not tree["products"]:
            raise Cond.CondError("products 가 비어 있다")
        rules = tree.get("rules")
        if not isinstance(rules, list) or not rules:
            raise Cond.CondError("rules 가 비어 있다")
        self._check_shape(tree, rules)
        # 펼친 조건식의 문법만 검사({"rule"} 참조는 이미 펼쳐짐) + $index 를 쓰면 그 상품에 index 가 있어야 한다
        for prod in tree["products"]:
            for _do, label, _ref, node in self.expressions(prod):
                Cond.validate(node, "%s.%s" % (prod, label or _do))
                if not self.index(prod) and any(n.get("sym") == "$index" for n in Cond.labeled_all(node)
                                                if isinstance(n, dict) and "px" in n):
                    raise Cond.CondError("%s.%s: $index 를 쓰는데 products.%s 에 index 가 없다" % (prod, label or _do, prod))
        return True

    @staticmethod
    def _keys(obj, allowed, where):
        if not isinstance(obj, dict):
            raise Cond.CondError("%s: 객체여야 한다" % where)
        extra = sorted(set(obj) - set(allowed))
        if extra:
            raise Cond.CondError("%s: 모르는 키 %s (허용 %s)" % (where, extra, " · ".join(allowed)))

    def _check_shape(self, tree, rules):
        """파일 형식 — 맨 위·상품·규칙·갈래·qty 의 키와 값의 모양."""
        self._keys(tree, TOP_KEYS, "트리 맨 위")
        for p, v in tree["products"].items():
            self._keys(v, PRODUCT_KEYS, "products.%s" % p)
        targets = set(tree["products"])
        labels = set()
        for r in rules:
            self._keys(r, RULE_KEYS, "규칙 %r" % (r.get("label") if isinstance(r, dict) else r))
            lab = r.get("label")
            if not (isinstance(lab, str) and lab.strip()):
                raise Cond.CondError("규칙에 label(이름)이 없다: %r" % sorted(r))
            if lab in labels:
                raise Cond.CondError("규칙 label 이 책 안에서 유일하지 않다: %r" % lab)
            labels.add(lab)
            if "then" in r and "skip" in r:
                raise Cond.CondError("규칙 %r: then 과 skip 을 같이 쓸 수 없다" % lab)
            if "then" not in r and "skip" not in r and "value" not in r:
                raise Cond.CondError("규칙 %r: then(행동)·value(이름 조건)·skip(못 옮김) 중 하나가 필요하다" % lab)
            if "skip" in r and not (isinstance(r["skip"], str) and r["skip"].strip()):
                raise Cond.CondError("규칙 %r: skip 사유 문자열이 필요하다" % lab)
            bad_on = [x for x in (r.get("on") or []) if x not in targets]
            if bad_on:
                raise Cond.CondError("규칙 %r: on 의 %s 가 products 에 없다" % (lab, bad_on))
            if "then" in r and not (isinstance(r["then"], list) and r["then"]):
                raise Cond.CondError("규칙 %r: then 은 갈래 목록이어야 한다" % lab)
            if "value" in r:                       # 이름 조건은 참조되지 않아도 문법을 본다
                Cond.validate(self._expand(r["value"]), "규칙 %r value" % lab)
            for k, t in enumerate(r.get("then") or []):
                where = "규칙 %r 갈래 %d" % (lab, k)
                self._keys(t, BRANCH_KEYS, where)
                do = t.get("do")
                if do not in Cond.VERBS:
                    raise Cond.CondError("%s: 모르는 동사 %r (허용 %s)" % (where, do, " · ".join(Cond.VERBS)))
                if "when" not in t and not (do == BUY and t.get("qty")):
                    raise Cond.CondError("%s: when(조건)이 필요하다(조건 없는 갈래는 산다의 비중·1차 분할뿐)" % where)
                if "repeat" in t and (t["repeat"] is not True or do != SELL):
                    raise Cond.CondError("%s: repeat 은 판다 갈래에 true 로만(산다·안 산다의 반복은 연산 없음)" % where)
                q = t.get("qty")
                if q is not None:
                    self._keys(q, ("of", "x"), where + " qty")
                    if q.get("of") not in QTY_OF.get(do, ()):
                        raise Cond.CondError("%s: %s 갈래의 qty 종류는 %s (받은 값 %r)"
                                             % (where, do, " · ".join(QTY_OF.get(do, ())) or "없음", q.get("of")))
                    Cond.validate(self._x_of(r)(q.get("x")), where + " qty.x")

    # ---------------------------------------------------------------- 책·상품
    def _p(self, prod):
        return self._d["products"][prod]

    def products(self):
        return list(self._d["products"])

    def has(self, prod):
        return prod in self._d["products"]

    def index(self, prod):
        """상품의 기준 지수 티커 — `$index` 가 채워지는 값(없으면 None)."""
        return self._p(prod).get("index")

    def note(self, prod):
        return self._p(prod).get("note")

    def skips(self):
        """못 옮긴 규칙(skip) [{rule, ref, reason}]."""
        return [{"rule": r.get("label"), "ref": r.get("ref"), "reason": r["skip"]}
                for r in self._d.get("rules", []) if "skip" in r]

    # ---------------------------------------------------------------- 동사별 갈래
    def gate(self, prod, do):
        """등급 동사(안 산다·산다)의 갈래 any 묶음 — 갈래 하나라도 참이면 그 동사.
        등급은 포지션 독립이라 pos 쓰는 갈래(분할 2차+·보유 조건)는 뺀다 — 그것은 tranches·sells 가 본다."""
        if do not in Cond.GATES:
            raise Cond.CondError("등급 동사가 아님 %r (허용 %s)" % (do, " · ".join(Cond.GATES)))
        members = []
        for r in self._rules_for(prod):
            for t in r.get("then", []):
                if t.get("do") != do or "when" not in t:
                    continue
                w = self._when_of(r, t)
                if Cond._uses_pos(w):                    # 포지션 조건(분할 2차+)은 등급 밖 — tranches 가 본다
                    continue
                if isinstance(w, dict):                  # 규칙 이름·소절·공통 여부를 붙여 화면이 '무슨 규칙'인지 보이게
                    w = dict(w, label=r.get("label"), ref=r.get("ref"), allprod=not r.get("on"))
                members.append(w)
        return {"any": members}

    def _qty_branches(self, prod, do, of=None):
        """이 상품의 do 갈래 [(규칙, 갈래)] — of 를 주면 qty 종류가 그것인 갈래만(qty 를 고르기만 한다 — 변환 아님)."""
        return [(r, t) for r in self._rules_for(prod) for t in r.get("then", [])
                if t.get("do") == do and (of is None or (t.get("qty") or {}).get("of") == of)]

    def weight(self, prod):
        """비중 — 산다 갈래 중 qty cash 의 첫 갈래(Qty cash). 없으면 qty.x None 인 빈 Branch."""
        for r, t in self._qty_branches(prod, BUY, "cash"):
            return Branch(r.get("label"), r.get("ref"), r.get("note"), qty=_qty(t["qty"], expand=self._x_of(r)))
        return Branch(qty=Qty("cash", None))

    def tranches(self, prod):
        """분할 차수 — 산다 갈래 중 qty budget. 1차(산횟수 조건 없는 것)는 when None."""
        return [Branch(r.get("label"), r.get("ref"), r.get("note"), when=self._when_of(r, t),
                     qty=_qty(t["qty"], expand=self._x_of(r)), allprod=not r.get("on"))
                for r, t in self._qty_branches(prod, BUY, "budget")]

    def sells(self, prod):
        """판다 갈래 [Branch(when, qty bought/held)] — qty 없으면 남은 전량. 없으면 [](trades.exit_policy 가 정책을 정한다)."""
        return [Branch(r.get("label"), r.get("ref"), r.get("note"), when=self._when_of(r, t),
                     qty=_qty(t.get("qty"), Qty("held", 1.0), self._x_of(r)), allprod=not r.get("on"),
                     repeat=bool(t.get("repeat")))
                for r, t in self._qty_branches(prod, SELL)]

    def expressions(self, prod):
        """상품 하나의 모든 식 [(동사, 라벨, ref, 식)] — 심볼·워밍업·ref 훑기용(등급 묶음은 라벨 None)."""
        out = [(do, None, None, self.gate(prod, do)) for do in Cond.GATES]
        for t in self.tranches(prod):
            if t.when is not None:
                out.append((BUY, t.label, t.ref, t.when))
        w = self.weight(prod)
        if w.qty.x is not None:
            out.append((BUY, w.label, w.ref, w.qty.x))
        for r in self.sells(prod):
            out.append((SELL, r.label, r.ref, r.when))
        return out

    # ---------------------------------------------------------------- 트리 전체 훑기
    def _all_nodes(self):
        nodes = []
        for p in self._d["products"]:
            nodes.extend(n for _z, _l, _r, n in self.expressions(p))
        return nodes

    def symbols(self, prods=None):
        """트리가 참조하는 실제 심볼 전부 — 상품 · 그 상품의 지수 · 식의 구체 티커($self·$index 는 위 둘로 채워짐)."""
        out = set()

        def walk(n):
            if isinstance(n, dict):
                if "px" in n and n.get("sym") not in Cond.ROLES:
                    out.add(n.get("sym"))
                for k, x in n.items():
                    if k not in Cond.META:
                        walk(x)
            elif isinstance(n, list):
                for x in n:
                    walk(x)

        for p in (self._d["products"] if prods is None else prods):
            out.add(p)
            if self.index(p):
                out.add(self.index(p))
            for _z, _l, _r, node in self.expressions(p):
                walk(node)
        out.discard(None)
        return out

    def minute_symbols(self):
        out = set()
        for node in self._all_nodes():
            for n in Cond.labeled_all(node):
                if not (isinstance(n, dict) and "px" in n and n.get("tf") in ("1m", "5m")):
                    continue
                s = n.get("sym")
                if s == "$self":
                    out.update(self._d["products"])
                elif s == "$index":
                    out.update(self.index(p) for p in self._d["products"])
                else:
                    out.add(s)
        out.discard(None)
        return out

    def timeframes(self):
        return {n.get("tf", "1d") for node in self._all_nodes() for n in Cond.labeled_all(node)
                if isinstance(n, dict) and "px" in n}

    def warmup(self, prod=None):
        mx = 0
        for p in [prod] if prod is not None else self._d["products"]:
            for do in Cond.GATES:
                mx = max(mx, Cond.warmup_of(self.gate(p, do)))
        return mx

    def refs(self):
        """트리가 근거로 단 원문 소절 전부 — 규칙·상품의 ref("·" 로 여럿)."""
        out = set()
        items = list(self._d.get("rules", [])) + list(self._d["products"].values())
        for r in items:
            rf = r.get("ref")
            if isinstance(rf, str):
                out.update(x.strip() for x in rf.replace(",", "·").split("·") if x.strip())
            elif isinstance(rf, list):
                out.update(rf)
        return out

    # ---------------------------------------------------------------- 규칙 단위(구간② 검사기 — a·b 비교·심판 채점)
    def labels(self):
        """규칙 이름 목록(파일 순서)."""
        return [r.get("label") for r in self._d.get("rules", [])]

    def body(self, label, expand=True):
        """규칙 하나의 '뜻'(이름·출처·메모·why 를 뺀 것) — {products, value, branches[{do, when, qty}], skip}.
        expand=True 면 {"rule"} 참조를 펼친 식(a·b 가 이름을 달리 지어도 뜻이 같으면 같다), False 면 적힌 그대로
        (같은 측정을 참조 없이 두 번 쓴 '두 벌'을 가린다). 같은 뜻인지 가리는 비교용(구간② 검사기). 없는 이름이면 None."""
        r = self._by_label.get(label)
        if r is None:
            return None
        ex = self._expand if expand else (lambda n: n)
        return {"products": sorted(r.get("on") or []), "value": ex(r["value"]) if "value" in r else None,
                "branches": [{"do": t.get("do"), "when": (self._when_of(r, t) if expand else t.get("when")),
                              "qty": t.get("qty")} for t in r.get("then", [])],
                "skip": r.get("skip")}

    def value(self, label, expand=True):
        """규칙의 측정(value) — 없으면 None. expand=False 면 적힌 그대로({"rule"} 참조를 펼치지 않음)."""
        r = self._by_label.get(label) or {}
        if "value" not in r:
            return None
        return self._expand(r["value"]) if expand else r["value"]

    def why(self, label):
        """심판이 그 규칙을 a·b 중 고른 이유(최종 트리만) — 없으면 None."""
        return (self._by_label.get(label) or {}).get("why")


    def cards(self):
        """규칙 카드 [Card](파일 순서) — 판정 로직(동사별 재배치·등급·펼치기) 안 거친 트리 1:1. 원시 트리 보기(화면)용."""
        out = []
        for r in self._d.get("rules", []):
            if not isinstance(r, dict):
                continue
            val = r.get("value")
            brs = [CardBranch(t.get("do"),
                              self._sub_value(t["when"], val) if ("when" in t and val is not None) else t.get("when"),
                              Qty((t.get("qty") or {}).get("of"), (t.get("qty") or {}).get("x")) if t.get("qty") else None,
                              bool(t.get("repeat")))
                   for t in r.get("then") or [] if isinstance(t, dict)]
            out.append(Card(r.get("label"), r.get("ref"), r.get("note"), r.get("on"), val, brs, r.get("skip"), r.get("why")))
        return out

    def conditions(self):
        """트리에 적힌 조건식 전부(펼치기 전, 적힌 그대로) — 규칙의 value·갈래 when·qty 식. 검사기가 수동 잎의
        이름·사유를 훑는 용도(파일 키는 모른 채 조건 문법만 본다)."""
        out = []
        for r in self._d.get("rules", []):
            if "value" in r:
                out.append(r["value"])
            for t in r.get("then", []):
                if "when" in t:
                    out.append(t["when"])
                if isinstance((t.get("qty") or {}).get("x"), dict):
                    out.append(t["qty"]["x"])
        return out
