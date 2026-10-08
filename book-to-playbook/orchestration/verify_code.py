#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""코드 규칙 검사 — 폴더 경계 + 주인 표. 코드만 본다(책 산출물·시세 무관).

## 왜 있나

① 폴더 = 조직도. 팀 코드가 다른 팀의 '속'을 import 하는 순간 "한 검사기 안의 정의를 다른 검사기가 몰래 빌려 쓰다
갈라지는" 사고로 돌아간다. 그래서 무엇을 import 해도 되는지를 층마다 한 줄로 정해 둔다(IMPORTS).
  · playbook/      구간① 책 원본 → 전사본(플레이북)
  · checklist/     구간② 전사본 → 조건 트리(tree.json) + 그 트리의 언어(DSL: 출입구·문법·등급의 뜻)
  · trading/       구간③ 판정 · 백테스트 · 장중(Judge·signal_series·체결 워크·계산기·알림)
  · shared/        공통층 — 시세 창구(md_feed)·경로(paths)뿐
  · web/           화면층 — 판정·백테스트 결과를 화면 모양으로 빚고 서빙(판정을 다시 내지 않는다)
  · orchestration/ 조립·감사층(run 러너·이 검사 — 전 구간을 실행·검사만)

② 결정 하나 = 주인 하나. 같은 결정(트리 키 배치·책 산출물 경로·매도 정책·칸/등급 이름표·등급 사다리…)이 두 곳에
적히면 한쪽만 고쳐져 갈라진다. 그래서 개념마다 주인 파일과 '주인 밖에서 보이면 안 되는 표식'을 표 하나(OWNERS)에 적는다.

