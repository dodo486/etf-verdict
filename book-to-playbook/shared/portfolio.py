#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vectorbt 백테스트 '계산기' + 체결 글루 — 돈·성적만 계산한다(판단은 머리=cond.py/tree 의 등급이 낸다).

무엇을 하나
  · 글루(build_trades): 머리(tree)가 정한 진입 신호·분할·매도 규칙을 받아 '한 진입 → 그 청산까지'의
    체결 일정(buys/sells)을 만든다. 포지션 사실(진입가·평단·ret·maxret·days)은 글루가 봉마다 계산하고,
    cond.py(순수 규칙 평가기)는 그 값을 pos 로 '읽어' exit/분할 규칙만 평가한다(단방향 폭포수).
  · 계산기(run_product): 그 체결 일정을 vectorbt 로 굴려 포트폴리오 지표(자산곡선·MaxDD·샤프·총수익)를 낸다.
  (옛 shared/trades.py 의 simulate/stats 가 이 두 일을 하던 자리였다 — 2단계에서 여기로 옮기고 거기서 삭제.
   trades.py 에는 '규칙 리더'(exits_of·tranches_of·standard_label 등)만 남는다.)

머리=판단 / 계산기=계산 분리
  진입/청산 신호와 분할(tranche)·매도 규칙은 머리(tree)에서 나온다. 글루는 그 규칙을 읽어 체결 일정을
  만들고, 계산기는 그 일정을 받아 vectorbt 로 돈을 굴린다.
  분할매수/부분매도는 from_signals 의 bool 로는 안 되므로(spike 권고), 체결 일정을 size 배열로 선계산해
  vbt.Portfolio.from_orders 에 넣는 '접착제'로 처리한다.

하드코딩 0
  수수료·거래세·슬리피지·시작자본은 shared/market_config.json(시장별 US/KR)에서 읽는다.
  코드에 시장 숫자 리터럴을 두지 않는다. 심볼의 시장은 md_feed.market_of 가 정한다.

우리 체결 규약 유지
  체결가·체결일은 글루가 '신호 다음날 시가 진입'(미래누수 없음)으로 정한다 — 계산기(vectorbt)가
  체결 타이밍을 다시 정하지 않는다(글루의 규약을 존중).

한국 거래세(매도측 비대칭)
  vectorbt fees 는 양방향 동일이라 '매도에만 세금'을 바로 넣을 파라미터가 없다. spike exp5 방식대로
  fees 를 시변(time-varying) 배열로 주고, 매도(청산)가 일어나는 봉에만 (수수료+거래세)를, 매수 봉엔
  (수수료)만 넣어 매도 비대칭을 정확히 구현한다.

상하한가·호가단위(placeholder)
  market_config 의 price_limit_pct·tick_size 가 non-null 이어도 체결 글루가 아직 적용하지 못한다
  (vectorbt 체결엔진엔 없다 — spike exp5). 값이 있으면 '미적용'을 경고 로그로 정직하게 표면화하고
  (_warn_unapplied_limits), 결과 dict 의 limits_unapplied 로도 돌려준다. null 이면 제한 없음(미국).

parity(옛 계산기와 숫자 일치)
  거래 경계는 머리가 정한다 — '한 진입 신호 → 그 청산까지'가 한 거래(글루 build_trades 정의).
  vectorbt 의 pf.trades 는 부분매도를 FIFO 로트로 쪼개 세므로 '거래 수'가 다르게 보인다.
  그래서 parity 지표(거래수·승률·거래당 평균수익률)는 '머리가 정한 거래 경계'로 집계한다
  (글루가 낸 체결 일정을 그대로 쓰므로 거래당 수익률은 '구성상 동일'하다). vectorbt 가 새로 더하는
  것은 포트폴리오 지표(자산곡선·MaxDD·샤프·총수익)뿐이다.

