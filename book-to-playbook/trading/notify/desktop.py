#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""데스크톱 알림 송신(구간③) — 판정 결과를 OS 기본 알림으로 보낸다. 네트워크 없음(subprocess 로 OS 도구 호출)."""
import json
import subprocess
import sys


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
