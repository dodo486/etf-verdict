#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TreeGateway — 조건 트리(books/<slug>/tree.json)를 읽는 유일한 출입구 (구간② 소유, 책 무관).

왜 있나
  트리의 키 배치를 아는 코드가 판정·백테스트·검사기 곳곳에 흩어지지 않게, 원본 키를 만지는 코드는 이 파일 하나다.
  나머지(판정 엔진·백테스트·화면)는 여기에 '질문'만 한다. 직접 접근은 verify/verify_code 주인 표가 막는다.

트리 v3 (규칙 목록) — 바깥 API 는 그대로
  파일은 `rules` 목록(원문 판단 하나 = 규칙 하나, 동사 셋 안 산다·산다·판다)이지만, 소비자는 옛 API 그대로 쓴다:
  section(filter/entry/avoid)·cautions·sizing·tranches·exit_rules. 이 파일이 do 동사를 그 칸 모양으로 **번역**한다.
    · 안 산다 → avoid(any 걸림 → 사지 않음)          · 산다 → entry(any 걸림 → 매수 후보) + 분할(qty budget) → tranches
    · 판다  → exit_rules(qty held/bought → sell)      · filter 는 항상 참(시장 게이트도 '안 산다'로 흡수)
  `{"rule": "이름"}` 참조와 이름 심볼(`$빅테크` 등 names)은 건네기 전에 **펼친다** — 평가기(Cond)는 평범한 식만 본다.
  `{"pos": "filled"/"sold", "rule": ...}` 는 pos 값만 남긴다(포지션이 없으면 None → 그 갈래 안 침 — 정직한 degrade).
