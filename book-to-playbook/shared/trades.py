#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""거래 시뮬레이터 — 매수 신호 + 분할(sizing.tranches) + 매도 규칙(exit) → 거래 목록 (책 무관).

규약
  · 물량 단위 = 한 상품에 계획한 전체 물량 1.0. 분할이 없거나 비율이 저자 미명시(frac null)면 1차에 1.0 을 다 산다.
  · 1차: 매수 신호가 시작된 날 T 의 다음 날 시가(T+1)에 frac₁ 만큼. 한 상품에 포지션은 하나 — 보유 중의 신호는 건너뛴다.
  · 2차 이후: 매일 종가에 다음 차수의 when 을 평가해 참이면 다음 날 시가에 그 frac 만큼(차례대로, 각 한 번).
      같은 날 매도 규칙이 걸렸으면 그날은 사지 않는다.
  · 포지션 값(pos): ret = 평균 매입가 대비 수익률 — 추가 매수가 체결되면 그날부터 평균 매입가가 바뀐다.
  · 매도: 매일 종가에 규칙을 평가하고, 걸리면 다음 날 시가에 판다. 규칙마다 한 번만(같은 날 여럿이면 적힌 순서).
      sell "all" = 남은 전량 · {"initial": f} = 그때까지 산 물량의 f(남은 것보다 많으면 남은 만큼) · {"remaining": f} = 남은 물량의 f
  · 수익률 = (판 금액 + 남은 물량 × 마지막 종가) ÷ 산 금액 − 1.
  · 저자 기준만: 안전장치(표준 손절 등)를 끼우지 않는다. 끝까지 안 팔린 물량은 마지막 종가로 평가하고 '미청산'으로 남긴다
    — 그 사실 자체가 그 규칙의 성적이다.
  · 수동(manual) 조건은 과거를 확인할 수 없어 **매매가 안 나가는 쪽**으로 푼다 — 그냥 쓰이면 거짓,
    not 아래면 안쪽을 참으로 둬 결과가 거짓(확인 못 한 조건 때문에 사고팔지 않는다).
  · 책에 매도 규칙이 없는 상품은 STANDARD(+9% / −5% / 10거래일)로 하고 결과에 '표준 기준(책 아님)'이라 표시한다.
