#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vectorbt 백테스트 '계산기'(구간③) — 돈·성적만 계산한다(판단은 판정기 Judge 의 등급이 낸다).

무엇을 하나
  체결 일정(한 진입 → 그 청산까지의 buys/sells)은 체결 워크(trading.trades.build_trades)가 만든다.
  이 계산기는 그 체결 일정을 받아 vectorbt 로 굴려 포트폴리오 지표(자산곡선·MaxDD·샤프·총수익)를 낸다 —
  모의 실행기(시작자본·수수료·세금으로 체결 일정을 돈으로 굴림)다. (규칙 평가·거래 경계·거래당 수익률은
  trading.trades 에 있다 — 여기서 다시 정하지 않는다.)
  분할매수/부분매도는 from_signals 의 bool 로는 안 되므로(spike 권고), 체결 일정을 size 배열로 선계산해
  vbt.Portfolio.from_orders 에 넣는 '접착제'로 처리한다.

실주문 실행기 자리(LiveExecutor — 범위 밖)
  같은 체결 일정을 증권사(jhts) 실주문으로 내는 실행기가 들어올 자리다. 지금은 빈 자리표(아래 LiveExecutor)뿐 —
  네트워크·주문 코드 없음.

하드코딩 0
  수수료·거래세·슬리피지·시작자본은 trading/market_config.json(시장별 US/KR)에서 읽는다.
  코드에 시장 숫자 리터럴을 두지 않는다. 심볼의 시장은 md_feed.market_of 가 정한다.

우리 체결 규약 유지
  체결가·체결일은 trading.trades.build_trades 가 '신호 다음날 시가 진입'(미래누수 없음)으로 정한다 —
  계산기(vectorbt)가 체결 타이밍을 다시 정하지 않는다(규약을 존중).

한국 거래세(매도측 비대칭)
  vectorbt fees 는 양방향 동일이라 '매도에만 세금'을 바로 넣을 파라미터가 없다. spike exp5 방식대로
  fees 를 시변(time-varying) 배열로 주고, 매도(청산)가 일어나는 봉에만 (수수료+거래세)를, 매수 봉엔
  (수수료)만 넣어 매도 비대칭을 정확히 구현한다.

상하한가·호가단위(placeholder)
  market_config 의 price_limit_pct·tick_size 가 non-null 이어도 체결 글루가 아직 적용하지 못한다
  (vectorbt 체결엔진엔 없다 — spike exp5). 값이 있으면 '미적용'을 경고 로그로 정직하게 표면화하고
  (_warn_unapplied_limits), 결과 dict 의 limits_unapplied 로도 돌려준다. null 이면 제한 없음(미국).

parity(옛 계산기와 숫자 일치)
  거래 경계는 머리가 정한다 — '한 진입 신호 → 그 청산까지'가 한 거래(trading.trades.build_trades 정의).
  vectorbt 의 pf.trades 는 부분매도를 FIFO 로트로 쪼개 세므로 '거래 수'가 다르게 보인다.
  그래서 parity 지표(거래수·승률·거래당 평균수익률)는 '머리가 정한 거래 경계'로 집계한다
  (trading.trades._parity_stats). vectorbt 가 새로 더하는 것은 포트폴리오 지표뿐이다.

지표 정의(라이브러리마다 다르므로 못박는다)
  · total_return  = (마지막 자산 / 시작자본) − 1. vbt.Portfolio.total_return().
  · max_drawdown  = 자산곡선의 최고점 대비 최대 하락폭(음수 아닌 비율). vbt.Portfolio.max_drawdown()
                    (vbt 는 음수로 돌려주므로 절댓값으로 보고). 'value'(현금+보유평가) 곡선 기준.
  · sharpe        = vbt.Portfolio.sharpe_ratio(). 일별 수익률 기준, freq='1D' 로 연율화
                    (무위험수익률 0 가정). 거래가 없으면 NaN → None 으로 보고.
  · equity_curve  = vbt.Portfolio.value() — 매 거래일의 (현금 + 보유 평가액). 점 개수 = 거래일 수.
  · win_rate/avg  = 머리가 정한 거래 경계로 집계(trading.trades._parity_stats).
"""
import json
import logging
import math
import os

from shared.paths import read_text
from shared import md_feed
from trading.trades import _parity_stats, _position_facts

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_config.json")
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


# ------------------------------------------------------------------ 접착제: 머리의 체결 일정 → vbt 입력
def _orders_from_trades(trade_list, cal):
    """trading.trades.build_trades 가 낸 거래 목록(각 거래의 buys/sells)을 '거래일별 주문'으로 편다.
    돌려주는 것: 날짜 인덱스 i → (signed_units, fill_price, is_sell_bar).
      signed_units > 0 매수, < 0 매도(한 봉에 매수·매도가 겹치면 합산; 세금은 매도가 있으면 가산).
    단위(units)는 규칙 평가 워크의 추상 물량(tranche frac 합=1.0) 그대로다 — 계산기가 물량을 다시 정하지 않는다."""
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


# ------------------------------------------------------------------ 메인: 한 상품을 vectorbt 로 굴린다
def run_product(symbol, cal, closes, trade_list):
    """한 상품의 성적을 vectorbt 로 계산해 dict 로 돌려준다.
      symbol     : 심볼(시장 파라미터를 고르는 데 씀)
      cal        : 거래일 목록(YYYYMMDD, 오름차순) — grade.history 의 달력 그대로
      closes     : cal 과 같은 길이의 종가 리스트(없는 날은 None 가능)
      trade_list : 머리가 낸 신호·규칙을 trading.trades.build_trades 가 체결 일정으로 편 거래 목록(buys/sells 포함)

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

    # 축은 일봉(YYYYMMDD) 또는 장중 분봉(YYYYMMDDHHMM) — 키 길이로 포맷을 고른다(둘 다 지원).
    _fmt = "%Y%m%d%H%M" if cal and len(cal[0]) == 12 else "%Y%m%d"
    idx = pd.DatetimeIndex(pd.to_datetime(cal, format=_fmt))
    # 종가에 빈 날(None)이 있으면 앞 값으로 채운다(자산 평가용 — 체결가는 price 로 따로 줌)
    close_ser = pd.Series(closes, index=idx).ffill().bfill()

    # 주기(freq) — 지표 연율화의 단위. 일봉 축이면 1D, 장중(분봉) 축이면 봉 간격(중앙값)을 그대로 쓴다
    #   (분봉 축에 1D 를 넣으면 샤프 연율화가 틀린다 — 축에서 간격을 읽어 맞춘다. 짧은 구간은 참고용).
    freq = "1D"
    if _fmt.endswith("%M") and len(idx) >= 2:
        step = pd.Series(idx).diff().dropna().median()
        if pd.notna(step) and step.total_seconds() > 0:
            freq = step

    pf = vbt.Portfolio.from_orders(
        close=close_ser,
        size=pd.Series(size, index=idx),
        price=pd.Series(price, index=idx),
        fees=pd.Series(fees, index=idx),
        slippage=slippage,
        init_cash=init_cash,   # 1 unit = 자본 전액(init_cash/px 주). 진입이 시간상 겹치지 않아(build_trades free_from) 초과 없음.
        freq=freq,
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


class LiveExecutor:
    """(빈 자리) 실주문 실행기 — 체결 일정(buys/sells)을 jhts 증권사 주문으로 낸다. 범위 밖이라 구현 없음."""

    def __init__(self, *_a, **_k):
        raise NotImplementedError("LiveExecutor — jhts 실주문 미구현(자리만 있음)")
