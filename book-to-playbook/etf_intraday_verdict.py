#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""장중 진입조건 자동 판정 (미국 개장+31분 실행)
KIS 실시간 시세로 '장중 3항목'을 모두 자동으로 채운다:
  - 시초가 지지: 현재가 > 시가 (price-detail)
  - 빅테크/대표주 플러스: 전일종가 대비 등락% (price-detail)
  - 첫 눌림 저점 높임: 분봉 저점 시퀀스 (inquire-time-itemchartprice)

출력: kis-intraday.json (아티팩트가 읽어 진입조건 체크에 반영)
"""
import os, json
from datetime import datetime, timezone
from kis_intraday import overseas_price, higher_low, APP_KEY, APP_SECRET

BASE=os.path.dirname(os.path.abspath(__file__))

def pct_base(o):  # 전일종가 대비 등락률(%)
    if o and not o.get("error") and o.get("last") and o.get("base"):
        return (o["last"]-o["base"])/o["base"]*100
    return None

def pct_open(o):  # 시가 대비 괴리율(%)
    if o and not o.get("error") and o.get("last") and o.get("open"):
        return (o["last"]-o["open"])/o["open"]*100
    return None

def rate(o):  # 전일 대비 상승?
    p=pct_base(o); return p is not None and p>0

def above_open(o):
    p=pct_open(o); return p is not None and p>0

def snap(sym):
    """반환 (data|None, error_str|None)"""
    o=overseas_price(sym)
    if o and not o.get("error") and o.get("last"):
        return o, None
    if o and o.get("error"):
        return None, o["error"]
    return None, "빈 응답(no data)"

# 종목별 주도주 매핑 (진입조건 ②에 해당)
LEADERS={
    "TQQQ":[("NVDA","엔비디아"),("MSFT","MS"),("AAPL","애플")],
    "SOXL":[("NVDA","엔비디아"),("AMD","AMD"),("AVGO","브로드컴")],
    "UPRO":[],  # 섹터 데이터는 무료 불가 → 수동
}

def main():
    now=datetime.now(timezone.utc).astimezone()
    out=os.path.join(BASE,"kis-intraday.json")
    # 키 없음 = 설정 오류(실패)
    if not APP_KEY or not APP_SECRET:
        json.dump({"ts":now.isoformat(),"status":"error","reason":"KIS 키 없음(kis.env)","intraday":{}},
                  open(out,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
        print("KIS 키 없음 → 실패 기록"); return

    # 심볼별 조회(데이터+에러 분리)
    syms=set(["TQQQ","SOXL","UPRO"])
    for p in LEADERS.values():
        for s,_ in p: syms.add(s)
    px={}; err={}
    for s in syms:
        d,e = snap(s)
        px[s]=d; err[s]=e

    # 토큰/전면 실패 판단: 대상 ETF 3개가 전부 에러면 수집 자체 실패
    etf_errs=[err[s] for s in ("TQQQ","SOXL","UPRO") if err.get(s)]
    if len(etf_errs)==3:
        json.dump({"ts":now.isoformat(),"status":"error",
                   "reason":f"KIS 조회 실패: {etf_errs[0]}","intraday":{}},
                  open(out,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"전면 실패 → 기록: {etf_errs[0]}"); return

    result={"ts":now.isoformat(),"status":"ok","intraday":{}}
    for prod in ("TQQQ","SOXL","UPRO"):
        o=px.get(prod); e=err.get(prod)
        if not o:  # 이 종목만 실패
            result["intraday"][prod]={"status":"error","reason":e or "no data"}
            continue
        checks={}
        # 시초가 지지: 현재가·시가·괴리% 수치로
        opct=pct_open(o); bpct=pct_base(o)
        ol=f"현재 {o['last']:.2f} / 시가 {o['open']:.2f}"
        if opct is not None: ol+=f" (시가比 {opct:+.1f}%)"
        if bpct is not None: ol+=f" · 전일比 {bpct:+.1f}%"
        checks["open_hold"]={"auto":True,"ok":bool(above_open(o)),"label":ol}
        leaders=LEADERS.get(prod,[])
        if leaders:
            miss=[nm for s,nm in leaders if err.get(s)]
            # 각 주도주 등락률(%) 수치 라벨
            parts=[]
            for s,nm in leaders:
                if err.get(s): parts.append(f"{nm} 실패"); continue
                p=pct_base(px.get(s))
                parts.append(f"{nm} {p:+.1f}%" if p is not None else f"{nm} –")
            up=[nm for s,nm in leaders if rate(px.get(s))]
            if len(miss)==len(leaders):
                checks["leaders"]={"auto":True,"status":"error","reason":"주도주 조회 실패"}
            else:
                lbl=f"{len(up)}/{len(leaders)}↑ · " + ", ".join(parts)
                checks["leaders"]={"auto":True,"ok":len(up)>=2,"label":lbl}
        # 첫 눌림 저점 높임: KIS 분봉으로 자동 판정
        hl=higher_low(prod)
        if hl.get("error"):
            checks["pullback"]={"auto":True,"status":"error","reason":f"분봉: {hl['error']}"}
        else:
            checks["pullback"]={"auto":True,"ok":bool(hl["ok"]),"label":hl["label"]}
        result["intraday"][prod]={
            "status":"ok","last":o.get("last"),"open":o.get("open"),"base":o.get("base"),
            "checks":checks,
        }
    json.dump(result, open(out,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"장중 판정 저장: {out}")
    for prod,v in result["intraday"].items():
        if v.get("status")=="error": print(f"  {prod}: ❌ {v.get('reason')}"); continue
        cs=v["checks"]; auto_ok=[k for k,c in cs.items() if c.get("auto") and c.get("ok")]
        print(f"  {prod}: 시가 {v['open']} 현재 {v['last']} → 자동충족 {auto_ok}")

if __name__=="__main__":
    main()
