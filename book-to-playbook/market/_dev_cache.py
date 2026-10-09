#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DEV 전용 시세 캐시 — 반복 실행의 네트워크(jhts→야후 등)를 없애 개발을 빠르게.

프로덕션 미사용: 환경변수 ETF_DEV_CACHE(캐시 디렉토리)가 설정됐을 때만 켜진다.
안 켜져 있으면 no-op(그냥 producer 호출) — 실데이터 정합성·신선도에 영향 없음.
데이터 자체는 바꾸지 않는다(jhts가 준 값을 그대로 저장/반환).

흔적0: 이 파일 삭제 + md_feed 의 _dev_cache 호출 제거면 완전히 사라진다.
(불완전/부분 fetch 가 캐시되면 그 심볼 캐시만 지우면 됨 — 디렉토리 삭제로 전체 초기화.)
"""
import os
import pickle
import hashlib

_DIR = os.environ.get("ETF_DEV_CACHE")  # 설정된 디렉토리면 캐시 ON, 없으면 OFF(no-op)


def enabled():
    return bool(_DIR)


def cached(key, producer):
    """key 로 디스크 캐시를 보고, 있으면 그대로, 없으면 producer() 실행 후 저장.
    캐시 OFF면 producer() 를 그냥 호출(no-op)."""
    if not _DIR:
        return producer()
    try:
        os.makedirs(_DIR, exist_ok=True)
        h = hashlib.md5(repr(key).encode("utf-8")).hexdigest()
        path = os.path.join(_DIR, h + ".pkl")
        if os.path.exists(path):
            with open(path, "rb") as f:
                return pickle.load(f)
        v = producer()
        with open(path, "wb") as f:
            pickle.dump(v, f)
        return v
    except Exception:  # noqa: BLE001 — 캐시는 보조물: 실패하면 그냥 직접 호출(무크래시)
        return producer()