"""
from shared import cond

STANDARD = [
    {"label": "표준 익절 +9%", "when": {"ge": [{"pos": "ret"}, 9]}, "sell": "all"},
    {"label": "표준 손절 −5%", "when": {"le": [{"pos": "ret"}, -5]}, "sell": "all"},
    {"label": "표준 기간만료 10거래일", "when": {"ge": [{"pos": "days"}, 10]}, "sell": "all"},
]
FULL = [{"label": "전량", "frac": 1.0}]


def _std_const(field, op):
    """STANDARD 에서 (pos.<field> op 상수) 꼴 규칙의 상수를 꺼낸다 — 숫자를 다시 적지 않고 구조에서 끌어온다."""
    for r in STANDARD:
        w = r.get("when") or {}
        args = w.get(op)
        if args and isinstance(args[0], dict) and args[0].get("pos") == field:
            return args[1]
    return None


def standard_label():
    """표준 매도 규칙의 짧은 표시 문자열(예 '+9%/−5%/10일') — STANDARD 상수에서 파생(단일 출처).
    화면은 이 문자열을 받아 쓰고 숫자를 복붙하지 않는다."""
    tp, sl, dys = _std_const("ret", "ge"), _std_const("ret", "le"), _std_const("days", "ge")
    return "+%g%%/−5%%/%g일" % (tp, dys) if sl == -5 else \
           "+%g%%/%g%%/%g일" % (tp, sl, dys)


def exits_of(tree, prod):
    """(규칙 목록, 출처) — 책 규칙이 없으면 표준."""
    ex = tree["products"][prod].get("exit")
    return (ex, "책") if ex else (STANDARD, "표준 기준(책 아님)")


def tranches_of(tree, prod):
    """시뮬레이션에 쓰는 분할 — 저자가 비율을 안 줬으면(frac null) 전량 한 번으로 계산한다
    (비율을 지어내지 않는다 — 결과에 tranche_note 로 표시)."""
    trs = (tree["products"][prod].get("sizing") or {}).get("tranches") or FULL
    return FULL if trs[0].get("frac") is None else trs


def tranche_note(tree, prod):
    trs = (tree["products"][prod].get("sizing") or {}).get("tranches") or []
    return "분할 비율 저자 미명시 — 전량 한 번 매수로 계산" if trs and trs[0].get("frac") is None else None


def simulate(tree, prod, hist, cal, starts, exits, tranches=None):
    """starts = 신호 시작일 인덱스 목록 → 거래 목록. tranches 생략 = 트리의 분할."""
    tranches = tranches if tranches is not None else tranches_of(tree, prod)
    tranches = FULL if (not tranches or tranches[0].get("frac") is None) else tranches
    cs = {c.date: c for c in hist.get(prod) or []}
    opens = [cs[d].open if d in cs else None for d in cal]
    closes = [cs[d].close if d in cs else None for d in cal]
    cfg, defs = tree["products"][prod], tree.get("defs") or {}
    L = len(cal)
    trades, free_from = [], 0
    for s in starts:
        e = s + 1
        if e >= L or e < free_from or not opens[e]:
            continue
        buys = [{"date": cal[e], "px": opens[e], "qty": tranches[0]["frac"], "tranche": tranches[0]["label"]}]
        bought = tranches[0]["frac"]
        remaining = bought
        cost = [None] * L

        def rebuild(frm):
            """frm 부터 평균 매입가가 바뀐다 → 포지션 값을 쓰는 식을 다시 계산."""
            q = sum(b["qty"] for b in buys)
            avg = sum(b["qty"] * b["px"] for b in buys) / q
            for k in range(frm, L):
                cost[k] = avg
            ctx = cond.Ctx(hist, cal, prod, cfg.get("index"), defs, manual_as=False, pos=(e, list(cost)))
            return ([cond.series(r["when"], ctx) for r in exits],
                    [cond.series(t["when"], ctx) if "when" in t else None for t in tranches])

        whens, twhens = rebuild(e)
        nxt, sells, fired, last = 1, [], set(), None
        for d in range(e, L):
            sold_today = False
            for k, r in enumerate(exits):
                if k in fired or whens[k][d] is not True:
                    continue
                fired.add(k)
                if d + 1 >= L or not opens[d + 1]:
                    continue                      # 다음 날이 없다 — 체결 못 함(미청산으로 남는다)
                sell = r["sell"]
                if sell == "all":
                    q = remaining
                elif "initial" in sell:
                    q = min(sell["initial"] * bought, remaining)
                else:
                    q = remaining * sell["remaining"]
                if q <= 1e-12:
                    continue
                sells.append({"date": cal[d + 1], "px": opens[d + 1], "qty": q, "rule": r["label"]})
                remaining -= q
                sold_today = True
            if remaining <= 1e-9:
                last = d + 1
                break
            if (not sold_today and nxt < len(tranches) and twhens[nxt] is not None
                    and twhens[nxt][d] is True and d + 1 < L and opens[d + 1]):
                t = tranches[nxt]
                buys.append({"date": cal[d + 1], "px": opens[d + 1], "qty": t["frac"], "tranche": t["label"]})
                bought += t["frac"]
                remaining += t["frac"]
                nxt += 1
                whens, twhens = rebuild(d + 1)
        closed = remaining <= 1e-9
        end = last if closed else L - 1
        spent = sum(b["qty"] * b["px"] for b in buys)
        value = sum(x["qty"] * x["px"] for x in sells)
        if not closed:
            value += remaining * (closes[L - 1] or buys[-1]["px"])
        px = opens[e]
        trades.append({"entry": cal[e], "entry_px": px, "exit": cal[end] if closed else None,
                       "closed": closed, "days": end - e, "ret": (value / spent - 1) * 100,
                       "buys": buys, "sells": sells, "fixed20": ((closes[e + 19] / px - 1) * 100
                                                                 if e + 19 < L and closes[e + 19] else None)})
        free_from = end + 1 if closed else L
    return trades


def stats(trades):
    import statistics
    closed = [t for t in trades if t["closed"]]
    rets = [t["ret"] for t in closed]
    f20 = [t["fixed20"] for t in trades if t["fixed20"] is not None]
    out = {"trades": len(trades), "closed": len(closed), "open": len(trades) - len(closed)}
    if rets:
        out.update(win=sum(1 for r in rets if r > 0) / len(rets) * 100, avg=statistics.mean(rets),
                   median=statistics.median(rets), days=statistics.mean(t["days"] for t in closed))
    if f20:
        out.update(f20_win=sum(1 for r in f20 if r > 0) / len(f20) * 100, f20_avg=statistics.mean(f20))
    rules = {}
    for t in trades:
        for s in t["sells"]:
            rules[s["rule"]] = rules.get(s["rule"], 0) + 1
    out["rule_hits"] = rules
    adds = {}
    for t in trades:
        for b in t.get("buys", [])[1:]:
            adds[b["tranche"]] = adds.get(b["tranche"], 0) + 1
    out["tranche_hits"] = adds
    return out
