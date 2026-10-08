#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""팀 경계 검사 — 폴더 구조가 곧 조직도라는 약속을 기계로 강제한다.

## 왜 있나

이 파이프라인은 세 구간을 세 팀 폴더로, 그 밖의 일을 층으로 나눈다.
  · playbook/      구간① 책 원본 → 전사본(플레이북)
  · checklist/     구간② 전사본 → 조건 트리(tree.json) + 그 트리의 언어(DSL: 출입구·문법·등급의 뜻)
  · trading/       구간③ 판정 · 백테스트 · 장중(Judge·Timeline·체결 워크·계산기·알림)
  · shared/        공통층 — 시세 창구(md_feed)·경로(paths)뿐
  · web/           화면층 — 판정·백테스트 결과를 화면 모양으로 빚고 서빙(판정을 다시 내지 않는다)
  · orchestration/ 조립·감사층(run 러너·verify_structure·verify_teams — 전 구간을 실행·검사만)

팀 코드가 다른 팀의 '속'을 import 하는 순간, 예전처럼 "한 검사기 안의 정의를 다른 검사기가 몰래 빌려 쓰다
갈라지는" 사고로 돌아간다. 그래서 무엇을 import 해도 되는지를 층마다 한 줄로 정해 둔다(IMPORTS).

## 무엇을 강제하나

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
  규칙 4  트리 원본 키 직접 접근 금지 — tree.json 의 키 배치(products·defs·여섯 칸·sell/scale/frac…)를 아는
          코드는 checklist/tree_gateway.py 하나다. 다른 파일에서 그 키로 첨자([..])·.get/.pop/.setdefault 를
          읽으면 위반(정적 AST 검사). 같은 이름 키를 쓰는 '트리 아닌' dict(거래·판정 JSON 등)는 KEY_ALLOW 한 곳에 사유와 함께.

## 사용

    python -m orchestration.verify_teams   # 위반 있으면 exit 1 (orchestration.run 의 구조 게이트에 포함)
