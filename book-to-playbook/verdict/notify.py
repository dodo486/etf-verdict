#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""알림 발신(텔레그램·데스크톱) — 시세와 무관한 송신 전용(구간③ 소유).

판정 결과로 알림을 쏘는 곳이 구간③(verdict) 하나뿐이라 이 팀 안에 둔다. 다만 알림용
urllib 가 들어 있어 "팀 폴더엔 네트워크 코드 금지(= 시세 자가수집 재발 방지)" 규칙과
부딪히므로, verify_teams.py ALLOW 에 (verdict, notify.py): {urllib} 로 **이 한 파일만**
예외를 둔다. 여기는 데이터를 **보내기만** 한다 — 시세를 받아오는 코드는 이 파일에 올 수 없다.
"""
import json
import os
import ssl
import subprocess
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


def send_desktop(msg, title="진입 환경"):
    """데스크톱 알림 — macOS/Windows/Linux 각각의 기본 수단. 실패해도 조용히 넘어간다."""
    first = msg.split("\n")[1] if "\n" in msg else msg
    try:
        if sys.platform == "darwin":
            subprocess.run(["osascript", "-e",
                            "display notification %s with title %s"
                            % (json.dumps(first), json.dumps(title))], check=False)
        elif sys.platform == "win32":
            ps = ("[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');"
                  "$n=New-Object System.Windows.Forms.NotifyIcon;"
                  "$n.Icon=[System.Drawing.SystemIcons]::Information;$n.Visible=$true;"
                  "$n.ShowBalloonTip(10000,%s,%s,'Info');Start-Sleep -Seconds 6;$n.Dispose()"
                  % (json.dumps(title), json.dumps(first)))
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           check=False, capture_output=True)
        else:
            subprocess.run(["notify-send", title, first], check=False)
        return True
    except Exception:  # noqa: BLE001
        return False
