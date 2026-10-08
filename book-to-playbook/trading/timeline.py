#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Timeline — "시간을 밟으며 매 asof 판정하는" 단일 코어 (구간③, 책 무관).

## 왜 하나인가

"시간을 밟으며 asof 판정"하는 루프가 백테스트(일봉 하루씩)와 장중 재생(분봉 asof)에 따로 있던 것을 여기 하나로
모았다. 판정은 늘 Judge(trading/judge.py) 하나가 내고 — 라이브 판정도 같은 Judge 의 latest() — 이 코어는 시점을
까는 '축'만 고른다. 뒤에 붙는 것만 용도별로 다르다(백테스트=계산기 / 재생=신호출력).

## finest_tf 로 간격을 정한다

트리가 쓰는 가장 촘촘한 tf(finest_tf)가 **신호 생성 입구 `run()`** 의 내부 경로를 정한다(로직이 아니라
'속도·축'만 다르다 — 같은 Judge, 같은 답):

  · finest=1d  — 하루 한 점(일봉 축). 상품마다 Judge 를 한 번 만들어 전체 달력의 grade(i)/incomplete(i) 를 뽑는다
    (벡터 1회계산 — 하루마다 Judge 를 새로 세우지 않는다; 수백배 느려지니 금지). 분봉 축(asofs)은 쓰지 않는다.
  · finest=5m/1m — 분봉 축. asofs(분봉 데이터 있는 범위, 세션 안)로 각 asof 를 깔고, 그 시점마다 Judge(asof)
    의 latest() 로 장중 신호·등급 시계열을 낸다(step). 일봉 잎은 그 asof 이하 마지막 확정 일봉(어제값),
    분봉 잎은 그 asof 이하 마지막 분봉 — 둘 다 cond 가 asof 로 자른다.

## 정직한 한계 (가짜로 안 늘린다)

