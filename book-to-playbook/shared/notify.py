#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""알림 발신(텔레그램·데스크톱) — 시세와 무관한 송신 전용.

원래 verdict_engine.py(구간③) 안에 있었다. 구간③은 시세를 오직 jhts 시세수집팀
(shared/md_feed.py)으로만 받는다는 경계를 기계로 검사하는데, 알림용 urllib 가
그 안에 섞여 있으면 "네트워크 코드 = 자가 수집" 검사를 세울 수 없다.
그래서 네트워크 송신은 여기로 나왔다 — 여기는 데이터를 **보내기만** 하고,
시세를 받아오는 코드는 이 파일에 올 수 없다.
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