## 무엇을 강제하나

  폴더 경계
  규칙 1  층마다 import 해도 되는 층(IMPORTS). 흐름은 한 방향이다 — 아래(shared)는 위를 모르고, 구간②는 구간③·화면을,
          구간③은 화면을 모른다:
            playbook  → shared
            checklist → shared
            trading   → shared · checklist 공개 DSL
            web       → shared · checklist 공개 DSL · trading
            shared    → (없음)
            orchestration → 전부(단 checklist 는 공개 DSL 만)
          checklist 공개 DSL = PUBLIC_DSL 한 목록(tree_gateway·cond·grade). checklist 의 다른 모듈(검사기 등)은
          어느 층도 import 하지 않는다.
  규칙 2  `import jhts` 는 **shared/md_feed.py 하나**에서만 허용된다 — 파이프라인의 시세는 jhts 창구로만 들어온다.
  규칙 3  네트워크 모듈(urllib·http·requests·socket·aiohttp·httpx) import 금지 — 시세 자가수집이 다시 자라나는
          길목을 막는다. 명시 예외(ALLOW)만: 알림 송신 trading/notify.py, 로컬 서빙 web/serve.py.

  주인 표(OWNERS) — 한 줄 = 개념 · 주인 파일 · 주인 밖 금지 표식(매처) · 사유 · 명시 예외
          (everywhere = 주인 안까지 포함해 어디서도 안 되는 표식 — 폐지된 결정이 되살아나지 않게).
          파이썬은 AST(식별자·docstring 아닌 문자열 상수)로, web/ui/*.js 는 주석을 뗀 코드·문자열 리터럴로 본다
          (주석·docstring 의 설명 글은 걸리지 않는다). 이 파일은 표 자신이라 표식 검사에서 뺀다.
          예외는 행의 allow 한 곳에만 — {(파일, 함수|None): (표식 묶음|None=전부, 사유)}.

## 사용

    python -m orchestration.verify_code   # 위반 있으면 exit 1 (orchestration.run 의 검사 목록 CHECKS 에 포함)
"""
import ast
import os
import re
import sys

from shared import paths  # noqa: F401  (경로·UTF-8 출력 고정)
from shared.paths import BASE

TEAMS = ("playbook", "checklist", "trading")
LAYERS = TEAMS + ("shared", "web", "orchestration")

# 규칙 1 — 층마다 import 해도 되는 층. "checklist" 는 공개 DSL(PUBLIC_DSL)만 뜻한다(자기 팀 checklist 는 전부).
IMPORTS = {
    "playbook": {"playbook", "shared"},
    "checklist": {"checklist", "shared"},
    "trading": {"trading", "shared", "checklist"},
    "web": {"web", "shared", "checklist", "trading"},
    "shared": {"shared"},
    "orchestration": set(LAYERS),
}
# 구간②의 공개 DSL — 다른 층이 import 해도 되는 checklist 모듈은 이 목록뿐(한 곳).
PUBLIC_DSL = ("checklist.tree_gateway", "checklist.tradeTool")

# 시세 자가수집에 쓰이는 모듈들 — 보이면 그 자체로 위반.
NET_MODULES = {"urllib", "http", "requests", "socket", "aiohttp", "httpx"}

# 규칙 2·3 의 명시적 예외 — 예외는 여기 한 곳에만 적는다(코드 곳곳에 흩지 않는다).
ALLOW = {
    ("shared", "md_feed.py"): {"jhts"},                     # 유일한 시세 창구
    ("trading", "notify/telegram.py"): {"urllib"},          # 알림 '송신' 전용(수집 아님) — 구간③ 소유, 이 한 파일만
    ("web", "serve.py"): {"http", "urllib"},                # 로컬 서버(서빙·URL 파싱)
}


# ------------------------------------------------------------------ 소스 읽기(파이썬 AST · JS 토큰)
class Src:
    """검사 대상 파일 하나 — rel("web/ui/x.js"), kind("py"|"js"), py 면 tree(AST), js 면 code(주석 뗀 코드)·lits[(줄, 문자열)]."""

    def __init__(self, rel, kind, text):
        self.rel, self.kind = rel, kind
        self.tree = self.code = None
        self.lits = []
        if kind == "py":
            self.tree = ast.parse(text)
        else:
            self.code, self.lits = _js_scan(text)


def _js_scan(text):
    """JS → (주석을 공백으로 바꾼 코드, [(줄, 문자열 리터럴 내용)]). 정규식 리터럴은 앞 글자로 가려 건너뛴다."""
    out, lits, i, n, line = [], [], 0, len(text), 1
    prev = ""                                   # 공백 아닌 직전 코드 글자(정규식 리터럴 판별)
    while i < n:
        c = text[i]
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            seg = text[i:j]
            out.append("".join(ch if ch == "\n" else " " for ch in seg))
            line += seg.count("\n")
            i = j
            continue
        if c in "'\"`":
            j, buf = i + 1, []
            while j < n and text[j] != c:
                if text[j] == "\\":
                    buf.append(text[j:j + 2])
                    j += 2
                    continue
                buf.append(text[j])
                j += 1
            seg = text[i:j + 1]
            lits.append((line, "".join(buf)))
            out.append(seg)
            line += seg.count("\n")
            i = j + 1
            prev = c
            continue
        if c == "/" and (prev == "" or prev in "(,=:[!&|?{};+-*%<>~^"):
            j, cls = i + 1, False
            while j < n and text[j] != "\n":
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "[":
                    cls = True
                elif text[j] == "]":
                    cls = False
                elif text[j] == "/" and not cls:
                    break
                j += 1
            out.append(text[i:j + 1])
            i = j + 1
            prev = "/"
            continue
        out.append(c)
        if c == "\n":
            line += 1
        elif not c.isspace():
            prev = c
        i += 1
    return "".join(out), lits


def _py_nodes(tree):
    """[(노드, 가장 안쪽 def 이름)] 전부 — docstring 상수는 뺀다."""
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    out = []

    def visit(node, fn):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = node.name
        if id(node) not in docs:
            out.append((node, fn))
        for child in ast.iter_child_nodes(node):
            visit(child, fn)
    visit(tree, None)
    return out


def _py_strs(src):
    """[(줄, 함수, 문자열)] — docstring 아닌 문자열 상수."""
    return [(n.lineno, fn, n.value) for n, fn in _py_nodes(src.tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _py_names(src):
    """[(줄, 함수, 이름)] — 변수·속성 이름."""
    out = []
    for n, fn in _py_nodes(src.tree):
        if isinstance(n, ast.Name):
            out.append((n.lineno, fn, n.id))
        elif isinstance(n, ast.Attribute):
            out.append((n.lineno, fn, n.attr))
    return out


def _js_hits(src, regex):
    """주석 뗀 JS 코드에서 정규식이 걸린 [(줄, 걸린 글자)]."""
    return [(src.code.count("\n", 0, m.start()) + 1, m.group(0)) for m in re.finditer(regex, src.code)]


# ------------------------------------------------------------------ 주인 표의 매처 — Src → [(줄, 함수, 표식)]
# 트리 원본 키 — tree.json 의 구조 키(COND_DSL 5절 파일 형식)를 첨자([..])·.get/.pop/.setdefault 로 읽는 자리.
TREE_KEYS = {"products", "defs", "filter", "avoid", "entry", "caution", "sizing", "exit", "tranches", "sell",
             "scale", "weight", "frac", "unexpressed", "review", "source", "sections_read", "exit_note"}


def m_tree_keys(src):
    if src.kind != "py":
        return []
    out = []
    for node, fn in _py_nodes(src.tree):
        key = None
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) \
                and isinstance(node.slice, ast.Constant) and node.slice.value in TREE_KEYS:
            key = node.slice.value
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ("get", "pop", "setdefault") and node.args \
                and isinstance(node.args[0], ast.Constant) and node.args[0].value in TREE_KEYS:
            key = node.args[0].value
        if key:
            out.append((node.lineno, fn, key))
    return out


# 책 산출물 경로 — os.path.join(…, "books", …) 와 옛 루트 산출물 이름 조각.
OLD_ARTIFACTS = ("-playbook.html", "latest-verdict", "backtest-%s", "disagree-%s")


def m_book_paths(src):
    if src.kind != "py":
        return []
    out = []
    for n, fn in _py_nodes(src.tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "join" \
                and any(isinstance(a, ast.Constant) and isinstance(a.value, str)
                        and (a.value == "books" or a.value.startswith("books/")) for a in n.args):
            out.append((n.lineno, fn, 'os.path.join 에 "books"'))
    for line, fn, v in _py_strs(src):
        hit = [x for x in OLD_ARTIFACTS if x in v]
        if hit:
            out.append((line, fn, "옛 산출물 이름 %s" % hit[0]))
    return out


# 매도 정책 — 책에 매도 규칙이 없으면 어떻게 하나(정본 trades.exit_policy: "book" | "none" = 매수 신호만 평가).
#   폐지된 '표준 매도'(대체 매도 규칙·그 숫자 파일·출처 글자·화면 플래그)의 이름은 주인 포함 어디서도 다시 쓰지 않는다.
STD_GONE = ("STANDARD", "exit_defaults", "standard_label", "uses_standard_exit", "exit_standard",
            "standard_exit_label", "exits_of", "exit_source")
STD_GONE_TEXT = ("표준 기준", "표준 매도")


def m_exit_policy(src):
    """주인 밖 — 매도 정책 함수(exit_policy)를 또 정의하는 자리."""
    if src.kind == "py":
        return [(n.lineno, n.name, n.name) for n, _ in _py_nodes(src.tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "exit_policy"]
    return [(ln, None, x) for ln, x in _js_hits(src, r"\bfunction\s+exit_?[pP]olicy\s*\(")]


def m_std_exit_gone(src):
    """어디서든(주인 포함) — 폐지된 표준 매도의 이름·문구."""
    if src.kind == "py":
        return ([(ln, f, x) for ln, f, x in _py_names(src) if x in STD_GONE]
                + [(ln, f, t) for ln, f, v in _py_strs(src) for t in STD_GONE + STD_GONE_TEXT if t in v])
    return ([(ln, None, x) for ln, x in _js_hits(src, r"\b(?:%s)\b" % "|".join(STD_GONE))]
            + [(ln, None, t) for ln, v in src.lits for t in STD_GONE_TEXT if t in v])


# 금액 정책 — 그날의 '얼마나' 사실(Judge.amount)을 매수 크기로 바꾸는 규칙(모름을 어떻게 세나). 정본 trades.size_of.
#   사실을 꺼내는 grade 의 amount_factor·weight_of 는 Judge.amount 한 경로로만 읽는다(라이브·백테스트 같은 값).
AMOUNT_FACTS = {"amount_factor", "weight_of"}


def m_amount_policy(src):
    """구간③·화면(매수 크기를 다루는 층)만 본다 — 구간②(checklist)는 트리의 뜻을 검사하려고 사실을 직접 읽는다."""
    if not src.rel.startswith(("trading/", "web/")):
        return []
    if src.kind == "py":
        return ([(ln, f, x) for ln, f, x in _py_names(src) if x in AMOUNT_FACTS]
                + [(n.lineno, n.name, n.name) for n, _ in _py_nodes(src.tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "size_of"])
    return [(ln, None, x) for ln, x in _js_hits(src, r"\bfunction\s+size_?[oO]f\s*\(")]


# 수량 변환 — 정규화된 '얼마나'(출입구 Qty(of, x))를 물량으로 바꾸는 곳은 trades.to_units 하나(매수·매도·비중·조심 모두).
#   밖에서 basis(of)를 가르거나 수량(qty.x)으로 셈을 하면 종류별 해석이 다시 흩어진다.
QTY_BASES = ("bought", "held", "budget")
QTY_JS = (r"\.of\b|\b(?:frac|scale|weight)\b\s*\*(?!\s*100\b)"
          r"|\*\s*(?:[\w$]+\.)*(?:frac|scale|weight)\b")


def _is_qty_x(n):
    return isinstance(n, ast.Attribute) and n.attr == "x" and isinstance(n.value, ast.Attribute) and n.value.attr == "qty"


def m_qty_convert(src):
    if src.kind == "py":
        out = []
        for n, fn in _py_nodes(src.tree):
            if isinstance(n, ast.Attribute) and n.attr == "of" and isinstance(n.value, ast.Attribute)                     and n.value.attr == "qty":
                out.append((n.lineno, fn, "qty.of"))
            elif isinstance(n, ast.BinOp) and (_is_qty_x(n.left) or _is_qty_x(n.right)):
                out.append((n.lineno, fn, "qty.x 셈"))
            elif isinstance(n, ast.Compare) and any(isinstance(c, ast.Constant) and c.value in QTY_BASES
                                                     for c in [n.left] + n.comparators):
                out.append((n.lineno, fn, "basis 비교"))
        return out
    return [(ln, None, x) for ln, x in _js_hits(src, QTY_JS)]


def _labels():
    """칸·등급 이름표 글자 — 정본(Cond.ZONE_LABELS · Grade.GRADES)에서 읽는다(여기 다시 적지 않는다)."""
    from checklist.tradeTool import Cond, Grade
    return set(Cond.ZONE_LABELS.values()) | set(Grade.GRADES.values())


def m_labels(src):
    labels = _labels()
    lits = _py_strs(src) if src.kind == "py" else [(ln, None, v) for ln, v in src.lits]
    return ([(ln, f, v) for ln, f, v in lits if v in labels]
            + [(ln, f, "grade_rules.json") for ln, f, v in lits if "grade_rules.json" in v])


# 등급 사다리 — 날짜별 등급·금액 배수를 내는 함수(정본 grade.ProductEval.grade_key·caution_state·amount_factor).
LADDER_PY = {"grade_key", "caution_state", "amount_factor"}
LADDER_JS = (r"\bfunction\s+(?:gradeKey|and3|or3|ev|cautionOf)\s*\("
             r"|\b(?:const|let|var)\s+(?:gradeKey|and3|or3|ev|cautionOf)\s*=")


def m_grade_ladder(src):
    if src.kind == "py":
        return [(n.lineno, n.name, n.name) for n, _ in _py_nodes(src.tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in LADDER_PY]
    return [(ln, None, x) for ln, x in _js_hits(src, LADDER_JS)]


# ------------------------------------------------------------------ 주인 표 — 개념 하나 = 주인 하나(여기 한 곳)
# concept · owners(주인 파일 — 그 안에선 자유) · match(매처) · why(한 줄 사유) · hint(고칠 길) · allow(명시 예외, 사유 필수).
OWNERS = [
    dict(concept="트리 원본 키", owners=("checklist/tree_gateway.py",), match=m_tree_keys,
         why="tree.json 키 배치(products·defs·여섯 칸·sell/scale/frac…)를 아는 코드는 출입구 하나 — 형식 교체 시 한 파일만",
         hint="TreeGateway 에 물어볼 것",
         allow={   # 같은 이름 키를 쓰는 '트리 아닌' dict
             ("checklist/verify_tree.py", "compare"): ({"sizing"}, "칸별 비교 결과 dict(트리 아님)"),
             ("checklist/verify_tree.py", "render_zone"): ({"weight", "tranches"}, "zone_diff 결과(심판 덤프) dict"),
             ("checklist/tradeTool.py", "amount_factor"): ({"scale"}, "caution_state 결과(판정 JSON caution 항목)"),
             ("trading/verify_trading.py", "t_trades"): ({"entry", "exit"}, "거래 dict 검사"),
             ("trading/verify_trading.py", "parity_text"): ({"products"}, "파리티 보고 dict"),
             ("trading/backtest/portfolio.py", "run_product"): ({"sell"}, "주문 dict 의 매도 표시"),
             ("web/verdict_view.py", "ref_map"): ({"unexpressed"}, "판정 JSON refs 항목을 만드는 자리"),
             ("web/verdict_view.py", "render"): ({"sizing", "weight"}, "판정 JSON verdict.sizing 을 읽어 현금 % 계산"),
             ("web/verdict_view.py", "build_text"): ({"sizing", "weight", "exit"}, "판정 JSON 을 알림 문장으로"),
         }),
    dict(concept="책 산출물 경로", owners=("shared/paths.py",), match=m_book_paths,
         why="books/<slug>/ 아래 산출물 경로를 짓는 곳은 하나 — 옛 루트 산출물로 되돌아가지 않게",
         hint="shared/paths.py(book_dir·book_file…)로", allow={}),
    dict(concept="매도 정책", owners=("trading/backtest/trades.py",), match=m_exit_policy, everywhere=m_std_exit_gone,
         why="책에 매도 규칙이 없을 때의 정책은 trades.exit_policy 하나(\"none\" = 대체 규칙 없이 매수 신호만 평가) — "
             "폐지된 표준 매도(대체 규칙·숫자 파일·출처 글자·플래그)는 주인 포함 어디서도 되살리지 않는다",
         hint="trades.exit_policy · 화면은 exit_policy 필드와 no_exit_note 문구로", allow={}),
    dict(concept="금액 정책", owners=("trading/backtest/trades.py",), match=m_amount_policy,
         why="매수 크기(비중 × 분할 × 조심 배수)와 모름(폭 미명시·확인 필요·비중 모름)을 어떻게 셀지는 trades.size_of 하나 — "
             "그 사실은 Judge.amount 한 경로로만(라이브 화면 = 백테스트)",
         hint="Judge.amount 로 사실을, trades.size_of 로 크기를",
         allow={("trading/signal/judge.py", "amount"): (AMOUNT_FACTS, "Judge.amount — 그날 사실(Amount)을 꺼내는 한 경로")}),
    dict(concept="수량 변환", owners=("trading/backtest/trades.py",), match=m_qty_convert,
         why="'얼마나'(Qty: cash·budget·order·bought·held)를 물량으로 바꾸는 곳은 trades.to_units 하나 — 매수(분할)·매도·"
             "비중·조심이 같은 변환을 지난다. 밖은 Qty 를 건네기만 하고 basis 를 가르거나 셈하지 않는다",
         hint="trades.to_units(Qty, Ledger) · 화면은 엔진이 낸 units·sell 문장으로",
         allow={("checklist/tree_gateway.py", "_qty"): (None, "원본 키(sell·scale·frac·weight) → Qty 정규화(변환 아님)")}),
    dict(concept="칸·등급 이름표", owners=("checklist/tradeTool.py",), match=m_labels,
         why="Cond.ZONE_LABELS · Grade.GRADES · grade_rules.json 이 정본 — 화면은 판정 JSON(zones·grades·grade_rules)으로 받는다",
         hint="판정 JSON 의 zones·grades·grade_rules 로", allow={}),
    dict(concept="등급 사다리", owners=("checklist/tradeTool.py",), match=m_grade_ladder,
         why="날짜별 등급·금액 배수를 내는 곳은 Grade 하나 — 두 벌이면 엔진과 화면 등급이 갈라진다",
         hint="판정 JSON 의 key 를 그대로(수동 답은 POST /api/verdict — 서버가 Cond.Ctx answers 로 낸다)", allow={}),
]
SELF = "orchestration/verify_code.py"      # 표 자신(금지 표식 목록을 들고 있다) — 표식 검사에서 뺀다


def _allowed(row, rel, func, token):
    for key in ((rel, func), (rel, None)):
        if key in row["allow"]:
            toks = row["allow"][key][0]
            if toks is None or token in toks:
                return True
    return False


def owner_hits(srcs):
    """주인 표 위반 [(파일, 사유)]."""
    bad = []
    for row in OWNERS:
        for src in srcs:
            if src.rel == SELF:
                continue
            hits = [] if src.rel in row["owners"] else row["match"](src)
            hits += row["everywhere"](src) if row.get("everywhere") else []     # 주인도 예외 없는 표식
            for line, func, token in hits:
                if not _allowed(row, src.rel, func, token):
                    bad.append((src.rel, "%d행 %s%r — [%s] 주인은 %s. %s"
                                % (line, ("%s() " % func) if func else "", token, row["concept"],
                                   " · ".join(row["owners"]), row["hint"])))
    return bad


# ------------------------------------------------------------------ 폴더 경계(규칙 1~3)
def _imports(tree):
    """파일의 최상위/함수내 import 전부 → {점 이름}(from a.b import c → "a.b.c"). 상대 import 는 자기 팀 안이라 뺀다."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:          # 상대 import 는 자기 팀 안이므로 통과
                continue
            if node.module:
                out.update("%s.%s" % (node.module, a.name) for a in node.names)
    return out


def _is_public(name):
    return any(name == m or name.startswith(m + ".") for m in PUBLIC_DSL)


def boundary_hits(srcs):
    """폴더 경계 위반 [(파일, 사유)]."""
    bad = []
    for src in srcs:
        if src.kind != "py":
            continue
        layer, fn = src.rel.split("/", 1)
        names = _imports(src.tree)
        mods = {m.split(".")[0] for m in names}
        allow = ALLOW.get((layer, fn), set())

        # 규칙 1 — 층마다 import 해도 되는 층만. checklist 는(자기 팀이 아니면) 공개 DSL 만.
        ok = IMPORTS[layer]
        wrong = sorted((set(LAYERS) & mods) - ok)
        if wrong:
            bad.append((src.rel, "import 금지 층: %s — %s 는 %s 만 import 한다"
                        % (", ".join(wrong), layer, " · ".join(sorted(ok)))))
        if layer != "checklist" and "checklist" in ok:
            inner = sorted(m for m in names if m.split(".")[0] == "checklist" and not _is_public(m))
            if inner:
                bad.append((src.rel, "checklist 비공개 모듈 import: %s — 구간②는 공개 DSL(%s)로만"
                            % (", ".join(inner), ", ".join(PUBLIC_DSL))))

        # 규칙 2 — jhts 는 shared/md_feed.py 만
        if "jhts" in mods and "jhts" not in allow:
            bad.append((src.rel, "jhts 직접 import — 시세 창구는 shared/md_feed.py 하나다"))

        # 규칙 3 — 네트워크 모듈 금지(명시 예외 제외)
        net = (NET_MODULES & mods) - allow
        if net:
            bad.append((src.rel, "네트워크 모듈 import: %s — 시세 자가수집 금지"
                        " (수집은 jhts, 알림은 trading/notify)" % ", ".join(sorted(net))))
    return bad


def _sources():
    """검사 대상 — 층 폴더의 *.py 와 web/ui/*.js. → ([Src], [(파일, 사유)] 층 폴더 없음·파싱 실패)."""
    srcs, bad = [], []
    for layer in LAYERS:
        d = os.path.join(BASE, layer)
        if not os.path.isdir(d):
            bad.append((layer + "/", "층 폴더가 없음"))
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".py"):
                rel = "%s/%s" % (layer, fn)
                try:
                    srcs.append(Src(rel, "py", open(os.path.join(d, fn), encoding="utf-8").read()))
                except SyntaxError as e:
                    bad.append((rel, "파이썬 파싱 실패: %s" % e))
    ui = os.path.join(BASE, "web", "ui")
    for fn in sorted(os.listdir(ui)) if os.path.isdir(ui) else ():
        if fn.endswith(".js"):
            srcs.append(Src("web/ui/" + fn, "js", open(os.path.join(ui, fn), encoding="utf-8").read()))
    return srcs, bad


TODO_OWNER = "docs/HANDOFF.md"


def todo_hits():
    """주인 표 '할 일 목록'(문서 — 파일 이름으로 본다): 할 일은 docs/HANDOFF.md 한 곳. 다른 TODO 파일이 생기면 정지."""
    bad = []
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in (".venv", "__pycache__", "books", "logs", ".git")]
        for fn in files:
            if "todo" in fn.lower():
                rel = os.path.relpath(os.path.join(root, fn), BASE).replace(os.sep, "/")
                bad.append((rel, "[할 일 목록] 주인은 %s — 할 일은 거기 한 곳에" % TODO_OWNER))
    return bad


def check():
    srcs, bad = _sources()
    return bad + boundary_hits(srcs) + owner_hits(srcs) + todo_hits()


def main():
    bad = check()
    if bad:
        print("코드 규칙 위반 %d건" % len(bad))
        for rel, why in bad:
            print("  ✗ %-28s %s" % (rel, why))
        print("\n흐름은 한 방향이다: shared ← playbook · checklist(공개 DSL) ← trading ← web (orchestration 은 조립만)."
              " 결정 하나 = 주인 하나(주인 표 OWNERS).")
        return 1
    print("코드 규칙 통과 — 층 import 방향 위반 0 · checklist 는 공개 DSL 로만 · jhts 창구 단일 · 자가수집 네트워크 코드 0"
          " · 주인 표 %d행 위반 0(%s) · 할 일은 %s 한 곳." % (len(OWNERS), " · ".join(r["concept"] for r in OWNERS), TODO_OWNER))
    return 0


if __name__ == "__main__":
    sys.exit(main())
