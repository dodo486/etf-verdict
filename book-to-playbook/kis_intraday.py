#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한국투자증권(KIS) Open API — 미국주식 실시간 시세 (스킬 자립 구현, 외부 프로젝트 비의존)
시세 전용: 토큰 발급 + 해외주식 현재가/분봉. 주문 API 없음.
크레덴셜: kis.env (KIS_APP_KEY / KIS_APP_SECRET / KIS_BASE_URL)
"""
import os, json, ssl, time, urllib.request, urllib.parse
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, "kis.env")
TOKEN_PATH = os.path.join(BASE_DIR, ".kis_token.json")
# 실 크레덴셜을 보내는 프로덕션 엔드포인트 → TLS 인증서 정상 검증(기본값 유지)
CTX = ssl.create_default_context()

def _load_env():
    d={}
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH, encoding="utf-8"):
            line=line.strip()
            if line and not line.startswith("#") and "=" in line:
                k,v=line.split("=",1); d[k.strip()]=v.strip()
    return d
ENV=_load_env()
APP_KEY=ENV.get("KIS_APP_KEY",""); APP_SECRET=ENV.get("KIS_APP_SECRET","")
BASE_URL=ENV.get("KIS_BASE_URL","https://openapi.koreainvestment.com:9443")

def _post(path, body, headers):
    req=urllib.request.Request(BASE_URL+path, data=json.dumps(body).encode(),
                               headers={"content-type":"application/json; charset=utf-8", **headers})
    with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
        return json.load(r)

def _get(path, params, headers):
    url=BASE_URL+path+"?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
        return json.load(r)

def get_token():
    # 캐시된 토큰 재사용(24h)
    if os.path.exists(TOKEN_PATH):
        try:
            t=json.load(open(TOKEN_PATH))
            if t.get("expires_at",0) > time.time()+300:
                return t["access_token"]
        except Exception: pass
    d=_post("/oauth2/tokenP",
            {"grant_type":"client_credentials","appkey":APP_KEY,"appsecret":APP_SECRET}, {})
    tok=d["access_token"]
    exp=time.time()+int(d.get("expires_in",86400))
    json.dump({"access_token":tok,"expires_at":exp}, open(TOKEN_PATH,"w"))
    os.chmod(TOKEN_PATH,0o600)
    return tok

# 미국 거래소 코드: 나스닥=NAS, 뉴욕=NYS, 아멕스=AMS (ETF는 대개 AMS/NYS)
EXCH={"TQQQ":"NAS","SOXL":"AMS","UPRO":"AMS","NVDA":"NAS","MSFT":"NAS","AAPL":"NAS","AMD":"NAS","AVGO":"NAS"}

def overseas_price(symbol, exch=None):
    """해외주식 현재가 상세 스냅샷(시가·고저 포함).
    price-detail(HHDFS76200200)은 open/high/low/last/base 제공. 반환 dict 또는 None."""
    tok=get_token()
    ex=exch or EXCH.get(symbol,"NAS")
    headers={"authorization":f"Bearer {tok}","appkey":APP_KEY,"appsecret":APP_SECRET,
             "tr_id":"HHDFS76200200","custtype":"P"}
    try:
        d=_get("/uapi/overseas-price/v1/quotations/price-detail",
               {"AUTH":"","EXCD":ex,"SYMB":symbol}, headers)
        o=d.get("output",{})
        if not o or not o.get("last"):
            return None
        f=lambda k: float(o[k]) if o.get(k) not in (None,"","0") else None
        return {"symbol":symbol,"exch":ex,"last":f("last"),"open":f("open"),
                "high":f("high"),"low":f("low"),"base":f("base"),"rate":f("rate"),
                "tvol":f("tvol"),"tamt":f("tamt")}
    except Exception as e:
        return {"symbol":symbol,"error":str(e)}

def overseas_minutes(symbol, exch=None, nmin=30):
    """해외주식 분봉(최근 N개). 반환 [{t,open,high,low,close}, ...] 시간오름차순 또는 None.
    inquire-time-itemchartprice(HHDFS76950200). 저점 추적용."""
    tok=get_token()
    ex=exch or EXCH.get(symbol,"NAS")
    headers={"authorization":f"Bearer {tok}","appkey":APP_KEY,"appsecret":APP_SECRET,
             "tr_id":"HHDFS76950200","custtype":"P"}
    try:
        d=_get("/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice",
               {"AUTH":"","EXCD":ex,"SYMB":symbol,"NMIN":"1","PINC":"1","NEXT":"",
                "NREC":str(nmin),"FILL":"","KEYB":""}, headers)
        rows=d.get("output2") or []
        bars=[]
        for r in rows:
            f=lambda k: float(r[k]) if r.get(k) not in (None,"","0") else None
            o,h,l,c=f("open"),f("high"),f("low"),f("last") or f("clos")
            if l is None: continue
            bars.append({"t":(r.get("xhms") or r.get("khms") or ""),"open":o,"high":h,"low":l,"close":c})
        bars.reverse()  # 응답이 최신순 → 시간오름차순
        return bars or None
    except Exception as e:
        return {"error":str(e)}

def higher_low(symbol, exch=None):
    """장 초반 첫 눌림에서 저점을 높였는가 판정.
    분봉 저점 시퀀스에서 (첫 저점 형성 → 반등 → 두 번째 눌림 저점이 첫 저점보다 높음) 확인.
    반환 {ok, label} 또는 {error}."""
    bars=overseas_minutes(symbol,exch,nmin=30)
    if isinstance(bars,dict) and bars.get("error"): return {"error":bars["error"]}
    if not bars or len(bars)<6: return {"error":"분봉 부족(장 초반 아님)"}
    lows=[b["low"] for b in bars if b.get("low")]
    if len(lows)<6: return {"error":"분봉 저점 부족"}
    # 국소 최저 두 개(첫 눌림 저점, 이후 눌림 저점) 근사: 전반부 최저 vs 후반부 최저
    half=len(lows)//2
    first_low=min(lows[:half]); second_low=min(lows[half:])
    ok=second_low>first_low
    return {"ok":bool(ok),
            "label":f"저점 {first_low:.2f}→{second_low:.2f} ({'높임 ✓' if ok else '이탈'})"}

if __name__=="__main__":
    import sys
    if not APP_KEY or not APP_SECRET:
        print("❌ kis.env에 KIS_APP_KEY/SECRET 없음"); sys.exit(1)
    print("토큰 발급 시도…")
    try:
        tok=get_token(); print("✅ 토큰 OK (앞 8자):", tok[:8]+"…")
    except Exception as e:
        print("❌ 토큰 실패:", e); sys.exit(1)
    for s in (sys.argv[1:] or ["TQQQ","NVDA","AAPL"]):
        r=overseas_price(s)
        print(f"  {s}: {r}")
