#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""통합 스테핑 드라이버 (책 무관) — 구간④. "시간을 밟으며 매 asof 판정하는" 단일 코어.

## 왜 하나로 합쳤나

옛날엔 "시간을 밟으며 asof 판정"하는 루프가 둘로 중복됐다: operations.backtest.run(일봉 하루씩)과
operations.replay(장중 asof). 판정 머리(verdict_engine.product_verdict / tree_grade.ProductEval)는 이미
한 벌을 공유했지만(신호 파리티 720/720 로 증명), '시간을 밟는' 바깥 루프가 둘이었다. 이 모듈이 그
스테핑을 하나로 모은다 — 뒤에 붙는 것만 용도별로 다르다(백테스트=계산기 / 재생=신호출력 / 라이브=단건).

## finest_tf 로 간격을 정한다

트리가 쓰는 가장 촘촘한 tf(finest_tf)가 스테핑 간격을 정한다:

  · finest=1d  — 하루 한 점(일봉 축). 신호는 operations.backtest 의 '벡터 1회계산 경로'(ProductEval 를
    한 번 만들어 전체 달력을 인덱싱)가 낸다 — 여기서 하루마다 product_verdict 를 재호출하지 않는다
    (수백배 느려지니 금지). 그 경로가 일봉 파리티(백테스트==라이브)를 지킨다. 이 모듈의 timeline 은
    '일봉 축은 장중 재생 대상이 아님'을 뜻하는 빈 리스트다.
  · finest=5m/1m — 분봉 축. asof_timeline(분봉 데이터 있는 범위, 세션 안)으로 각 asof 를 깔고, 그 각
    시점에서 머리(product_verdict)를 호출해 장중 신호·등급 시계열을 낸다(step). 일봉 잎은 그 asof 이하
    마지막 확정 일봉(어제값), 분봉 잎은 그 asof 이하 마지막 분봉 — 둘 다 cond 가 asof 로 자른다.

## 세 용도 (뒤에 붙는 것만 다르다)

  · 재생(replay)    : step() 의 신호 시계열을 그대로 쓴다(신호만).
  · 백테스트(backtest): finest=1d → 기존 벡터 경로(일봉 vectorbt). finest=5m/1m → step() 으로 분봉
    신호를 얻고, 그 분봉 종가 시리즈로 vectorbt 계산기를 돌려 '장중 백테스트' 지표를 낸다.
  · 라이브(live)    : timeline=[now] 한 점 — render/product_verdict 단건(미래 실행 대상 = 증권사).

## 정직한 한계 (가짜로 안 늘린다)

분봉은 jhts 분봉(md_feed.minutes → jhts.minute_bars, OHLCV+UTC)에서 온다. 지수·선물·Alpaca 미연결은
최근 ~7거래일만 온다. 장중 타임라인도 데이터 있는 세션·봉만 깔린다. 비거나 짧으면 "N세션·M봉만,
그 밖 데이터 없음"을 그대로 표면화한다(limit_note). 짧은 구간의 샤프/MaxDD 는 참고용으로만 본다.

## 단방향(폭포수)

