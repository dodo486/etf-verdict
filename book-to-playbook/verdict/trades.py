#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""거래 시뮬레이터 — 매수 신호 + 매도 규칙(tree.json products.X.exit) → 거래 목록 (책 무관).

규약
  · 진입: 매수 신호가 시작된 날 T 의 다음 날 시가(T+1). 한 상품에 포지션은 하나 — 보유 중의 신호는 건너뛴다.
  · 매도: 매일 종가에 규칙을 평가하고, 걸리면 다음 날 시가에 판다. 규칙마다 한 번만(같은 날 여럿이면 적힌 순서).
      sell "all" = 남은 전량 · {"initial": f} = 처음 물량의 f(남은 것보다 많으면 남은 만큼) · {"remaining": f} = 남은 물량의 f
  · 저자 기준만: 안전장치(표준 손절 등)를 끼우지 않는다. 끝까지 안 팔린 물량은 마지막 종가로 평가하고 '미청산'으로 남긴다
    — 그 사실 자체가 그 규칙의 성적이다.
  · 수동(manual) 매도 조건은 과거를 확인할 수 없어 **매도가 안 나가는 쪽**으로 푼다 — 그냥 쓰이면 거짓,
    not 아래면 안쪽을 참으로 둬 결과가 거짓(확인 못 한 조건 때문에 팔지 않는다).
  · 책에 매도 규칙이 없는 상품은 STANDARD(+9% / −5% / 10거래일)로 하고 결과에 '표준 기준(책 아님)'이라 표시한다.
"""
from verdict import cond

STANDARD = [
    {"label": "표준 익절 +9%", "when": {"ge": [{"pos": "ret"}, 9]}, "sell": "all"},
    {"label": "표준 손절 −5%", "when": {"le": [{"pos": "ret"}, -5]}, "sell": "all"},
    {"label": "표준 기간만료 10거래일", "when": {"ge": [{"pos": "days"}, 10]}, "sell": "all"},
]


def exits_of(tree, prod):
    """(규칙 목록, 출처) — 책 규칙이 없으면 표준."""
    ex = tree["products"][prod].get("exit")
    return (ex, "책") if ex else (STANDARD, "표준 기준(책 아님)")


def simulate(tree, prod, hist, cal, starts, exits):
    """starts = 신호 시작일 인덱스 목록 → 거래 목록."""
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
        px = opens[e]
        ctx = cond.Ctx(hist, cal, prod, cfg.get("index"), defs, manual_as=False, pos=(e, px))
        whens = [cond.series(r["when"], ctx) for r in exits]
        remaining, sells, fired, last = 1.0, [], set(), None
        for d in range(e, L):
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
                    q = min(sell["initial"], remaining)
                else:
                    q = remaining * sell["remaining"]
                if q <= 1e-12:
                    continue
                sells.append({"date": cal[d + 1], "px": opens[d + 1], "qty": q, "rule": r["label"]})
                remaining -= q
            if remaining <= 1e-9:
                last = d + 1
                break
        closed = remaining <= 1e-9
        end = last if closed else L - 1
        value = sum(x["qty"] * x["px"] for x in sells)
        if not closed:
            value += remaining * (closes[L - 1] or px)
        trades.append({"entry": cal[e], "entry_px": px, "exit": cal[end] if closed else None,
                       "closed": closed, "days": end - e, "ret": (value / px - 1) * 100,
                       "sells": sells, "fixed20": ((closes[e + 19] / px - 1) * 100
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
    return out
