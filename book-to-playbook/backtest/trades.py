#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""규칙 평가 워크(구간③) — 상품 판단자가 건넨 판다 갈래·산다 분할(qty budget)을 봉마다 평가해
체결 일정·거래 요약을 만든다(책 무관, 돈·수수료·지표 없음).

이 모듈은 '체결'만 다룬다 — 돈·수수료·성적(자산곡선·MaxDD·샤프)은 계산기(backtest/portfolio)가
build_trades 결과(체결 일정)를 받아서 낸다. '얼마나'(매도 정책 exit_policy · 수량 변환 to_units · 금액 정책 size_of ·
분할 tranches_of)는 판정의 일부라 판단자(judge/judge.py '얼마나' 절)가 주인 — 여기는 그걸 불러 쓰기만 한다.

규칙 평가 워크(돈·수수료·지표 없음)
  · build_trades   : 머리(tree)가 정한 진입 신호·분할·매도 규칙을 받아 '한 진입 → 그 청산까지'의
                     체결 일정(buys/sells)을 만든다. 평단은 봉마다 여기서 계산해 보유(judge.Holding — 라이브
                     보유 화면과 같은 pos 주입 문맥)로 cond 에 넣고, cond 는 그 값을 '읽어' 판다·분할 갈래만
                     평가한다. 돈·수수료는 손대지 않는다 — 그건 계산기(portfolio)의 일.
  · _parity_stats  : 머리가 정한 거래 경계(한 진입→청산)로 집계한 거래 요약(거래수·승률·거래당 평균 등).
  · _position_facts: 지금 열려 있는(미청산) 마지막 거래의 사실(진입가·평단·현재수익률·보유일 등).