"""
import json
import os
from collections import namedtuple

from dsl.tradeTool import Cond
from shared.paths import book_file

TREE_TOP = ("version", "products", "names", "rules", "note",
            "defs", "source", "unexpressed", "review")   # 뒤 4개는 옛 v2 호환(읽기만)
PRODUCT_KEYS = ("index", "ref", "note", "exit_note")
DO_VERBS = ("안 산다", "산다", "판다")
# 옛 v2 이름들(합성 트리·검사기 호환용 — v3 에선 안 쓰지만 import 가 깨지지 않게 남긴다)
EMPTY_ZONE = {"filter": {"all": []}, "entry": {"all": []}, "avoid": {"any": []},
              "caution": [], "sizing": {"weight": None, "tranches": []}, "exit": []}


def empty_product(**zones):
    return dict(EMPTY_ZONE, **zones)


def synthetic(products, **top):
    return dict(top, products=products)


class Qty(namedtuple("Qty", "of x")):
    """'얼마나' — 정규화된 수량 (트리 v3 qty {of, x}). x = 수 · 식 · None(저자 미명시).
      of = "cash"(총 투자금의 x %) · "budget"(배정 금액의 x · 분할) · "bought"(산 물량의 x) · "held"(남은 물량의 x, 1=전량)"""
    __slots__ = ()


def _qty(raw):
    """합성한 v2 모양 규칙(sell·frac·weight)의 수량 → Qty. 없으면 None."""
    if "sell" in raw:
        sell = raw["sell"]
        if sell == "all":
            return Qty("held", 1.0)
        (k, x), = sell.items()
        return Qty("bought" if k == "initial" else "held", x)
    for k, of in (("frac", "budget"), ("weight", "cash")):
        if k in raw:
            return Qty(of, raw[k])
    return None


class Rule:
    """규칙 하나(분할 차수·매도·비중)의 읽기 전용 값. 없는 필드는 None. qty = Qty(얼마나)."""
    __slots__ = ("label", "ref", "note", "when", "qty", "allprod", "_raw")

    def __init__(self, raw):
        self._raw = raw
        for k in ("label", "ref", "note", "when"):
            setattr(self, k, raw.get(k))
        self.allprod = raw.get("allprod")       # 공통(on 없음) 규칙이면 True — 화면이 공통 섹션으로 모은다
        self.qty = _qty(raw)

    def shown(self, *keys):
        return {k: self._raw[k] for k in keys if k in self._raw}

    def raw(self):
        return self._raw

    def with_when(self, when):
        return Rule(dict(self._raw, when=when))


def _qty_to_sell(q):
    """판다 규칙 qty(dict {of,x}) → 옛 sell 모양. x '?'·None = 비율 미명시."""
    if not q:
        return "all"
    x = _num(q.get("x"))
    if q.get("of") == "bought":
        return {"initial": x}
    if q.get("of") == "held" and x == 1:
        return "all"
    return {"remaining": x}


def _num(x):
    """'?' → None(저자 미명시), 그 외는 그대로."""
    return None if x in ("?", None) else x


class TreeGateway:
    """트리 하나(v3 규칙 목록). load/read/open/of 로 만들고 질문으로 읽는다.
    v3 rules 를 읽어 do 동사를 옛 칸 API 로 번역하고, {"rule"}·이름 심볼을 펼쳐 건넨다."""

    def __init__(self, data):
        self._d = data or {}
        self._by_label = {r.get("label"): r for r in self._d.get("rules", []) if isinstance(r, dict)}
        self._names = self._d.get("names") or {}

    def __bool__(self):
        return bool(self._d)

    # ---------------------------------------------------------------- 읽기
    @staticmethod
    def path(slug, name="tree.json"):
        return book_file(slug, name)

    @classmethod
    def open(cls, path):
        return cls(json.load(open(path, encoding="utf-8")))

    @classmethod
    def read(cls, slug, name="tree.json"):
        p = cls.path(slug, name)
        return cls.open(p) if os.path.exists(p) else None

    @classmethod
    def load(cls, slug, name="tree.json"):
        t = cls.read(slug, name)
        if t is not None:
            t.validate()
        return t

    @classmethod
    def of(cls, data):
        t = cls(data)
        t.validate()
        return t

    @staticmethod
    def as_rules(raw):
        return [Rule(r) for r in raw]

    # ---------------------------------------------------------------- 펼치기 ({"rule"}·이름 심볼)
    def _syms_of(self, name, seen=()):
        """이름 심볼($빅테크) → 실제 티커 목록(중첩 이름은 재귀로 평탄화)."""
        if name in seen:
            return []
        out = []
        for s in (self._names.get(name) or {}).get("syms", []):
            if isinstance(s, str) and s.startswith("$") and s in self._names:
                out.extend(self._syms_of(s, seen + (name,)))
            else:
                out.append(s)
        return out

    def _expand(self, node, seen=()):
        """조건식을 평가기가 바로 먹을 모양으로 — {"rule"} 펼침, pos 의 rule 제거, across 의 이름 심볼 평탄화."""
        if isinstance(node, list):
            return [self._expand(x, seen) for x in node]
        if not isinstance(node, dict):
            return node
        # {"pos": ..., "rule": ...} → pos 값만 (포지션 없으면 None → 갈래 안 침)
        if "pos" in node:
            return {"pos": node["pos"]}
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
        if "across" in node and isinstance(node["across"], dict):
            ac = dict(node["across"])
            syms = []
            for s in ac.get("syms") or []:
                if isinstance(s, str) and s.startswith("$") and s in self._names:
                    syms.extend(self._syms_of(s))
                else:
                    syms.append(s)
            ac["syms"] = syms
            if "cond" in ac:
                ac["cond"] = self._expand(ac["cond"], seen)
            return {"across": ac}
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

    def _when_of(self, r, t):
        """규칙 r 의 갈래 t 의 when 을 평가기가 먹을 모양으로 — {"rule"}·이름심볼 펼치고 `"$value"` 를 r 의 value 로 치환."""
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
            on = r.get("on")
            if not on or prod in on:
                yield r

    def _whens(self, prod, do):
        """이 상품의 do 갈래들의 (펼친) when 목록."""
        out = []
        for r in self._rules_for(prod):
            for t in r.get("then", []):
                if t.get("do") == do and "when" in t:
                    out.append(self._expand(t["when"]))
        return out

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
        labels = [r.get("label") for r in rules if isinstance(r, dict)]
        if len(labels) != len(set(labels)):
            raise Cond.CondError("규칙 label 이 책 안에서 유일하지 않다")
        # 펼친 조건식의 문법만 검사(참조·이름 심볼은 이미 펼쳐짐)
        for prod in tree["products"]:
            for sec in Cond.SECTIONS:
                Cond.validate(self.section(prod, sec), {}, "products.%s.%s" % (prod, sec))
        return True

    # ---------------------------------------------------------------- 책·상품
    def _p(self, prod):
        return self._d["products"][prod]

    def products(self):
        return list(self._d["products"])

    def has(self, prod):
        return prod in self._d["products"]

    def index(self, prod):
        return self._p(prod).get("index")

    def note(self, prod):
        return self._p(prod).get("note")

    def book(self, default=None):
        return self._d.get("book", (self._d.get("source") or {}).get("book", default))

    def defs(self):
        """v3 는 {"rule"} 를 미리 펼치므로 평가기에 넘길 def 표는 비어 있다."""
        return {}

    def unexpressed(self):
        """못 옮긴 규칙 [{rule, ref, reason}] — v3 의 skip 규칙을 옛 모양으로."""
        out = []
        for r in self._d.get("rules", []):
            if "skip" in r:
                out.append({"rule": r.get("label"), "ref": r.get("ref"), "reason": r["skip"]})
        out.extend(self._d.get("unexpressed") or [])
        return out

    # ---------------------------------------------------------------- 칸·규칙 (do → 칸 번역)
    def section(self, prod, sec):
        """조건 칸 — filter 는 항상 참, avoid = 안 산다 갈래 any, entry = 산다 갈래 any.
        등급 칸은 포지션 독립이라 pos 쓰는 갈래(분할 2차+·보유 조건)는 뺀다 — 그것은 tranches·exit 가 본다."""
        if sec == "filter":
            return {"all": []}
        if sec in ("avoid", "entry"):
            do = "안 산다" if sec == "avoid" else "산다"
            members = []
            for r in self._rules_for(prod):
                for t in r.get("then", []):
                    if t.get("do") != do or "when" not in t:
                        continue
                    w = self._when_of(r, t)
                    if Cond._uses_pos(w, {}):            # 포지션 조건(분할 2차+)은 등급 칸 밖 — tranches 가 본다
                        continue
                    if isinstance(w, dict):              # 규칙 이름·소절·공통 여부를 붙여 화면이 '무슨 규칙'인지 보이게
                        w = dict(w, label=r.get("label"), ref=r.get("ref"), allprod=not r.get("on"))
                    members.append(w)
            return {"any": members}
        raise Cond.CondError("모르는 칸 %r" % sec)

    def cautions(self, prod):
        """v3 엔 조심 칸이 없다(조심 = 안 산다로 흡수) — 항상 []."""
        return []

    def sizing(self, prod):
        """비중 — 산다 갈래 중 qty.of='cash' 가 있으면 그 식, 없으면 None."""
        for r in self._rules_for(prod):
            for t in r.get("then", []):
                q = t.get("qty")
                if t.get("do") == "산다" and q and q.get("of") == "cash":
                    return Rule({"label": r.get("label"), "ref": r.get("ref"), "weight": _num(q.get("x"))})
        return Rule({"weight": None})

    def tranches(self, prod):
        """분할 차수 — 산다 갈래 중 qty.of='budget'. 1차(산횟수 조건 없는 것)는 when None."""
        out = []
        for r in self._rules_for(prod):
            for t in r.get("then", []):
                q = t.get("qty")
                if t.get("do") == "산다" and q and q.get("of") == "budget":
                    out.append(Rule({"label": r.get("label"), "ref": r.get("ref"), "allprod": not r.get("on"),
                                     "frac": _num(q.get("x")), "when": self._when_of(r, t)}))
        return out

    def exit_rules(self, prod):
        """판다 규칙 [Rule(when, qty=held/bought)] — 없으면 [](trades.exit_policy 가 정책을 정한다)."""
        out = []
        for r in self._rules_for(prod):
            for t in r.get("then", []):
                if t.get("do") == "판다":
                    out.append(Rule({"label": r.get("label"), "ref": r.get("ref"), "allprod": not r.get("on"),
                                     "when": self._when_of(r, t), "sell": _qty_to_sell(t.get("qty"))}))
        return out

    def expressions(self, prod):
        """상품 하나의 모든 식 [(칸, 라벨, ref, 식)] — 심볼·워밍업·ref 훑기용."""
        out = [(sec, None, None, self.section(prod, sec)) for sec in Cond.SECTIONS]
        for t in self.tranches(prod):
            if t.when is not None:
                out.append(("sizing", t.label, t.ref, t.when))
        w = self.sizing(prod)
        if w.qty and w.qty.x is not None:
            out.append(("sizing", w.label, w.ref, w._raw["weight"]))
        for r in self.exit_rules(prod):
            out.append(("exit", r.label, r.ref, r.when))
        return out

    def scenario_node(self, prod, sec, rule=None):
        if not self.has(prod):
            return None
        if sec in Cond.SECTIONS:
            return self.section(prod, sec)
        return None

    # ---------------------------------------------------------------- 트리 전체 훑기
    def _all_nodes(self):
        nodes = []
        for p in self._d["products"]:
            nodes.extend(n for _z, _l, _r, n in self.expressions(p))
        return nodes

    def symbols(self, prods=None):
        """트리가 참조하는 실제 심볼 전부(상품·지수·펼친 식의 티커)."""
        out = set()

        def walk(n):
            if isinstance(n, dict):
                if "px" in n:
                    s = n.get("sym", "$self")
                    if not s.startswith("$"):
                        out.add(s)
                if "across" in n and isinstance(n["across"], dict):
                    out.update(s for s in (n["across"].get("syms") or []) if not str(s).startswith("$"))
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
        defs = {}
        out = set()
        for node in self._all_nodes():
            for n in Cond.labeled_all(node, defs):
                if not (isinstance(n, dict) and "px" in n and n.get("tf") in ("1m", "5m")):
                    continue
                s = n.get("sym", "$self")
                if s.startswith("$"):
                    out.update(self.index(p) if s == "$index" else p for p in self._d["products"])
                else:
                    out.add(s)
        out.discard(None)
        return out

    def timeframes(self):
        defs = {}
        return {n.get("tf", "1d") for node in self._all_nodes() for n in Cond.labeled_all(node, defs)
                if isinstance(n, dict) and "px" in n}

    def warmup(self, prod=None):
        mx = 0
        for p in [prod] if prod is not None else self._d["products"]:
            for sec in Cond.SECTIONS:
                mx = max(mx, Cond.warmup_of(self.section(p, sec), {}))
        return mx

    def refs(self):
        out = set()
        for r in self._d.get("rules", []):
            rf = r.get("ref")
            if isinstance(rf, str):
                out.update(x.strip() for x in rf.replace(",", "·").split("·") if x.strip())
            elif isinstance(rf, list):
                out.update(rf)
        return out

    def def_users(self):
        """v3 엔 defs 가 없다 — 공유는 {"rule"} 참조로, 호환용 빈 dict."""
        return {}

    # ---------------------------------------------------------------- 심판 기록(review) — 구간② 검사기만
    def _review(self):
        return self._d.get("review") or {}

    def review_sections(self):
        return self._review().get("sections") or {}

    def review_exits(self):
        return self._review().get("exits") or {}

    def scenario_overrides(self):
        return self._review().get("scenario_overrides") or {}

    def fire_ack(self):
        return self._review().get("fire_ack") or {}

    # ---------------------------------------------------------------- 원본 그대로(덤프·훑기 전용)
    def raw_defs(self):
        return None

    def raw_product(self, prod):
        return self._p(prod)

    def raw_zone(self, prod, zone):
        return self.section(prod, zone) if zone in Cond.SECTIONS else None

    def rules(self):
        """v3 규칙 원본 목록 — 사람이 읽는 렌더·심판 덤프 전용."""
        return self._d.get("rules", [])

    def whole(self):
        return self._d
