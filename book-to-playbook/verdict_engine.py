#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""범용 판정 엔진 (book-to-playbook)

data_spec(JSON)을 받아 각 체크 항목을 어댑터로 자동 채운다.
  - source=="manual" 이거나 커버 안 되는 metric → manual(직접 확인)로 표시
  - 커버되는 metric → resolve→fetch 로 자동 판정(값·라벨·ok·수집상태)

data_spec 형식(리스트 또는 {"items":[...]}):
  {"item": "나스닥100 20일선 위",
   "source": "auto",              # auto | manual (선택; 없으면 metric 유무로 추정)
   "metric": {"type": "above_ma", "symbol": "^NDX", "ma": 20},
   "cadence": "eod",              # eod | intraday | manual (선택; 없으면 어댑터 기본)
   "reason": "..."}               # manual일 때 사유(선택)

출력(evaluate → dict):
  {"ts": <iso>, "items": [ {item, ok, label, value, cadence, source, status,
                            metric_type}... ],
   "coverage": {"auto": n, "manual": m, "total": t}}

각 item의 뱃지 소스 매핑(아티팩트 렌더용):
  source=="yahoo" → 🤖 야후 EOD,  "kis" → ⚡ KIS 장중,
  "nasdaq" → 🗞 나스닥 캘린더,  "manual" → ✋ 직접
"""
import paths  # noqa: F401  (경로·UTF-8 출력 고정. 반드시 먼저 import)
import json
import os
import sys
from datetime import datetime, timezone

from datasources import resolve, cadence_of


def _load_spec(spec):
    """spec: 파일경로(str) | list | {"items":[...]} → item 리스트."""
    if isinstance(spec, str):
        with open(spec, encoding="utf-8") as f:
            spec = json.load(f)
    if isinstance(spec, dict):
        spec = spec.get("items", [])
    if not isinstance(spec, list):
        raise ValueError("data_spec은 list 또는 {'items':[...]} 형식이어야 함")
    return spec


def evaluate_item(spec_item):
    """단일 체크 항목을 어댑터로 채워 표준 결과 dict 반환."""
    item_name = spec_item.get("item", "?")
    metric = spec_item.get("metric")
    forced_manual = spec_item.get("source") == "manual" or metric is None

    if forced_manual:
        from datasources import ManualAdapter  # noqa: PLC0415
        res = ManualAdapter().fetch(spec_item)
        cadence = spec_item.get("cadence", "manual")
        mtype = (metric or {}).get("type")
    else:
        adapter = resolve(metric)
        res = adapter.fetch(spec_item)
        cadence = cadence_of(adapter, spec_item)
        mtype = metric.get("type")

    return {
        "item": item_name,
        "ok": res.get("ok"),
        "label": res.get("label"),
        "value": res.get("value"),
        "cadence": cadence,
        "source": res.get("source", "manual"),
        "status": res.get("status", "manual"),
        "reason": res.get("reason"),
        "metric_type": mtype,
    }


def evaluate(spec):
    """data_spec 전체를 평가. 반환은 아티팩트 verdict-data와 호환되는 dict."""
    items = _load_spec(spec)
    now = datetime.now(timezone.utc).astimezone()
    results = [evaluate_item(it) for it in items]
    auto = sum(1 for r in results if r["source"] in ("yahoo", "kis"))
    manual = sum(1 for r in results if r["source"] == "manual")
    return {
        "ts": now.isoformat(),
        "items": results,
        "coverage": {"auto": auto, "manual": manual, "total": len(results)},
    }


def _fmt(r):
    icon = {"ok": {True: "🟢", False: "🔴", None: "⚪"},
            "manual": {None: "✋"}, "error": {None: "⚠"}}
    st = r["status"]
    sym = icon.get(st, {}).get(r["ok"], "·")
    badge = {"yahoo": "🤖야후EOD", "kis": "⚡KIS장중", "nasdaq": "🗞나스닥캘린더",
              "manual": "✋직접"}.get(r["source"], "?")
    lab = r.get("label") or r.get("reason") or ""
    return f"  {sym} [{badge}] {r['item']}: {lab}"


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    spec_path = args[0] if args else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "etf_data_spec.json")
    out = evaluate(spec_path)
    if "--json" in sys.argv:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        cov = out["coverage"]
        print(f"판정 결과 ({out['ts']})  자동 {cov['auto']}/{cov['total']} · 수동 {cov['manual']}")
        for r in out["items"]:
            print(_fmt(r))