트리·시세 원본은 모른다 — 상품 판단자(judge/judge.ProductJudge)에게 갈래 목록(판다·분할 Branch 값)·날짜·가격(시가·종가)·
'이 보유 상태로 조건 값'(conditions)을 받아 체결(언제 몇 주)만 정한다. 수량은 정규화된 Qty(of, x)로만 다룬다.
"""
import statistics

from tree.gateway import Qty
from judge.judge import SIZE_NOTES, Holding, Ledger, size_of, to_units, tranches_of


# ------------------------------------------------------------------ 규칙 평가 워크: 신호·규칙 → 체결 일정(buys/sells)
def build_trades(judge, starts, sell_rules, tranches=None, amount=None):
    """상품 판단자(judge — ProductJudge)가 낸 진입 신호·분할·판다 갈래로 '한 진입 → 그 청산까지'의 거래 목록을 만든다.
    평단·체결 장부는 여기(체결 워크)가 봉마다 계산해 Holding 으로 넘기고, 조건 값은 판단자가 그 보유 상태로
    평가해 준다(judge.conditions). 돈·수수료·지표는 손대지 않는다 — 그건 계산기(portfolio)가 한다.

    규약(계산기가 체결 타이밍을 다시 정하지 않는다):
      · 물량 단위 = 시작자본 1.0. 사고팔 양은 전부 to_units(규칙 Qty, 장부) 하나로 낸다:
        매수 = 분할 차수(Qty "budget" — 없거나 미명시면 1차에 전량)를 그 매수를 정한 날(1차 = 신호일 T, 2차 이후 =
        조건이 참이 된 날)의 장부 size_of(amount(그날)) — 비중 — 로, 매도 = 매도 규칙 Qty 를 지금의
        산 물량·남은 물량 장부로. amount 생략(검사기 합성)이면 비중 100%.
      · 1차: 신호 시작일 T 의 다음 날 시가(T+1)에. 한 상품에 포지션은 하나(보유 중 신호는 건너뜀).
      · 2차 이후: 매일 종가에 다음 차수 when 을 평가 → 참이면 다음 날 시가에(차례대로 각 한 번).
      · 장부(pos filled·sold): 그날까지 체결된 매수의 차수별 횟수와 판 비율을 날짜별로 cond 에 넣는다
        (체결 = 다음 날 시가 — 체결한 날 종가 평가부터 반영). 매수·매도가 있을 때마다 다시 넣는다.
        같은 날 매도가 걸렸으면 그날은 사지 않는다.
      · 매도: 매일 종가에 규칙 평가 → 걸리면 다음 날 시가에. 규칙마다 한 번만(같은 날 여럿이면 적힌 순서) —
        repeat 인 판다 갈래는 조건이 다시 맞을 때마다(거짓·모름 → 참으로 바뀐 날) 또 판다.
        qty held x=남은 물량의 x(1 = 전량) · bought x=그때까지 산 물량의 x.
      · 수익률 = (판 금액 + 남은 물량 × 마지막 종가) ÷ 산 금액 − 1. 미청산은 마지막 종가로 평가.
      · manual 은 '매매가 안 나가는 쪽'으로 푼다(manual_as=False). 매도 비율 "?"(저자 미명시)도 같은 쪽 — 팔지 않는다.

    starts = 신호 시작일 인덱스 목록. sell_rules·tranches = 판단자가 건넨 갈래(Branch), tranches 생략 = 그 상품의 분할.
    amount = 봉 인덱스 → Amount(judge.amount — 라이브와 같은 경로) | None. 각 매수에 size(배수)·flags(모름) 를 남긴다."""
    tranches = tranches_of(judge.tranches() if tranches is None else tranches)
    days = judge.days

    def buy(i, at, t):
        """i 번째 봉에서 정한 차수 t 의 매수(체결 at = 다음 봉) — 물량은 to_units(차수 Qty, 그날 장부)."""
        led, fl = size_of(amount(i)) if amount is not None else (Ledger(), set())
        return {"date": days[at], "px": opens[at], "qty": to_units(t.qty, led), "tranche": t.label,
                "size": to_units(Qty("budget", 1.0), led), "flags": sorted(fl)}
    at = {d: k for k, d in enumerate(days)}
    opens, closes = judge.price("open"), judge.price("close")
    L = len(days)
    out, free_from = [], 0
    for s in starts:
        e = s + 1
        if e >= L or e < free_from or not opens[e]:
            continue
        buys = [buy(s, e, tranches[0])]
        if buys[0]["qty"] <= 1e-12:
            continue                              # 그날 비중 0% — 사지 않는다
        bought = buys[0]["qty"]
        remaining = bought
        cost = [None] * L

        def book():
            """날짜별 체결 장부 — 차수(규칙 이름)별·전체 산 횟수, 판 비율(판 물량 ÷ 산 물량). 체결일부터 센다."""
            filled, got, gone = {None: [0] * L}, [0.0] * L, [0.0] * L
            for b in buys:
                k = at[b["date"]]
                filled.setdefault(b["tranche"], [0] * L)
                for j in range(k, L):
                    filled[b["tranche"]][j] += 1
                    filled[None][j] += 1
                    got[j] += b["qty"]
            for x in sells:
                for j in range(at[x["date"]], L):
                    gone[j] += x["qty"]
            return {"filled": filled, "sold": [(g / q) if q > 1e-12 else None for g, q in zip(gone, got)]}

        def rebuild(frm):
            """frm 부터 평단이 바뀐다 → 날짜별 평단(cost)을 다시 계산해 장부와 함께 보유 상태로 넘기고, 판단자가 그 상태로
            판다·분할 갈래의 날짜별 값을 평가해 준다(manual 은 매매가 안 나가는 쪽)."""
            q = sum(b["qty"] for b in buys)
            avg = sum(b["qty"] * b["px"] for b in buys) / q
            for k in range(frm, L):
                cost[k] = avg
            return judge.conditions(Holding(e, list(cost), book=book()), sell_rules, tranches, manual_as=False)

        nxt, sells, fired, last = 1, [], set(), None
        whens, twhens = rebuild(e)
        for d in range(e, L):
            sold_today = False
            for k, r in enumerate(sell_rules):
                if whens[k][d] is not True:
                    continue
                if k in fired and not (r.repeat and d > e and whens[k][d - 1] is not True):
                    continue                      # 한 번만 — repeat 이면 다시 참이 된 날에만 또
                fired.add(k)
                q = to_units(r.qty, Ledger(bought=bought, held=remaining))
                if q is None:
                    continue                      # 비율 저자 미명시 — 팔지 않는다(judge.unsized_note 로 표시)
                if d + 1 >= L or not opens[d + 1]:
                    continue                      # 다음 날이 없다 — 체결 못 함(미청산으로 남는다)
                q = min(q, remaining)             # 남은 것보다 많이 팔 수는 없다
                if q <= 1e-12:
                    continue
                sells.append({"date": days[d + 1], "px": opens[d + 1], "qty": q, "rule": r.label})
                remaining -= q
                sold_today = True
            if remaining <= 1e-9:
                last = d + 1
                break
            if sold_today:
                whens, twhens = rebuild(d + 1)    # 판 비율(pos sold)이 바뀌었다 — 장부를 다시 넣는다
            if (not sold_today and nxt < len(tranches) and twhens[nxt] is not None
                    and twhens[nxt][d] is True and d + 1 < L and opens[d + 1]):
                b = buy(d, d + 1, tranches[nxt])
                buys.append(b)
                bought += b["qty"]
                remaining += b["qty"]
                nxt += 1
                whens, twhens = rebuild(d + 1)
        closed = remaining <= 1e-9
        end = last if closed else L - 1
        spent = sum(b["qty"] * b["px"] for b in buys)
        value = sum(x["qty"] * x["px"] for x in sells)
        if not closed:
            value += remaining * (closes[L - 1] or buys[-1]["px"])
        px = opens[e]
        out.append({"entry": days[e], "entry_px": px, "exit": days[end] if closed else None,
                    "closed": closed, "days": end - e, "ret": (value / spent - 1) * 100,
                    "buys": buys, "sells": sells, "fixed20": ((closes[e + 19] / px - 1) * 100
                                                              if e + 19 < L and closes[e + 19] else None)})
        free_from = end + 1 if closed else L
    return out


def _parity_stats(trade_list, last_close=None):
    """머리가 정한 거래 경계(한 진입→청산)로 집계한 거래 요약 — 돈·수수료 없는 '규칙 결과' 집계다.
    build_trades 가 낸 체결 일정을 그대로 쓰므로 거래당 수익률은 구성상 동일하다.
      trades/closed/open · win/avg/median/days(청산 거래 기준) · f20_win/f20_avg(20거래일 보유)
      · rule_hits(매도 규칙별 발동 수) · tranche_hits(2차 이후 분할 매수 수)
      · size_counts(금액 정책 — 매수 결정 buys 회 중 모름 종류별 횟수, 문구는 judge.size_notes)."""
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
    bs = [b for t in trade_list for b in t.get("buys", [])]
    out["size_counts"] = {"buys": len(bs), **{k: sum(1 for b in bs if k in b.get("flags", ()))
                                         for k, _ in SIZE_NOTES}}
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
