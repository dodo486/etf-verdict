#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""매도·분할 규칙 리더 + 규칙 평가 워크(머리/shared) — 트리(books/<slug>/tree.json)의
exit/sizing 규칙을 읽어, 그 규칙을 봉마다 평가해 체결 일정·거래 요약을 만든다(책 무관, 돈·수수료·지표 없음).

이 모듈은 '규칙'만 다룬다 — 돈·수수료·성적(자산곡선·MaxDD·샤프)은 계산기(operations/portfolio)가 낸다
(단방향 폭포수: 계산기가 build_trades 결과(체결 일정)를 받아 돈·지표를 낸다. 여기서 operations 를 부르지 않는다).

규칙 리더
  · exits_of    : 책에 매도 규칙이 있으면 그걸, 없으면 표준(STANDARD)을. (규칙 목록, 출처) 로 돌려준다.
  · tranches_of : 분할 매수 차수. 저자가 비율을 안 줬으면(frac null) 전량 한 번(비율을 지어내지 않는다).
  · unsized_note: 분할 비율·매도 비율 '저자 미명시'를 백테스트가 어떻게 계산했는지 결과에 표시할 문구.
  · standard_label / STANDARD : 책에 매도 규칙이 없는 상품에 쓰는 '책 무관 기본값'(결과엔 '표준 기준(책 아님)').
    표준 규칙의 숫자(+9%/−5%/10일)는 코드가 아니라 shared/exit_defaults.json 한 곳에 있다(하드코딩 0 — grade_rules 패턴).

규칙 평가 워크(돈·수수료·지표 없음 — 머리/shared 관심사)
  · build_trades   : 머리(tree)가 정한 진입 신호·분할·매도 규칙을 받아 '한 진입 → 그 청산까지'의
                     체결 일정(buys/sells)을 만든다. 포지션 사실(진입가·평단·ret·maxret·days)은 봉마다
                     여기서 계산하고, cond.py(순수 규칙 평가기)는 그 값을 pos 로 '읽어' exit/분할 규칙만
                     평가한다(단방향 폭포수). 돈·수수료는 손대지 않는다 — 그건 계산기(operations)의 일.
  · _parity_stats  : 머리가 정한 거래 경계(한 진입→청산)로 집계한 거래 요약(거래수·승률·거래당 평균 등).
  · _position_facts: 지금 열려 있는(미청산) 마지막 거래의 사실(진입가·평단·현재수익률·보유일 등).