분봉은 jhts 분봉(md_feed.minutes → jhts.minute_bars, OHLCV+UTC)에서 온다. 지수·선물·Alpaca 미연결은
최근 ~7거래일만 온다. 장중 타임라인도 데이터 있는 세션·봉만 깔린다. 비거나 짧으면 "N세션·M봉만,
그 밖 데이터 없음"을 그대로 표면화한다(limit_note). 짧은 구간의 샤프/MaxDD 는 참고용으로만 본다.
"""
from datetime import datetime, timedelta, timezone

from checklist.grade import GRADES, WARMUP_DAYS, History, history
from trading.judge import Judge

# tf 촘촘함 순서 — 초로 환산(작을수록 촘촘). cond.TIMEFRAMES 와 짝(그 밖 tf 는 문법이 막는다).
TF_SECONDS = {"1m": 60, "5m": 300, "1d": 86400}


def finest_tf(tree):
    """트리(TreeGateway)의 '가장 촘촘한 tf'(1m < 5m < 1d). px 잎이 없으면(순수 수동 트리) 기본 "1d"."""
    tfs = tree.timeframes()
    if not tfs:
        return "1d"
    return min(tfs, key=lambda tf: TF_SECONDS.get(tf, TF_SECONDS["1d"]))


def load_hist(tree):
    """장중 스테핑에 쓸 시세(일봉 + 분봉) 한 벌 — 재생·장중 백테스트가 같이 쓴다."""
    return history(tree, (datetime.now() - timedelta(days=WARMUP_DAYS)).strftime("%Y%m%d"))


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


class Timeline:
    """트리 하나 + 시세 한 벌 위의 시간 축. run() 이 신호 생성 단일 입구다."""

    def __init__(self, tree, hist):
        self.tree, self.hist = tree, hist

    def asofs(self, limit=None):
        """트리의 가장 촘촘한 tf 봉 타임스탬프로 asof 타임라인(UTC datetime 오름차순)을 만든다.

        · finest=1d : 일봉 트리는 '분봉 재생' 대상이 아니다 → 빈 타임라인(이 함수는 장중 전용 경로).
          (일봉 신호는 run() 의 벡터 1회계산 경로가 낸다.)
        · finest=5m/1m : 그 심볼들의 분봉 키(데이터 있는 범위)를 asof 로 깐다. 5m 는 1분봉을 5분 버킷으로 접은
          '각 5분 봉의 종료(=다음 버킷 직전 마지막 분봉)' 시각을, 1m 는 분봉 키 그대로를 asof 로 쓴다.
        limit 을 주면 뒤(가장 최근)에서 limit 개만 — 긴 분봉도 꼬리만 빠르게 재생."""
        tf = finest_tf(self.tree)
        if tf == "1d":
            return []                               # 일봉 전용 트리 — 장중 재생할 분봉 축이 없다(빈 타임라인)
        keys = _minute_keys(self.hist, self.tree.minute_symbols())
        if not keys:
            return []                               # 분봉 데이터 없음 — 타임라인도 없음(가짜로 안 늘림)
        if tf == "5m":
            # 5분봉 축 — 1분봉을 5분 버킷으로 접은 뒤, 각 버킷 안의 '마지막 분봉' 시각을 asof 로. 그 asof 에서 minute_series
            # 가 그 버킷을 asof 이하 마지막 5분봉으로 집계한다(합집합 키로 세션 경계 안에서 접으므로 각 asof 에서
            # 심볼별로 자기 마지막 버킷을 본다).
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

    @staticmethod
    def truncate(full, upto):
        """full(History) 을 날짜 upto(YYYYMMDD) 이하로 자른 새 History. 분봉(minutes)은 그대로 넘긴다.
        과거 세션을 재생할 때 '그 세션 마감 직후 라이브가 보유했을' 일봉(그날까지의 확정 일봉)을 재현한다 —
        신호 파리티(verify_trading --parity)가 쓰는 바로 그 규약."""
        t = History({s: [c for c in (cs or []) if c.date <= upto] for s, cs in full.items()})
        t.minutes = getattr(full, "minutes", {})
        return t

    def step(self, timeline, prods, truncate=False):
        """각 asof 에서 Judge(tree, p, hist, asof).latest() — 라이브가 보는 그대로 — 로 (asof, key, grade, close) 를 모은다.
        평가 규칙을 새로 만들지 않고, asof 를 분봉 간격으로 깔아 '같은 판정기'를 여러 시점에 돌릴 뿐이다.

        truncate=False(재생 기본) = full hist 에 asof 만 바꿔 '지금 상품 상태'를 여러 분봉 스냅샷으로 본다
        (latest 는 늘 달력 마지막 봉(오늘)을 판정하므로 과거 세션 asof 에선 오늘 일봉 regime 을 과거 분봉과 묶는다).
        truncate=True(장중 백테스트) = 각 asof 마다 일봉 hist 를 그 asof 세션일 이하로 잘라 그 세션 자신의 일봉 regime 을
        그날 분봉 스냅샷과 묶는다(look-ahead 0 — 일봉 잎은 그 세션 마감 전엔 미확정, 마감 후 확정).

        → {prod: [{asof(UTC iso), key, grade, close}, ...]}  (timeline 순서대로)."""
        series = {p: [] for p in prods}
        cache = {}
        for asof in timeline:
            h = self.hist
            if truncate:
                day = asof.astimezone(timezone.utc).strftime("%Y%m%d")
                if day not in cache:
                    cache[day] = self.truncate(self.hist, day)
                h = cache[day]
            for p in prods:
                key, close = Judge(self.tree, p, h, asof=asof).latest()
                series[p].append({"asof": asof.isoformat(), "key": key, "grade": GRADES[key], "close": close})
        return series

    def run(self, start=None, unobserved=None, limit=None, truncate=False, prods=None, axis=None):
        """책 무관 **단일 신호 생성 입구** — finest_tf 로 내부 경로를 고른다(로직이 아니라 '속도·축'만 다르다).

        axis 로 축을 강제할 수 있다(None 이면 finest_tf 자동). **일봉 백테스트는 의미상 늘 일봉축**이므로
        backtest.run 은 axis="1d" 로 부른다 — 트리에 분봉(관측) 잎이 섞여 finest_tf 가 "1m"이어도, 일봉 판정은
        Judge 가 그 관측 잎을 일봉 asof 에서 manual/None 으로 바르게 처리한다(분봉 per-asof 로 빠지면 안 된다).

        · 1d   : 상품마다 Judge 를 한 번 만들고 전체 달력의 grade(i)/incomplete(i) 를 뽑는다. start(YYYYMMDD)을
          주면 그 이상 날만.
        · 5m/1m: asofs(분봉 범위)를 깔고 step 으로 각 asof 에서 판정한다. truncate 는 step 참고, limit 은 꼬리 개수.

        prods 를 주면 그 상품만(없으면 트리의 전 상품). 반환:
          {tf, prods, series:{prod:[점]},
           judges:{prod:Judge}|None,                      # 1d 만 — 워밍업·수동조건 조회용(분봉은 None)
           timeline:[UTC datetime], sessions:[YYYYMMDD]}   # 분봉 축(1d 는 빈 리스트)
        점(1d)   = {date, key, grade, close, incomplete}
        점(분봉) = {asof(UTC iso), key, grade, close}   (step 결과 그대로)."""
        tree, hist = self.tree, self.hist
        tf = axis or finest_tf(tree)
        prods = prods if prods is not None else tree.products()
        if tf == "1d":
            series, judges = {}, {}
            for p in prods:
                cs = hist.get(p) or []
                cal = [c.date for c in cs]
                j = Judge(tree, p, hist, cal, unobserved=unobserved)
                pts = []
                for i, d in enumerate(cal):
                    if start is not None and d < start:
                        continue
                    inc = j.incomplete(i)          # 워밍업 부족 — grade 가 ❔(불완전)로 내보낸다
                    k = j.grade(i)
                    pts.append({"date": d, "key": k, "grade": GRADES[k], "close": cs[i].close, "incomplete": inc})
                series[p], judges[p] = pts, j
            return {"tf": tf, "prods": prods, "series": series, "judges": judges,
                    "timeline": [], "sessions": []}       # 일봉 트리 — 분봉 축 없음(asofs 와 같은 빈 리스트)
        timeline = self.asofs(limit=limit)
        series = self.step(timeline, prods, truncate=truncate)
        sessions = sorted({a.strftime("%Y%m%d") for a in timeline})
        return {"tf": tf, "prods": prods, "series": series, "judges": None,
                "timeline": timeline, "sessions": sessions}

    def limit_note(self, tf, timeline, sessions):
        """정직한 한계 표면화 — 분봉 범위(세션·봉 수)와 '왜 이만큼뿐인지'. 짧은 구간 지표는 참고용임을 알린다."""
        if tf == "1d":
            return {"reason": "일봉 전용 트리 — 장중(분봉) 재생 대상 아님(하루 한 점은 일봉 판정과 같다). "
                              "tf:5m/1m 조건이 있어야 장중 타임라인이 깔린다.",
                    "sessions": 0, "bars": 0}
        if not timeline:
            syms = sorted(self.tree.minute_symbols())
            return {"reason": "분봉 데이터 없음 — jhts 분봉(md_feed.minutes)에서 %s 분봉이 비어 있다"
                              "(미설치·네트워크·그 심볼 분봉 미보관). 없는 봉을 지어내 타임라인을 늘리지 않는다." % (", ".join(syms) or "대상 심볼"),
                    "sessions": 0, "bars": 0}
        return {"reason": "분봉은 jhts 분봉(지수·선물은 최근 ~7거래일 한계)만큼만 온다 — 장중 타임라인도 데이터 있는 %d세션·%d봉(tf=%s)만 "
                          "재생된다. 그 밖 기간은 분봉이 없어 재생할 수 없다(정직한 한계). 짧은 구간의 샤프/MaxDD 는 참고용이다." % (len(sessions), len(timeline), tf),
                "sessions": len(sessions), "bars": len(timeline)}
