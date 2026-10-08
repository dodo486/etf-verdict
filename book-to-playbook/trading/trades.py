#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""매도·분할 규칙 리더 + 규칙 평가 워크(구간③) — 트리(books/<slug>/tree.json)의
exit/sizing 규칙을 읽어, 그 규칙을 봉마다 평가해 체결 일정·거래 요약을 만든다(책 무관, 돈·수수료·지표 없음).

이 모듈은 '규칙'만 다룬다 — 돈·수수료·성적(자산곡선·MaxDD·샤프)은 계산기(trading/portfolio)가
build_trades 결과(체결 일정)를 받아서 낸다. 매도 정책(책에 매도 규칙이 없으면 어떻게 하나)의 주인도 이 파일.

규칙 리더
  · exit_policy : 매도 정책 "book"(책 매도 규칙으로 청산 시뮬레이션) | "none"(책에 매도 규칙 없음 — 대체 규칙을
                  지어내지 않고 매수 신호 뒤 N거래일 보유 수익률로만 평가, 표시 문구 NO_EXIT_NOTE). 모두 이걸 묻는다.
  · tranches_of : 분할 매수 차수. 저자가 비율을 안 줬으면(frac null) 전량 한 번(비율을 지어내지 않는다).
  · unsized_note: 분할 비율·매도 비율 '저자 미명시'를 백테스트가 어떻게 계산했는지 결과에 표시할 문구.

수량 변환(이 파일 하나가 주인, verify_code 주인 표 '수량 변환')
  · to_units    : 정규화된 '얼마나'(출입구 Qty(of, x) — cash·budget·order·bought·held)를 물량으로 바꾸는 단 하나의
                  함수. 매수(분할 차수)·매도(산/남은 물량의 비율)·비중·조심 배수가 전부 여기를 지난다 — 종류별로 따로
                  해석하던 코드(분할 frac·매도 initial/remaining·안 쓰던 비중/조심)를 하나로 모았다. 장부 = Ledger.
  · sell_text · live_units : 화면이 basis 를 다시 해석하지 않게 매도 문장·라이브 오늘 장부를 여기서 빚는다.

금액 정책(얼마나 사나 — 이 파일 하나가 주인, verify_code 주인 표 '금액 정책')
  · size_of     : 그날의 '얼마나' 사실(judge.Amount — 라이브 화면과 같은 Judge.amount 한 경로)을 그날 장부
                  Ledger(budget = 비중, order = 조심 배수)로. 매수 물량 = to_units(분할 차수 Qty, 그 장부)
                  = 분할 비율 × 비중(%)/100 × 조심 배수.
                  모름은 지어내지 않는다(아래 SIZE_NOTES 로 횟수를 결과에 드러낸다):
                    · 폭 미명시 조심(scale null)이 걸림 → 그 규칙은 ×1(줄이지 않음)
                    · 걸렸는지 모르는 조심(수동·데이터 없음) → ×1. 'manual → 매매가 안 나가는 쪽' 규칙은 매매가 '나가나'
                      (진입·분할·매도 발동)의 규칙이라 '얼마나'엔 그대로 적용되지 않는다 — 비관 쪽으로 깎지 않는다.
                    · 비중 저자 미명시(weight null) → 상품 예산 100% 기준(배수 1)
                    · 비중 식은 있으나 그날 값 모름(저자 미명시 숫자 "?"·수동) → 상품 예산 100% 기준(배수 1)
                    · 금액 사실이 없음(그 봉의 판정 없음) → 배수 1
  · size_notes  : 위 횟수(_parity_stats 의 size_counts)를 결과에 보일 문구로.

규칙 평가 워크(돈·수수료·지표 없음)
  · build_trades   : 머리(tree)가 정한 진입 신호·분할·매도 규칙을 받아 '한 진입 → 그 청산까지'의
                     체결 일정(buys/sells)을 만든다. 평단은 봉마다 여기서 계산해 보유(judge.Holding — 라이브
                     보유 화면과 같은 pos 주입 문맥)로 cond 에 넣고, cond 는 그 값을 '읽어' exit/분할 규칙만
                     평가한다. 돈·수수료는 손대지 않는다 — 그건 계산기(portfolio)의 일.
  · _parity_stats  : 머리가 정한 거래 경계(한 진입→청산)로 집계한 거래 요약(거래수·승률·거래당 평균 등).
  · _position_facts: 지금 열려 있는(미청산) 마지막 거래의 사실(진입가·평단·현재수익률·보유일 등).

