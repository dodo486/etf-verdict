#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""아티팩트 원본(etf-playbook.html)의 verdict-data JSON 블록을 최신 판정으로 교체해
public/index.html 로 출력. GitHub Pages 자동 갱신용. (디자인/내용은 원본 그대로 승계)"""
import os, re, sys

import json
BASE = os.path.expanduser("~/.claude/skills/book-to-playbook")
src  = os.path.join(BASE, "etf-playbook.html")
js   = os.path.join(BASE, "latest-verdict.json")
intraday_js = os.path.join(BASE, "kis-intraday.json")
outd = os.path.join(BASE, "public", "etf")   # ETF 책은 /etf/ 서브경로
os.makedirs(outd, exist_ok=True)

html = open(src, encoding="utf-8").read()
data = json.loads(open(js, encoding="utf-8").read())

# 장중 자동판정 병합 + 수집상태 판정(ok / pending(대기) / error(실패))
# data.intraday_state = 전체 상태, 각 verdict.intraday_auto엔 종목/체크별 status 포함
intraday_state = "pending"  # 기본: 아직 안 걷힘
if os.path.exists(intraday_js):
    try:
        from datetime import datetime, timezone
        iv = json.loads(open(intraday_js, encoding="utf-8").read())
        ts = iv.get("ts")
        age_h = 999
        if ts:
            age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(ts).astimezone(timezone.utc)).total_seconds()/3600
        st = iv.get("status")
        if st == "error":
            # 수집 시도했으나 실패 → error (오래돼도 실패는 실패로 노출, 단 3일 넘으면 pending)
            intraday_state = "error" if age_h <= 72 else "pending"
            data["intraday_error"] = iv.get("reason")
            data["intraday_ts"] = ts
        elif st == "ok" and age_h <= 12:
            intraday_state = "ok"
            data["intraday_ts"] = ts
            for v in data.get("verdicts", []):
                v["intraday_auto"] = iv.get("intraday", {}).get(v["prod"])
        else:
            intraday_state = "pending"  # 성공했지만 오래됨 = 다음 갱신 대기
            if ts: data["intraday_ts"] = ts
    except Exception as e:
        intraday_state = "error"
        data["intraday_error"] = f"병합 오류: {e}"
        print("장중 데이터 병합 실패:", e, file=sys.stderr)
data["intraday_state"] = intraday_state

data_str = json.dumps(data, ensure_ascii=False)
pat = re.compile(r'(<script type="application/json" id="verdict-data">)(.*?)(</script>)', re.S)
if not pat.search(html):
    print("verdict-data 블록을 찾지 못함", file=sys.stderr); sys.exit(1)
html = pat.sub(lambda m: m.group(1) + "\n" + data_str + "\n" + m.group(3), html)

# 책 전환 사이드 레일 주입
try:
    from inject_nav import inject
    html = inject(html, "etf")
except Exception as e:
    print("레일 주입 실패(무시):", e, file=sys.stderr)

open(os.path.join(outd, "index.html"), "w", encoding="utf-8").write(html)
open(os.path.join(BASE, "public", ".nojekyll"), "a").close()
print("public/etf/index.html 갱신 완료")