지표 정의(라이브러리마다 다르므로 못박는다)
  · total_return  = (마지막 자산 / 시작자본) − 1. vbt.Portfolio.total_return().
  · max_drawdown  = 자산곡선의 최고점 대비 최대 하락폭(음수 아닌 비율). vbt.Portfolio.max_drawdown()
                    (vbt 는 음수로 돌려주므로 절댓값으로 보고). 'value'(현금+보유평가) 곡선 기준.
  · sharpe        = vbt.Portfolio.sharpe_ratio(). 일별 수익률 기준, freq='1D' 로 연율화
                    (무위험수익률 0 가정). 거래가 없으면 NaN → None 으로 보고.
  · equity_curve  = vbt.Portfolio.value() — 매 거래일의 (현금 + 보유 평가액). 점 개수 = 거래일 수.
  · win_rate/avg  = 머리가 정한 거래 경계로 집계(옛 stats 와 같은 정의).
"""
import json
import logging
import math
import os

from shared.paths import BASE, read_text
from shared import cond, md_feed, trades as trades_mod

_CONFIG_PATH = os.path.join(BASE, "shared", "market_config.json")
_CONFIG = None
_log = logging.getLogger(__name__)


def _config():
    """market_config.json 을 한 번 읽어 캐시. 숫자는 전부 여기서 온다(코드 리터럴 금지)."""
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = json.loads(read_text(_CONFIG_PATH))
    return _CONFIG


def market_params(symbol):
    """심볼의 시장(US/KR) 체결·비용 파라미터 dict. 시장을 모르면 config 의 default 시장을 쓴다.
    (심볼→시장은 md_feed.market_of 가 정한다 — 여기서 시장을 추측하지 않는다.)"""
    cfg = _config()
    mk = md_feed.market_of(symbol) or cfg["default"]
    params = cfg["markets"].get(mk) or cfg["markets"][cfg["default"]]
    return dict(params, market=mk)


def _warn_unapplied_limits(symbol, mp):
    """상하한가(price_limit_pct)·호가단위(tick_size) placeholder 를 정직하게 표면화한다.
    값이 있으면(non-null) 아직 체결 글루가 적용하지 못하므로 '미적용'을 경고로 남긴다 —
    없는데 적용한 척하지 않는다(값 null 이면 제한 없음이므로 조용히 넘어간다).
    완전구현(체결 거부·가격 반올림)은 데이터 확정 후 이 글루 안에서 한다(후속)."""
    unapplied = [name for name in ("price_limit_pct", "tick_size") if mp.get(name) is not None]
    if unapplied:
        _log.warning("[%s/%s] %s config 값이 있으나 체결 글루가 아직 적용하지 못합니다 — 미적용(placeholder). "
                     "완전구현 전까지 체결가·체결 가능 여부는 상하한가/호가단위를 반영하지 않습니다.",
                     mp.get("market"), symbol, ", ".join(unapplied))
    return unapplied


# ------------------------------------------------------------------ 글루: 신호·규칙 → 체결 일정(buys/sells)
def build_trades(tree, prod, hist, cal, starts, exits, tranches=None):
    """머리(tree)가 정한 진입 신호·분할·매도 규칙을 받아 '한 진입 → 그 청산까지'의 거래 목록을 만든다.
    이것이 '글루'다 — 포지션 사실(진입가·평단·ret·maxret·days)은 여기(글루)가 봉마다 계산하고,
    cond.py(순수 규칙 평가기)는 그 포지션 값을 pos 로 '읽어' exit/분할 규칙만 평가한다(단방향 폭포수).

    규약(옛 trades.simulate 와 동일 — 계산기가 체결 타이밍을 다시 정하지 않는다):
      · 물량 단위 = 전체 1.0. 분할이 없거나 비율 미명시(frac null)면 1차에 1.0 전량.
      · 1차: 신호 시작일 T 의 다음 날 시가(T+1)에. 한 상품에 포지션은 하나(보유 중 신호는 건너뜀).
      · 2차 이후: 매일 종가에 다음 차수 when 을 평가 → 참이면 다음 날 시가에(차례대로 각 한 번).
        같은 날 매도가 걸렸으면 그날은 사지 않는다.
      · 매도: 매일 종가에 규칙 평가 → 걸리면 다음 날 시가에. 규칙마다 한 번만(같은 날 여럿이면 적힌 순서).
        sell "all"=남은 전량 · {"initial":f}=그때까지 산 물량의 f · {"remaining":f}=남은 물량의 f.
      · 수익률 = (판 금액 + 남은 물량 × 마지막 종가) ÷ 산 금액 − 1. 미청산은 마지막 종가로 평가.
      · manual 은 '매매가 안 나가는 쪽'으로 푼다(manual_as=False).

    starts = 신호 시작일 인덱스 목록. tranches 생략 = 트리의 분할(trades_mod.tranches_of)."""
    tranches = tranches if tranches is not None else trades_mod.tranches_of(tree, prod)
    tranches = trades_mod.FULL if (not tranches or tranches[0].get("frac") is None) else tranches
    cs = {c.date: c for c in hist.get(prod) or []}
    opens = [cs[d].open if d in cs else None for d in cal]
    closes = [cs[d].close if d in cs else None for d in cal]
    cfg, defs = tree["products"][prod], tree.get("defs") or {}
    L = len(cal)
    out, free_from = [], 0
    for s in starts:
        e = s + 1
        if e >= L or e < free_from or not opens[e]:
            continue
        buys = [{"date": cal[e], "px": opens[e], "qty": tranches[0]["frac"], "tranche": tranches[0]["label"]}]
        bought = tranches[0]["frac"]
        remaining = bought
        cost = [None] * L

        def rebuild(frm):
            """frm 부터 평단이 바뀐다 → 글루가 날짜별 평단(cost)을 다시 계산해 pos 로 cond 에 주입(상태 주입).
            cond 는 그 값을 읽어 ret/days/maxret/minret 로 exit·분할 규칙만 평가한다(역류 아님)."""
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
        out.append({"entry": cal[e], "entry_px": px, "exit": cal[end] if closed else None,
                    "closed": closed, "days": end - e, "ret": (value / spent - 1) * 100,
                    "buys": buys, "sells": sells, "fixed20": ((closes[e + 19] / px - 1) * 100
                                                              if e + 19 < L and closes[e + 19] else None)})
        free_from = end + 1 if closed else L
    return out


# ------------------------------------------------------------------ 접착제: 머리의 체결 일정 → vbt 입력
def _orders_from_trades(trade_list, cal):
    """글루(build_trades)가 낸 거래 목록(각 거래의 buys/sells)을 '거래일별 주문'으로 편다.
    돌려주는 것: 날짜 인덱스 i → (signed_units, fill_price, is_sell_bar).
      signed_units > 0 매수, < 0 매도(한 봉에 매수·매도가 겹치면 합산; 세금은 매도가 있으면 가산).
    단위(units)는 옛 계산기의 추상 물량(tranche frac 합=1.0) 그대로다 — 계산기가 물량을 다시 정하지 않는다."""
    di = {d: i for i, d in enumerate(cal)}
    orders = {}  # i -> {"units": float, "price": float, "sell": bool}
    for t in trade_list:
        for b in t["buys"]:
            i = di[b["date"]]
            o = orders.setdefault(i, {"units": 0.0, "price": b["px"], "sell": False})
            o["units"] += b["qty"]
            o["price"] = b["px"]            # 같은 봉이면 체결가는 동일(시가)
        for s in t["sells"]:
            i = di[s["date"]]
            o = orders.setdefault(i, {"units": 0.0, "price": s["px"], "sell": False})
            o["units"] -= s["qty"]
            o["price"] = s["px"]
            o["sell"] = True
    return orders


def _parity_stats(trade_list, last_close=None):
    """머리가 정한 거래 경계(한 진입→청산)로 집계한 parity 지표 — 옛 trades.stats 와 같은 정의.
    글루(build_trades)가 낸 체결 일정을 그대로 쓰므로 거래당 수익률은 구성상 동일하다.
      trades/closed/open · win/avg/median/days(청산 거래 기준) · f20_win/f20_avg(20거래일 보유)
      · rule_hits(매도 규칙별 발동 수) · tranche_hits(2차 이후 분할 매수 수)."""
    import statistics
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


# ------------------------------------------------------------------ 포지션 현황(열린 거래 사실)
def _position_facts(trade_list, closes):
    """지금 열려 있는(미청산) 마지막 거래의 사실 — 없으면 None.
    {entry_px(진입가) · avg_px(평단) · ret(현재수익률%) · high(보유 중 최고 종가) ·
     low(보유 중 최저 종가) · days(보유일)}. 전부 글루(build_trades)가 준 값/시세에서 파생(새 숫자 없음)."""
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


# ------------------------------------------------------------------ 메인: 한 상품을 vectorbt 로 굴린다
def run_product(symbol, cal, closes, trade_list):
    """한 상품의 성적을 vectorbt 로 계산해 dict 로 돌려준다.
      symbol     : 심볼(시장 파라미터를 고르는 데 씀)
      cal        : 거래일 목록(YYYYMMDD, 오름차순) — tree_grade.history 의 달력 그대로
      closes     : cal 과 같은 길이의 종가 리스트(없는 날은 None 가능)
      trade_list : 머리가 낸 신호·규칙을 글루(build_trades)가 체결 일정으로 편 거래 목록(buys/sells 포함)

    출력: {market_params, total_return, max_drawdown, sharpe, equity_curve, win_rate,
           parity(거래수·승률·거래당평균 등 옛 정의), position_facts, limits_unapplied}
    vectorbt(pandas/numpy)는 여기서만 import 한다 — 미설치 환경에서도 모듈 import 는 되게."""
    import numpy as np
    import pandas as pd
    import vectorbt as vbt

    mp = market_params(symbol)
    init_cash = mp["init_cash"]
    commission = mp["commission"]
    sell_tax = mp["sell_tax"]
    slippage = mp["slippage"]
    limits_unapplied = _warn_unapplied_limits(symbol, mp)  # 상하한가·호가단위 placeholder 를 정직하게 표면화

    L = len(cal)
    orders = _orders_from_trades(trade_list, cal)

    # 추상 물량(units, frac 합 1.0)을 '주수'로 바꾼다: 1.0 unit = 진입 시 자본을 가득(1.0배) 쓴 것.
    #   → 1 unit 매수 = (init_cash / 체결가) 주. 부분매도는 같은 환산으로 음수 주수.
    #   (여러 진입이 시간상 겹치지 않으므로 — build_trades 의 free_from 가드 — 자본 초과가 없다.)
    size = np.full(L, np.nan)
    price = np.full(L, np.nan)
    fees = np.full(L, commission)  # 기본: 수수료만
    for i, o in orders.items():
        px = o["price"]
        size[i] = o["units"] * (init_cash / px)
        price[i] = px
        if o["sell"]:
            fees[i] = commission + sell_tax  # 매도(청산) 봉에만 거래세 가산(한국 매도 비대칭)

    idx = pd.DatetimeIndex(pd.to_datetime(cal, format="%Y%m%d"))
    # 종가에 빈 날(None)이 있으면 앞 값으로 채운다(자산 평가용 — 체결가는 price 로 따로 줌)
    close_ser = pd.Series(closes, index=idx).ffill().bfill()

    pf = vbt.Portfolio.from_orders(
        close=close_ser,
        size=pd.Series(size, index=idx),
        price=pd.Series(price, index=idx),
        fees=pd.Series(fees, index=idx),
        slippage=slippage,
        init_cash=init_cash,   # 1 unit = 자본 전액(init_cash/px 주). 진입이 시간상 겹치지 않아(build_trades free_from) 초과 없음.
        freq="1D",
    )

    eq = pf.value()
    mdd = pf.max_drawdown()
    sharpe = pf.sharpe_ratio()
    closes_clean = [c for c in closes if c is not None]
    last_close = closes_clean[-1] if closes_clean else None
    parity = _parity_stats(trade_list, last_close)

    def _f(x):
        """NaN/inf → None(라이브러리 지표가 거래 없을 때 NaN 을 주므로)."""
        try:
            x = float(x)
            return None if math.isnan(x) or math.isinf(x) else x
        except (TypeError, ValueError):
            return None

    return {
        "symbol": symbol,
        "market_params": mp,
        "total_return": _f(pf.total_return() * 100) if pf.total_return() is not None else None,
        "max_drawdown": _f(abs(mdd) * 100) if mdd is not None else None,  # 양수 비율(%)
        "sharpe": _f(sharpe),
        "equity_curve": [{"date": d, "value": _f(v)} for d, v in zip(cal, eq.tolist())],
        "equity_points": len(eq),
        "win_rate": parity.get("win"),
        "parity": parity,
        "position_facts": _position_facts(trade_list, closes),
        "limits_unapplied": limits_unapplied,  # 적용 못 한 상하한가·호가단위(placeholder) — 없으면 []
    }
