#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""장중 주기 재판정(구간③) — asof=지금 기준으로 N분마다 판정을 다시 낸다(백테스트 제외).

한 회차가 무엇을 하는지는 호출자가 cycle 로 준다(orchestration.run watch → 러너의 verdict 모드: 판정·알림·검사).
이 파일은 '언제 다시 판정하나'(간격·횟수)만 가진다.
"""
import time
from datetime import datetime


def watch(argv, cycle):
    """asof=지금 기준으로 주기적으로 재판정한다. 장중(tf="1m") 조건은 asof(관측 시점) 이하 마지막 분봉을 본다 —
    분봉이 연결되면 그대로 자동으로 살아나고, 그 전엔 None→manual(🟡)로 떨어진다.

    옛 watch 는 저자가 말한 '아침 고정 시각'까지 기다리는 용도였다 — asof 모델에선 그 고정 시점 개념이 없어
    '지금 기준 주기 평가'로 바뀌었다. --every N 으로 간격(분, 기본 5)을, --cycles K 로 횟수(기본 무한)를 준다.
    cycle(rest) = 한 회차 실행(종료코드 반환)."""
    rest = [a for a in argv if a != "watch" and a not in ("--every", "--cycles")]
    every = int(argv[argv.index("--every") + 1]) if "--every" in argv else 5
    cycles = int(argv[argv.index("--cycles") + 1]) if "--cycles" in argv else None
    code, n = 0, 0
    while cycles is None or n < cycles:
        n += 1
        print("watch: asof=지금 %d회차 판정 — %s" % (n, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        code = cycle(rest) or code
        if cycles is not None and n >= cycles:
            break
        time.sleep(max(1, every) * 60)
    return code