"""
import ast
import os
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
PUBLIC_DSL = ("checklist.tree_gateway", "checklist.cond", "checklist.grade")

# 시세 자가수집에 쓰이는 모듈들 — 보이면 그 자체로 위반.
NET_MODULES = {"urllib", "http", "requests", "socket", "aiohttp", "httpx"}

# 규칙 2·3 의 명시적 예외 — 예외는 여기 한 곳에만 적는다(코드 곳곳에 흩지 않는다).
ALLOW = {
    ("shared", "md_feed.py"): {"jhts"},                     # 유일한 시세 창구
    ("trading", "notify.py"): {"urllib"},                   # 알림 '송신' 전용(수집 아님) — 구간③ 소유, 이 한 파일만
    ("web", "serve.py"): {"http", "urllib"},                # 로컬 서버(서빙·URL 파싱)
}

# 규칙 4 — 트리의 구조 키(COND_DSL 5절 파일 형식). 이 키로 원본을 읽는 코드는 출입구 파일 하나뿐이어야 한다.
GATEWAY_FILE = ("checklist", "tree_gateway.py")
TREE_KEYS = {"products", "defs", "filter", "avoid", "entry", "caution", "sizing", "exit", "tranches", "sell",
             "scale", "weight", "frac", "unexpressed", "review", "source", "sections_read", "exit_note"}
# 규칙 4 의 오탐 예외 — 트리가 아닌 dict 가 같은 이름의 키를 쓰는 자리. (레이어/파일, 함수): (키, 사유). 여기 한 곳에만 적는다.
KEY_ALLOW = {
    ("checklist/verify_tree.py", "compare"): ({"sizing"}, "칸별 비교 결과 dict(트리 아님)"),
    ("checklist/verify_tree.py", "render_zone"): ({"weight", "tranches"}, "zone_diff 결과(심판 덤프) dict"),
    ("checklist/grade.py", "amount_factor"): ({"scale"}, "caution_state 결과(판정 JSON caution 항목)"),
    ("trading/verify_trading.py", "t_trades"): ({"entry", "exit"}, "거래 dict 검사"),
    ("trading/portfolio.py", "run_product"): ({"sell"}, "주문 dict 의 매도 표시"),
    ("trading/verify_signal_parity.py", "build_text"): ({"products"}, "파리티 보고 dict"),
    ("web/verdict_view.py", "ref_map"): ({"unexpressed"}, "판정 JSON refs 항목을 만드는 자리"),
    ("web/verdict_view.py", "render"): ({"sizing", "weight"}, "판정 JSON verdict.sizing 을 읽어 현금 % 계산"),
    ("web/verdict_view.py", "build_text"): ({"sizing", "weight", "exit"}, "판정 JSON 을 알림 문장으로"),
}


def _parse(path):
    """파이썬 파일 → AST. 파싱 불가면 None."""
    try:
        return ast.parse(open(path, encoding="utf-8").read())
    except SyntaxError as e:
        print("  ✗ 파싱 실패 %s: %s" % (path, e))
        return None


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


def _tree_key_reads(tree):
    """트리 구조 키를 첨자·.get/.pop/.setdefault 로 읽는 자리 [(줄, 함수, 키)] — 함수는 가장 안쪽 def 이름."""
    out = []

    def visit(node, fn):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = node.name
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
        for child in ast.iter_child_nodes(node):
            visit(child, fn)
    visit(tree, None)
    return out


def check():
    bad = []
    for layer in LAYERS:
        d = os.path.join(BASE, layer)
        if not os.path.isdir(d):
            bad.append((layer, "-", "층 폴더가 없음"))
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".py"):
                continue
            tree = _parse(os.path.join(d, fn))
            if tree is None:
                bad.append((layer, fn, "파이썬 파싱 실패"))
                continue
            names = _imports(tree)
            mods = {m.split(".")[0] for m in names}
            allow = ALLOW.get((layer, fn), set())

            # 규칙 1 — 층마다 import 해도 되는 층만. checklist 는(자기 팀이 아니면) 공개 DSL 만.
            ok = IMPORTS[layer]
            wrong = sorted((set(LAYERS) & mods) - ok)
            if wrong:
                bad.append((layer, fn, "import 금지 층: %s — %s 는 %s 만 import 한다"
                            % (", ".join(wrong), layer, " · ".join(sorted(ok)))))
            if layer != "checklist" and "checklist" in ok:
                inner = sorted(m for m in names if m.split(".")[0] == "checklist" and not _is_public(m))
                if inner:
                    bad.append((layer, fn, "checklist 비공개 모듈 import: %s — 구간②는 공개 DSL(%s)로만"
                                % (", ".join(inner), ", ".join(PUBLIC_DSL))))

            # 규칙 2 — jhts 는 shared/md_feed.py 만
            if "jhts" in mods and "jhts" not in allow:
                bad.append((layer, fn, "jhts 직접 import — 시세 창구는 shared/md_feed.py 하나다"))

            # 규칙 3 — 네트워크 모듈 금지(명시 예외 제외)
            net = (NET_MODULES & mods) - allow
            if net:
                bad.append((layer, fn, "네트워크 모듈 import: %s — 시세 자가수집 금지"
                            " (수집은 jhts, 알림은 trading/notify)" % ", ".join(sorted(net))))

            # 규칙 4 — 트리 원본 키 직접 접근 금지(출입구 파일 하나만 예외, 오탐은 KEY_ALLOW)
            if (layer, fn) != GATEWAY_FILE:
                for line, func, key in _tree_key_reads(tree):
                    keys, _why = KEY_ALLOW.get(("%s/%s" % (layer, fn), func), (set(), ""))
                    if key not in keys:
                        bad.append((layer, fn, "%d행 %s() 가 트리 키 %r 를 직접 읽음 — TreeGateway 에 물어볼 것"
                                    % (line, func or "<모듈>", key)))
    return bad


def main():
    bad = check()
    if bad:
        print("팀 경계 위반 %d건" % len(bad))
        for layer, fn, why in bad:
            print("  ✗ %-14s %-24s %s" % (layer + "/", fn, why))
        print("\n흐름은 한 방향이다: shared ← playbook · checklist(공개 DSL) ← trading ← web (orchestration 은 조립만).")
        return 1
    print("팀 경계 통과 — 층 import 방향 위반 0 · checklist 는 공개 DSL 로만 · jhts 창구 단일 · 자가수집 네트워크 코드 0"
          " · 트리 원본 직접 접근 0(출입구 하나).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
