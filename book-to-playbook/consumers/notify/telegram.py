#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""텔레그램 알림 송신(구간③) — 판정 결과를 텔레그램으로 보내기만 한다(수집 아님).

네트워크(urllib)가 들어 있어 "팀 폴더엔 네트워크 코드 금지(= 시세 자가수집 재발 방지)" 규칙과 부딪히므로,
verify/verify_code.py ALLOW 에 (trading, notify/telegram.py): {urllib} 로 **이 한 파일만** 예외를 둔다.
여기는 데이터를 **보내기만** 한다 — 시세를 받아오는 코드는 이 파일에 올 수 없다.
"""
import os
import ssl
import sys
import urllib.parse
import urllib.request

_UA = {"User-Agent": "Mozilla/5.0"}
_CTX = ssl.create_default_context()


def send_telegram(msg):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN"); cid = os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and cid):
        return False
    try:
        url = "https://api.telegram.org/bot%s/sendMessage" % tok
        body = urllib.parse.urlencode({"chat_id": cid, "text": msg}).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=body, headers=_UA),
                               timeout=20, context=_CTX)
        return True
    except Exception as e:  # noqa: BLE001
        print("[telegram 실패]", e, file=sys.stderr); return False
