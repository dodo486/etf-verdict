#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""알림(진입점) — 오늘 판정을 한 번 내서 문장으로 만들고 텔레그램(안 되면 데스크톱 알림)으로 보낸다. 수집 아님.

  python -m entry.notify <slug> [--json] [--no-send]   books.json engine.daily 가 이 모듈(러너 daily · 서버가 부른다)

판정 모양은 화면층(web/verdict_view.render·build_text)이 빚고, 여기는 보내기만 한다.
네트워크(urllib)는 "시세 자가수집 금지" 규칙과 부딪히므로 entry/verify_rules.py ALLOW 에 이 한 파일만 예외로 둔다.
여기는 데이터를 **보내기만** 한다 — 시세를 받아오는 코드는 이 파일에 올 수 없다.
"""
import json
import os
import ssl
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime

from shared.paths import book_log, write_text
from web.verdict_view import build_text, render

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


def _cli():
    argv = sys.argv[1:]
    slug = next((a for a in argv if not a.startswith("-")), None)
    if not slug:
        print("사용법: python -m entry.notify <slug> [--json] [--no-send]", file=sys.stderr)
        sys.exit(2)
    top = render(slug)
    text = build_text(top)
    if "--json" in argv:
        print(json.dumps(top, ensure_ascii=False, indent=1))
    else:
        print(text)
    if "--no-send" not in argv:
        if not send_telegram(text):
            send_desktop(text)
    try:
        now = datetime.fromisoformat(top["ts"])
        write_text(book_log(slug, "verdict-%s.txt" % now.strftime("%Y%m%d")), text)
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    _cli()