operations/(구간④)에 있고 verdict·shared 만 import 한다(downward). 상류(playbook·checklist·verdict·
shared)는 이 파일을 import 하지 않는다 — verify_teams 가 강제.
"""
from datetime import datetime, timezone

from shared import cond, tree_grade
from verdict import verdict_engine

# tf 촘촘함 순서 — 초로 환산(작을수록 촘촘). cond.TIMEFRAMES 와 짝(그 밖 tf 는 문법이 막는다).
TF_SECONDS = {"1m": 60, "5m": 300, "1d": 86400}


def tree_tfs(tree):
    """트리가 실제로 쓰는 tf 집합(모든 px 잎). defs 펼침. 늘 최소 {"1d"}(기본값)를 포함할 수 있다."""
    defs = tree.get("defs") or {}
    tfs = set()
    nodes = list(defs.values())
    for cfg in tree["products"].values():
        nodes.extend(n for _z, _l, _r, n in cond.zone_nodes(cfg))
    for node in nodes:
        for n in cond.labeled_all(node, defs):
            if isinstance(n, dict) and "px" in n:
                tfs.add(n.get("tf", "1d"))
    return tfs


def finest_tf(tree):
    """트리의 '가장 촘촘한 tf'(1m < 5m < 1d). px 잎이 없으면(순수 수동 트리) 기본 "1d"."""
    tfs = tree_tfs(tree)
    if not tfs:
        return "1d"
    return min(tfs, key=lambda tf: TF_SECONDS.get(tf, TF_SECONDS["1d"]))


def _minute_keys(hist, syms):
    """hist.minutes 에서 syms 심볼들의 분봉 키(UTC YYYYMMDDHHMM) 합집합, 오름차순.
    (타임라인 asof 는 '데이터가 실제로 있는' 분봉 시각으로만 깐다 — 없는 봉을 지어내지 않는다.)"""
    mins = getattr(hist, "minutes", {}) or {}
    keys = set()
    for s in syms:
        keys.update((mins.get(s) or {}).keys())
    return sorted(keys)


def _key_to_asof(key):
    """분봉 키(UTC YYYYMMDDHHMM) → asof(UTC datetime, tz-aware)."""
    return datetime.strptime(key, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)


def asof_timeline(tree, hist, limit=None):
    """트리의 가장 촘촘한 tf 봉 타임스탬프로 asof 타임라인(UTC datetime 오름차순)을 만든다.

    · finest=1d : 일봉 축 — 하루 한 점(그날 마지막 확정 일봉 마감 시각)이 기존 동작이다. 분봉 데이터가 없어도
      일봉 판정은 되므로, 일봉 트리는 '분봉 재생' 대상이 아니다 → 빈 타임라인(이 드라이버의 장중 전용 경로).
      (일봉 신호는 backtest 의 벡터 1회계산 경로가 낸다 — 이 모듈은 그 경로를 재호출하지 않는다.)
    · finest=5m/1m : 그 심볼들의 분봉 키(데이터 있는 범위)를 asof 로 깐다. 5m 는 1분봉을 5분 버킷으로 접은
      '각 5분 봉의 종료(=다음 버킷 직전 마지막 분봉)' 시각을, 1m 는 분봉 키 그대로를 asof 로 쓴다.
    limit 을 주면 뒤(가장 최근)에서 limit 개만 — 긴 분봉도 꼬리만 빠르게 재생."""
    tf = finest_tf(tree)
    if tf == "1d":
        return []                               # 일봉 전용 트리 — 장중 재생할 분봉 축이 없다(빈 타임라인)
    syms = cond.minute_symbols_of(tree)
    keys = _minute_keys(hist, syms)
    if not keys:
        return []                               # 분봉 데이터 없음 — 타임라인도 없음(가짜로 안 늘림)
    if tf == "5m":
        # 5분봉 축 — 1분봉을 5분 버킷으로 접은 뒤, 각 버킷 안의 '마지막 분봉' 시각을 asof 로. 그 asof 에서 minute_series
        # 가 그 버킷을 asof 이하 마지막 5분봉으로 집계한다(한 심볼 기준 버킷 — 심볼마다 분봉 범위가 조금 달라도
        # 합집합 키로 세션 경계 안에서 접으므로 각 asof 에서 심볼별로 자기 마지막 버킷을 본다).
        buckets = {}
        for k in keys:
            mm = int(k[10:12])
            bkey = k[:10] + "%02d" % (mm - mm % 5)
            if bkey not in buckets or k > buckets[bkey]:
                buckets[bkey] = k              # 그 5분 버킷의 마지막(가장 늦은) 분봉 키
        stamps = sorted(buckets.values())
    else:                                       # 1m — 분봉 키 그대로
        stamps = keys
    if limit is not None:
        stamps = stamps[-limit:]
    return [_key_to_asof(k) for k in stamps]


# ------------------------------------------------------------------ 공통 스테핑 코어
def _truncate(full, upto):
    """full(History) 을 날짜 upto(YYYYMMDD) 이하로 자른 새 History. 분봉(minutes)은 그대로 넘긴다.
    과거 세션을 재생할 때 '그 세션 마감 직후 라이브가 보유했을' 일봉(그날까지의 확정 일봉)을 재현한다 —
    verify_signal_parity._truncate 와 같은 규약(일봉 파리티를 증명한 바로 그 방식)."""
    t = tree_grade.History({s: [c for c in (cs or []) if c.date <= upto] for s, cs in full.items()})
    t.minutes = getattr(full, "minutes", {})
    return t


def step(tree, hist, timeline, prods, truncate=False):
    """'시간을 밟으며 매 asof 판정하는' 공통 코어 — 재생·장중 백테스트가 같이 쓴다.

    각 asof 에서 verdict_engine.product_verdict(tree, p, hist, {}, asof) 를 불러(라이브가 하는 그대로,
    부작용 없는 진입점) 그 시점 (asof, key, grade, close) 를 모은다. 일봉 잎은 asof 이하 마지막 확정 일봉
    (어제값), 분봉 잎은 asof 이하 마지막 분봉 — 둘 다 cond 가 asof 로 자른다. 평가 규칙을 새로 만들지
    않고, asof 를 분봉 간격으로 깔아 '같은 판정 엔진'을 여러 시점에 돌릴 뿐이다.

    truncate 기본값(False) = 재생(replay)의 기존 동작 그대로 — full hist 에 asof 만 바꿔 '지금 상품 상태'를
    여러 분봉 스냅샷으로 본다(최근 세션 재생용). product_verdict 는 늘 달력 마지막 봉(오늘)을 판정하므로,
    과거 세션의 asof 에선 오늘 일봉 regime 을 과거 분봉과 묶는다(최근 세션엔 맞지만 과거 세션 regime 은 아님).

    truncate=True = 장중 백테스트용 — 각 asof 마다 일봉 hist 를 그 asof 세션일(YYYYMMDD) 이하로 잘라
    (verify_signal_parity 가 일봉 파리티를 증명한 바로 그 방식), 그 세션의 일봉 regime 을 그날 분봉 스냅샷과
    묶어 판정한다. 과거 세션도 '그 세션 자신의 regime + 그 시점 분봉'으로 충실히 재생된다(look-ahead 0 유지 —
    일봉 잎은 그 세션 마감 전엔 미확정, 마감 후 확정).

    → {prod: [{asof(UTC iso), key, grade, close}, ...]}  (timeline 순서대로)."""
    series = {p: [] for p in prods}
    cache = {}
    for asof in timeline:
        h = hist
        if truncate:
            day = asof.astimezone(timezone.utc).strftime("%Y%m%d")
            if day not in cache:
                cache[day] = _truncate(hist, day)
            h = cache[day]
        for p in prods:
            v, _pe = verdict_engine.product_verdict(tree, p, h, {}, asof=asof)
            series[p].append({"asof": asof.isoformat(), "key": v["key"],
                              "grade": v["grade"], "close": v.get("close")})
    return series


def load_hist(tree):
    """장중 스테핑에 쓸 시세(일봉 + 분봉) 한 벌 — 재생·장중 백테스트가 같이 쓴다."""
    from datetime import timedelta
    start = (datetime.now() - timedelta(days=tree_grade.WARMUP_DAYS)).strftime("%Y%m%d")
    return tree_grade.history(tree, start)


def limit_note(tree, hist, tf, timeline, sessions):
    """정직한 한계 표면화 — 분봉 범위(세션·봉 수)와 '왜 이만큼뿐인지'. 짧은 구간 지표는 참고용임을 알린다."""
    if tf == "1d":
        return {"reason": "일봉 전용 트리 — 장중(분봉) 재생 대상 아님(하루 한 점은 일봉 판정과 같다). "
                          "tf:5m/1m 조건이 있어야 장중 타임라인이 깔린다.",
                "sessions": 0, "bars": 0}
    if not timeline:
        syms = sorted(cond.minute_symbols_of(tree))
        return {"reason": "분봉 데이터 없음 — jhts 분봉(md_feed.minutes)에서 %s 분봉이 비어 있다"
                          "(미설치·네트워크·그 심볼 분봉 미보관). 없는 봉을 지어내 타임라인을 늘리지 않는다." % (", ".join(syms) or "대상 심볼"),
                "sessions": 0, "bars": 0}
    return {"reason": "분봉은 jhts 분봉(지수·선물은 최근 ~7거래일 한계)만큼만 온다 — 장중 타임라인도 데이터 있는 %d세션·%d봉(tf=%s)만 "
                      "재생된다. 그 밖 기간은 분봉이 없어 재생할 수 없다(정직한 한계). 짧은 구간의 샤프/MaxDD 는 참고용이다." % (len(sessions), len(timeline), tf),
            "sessions": len(sessions), "bars": len(timeline)}