트리는 호출자가 넘긴 TreeGateway(gw — checklist/tree_gateway.py)로 읽는다. 공통층은 그 파일을 import 하지 않는다 —
규칙은 gw 가 건네는 Rule(label·when·sell·frac…)로만 다룬다.
"""
import json
import os
import statistics

from shared import cond

# 표준 매도 규칙의 '정본'은 코드가 아니라 데이터(shared/exit_defaults.json)에 있다 — 숫자를 코드에 복붙하지 않는다.
STANDARD = json.load(
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "exit_defaults.json"),
         encoding="utf-8"))["standard"]
FULL = [{"label": "전량", "frac": 1.0}]          # 한 번에 전량 — 트리 규칙 형식 그대로 두고 쓸 때 gw.as_rules 로 감싼다


def _std_const(field, op):
    """STANDARD 에서 (pos.<field> op 상수) 꼴 규칙의 상수를 꺼낸다 — 숫자를 다시 적지 않고 구조에서 끌어온다."""
    for r in STANDARD:
        w = r.get("when") or {}
        args = w.get(op)
        if args and isinstance(args[0], dict) and args[0].get("pos") == field:
            return args[1]
    return None


def standard_label():
    """표준 매도 규칙의 짧은 표시 문자열(예 '+9%/−5%/10일') — STANDARD config 에서 파생(단일 출처).
    숫자는 전부 exit_defaults.json 에서 끌어온다 — 화면·코드 어디에도 복붙하지 않는다."""
    tp, sl, dys = _std_const("ret", "ge"), _std_const("ret", "le"), _std_const("days", "ge")
    return ("+%g%%/%g%%/%g일" % (tp, sl, dys)).replace("-", "−")  # 음수 부호만 유니코드 글리프로(숫자는 config)


def exits_of(gw, prod):
    """(규칙 목록, 출처) — 책 규칙이 없으면 표준."""
    ex = gw.exit_rules(prod)
    return (ex, "책") if ex else (gw.as_rules(STANDARD), "표준 기준(책 아님)")


def tranches_of(gw, prod):
    """시뮬레이션에 쓰는 분할 — 저자가 비율을 안 줬으면(frac null) 전량 한 번으로 계산한다
    (비율을 지어내지 않는다 — 결과에 unsized_note 로 표시)."""
    trs = gw.tranches(prod) or gw.as_rules(FULL)
    return gw.as_rules(FULL) if trs[0].frac is None else trs


def _sell_frac(sell):
    """매도 비율 — "all" 이면 1, 아니면 initial/remaining 의 값(null = 저자 미명시)."""
    return 1 if sell == "all" else next(iter(sell.values()))


def unsized_note(gw, prod, exits):
    """저자가 비율을 안 준 수량 자리를 백테스트가 어떻게 계산했는지 — 없으면 None."""
    trs = gw.tranches(prod)
    out = ["분할 비율 저자 미명시 — 전량 한 번 매수로 계산"] if trs and trs[0].frac is None else []
    out += ["매도 비율 저자 미명시 「%s」 — 팔지 않은 것으로 계산" % r.label
            for r in exits if _sell_frac(r.sell) is None]
    return " · ".join(out) or None


# ------------------------------------------------------------------ 규칙 평가 워크: 신호·규칙 → 체결 일정(buys/sells)
def build_trades(gw, prod, hist, cal, starts, exits, tranches=None):
    """머리(tree — gw)가 정한 진입 신호·분할·매도 규칙을 받아 '한 진입 → 그 청산까지'의 거래 목록을 만든다.
    포지션 사실(진입가·평단·ret·maxret·days)은 여기(규칙 평가 워크)가 봉마다 계산하고,
    cond.py(순수 규칙 평가기)는 그 포지션 값을 pos 로 '읽어' exit/분할 규칙만 평가한다(단방향 폭포수).
    돈·수수료·지표는 손대지 않는다 — 그건 계산기(operations/portfolio)가 이 결과를 받아서 한다.

    규약(계산기가 체결 타이밍을 다시 정하지 않는다):
      · 물량 단위 = 전체 1.0. 분할이 없거나 비율 미명시(frac null)면 1차에 1.0 전량.
      · 1차: 신호 시작일 T 의 다음 날 시가(T+1)에. 한 상품에 포지션은 하나(보유 중 신호는 건너뜀).
      · 2차 이후: 매일 종가에 다음 차수 when 을 평가 → 참이면 다음 날 시가에(차례대로 각 한 번).
        같은 날 매도가 걸렸으면 그날은 사지 않는다.
      · 매도: 매일 종가에 규칙 평가 → 걸리면 다음 날 시가에. 규칙마다 한 번만(같은 날 여럿이면 적힌 순서).
        sell "all"=남은 전량 · {"initial":f}=그때까지 산 물량의 f · {"remaining":f}=남은 물량의 f.
      · 수익률 = (판 금액 + 남은 물량 × 마지막 종가) ÷ 산 금액 − 1. 미청산은 마지막 종가로 평가.
      · manual 은 '매매가 안 나가는 쪽'으로 푼다(manual_as=False). 매도 비율 null(저자 미명시)도 같은 쪽 — 팔지 않는다.

    starts = 신호 시작일 인덱스 목록. exits·tranches = [Rule](gw 가 건넨 것), tranches 생략 = 트리의 분할(tranches_of)."""
    tranches = tranches if tranches is not None else tranches_of(gw, prod)
    tranches = gw.as_rules(FULL) if (not tranches or tranches[0].frac is None) else tranches
    cs = {c.date: c for c in hist.get(prod) or []}
    opens = [cs[d].open if d in cs else None for d in cal]
    closes = [cs[d].close if d in cs else None for d in cal]
    index, defs = gw.index(prod), gw.defs()
    L = len(cal)
    out, free_from = [], 0
    for s in starts:
        e = s + 1
        if e >= L or e < free_from or not opens[e]:
            continue
        buys = [{"date": cal[e], "px": opens[e], "qty": tranches[0].frac, "tranche": tranches[0].label}]
        bought = tranches[0].frac
        remaining = bought
        cost = [None] * L

        def rebuild(frm):
            """frm 부터 평단이 바뀐다 → 날짜별 평단(cost)을 다시 계산해 pos 로 cond 에 주입(상태 주입).
            cond 는 그 값을 읽어 ret/days/maxret/minret 로 exit·분할 규칙만 평가한다(역류 아님)."""
            q = sum(b["qty"] for b in buys)
            avg = sum(b["qty"] * b["px"] for b in buys) / q
            for k in range(frm, L):
                cost[k] = avg
            ctx = cond.Ctx(hist, cal, prod, index, defs, manual_as=False, pos=(e, list(cost)))
            return ([cond.series(r.when, ctx) for r in exits],
                    [cond.series(t.when, ctx) if t.when is not None else None for t in tranches])

        whens, twhens = rebuild(e)
        nxt, sells, fired, last = 1, [], set(), None
        for d in range(e, L):
            sold_today = False
            for k, r in enumerate(exits):
                if k in fired or whens[k][d] is not True:
                    continue
                fired.add(k)
                if _sell_frac(r.sell) is None:
                    continue                      # 비율 저자 미명시 — 팔지 않는다(unsized_note 로 표시)
                if d + 1 >= L or not opens[d + 1]:
                    continue                      # 다음 날이 없다 — 체결 못 함(미청산으로 남는다)
                sell = r.sell
                if sell == "all":
                    q = remaining
                elif "initial" in sell:
                    q = min(sell["initial"] * bought, remaining)
                else:
                    q = remaining * sell["remaining"]
                if q <= 1e-12:
                    continue
                sells.append({"date": cal[d + 1], "px": opens[d + 1], "qty": q, "rule": r.label})
                remaining -= q
                sold_today = True
            if remaining <= 1e-9:
                last = d + 1
                break
            if (not sold_today and nxt < len(tranches) and twhens[nxt] is not None
                    and twhens[nxt][d] is True and d + 1 < L and opens[d + 1]):
                t = tranches[nxt]
                buys.append({"date": cal[d + 1], "px": opens[d + 1], "qty": t.frac, "tranche": t.label})
                bought += t.frac
                remaining += t.frac
                nxt += 1
                whens, twhens = rebuild(d + 1)
        closed = remaining <= 1e-9
        end = last if closed else L - 1
        spent = sum(b["qty"] * b["px"] for b in buys)
        value = sum(x["qty"] * x["px"] for x in sells)
        if not closed:
            value += remaining * (closes[L - 1] or buys[-1]["px"])
        px = opens[e]
        out.append({"entry": cal[e], "entry_px": px, "exit": cal[end] if closed else None,
                    "closed": closed, "days": end - e, "ret": (value / spent - 1) * 100,
                    "buys": buys, "sells": sells, "fixed20": ((closes[e + 19] / px - 1) * 100
                                                              if e + 19 < L and closes[e + 19] else None)})
        free_from = end + 1 if closed else L
    return out


def _parity_stats(trade_list, last_close=None):
    """머리가 정한 거래 경계(한 진입→청산)로 집계한 거래 요약 — 돈·수수료 없는 '규칙 결과' 집계다.
    build_trades 가 낸 체결 일정을 그대로 쓰므로 거래당 수익률은 구성상 동일하다.
      trades/closed/open · win/avg/median/days(청산 거래 기준) · f20_win/f20_avg(20거래일 보유)
      · rule_hits(매도 규칙별 발동 수) · tranche_hits(2차 이후 분할 매수 수)."""
    closed = [t for t in trade_list if t["closed"]]
    rets = [t["ret"] for t in closed]
    f20 = [t["fixed20"] for t in trade_list if t["fixed20"] is not None]
    out = {"trades": len(trade_list), "closed": len(closed), "open": len(trade_list) - len(closed)}
    if rets:
        out.update(win=sum(1 for r in rets if r > 0) / len(rets) * 100, avg=statistics.mean(rets),
                   median=statistics.median(rets), days=statistics.mean(t["days"] for t in closed))
    if f20:
        out.update(f20_win=sum(1 for r in f20 if r > 0) / len(f20) * 100, f20_avg=statistics.mean(f20))
    rules = {}
    for t in trade_list:
        for s in t["sells"]:
            rules[s["rule"]] = rules.get(s["rule"], 0) + 1
    out["rule_hits"] = rules
    adds = {}
    for t in trade_list:
        for b in t.get("buys", [])[1:]:
            adds[b["tranche"]] = adds.get(b["tranche"], 0) + 1
    out["tranche_hits"] = adds
    return out


def _position_facts(trade_list, closes):
    """지금 열려 있는(미청산) 마지막 거래의 사실 — 없으면 None.
    {entry_px(진입가) · avg_px(평단) · ret(현재수익률%) · high(보유 중 최고 종가) ·
     low(보유 중 최저 종가) · days(보유일)}. 전부 build_trades 가 준 값/시세에서 파생(돈·수수료 없음)."""
    open_trades = [t for t in trade_list if not t["closed"]]
    if not open_trades:
        return None
    t = open_trades[-1]
    units = sum(b["qty"] for b in t["buys"]) - sum(s["qty"] for s in t["sells"])
    spent_rem = sum(b["qty"] * b["px"] for b in t["buys"]) - sum(s["qty"] * s["px"] for s in t["sells"])
    avg_px = (spent_rem / units) if units > 1e-12 else t["entry_px"]
    last = closes[-1]
    # 보유 구간의 최고/최저 종가(진입일 인덱스는 days 로 역산 — build_trades 의 days = end-e, end=L-1)
    entry_i = (len(closes) - 1) - t["days"]
    seg = [c for c in closes[entry_i:] if c is not None]
    return {
        "entry_px": t["entry_px"],
        "avg_px": avg_px,
        "ret": (last / avg_px - 1) * 100 if last else None,
        "high": max(seg) if seg else None,
        "low": min(seg) if seg else None,
        "days": t["days"],
    }
