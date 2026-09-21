#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF 데일리 진입 환경 자동판정
- 김프로랩 『미국 돈복사 ETF 투자방법』 STEP1 정량규칙을 코드로 옮김
- 무인증 공개 소스(Yahoo Finance chart API)만 사용, 외부 의존성 없음(urllib)
- 최신 EOD 기준으로 다음 세션 진입 '환경'을 판정 (필터/스코어카드/회피).
  장중 패턴 3종(시초가 지지·첫 눌림 저점·30분 판별)은 자동 불가 → '장중 확인'으로 표시.

출력: 콘솔 표 + JSON(--json) + 텔레그램/ macOS 알림 푸시(가능 시)
크레덴셜(택1):
  export TELEGRAM_BOT_TOKEN=... ; export TELEGRAM_CHAT_ID=...
없으면 macOS 알림(osascript)으로 대체.
"""
import json, os, sys, ssl, urllib.request, urllib.parse
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0"}
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE  # 일부 macOS 환경 인증서 이슈 회피

def fetch(symbol, rng="3mo", interval="1d"):
    q = urllib.parse.quote(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?range={rng}&interval={interval}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
        data = json.load(r)
    res = data["chart"]["result"][0]
    q0 = res["indicators"]["quote"][0]
    closes = [c for c in q0.get("close", []) if c is not None]
    highs  = [h for h in q0.get("high",  []) if h is not None]
    vols   = [v for v in q0.get("volume",[]) if v is not None]
    meta = res.get("meta", {})
    return {"close": closes, "high": highs, "vol": vols, "meta": meta}

def ma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None

def pct(a, b):
    return (a - b) / b * 100 if (a is not None and b) else None

def up_days(closes, n=10):
    c = closes[-(n+1):]
    return sum(1 for i in range(1, len(c)) if c[i] > c[i-1])

def load(symbol):
    try:
        d = fetch(symbol)
        c = d["close"]
        if len(c) < 21:
            return None
        return {
            "sym": symbol, "close": c[-1], "prev": c[-2],
            "ma5": ma(c, 5), "ma20": ma(c, 20), "ma60": ma(c, 60),
            "chg": pct(c[-1], c[-2]),
            "ret5": pct(c[-1], c[-6]) if len(c) >= 6 else None,
            "high": d["high"][-1] if d["high"] else None,
            "vol": d["vol"][-1] if d["vol"] else None,
            "vol20": ma(d["vol"], 20) if len(d["vol"]) >= 20 else None,
            "updays10": up_days(c, 10),
            "closes": c,
        }
    except Exception as e:
        return {"sym": symbol, "error": str(e)}

def ok(v):  # 유효 데이터?
    return v and "error" not in v

# ---------- 데이터 수집 ----------
SYMS = ["^NDX","^GSPC","^SOX","TQQQ","SOXL","UPRO","^VIX","^TNX",
        "NVDA","MSFT","AAPL","AMD","AVGO"]
D = {s: load(s) for s in SYMS}

def above20(v): return ok(v) and v["ma20"] and v["close"] > v["ma20"]
def above60(v): return ok(v) and v["ma60"] and v["close"] > v["ma60"]
def plus(sym): return ok(D[sym]) and D[sym]["chg"] is not None and D[sym]["chg"] > 0

# ---------- 스코어카드 (5점) ----------
sc = []
sc.append(("나스닥100 방향", plus("^NDX")))
sc.append(("S&P500 방향", plus("^GSPC")))
vix = D["^VIX"]
sc.append(("VIX 안정(전일 +10% 미만)", ok(vix) and vix["chg"] is not None and vix["chg"] < 10))
tnx = D["^TNX"]
tnx_jump = ok(tnx) and tnx["chg"] is not None and (tnx["close"] - tnx["prev"]) >= 0.10
sc.append(("10년물 안정(+0.1%p 미만)", ok(tnx) and not tnx_jump))
# 달러인덱스: DX-Y.NYB, 실패 시 DX=F
dxy = D.get("DXY")
if dxy is None:
    dxy = load("DX-Y.NYB")
    if not ok(dxy): dxy = load("DX=F")
    D["DXY"] = dxy
sc.append(("달러인덱스 안정(급강세 아님)", ok(dxy) and dxy["chg"] is not None and dxy["chg"] < 0.5))
score = sum(1 for _, b in sc if b)

# ---------- 회피 신호 ----------
def avoid_common():
    a = []
    if ok(vix) and vix["chg"] is not None and vix["chg"] >= 10:
        a.append(f"VIX 전일 대비 +{vix['chg']:.1f}% (추격 금지)")
    if tnx_jump:
        a.append(f"10년물 +{(tnx['close']-tnx['prev']):.2f}%p 급등 (기술주 예민)")
    return a

def wick(v):  # 윗꼬리 근사: 고가 대비 종가 하락 폭
    if ok(v) and v["high"] and v["close"]:
        return (v["high"] - v["close"]) / v["high"] * 100
    return None

prod_cfg = {
    "TQQQ": {"idx":"^NDX", "color":"🔵"},
    "SOXL": {"idx":"^SOX", "color":"🟠"},
    "UPRO": {"idx":"^GSPC","color":"🟢"},
}

def verdict(prod):
    p = D[prod]; cfg = prod_cfg[prod]; idx = D[cfg["idx"]]
    if not ok(p) or not ok(idx):
        return {"prod":prod,"grade":"데이터오류","reason":"시세 조회 실패","avoid":[],"intraday":[]}
    av = []; akeys = []
    if ok(vix) and vix["chg"] is not None and vix["chg"] >= 10:
        av.append(f"VIX 전일 대비 +{vix['chg']:.1f}% (추격 금지)"); akeys.append("vix")
    if tnx_jump:
        av.append(f"10년물 +{(tnx['close']-tnx['prev']):.2f}%p 급등 (기술주 예민)"); akeys.append("tnx")
    # 필터
    if prod == "TQQQ":
        filt = above20(idx)
        filt_txt = "나스닥100 20일선 위"
    elif prod == "SOXL":
        filt = above20(p) and above20(idx)
        filt_txt = "SOXL·반도체지수 모두 20일선 위(스윙)"
    else:  # UPRO
        filt = above20(idx)
        filt_txt = "S&P500 20일선 위"
    # 상품별 회피
    if prod == "SOXL":
        if ok(idx) and idx["updays10"] >= 7 and p["ret5"] is not None and p["ret5"] >= 20:
            av.append(f"과열: 반도체 10일중 {idx['updays10']}일↑ + SOXL 5일 {p['ret5']:.0f}%↑"); akeys.append("overheat")
        elif p["ret5"] is not None and p["ret5"] >= 15:
            av.append(f"SOXL 최근 5일 {p['ret5']:.0f}% 급등"); akeys.append("run5")
        w = wick(p)
        if w is not None and w >= 4:
            av.append(f"장중 고점 대비 {w:.1f}% 밀려 마감(윗꼬리)"); akeys.append("wick")
        if plus("NVDA") and not (plus("AMD") or plus("AVGO")):
            av.append("엔비디아만 강하고 AMD·브로드컴 약함"); akeys.append("nvda_only")
    if prod == "TQQQ":
        if p["ret5"] is not None and p["ret5"] >= 25:
            av.append(f"TQQQ 최근 5일 {p['ret5']:.0f}% 급등(추격 위험)"); akeys.append("run5")
        w = wick(p)
        if w is not None and w >= 4:
            av.append(f"전고점권 윗꼬리(고점 대비 -{w:.1f}%)"); akeys.append("wick")
    # 등급
    if not filt:
        grade, reason = "🚫 진입 금지", f"필터 미충족 — {filt_txt} 아님(추세 없음)"
    elif av:
        grade, reason = "⛔ 보류", f"회피 신호 {len(av)}개 — 과열/위험, 눌림 대기"
    elif score >= 4:
        grade, reason = "✅ 매수 후보", f"필터 통과 · 스코어 {score}/5 → 1차 분할 진입 준비"
    elif score == 3:
        grade, reason = "🟡 소액만", f"스코어 {score}/5 — 확인 매수 수준"
    else:
        grade, reason = "⚪ 관망", f"스코어 {score}/5 — 신규 진입 보류"
    # 장중 확인항목(자동 불가)
    intraday = []
    if filt and not av and score >= 3:
        if prod == "TQQQ":
            intraday = ["나스닥 시초가 위 유지","첫 눌림 저점 높임","빅테크 3개 중 2개↑"]
        elif prod == "SOXL":
            intraday = ["엔비디아 시초가 위","AMD 전일 저점 지킴","브로드컴 안 밀림"]
        else:
            intraday = ["S&P500 20일선 종가 유지","섹터 3개↑ 동반"]
    # 거래량 신호(EOD): 전일 대비 1.5배 이상 + 종가가 당일 고점 근처(고점 대비 -1.5% 이내)
    vol_ok = False
    if ok(p) and p.get("vol") and p.get("vol20") and p["vol20"]:
        near_high = (p.get("high") and p["high"] and (p["high"]-p["close"])/p["high"] <= 0.015)
        vol_ok = (p["vol"] >= 1.5*p["vol20"]) and bool(near_high)

    # ---- 항목별 검증용 수치(metrics): 아티팩트가 작은글씨로 표시 ----
    def gap(c, m):  # 이격 %
        return (c-m)/m*100 if (c is not None and m) else None
    def mil(v):
        return f"{v/1e6:.1f}M" if v else "–"
    metrics = {}
    # 필터
    if prod == "SOXL":
        gp=gap(p["close"],p["ma20"]); gi=gap(idx["close"],idx["ma20"])
        metrics["filter"]=f"SOXL {p['close']:.2f}/20일선 {p['ma20']:.2f} ({gp:+.1f}%), ^SOX {gi:+.1f}%"
    else:
        gi=gap(idx["close"],idx["ma20"])
        iname={"TQQQ":"나스닥100","UPRO":"S&P500"}[prod]
        metrics["filter"]=f"{iname} {idx['close']:.1f}/20일선 {idx['ma20']:.1f} ({gi:+.1f}%)"
    # 거래량
    if ok(p) and p.get("vol") and p.get("vol20"):
        ratio=p["vol"]/p["vol20"] if p["vol20"] else None
        nh=(p["high"]-p["close"])/p["high"]*100 if p.get("high") else None
        metrics["vol"]=f"거래량 {mil(p['vol'])}/20일평균 {mil(p['vol20'])} ({ratio:.2f}배), 고점比 {-nh:+.1f}%" if ratio is not None else "거래량 데이터 없음"
    # 회피 지표(모두, 걸리든 안 걸리든 현재값 표시)
    if ok(vix) and vix["chg"] is not None:
        metrics["vix"]=f"^VIX {vix['close']:.1f} (전일比 {vix['chg']:+.1f}%)"
    if ok(tnx) and tnx.get("close") is not None and tnx.get("prev") is not None:
        metrics["tnx"]=f"^TNX {tnx['close']:.2f} (전일 {tnx['prev']:.2f}, {tnx['close']-tnx['prev']:+.2f}%p)"
    if p.get("ret5") is not None:
        metrics["run5"]=f"최근 5일 {p['ret5']:+.1f}%"
    w=wick(p)
    if w is not None:
        metrics["wick"]=f"고점 대비 종가 {-w:+.1f}%"
    if prod=="SOXL" and ok(idx):
        metrics["overheat"]=f"^SOX 10일중 {idx['updays10']}일↑ · SOXL 5일 {p['ret5']:+.0f}%" if p.get("ret5") is not None else f"^SOX 10일중 {idx['updays10']}일↑"
        nv=D['NVDA']['chg'] if ok(D.get('NVDA')) else None
        am=D['AMD']['chg'] if ok(D.get('AMD')) else None
        bc=D['AVGO']['chg'] if ok(D.get('AVGO')) else None
        if nv is not None:
            metrics["nvda_only"]=f"엔비디아 {nv:+.1f}%, AMD {am:+.1f}%, 브로드컴 {bc:+.1f}%" if (am is not None and bc is not None) else f"엔비디아 {nv:+.1f}%"
    return {"prod":prod,"color":cfg["color"],"grade":grade,"reason":reason,
            "avoid":av,"avoid_keys":akeys,"filter_ok":bool(filt),"vol_ok":bool(vol_ok),"intraday":intraday,
            "metrics":metrics,
            "close":p["close"],"ma20":p["ma20"],"chg":p["chg"]}

verdicts = [verdict(pp) for pp in ("TQQQ","SOXL","UPRO")]

# ---------- 출력 텍스트 ----------
now = datetime.now(timezone.utc).astimezone()
lead = {"NVDA":"엔비디아","MSFT":"MS","AAPL":"애플","AMD":"AMD","AVGO":"브로드컴"}
lead_txt = " ".join(f"{k}{'+' if plus(s) else '−'}" for s,k in lead.items() if ok(D[s]))

def build_text():
    L = []
    L.append(f"📈 ETF 데일리 진입 환경  ({now:%Y-%m-%d %H:%M} KST)")
    L.append(f"장 시작 전 스코어카드: {score}/5  " + ("공격가능" if score>=4 else "소액" if score==3 else "관망"))
    for lab, b in sc:
        L.append(f"   {'🟢' if b else '🔴'} {lab}")
    L.append(f"주도주: {lead_txt}")
    L.append("─"*30)
    for v in verdicts:
        if v["grade"]=="데이터오류":
            L.append(f"{v['prod']}: 데이터오류"); continue
        L.append(f"{v['color']} {v['prod']}  {v['grade']}")
        L.append(f"   {v['reason']}")
        if v.get("close") and v.get("ma20"):
            side = "위" if v["close"]>v["ma20"] else "아래"
            L.append(f"   종가 {v['close']:.2f} / 20일선 {v['ma20']:.2f} ({side}), 당일 {v['chg']:+.1f}%")
        for a in v["avoid"]:
            L.append(f"   ⚠ {a}")
        if v["intraday"]:
            L.append(f"   👁 장중 확인(31분째): " + " · ".join(v["intraday"]))
    L.append("─"*30)
    L.append("※ 환경 판정(EOD 기준). 장중 3항목은 직접 확인 후 최종 진입. 규칙 출처=저자 명시.")
    return "\n".join(L)

text = build_text()

# ---------- 전송 ----------
def send_telegram(msg):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN"); cid = os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and cid): return False
    try:
        url = f"https://api.telegram.org/bot{tok}/sendMessage"
        body = urllib.parse.urlencode({"chat_id":cid,"text":msg}).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=body, headers=UA), timeout=20, context=CTX)
        return True
    except Exception as e:
        print("[telegram 실패]", e, file=sys.stderr); return False

def send_macos(msg):
    try:
        import subprocess
        title = "ETF 진입 환경"
        first = msg.split("\n")[1] if "\n" in msg else msg
        subprocess.run(["osascript","-e",
            f'display notification {json.dumps(first)} with title {json.dumps(title)}'],
            check=False)
        return True
    except Exception:
        return False

def build_html():
    grade_cls = {"✅ 매수 후보":"go","🟡 소액만":"small","⛔ 보류":"no","🚫 진입 금지":"no","⚪ 관망":"","데이터오류":""}
    sc_rows = "".join(
        f'<div class="scitem"><span class="dot {"on" if b else "off"}"></span>{l}</div>' for l,b in sc)
    cards = ""
    for v in verdicts:
        if v["grade"]=="데이터오류":
            cards += f'<div class="card"><h3>{v["prod"]}</h3><p class="muted">데이터 오류</p></div>'; continue
        cls = grade_cls.get(v["grade"],"")
        av = "".join(f'<li class="warn">⚠ {a}</li>' for a in v["avoid"])
        idd = ""
        if v["intraday"]:
            idd = '<div class="intraday"><b>👁 장중 확인(31분째)</b><ul>' + \
                  "".join(f"<li>{x}</li>" for x in v["intraday"]) + "</ul></div>"
        side = "위" if (v.get("close") and v.get("ma20") and v["close"]>v["ma20"]) else "아래"
        px = ""
        if v.get("close") and v.get("ma20"):
            px = f'<div class="px">종가 <b>{v["close"]:.2f}</b> / 20일선 {v["ma20"]:.2f} <span class="{ "up" if side=="위" else "dn"}">({side})</span> · 당일 {v["chg"]:+.1f}%</div>'
        cards += f'''<div class="card pc-{v["prod"].lower()} {cls}">
          <div class="chd"><h3>{v["color"]} {v["prod"]}</h3><span class="grade {cls}">{v["grade"]}</span></div>
          <p class="reason">{v["reason"]}</p>{px}
          <ul class="flags">{av}</ul>{idd}</div>'''
    sc_verdict = "공격 가능" if score>=4 else ("소액만" if score==3 else "관망")
    lead_html = " ".join(
        f'<span class="{ "up" if plus(s) else "dn"}">{k}{"▲" if plus(s) else "▼"}</span>'
        for s,k in lead.items() if ok(D[s]))
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ETF 진입 환경 · {now:%m/%d}</title>
<style>
:root{{--ground:#12141a;--surface:#1a1e28;--s2:#20242f;--line:#2b303c;--text:#c7ccd6;--head:#eef1f6;--mute:#7a8194;--gold:#d4a24e;--tqqq:#4c8dff;--soxl:#f0883e;--upro:#3fb950;--go:#3fb950;--no:#e5484d}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--ground);color:var(--text);font-family:-apple-system,"Apple SD Gothic Neo","Pretendard",sans-serif;line-height:1.65;-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}}
.wrap{{max-width:760px;margin:0 auto;padding:28px 18px 80px}}
h1{{font-size:22px;color:var(--head);margin:0 0 2px;font-weight:800;letter-spacing:-.01em}}
.ts{{color:var(--mute);font-size:13px;margin-bottom:20px}}
.scorebox{{background:linear-gradient(180deg,var(--surface),var(--s2));border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin-bottom:16px}}
.scorebox .top{{display:flex;align-items:baseline;gap:12px;margin-bottom:12px}}
.scorebox .num{{font-size:34px;font-weight:800;color:var(--gold)}}
.scorebox .lab{{font-size:15px;font-weight:700;color:var(--head)}}
.scitem{{display:flex;align-items:center;gap:9px;padding:5px 0;font-size:13.5px}}
.dot{{width:9px;height:9px;border-radius:50%;flex:none}}
.dot.on{{background:var(--go)}}.dot.off{{background:var(--no)}}
.lead{{margin-top:10px;padding-top:10px;border-top:1px solid var(--line);font-size:13px;color:var(--mute);display:flex;gap:12px;flex-wrap:wrap}}
.up{{color:var(--go)}}.dn{{color:var(--no)}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:12px 0;border-left:4px solid var(--line)}}
.card.go{{border-left-color:var(--go)}}.card.no{{border-left-color:var(--no)}}.card.small{{border-left-color:var(--gold)}}
.chd{{display:flex;justify-content:space-between;align-items:center}}
.card h3{{margin:0;font-size:19px;font-weight:800;color:var(--head)}}
.pc-tqqq h3{{color:var(--tqqq)}}.pc-soxl h3{{color:var(--soxl)}}.pc-upro h3{{color:var(--upro)}}
.grade{{font-size:14px;font-weight:800;padding:4px 10px;border-radius:20px;background:var(--s2);color:var(--mute)}}
.grade.go{{background:rgba(63,185,80,.14);color:var(--go)}}.grade.no{{background:rgba(229,72,77,.14);color:var(--no)}}.grade.small{{background:rgba(212,162,78,.14);color:var(--gold)}}
.reason{{margin:8px 0 4px;font-size:14px;color:var(--text)}}
.px{{font-size:13px;color:var(--mute)}}.px b{{color:var(--head)}}
.flags{{list-style:none;padding:0;margin:8px 0 0}}.flags .warn{{color:#f0a3a5;font-size:13px;padding:2px 0}}
.intraday{{margin-top:10px;padding:10px 12px;background:var(--s2);border-radius:9px;font-size:13px}}
.intraday b{{color:var(--gold)}}.intraday ul{{margin:6px 0 0;padding-left:18px;color:var(--text)}}
.foot{{margin-top:24px;color:var(--mute);font-size:12px;border-top:1px solid var(--line);padding-top:14px;line-height:1.6}}
</style></head><body><div class="wrap">
<h1>📈 ETF 데일리 진입 환경</h1>
<div class="ts">{now:%Y-%m-%d %H:%M} KST · 최신 세션 종가 기준 · 규칙 출처=저자 명시</div>
<div class="scorebox">
  <div class="top"><span class="num">{score}/5</span><span class="lab">{sc_verdict}</span></div>
  {sc_rows}
  <div class="lead">주도주 {lead_html}</div>
</div>
{cards}
<div class="foot">환경 판정(EOD)입니다. 장중 3항목(시초가 지지·첫 눌림 저점·30분 판별)은 자동 계산이 안 되니 31분째 직접 확인 후 최종 진입하세요. 이 페이지는 매일 화~토 08:00 자동 갱신됩니다.</div>
</div></body></html>'''

if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps({"score":score,"scorecard":[{"label":l,"ok":b} for l,b in sc],
                          "verdicts":verdicts,"ts":now.isoformat()}, ensure_ascii=False, indent=2))
    else:
        print(text)
    if "--no-send" not in sys.argv:
        sent = send_telegram(text)
        if not sent:
            send_macos(text)
    # HTML 대시보드 + 로그 저장
    base = os.path.expanduser("~/.claude/skills/book-to-playbook")
    try:
        with open(os.path.join(base, "etf-verdict.html"), "w") as f:
            f.write(build_html())
    except Exception as e:
        print("[html 실패]", e, file=sys.stderr)
    try:
        logdir = os.path.join(base, "logs"); os.makedirs(logdir, exist_ok=True)
        with open(os.path.join(logdir, f"etf-{now:%Y%m%d}.txt"), "w") as f:
            f.write(text)
    except Exception:
        pass