트리는 호출자가 넘긴 TreeGateway(gw — checklist/tree_gateway.py)로 읽는다 — 규칙은 gw 가 건네는 Rule(label·when·qty)로만,
수량은 정규화된 Qty(of, x)로만 다룬다(원본의 sell·frac 키 모양을 모른다).
"""
import statistics
from collections import namedtuple

from checklist.tradeTool import Cond
from checklist.tree_gateway import Qty
from trading.judge import Holding

FULL = [{"label": "전량", "frac": 1.0}]          # 한 번에 전량 — 트리 규칙 형식 그대로 두고 쓸 때 gw.as_rules 로 감싼다
NO_EXIT_NOTE = "책에 매도 규칙 없음 — 매수 신호만 평가"   # 매도 정책 "none" 의 표시 문구(백테스트 탭·판정 화면이 받아 쓴다)


def exit_policy(gw, prod):
    """매도 정책 — 이 함수 하나가 주인이다(밖은 이걸 묻는다). "book" = 책의 매도 규칙으로 청산까지 시뮬레이션.
    "none" = 책에 매도 규칙이 없다 → 대체 매도 규칙을 지어내지 않고, 거래 시뮬레이션 없이 매수 신호 뒤
    N거래일 보유 수익률(backtest 의 HORIZONS)로만 평가한다(화면 문구 NO_EXIT_NOTE)."""
    return "book" if gw.exit_rules(prod) else "none"


def tranches_of(gw, prod):
    """시뮬레이션에 쓰는 분할 — 저자가 비율을 안 줬으면(frac null) 전량 한 번으로 계산한다
    (비율을 지어내지 않는다 — 결과에 unsized_note 로 표시)."""
    trs = gw.tranches(prod) or gw.as_rules(FULL)
    return gw.as_rules(FULL) if trs[0].qty.x is None else trs


def unsized_note(gw, prod, exits):
    """저자가 비율을 안 준 수량 자리를 백테스트가 어떻게 계산했는지 — 없으면 None."""
    trs = gw.tranches(prod)
    out = ["분할 비율 저자 미명시 — 전량 한 번 매수로 계산"] if trs and trs[0].qty.x is None else []
    out += ["매도 비율 저자 미명시 「%s」 — 팔지 않은 것으로 계산" % r.label for r in exits if r.qty.x is None]
    return " · ".join(out) or None


# ------------------------------------------------------------------ 수량 변환: 정규화된 '얼마나'(Qty) → 물량
class Ledger(namedtuple("Ledger", "budget order bought held")):
    """수량 변환의 그 시점 장부(물량 단위 = 시작자본 1.0). budget = 오늘 이 상품에 배정된 물량(비중) ·
    order = 오늘 매수량 배수(조심) · bought = 지금까지 산 물량 · held = 지금 남은 물량."""
    __slots__ = ()

    def __new__(cls, budget=1.0, order=1.0, bought=0.0, held=0.0):
        return super().__new__(cls, budget, order, bought, held)


def to_units(q, led):
    """정규화된 '얼마나'(출입구 Qty(of, x)) → 물량 — 매수·매도·비중·조심이 전부 지나는 단 하나의 변환
    (verify_code 주인 표 '수량 변환'). led = 그 시점 장부(Ledger).
      cash   x → x/100                      총 투자금의 x %         (비중)
      budget x → x × led.budget × led.order  이 상품 배정 금액의 x   (분할 차수 — 오늘 산다: 조심 배수가 곱해진다)
      order  x → x                          오늘 매수량의 x 배       (조심)
      bought x → x × led.bought             지금까지 산 물량의 x     (매도 {"initial": x})
      held   x → x × led.held               지금 남은 물량의 x(1=전량)(매도 "all"·{"remaining": x})
    x None(저자 미명시) → None — 지어내지 않는다(호출자 정책: 매도는 팔지 않음 · 비중·조심은 size_of)."""
    if q.x is None:
        return None
    return {"cash": lambda: q.x / 100.0, "budget": lambda: q.x * led.budget * led.order, "order": lambda: q.x,
            "bought": lambda: q.x * led.bought, "held": lambda: q.x * led.held}[q.of]()


def sell_text(q):
    """매도 수량(Qty)의 사람 문장 — 화면이 basis 를 다시 해석하지 않게 여기서 빚는다."""
    if q.x is None:
        return ("산 물량의 " if q.of == "bought" else "남은 물량의 ") + "? (비율 저자 미명시)"
    if q.of == "held" and q.x == 1:
        return "남은 전량"
    return ("산 물량의 " if q.of == "bought" else "남은 물량의 ") + "%d%%" % round(q.x * 100)


def live_units(a, q=None):
    """라이브 화면의 오늘 물량(시작자본 1.0 기준) — q(분할 차수 Qty) 생략이면 이 상품 오늘 배정 전체.
    비중을 모르면(미명시·그날 값 모름) None(화면은 금액을 '—'로 — 백테스트 정책으로 채우지 않는다).
    걸린 조심 배수는 a.factor(폭 미명시·확인 필요는 줄이지 않은 채 — 화면이 따로 표시)."""
    if not a.weight_set or a.weight is None:
        return None
    led = Ledger(budget=to_units(Qty("cash", a.weight), Ledger()), order=to_units(Qty("order", a.factor), Ledger()))
    return to_units(q or Qty("budget", 1.0), led)


# ------------------------------------------------------------------ 금액 정책: 그날의 '얼마나' 사실 → 매수 장부
# 결과에 남기는 모름의 종류 → 문구(%d = 매수 결정 횟수). 판단 근거는 모듈 docstring '금액 정책'.
SIZE_NOTES = (("unspecified", "폭 미명시 조심 %d회 — 금액 미반영(×1)"),
              ("unknown", "확인 필요(수동·데이터 없음) 조심 %d회 — 금액 미반영(×1)"),
              ("weight_unset", "비중 저자 미명시 — 상품 예산 100%% 기준(%d회)"),
              ("weight_unknown", "비중 그날 값 모름 %d회 — 상품 예산 100%% 기준"),
              ("no_facts", "금액 사실 없음 %d회 — 배수 1"))


def size_of(a):
    """그날의 Amount(judge.Judge.amount) → (오늘 장부 Ledger(budget=비중, order=조심 배수), 모름 표시 집합).
    물량 계산은 to_units 하나 — 여기는 모름을 어떻게 채울지(정책, 모듈 docstring '금액 정책')만 정한다:
    모름은 줄이지도 늘리지도 않고(×1·상품 예산 100%) 표시 집합으로 센다."""
    if a is None:
        return Ledger(), {"no_facts"}
    flags = set()
    if a.unspecified:
        flags.add("unspecified")
    if a.unknown:
        flags.add("unknown")
    if a.factor < 1:
        flags.add("cut")
    budget = to_units(Qty("cash", a.weight), Ledger()) if a.weight_set else None
    if budget is None:
        flags.add("weight_unknown" if a.weight_set else "weight_unset")
        budget = 1.0
    return Ledger(budget=budget, order=to_units(Qty("order", a.factor), Ledger())), flags


def size_notes(counts):
    """_parity_stats 의 size_counts 횟수 → 결과에 보일 문구 목록(모름이 없으면 [])."""
    return [txt % counts[k] for k, txt in SIZE_NOTES if counts.get(k)]


# ------------------------------------------------------------------ 규칙 평가 워크: 신호·규칙 → 체결 일정(buys/sells)
def build_trades(gw, prod, hist, cal, starts, exits, tranches=None, amount=None):
    """머리(tree — gw)가 정한 진입 신호·분할·매도 규칙을 받아 '한 진입 → 그 청산까지'의 거래 목록을 만든다.
    평단은 여기(규칙 평가 워크)가 봉마다 계산해 Holding 으로 주입하고, cond.py(순수 규칙 평가기)는 그 포지션 값을
    pos 로 '읽어' exit/분할 규칙만 평가한다. 돈·수수료·지표는 손대지 않는다 — 그건 계산기(portfolio)가 한다.

    규약(계산기가 체결 타이밍을 다시 정하지 않는다):
      · 물량 단위 = 시작자본 1.0. 사고팔 양은 전부 to_units(규칙 Qty, 장부) 하나로 낸다:
        매수 = 분할 차수(Qty "budget" — 없거나 미명시면 1차에 전량)를 그 매수를 정한 날(1차 = 신호일 T, 2차 이후 =
        조건이 참이 된 날)의 장부 size_of(amount(그날)) — 비중·조심 배수 — 로, 매도 = 매도 규칙 Qty 를 지금의
        산 물량·남은 물량 장부로. amount 생략(검사기 합성)이면 비중 100%·배수 1.
      · 1차: 신호 시작일 T 의 다음 날 시가(T+1)에. 한 상품에 포지션은 하나(보유 중 신호는 건너뜀).
      · 2차 이후: 매일 종가에 다음 차수 when 을 평가 → 참이면 다음 날 시가에(차례대로 각 한 번).
        같은 날 매도가 걸렸으면 그날은 사지 않는다.
      · 매도: 매일 종가에 규칙 평가 → 걸리면 다음 날 시가에. 규칙마다 한 번만(같은 날 여럿이면 적힌 순서).
        qty held x=남은 물량의 x(1 = 전량) · bought x=그때까지 산 물량의 x.
      · 수익률 = (판 금액 + 남은 물량 × 마지막 종가) ÷ 산 금액 − 1. 미청산은 마지막 종가로 평가.
      · manual 은 '매매가 안 나가는 쪽'으로 푼다(manual_as=False). 매도 비율 null(저자 미명시)도 같은 쪽 — 팔지 않는다.

    starts = 신호 시작일 인덱스 목록. exits·tranches = [Rule](gw 가 건넨 것), tranches 생략 = 트리의 분할(tranches_of).
    amount = 봉 인덱스 → judge.Amount(Judge.amount — 라이브와 같은 경로) | None. 각 매수에 size(배수)·flags(모름) 를 남긴다."""
    tranches = tranches if tranches is not None else tranches_of(gw, prod)
    tranches = gw.as_rules(FULL) if (not tranches or tranches[0].qty.x is None) else tranches

    def buy(i, at, t):
        """i 번째 봉에서 정한 차수 t 의 매수(체결 at = 다음 봉) — 물량은 to_units(차수 Qty, 그날 장부)."""
        led, fl = size_of(amount(i)) if amount is not None else (Ledger(), set())
        return {"date": cal[at], "px": opens[at], "qty": to_units(t.qty, led), "tranche": t.label,
                "size": to_units(Qty("budget", 1.0), led), "flags": sorted(fl)}
    cs = {c.date: c for c in hist.get(prod) or []}
    opens = [cs[d].open if d in cs else None for d in cal]
    closes = [cs[d].close if d in cs else None for d in cal]
    L = len(cal)
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

        def rebuild(frm):
            """frm 부터 평단이 바뀐다 → 날짜별 평단(cost)을 다시 계산해 pos 로 cond 에 주입(상태 주입).
            cond 는 그 값을 읽어 ret/days/maxret/minret 로 exit·분할 규칙만 평가한다(역류 아님)."""
            q = sum(b["qty"] for b in buys)
            avg = sum(b["qty"] * b["px"] for b in buys) / q
            for k in range(frm, L):
                cost[k] = avg
            ctx = Holding(e, list(cost)).ctx(gw, prod, hist, cal, manual_as=False)
            return ([Cond.series(r.when, ctx) for r in exits],
                    [Cond.series(t.when, ctx) if t.when is not None else None for t in tranches])

        whens, twhens = rebuild(e)
        nxt, sells, fired, last = 1, [], set(), None
        for d in range(e, L):
            sold_today = False
            for k, r in enumerate(exits):
                if k in fired or whens[k][d] is not True:
                    continue
                fired.add(k)
                q = to_units(r.qty, Ledger(bought=bought, held=remaining))
                if q is None:
                    continue                      # 비율 저자 미명시 — 팔지 않는다(unsized_note 로 표시)
                if d + 1 >= L or not opens[d + 1]:
                    continue                      # 다음 날이 없다 — 체결 못 함(미청산으로 남는다)
                q = min(q, remaining)             # 남은 것보다 많이 팔 수는 없다
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
      · rule_hits(매도 규칙별 발동 수) · tranche_hits(2차 이후 분할 매수 수)
      · size_counts(금액 정책 — 매수 결정 buys 회 중 조심으로 줄인 cut · 모름 종류별 횟수, 문구는 size_notes)."""
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
                                         for k in ("cut",) + tuple(k for k, _ in SIZE_NOTES)}}
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
