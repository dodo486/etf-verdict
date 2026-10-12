#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""판정 화면 데이터(웹 화면층, 책 무관) — 오늘 판정을 판정 JSON(#verdict-data)·알림 문장으로 빚는다.

판정(시세 조달 + 판단)은 구간③ 판단자(signals/judge.Judge.decisions)가 내고, 이 파일은 그 Decision 과 설명을
사람과 화면이 읽는 모양으로 빚기만 한다 — 화면은 트리를 다시 해석하지 않고 이 출력만 그린다(판단/표시 분리:
화면은 판정을 계산하지 않는다). books.json 의 engine.daily 가 이 모듈이다(python -m consumers.display.verdict_view <slug> —
라이브 서버·러너가 부르는 '진입+표시+알림' 껍데기 · 판단은 signals.judge 가 한다).

출력 계약(알림 · 화면 · /api/verdict 가 소비):
  top     : {slug, title, ts, date, source, cash, verbs[], grades{}, verdicts[], refs{}, missing{}, positions_note}
            verbs = 동사 셋(정본 Cond.VERBS — 화면 머리글) · grades = 등급 글자표(정본 Grade.GRADES)
  verdict : {prod, index, note, date, close, chg, key, grade, reason,
             gates{안 산다, 산다: view}, opt{..}, pes{..},     등급 동사 둘의 중첩 설명 + 낙관·비관 값
             size{label, ref, weight, weight_range, units, tranches[{label, ref, frac, units, view?}]},   얼마나(산다 qty)
                                                     units = 오늘 물량(시작자본 1.0 기준 — trades.to_units, 비중 모르면 None)
             sells[{label, ref, sell(문장 — trades.sell_text), note, view}], exit_policy("book"|"none" — trades.exit_policy),
             positions[{…, sells[], next_tranche}]}                  positions = 내 포지션(로컬 파일)이 있을 때만
  refs    : {원문 소절: {auto, manual, verbs[], prods[], skipped?[{rule, reason}]}}
            플레이북 소절별 체크리스트 반영 현황 + 트리로 못 옮긴 규칙(skip)과 그 사유
view 는 노드 하나당 항목 하나 {v, op?, n?, kids?, label?, ref?, manual?, note?, hidden?} (판단자 설명 signals/explain.view)
— 수동은 '모름'(사람이 답했으면 그 답 — render(answers=))으로 둔 그날 값. 화면은 다시 계산하지 않고 그대로 그린다.
"""
import json
import sys
from datetime import datetime, timedelta, timezone

from shared.paths import book_log, book_meta, write_text
from market import md_feed
from dsl.tradeTool import Cond
from dsl.tradeTool import Grade
from signals.judge import Judge
from consumers.backtest.trades import NO_EXIT_NOTE, exit_policy, live_units, sell_text
from consumers.notify.telegram import send_telegram
from consumers.notify.desktop import send_desktop

SOURCE = "jhts 시세팀(일봉)"


def book_title(slug):
    """books.json 에서 이 책의 제목(알림/콘솔 헤더용). 없으면 slug.
    명단 읽기는 공용 함수(paths.book_meta) 한 곳을 쓴다 — 직접 파싱하지 않는다."""
    return book_meta(slug).get("title") or slug


# ------------------------------------------------------------------ 상품 하나
def reason_of(key, ex, manual):
    """등급 사유 한 줄 — 무엇이 걸렸는지 라벨로. ex = 동사별 맨 위 라벨 노드 값, manual = [(동사, 라벨, ref)]."""
    def labels(do, val):
        return [l for l, _, v in ex.get(do, []) if l and v is val]
    if key == "avoid":
        hit = labels(Cond.BLOCK, True)
        return "%s: %s" % (Cond.BLOCK, " · ".join(hit[:3]) if hit else "조건 참")
    if key == "wait":
        return "%s 신호 없음 — 관망" % Cond.BUY
    if key == "confirm":
        items = [l for d, l, _ in manual if d == Cond.BUY] + \
                ["(%s 아님) %s" % (Cond.BLOCK, l) for d, l, _ in manual if d == Cond.BLOCK]
        return "수동·장중 확인 시 %s: %s" % (Cond.BUY, " · ".join(items[:4]))
    if key == "buy":
        ok = labels(Cond.BUY, True)
        return "%s: %s" % (Cond.BUY, " · ".join(ok[:3]) if ok else "조건 충족")
    return "데이터 부족으로 판정 불가"


def _rule_views(judge, a=None):
    """얼마나(비중·분할)·판다 규칙의 화면 모양 — 시세가 있든 없든 같은 모양(규칙 설명은 판단자가 낸 값 없는 설명).
    a = 그날 Amount(judge.amount) — 없으면(시세 없음) 비중·물량은 None."""
    sz = judge.weight()
    return {"size": {"label": sz.label, "ref": sz.ref, "note": sz.note,
                     "weight": a and a.weight, "weight_range": a and a.weight_range, "weight_set": a and a.weight_set,
                     "units": a and live_units(a),            # 오늘 물량(시작자본 1.0 기준, 화면이 × 총 투자금)
                     "tranches": [{"label": t.label, "ref": t.ref, "frac": t.qty.x,
                                   "units": a and live_units(a, t.qty), "conditional": t.when is not None,
                                   "view": judge.describe(t)} for t in judge.tranches()]},
            "sells": [{"label": r.label, "ref": r.ref, "allprod": r.allprod, "sell": sell_text(r.qty, r.repeat),
                       "note": r.note, "view": judge.describe(r)} for r in judge.sells()],
            "exit_policy": exit_policy(judge.sells())}


def product_verdict(judge, d, mine):
    """상품 하나의 판정 JSON — 판정(Decision d)과 설명은 판단자(signals/judge)가 내고, 여기는 화면 모양으로 빚기만 한다.
    mine = 이 상품의 내 포지션(로컬 파일)."""
    base = {"prod": judge.product, "index": judge.index, "note": judge.note}
    if not d.has_data:
        # 시세가 없어도 체크리스트 '구조'(규칙·조건 항목)는 정적으로 보여준다 — 값은 모름(❔), 지어내지 않는다.
        req = md_feed.requested().get(judge.product, "-")
        return dict(base, key="unknown", grade=Grade.GRADES["unknown"], date="", close=None, chg=None,
                    reason="%s 시세 없음(수집 요청 %s) — 아래는 판정 전 체크리스트 구조" % (judge.product, req),
                    gates=judge.static_views(), opt={}, pes={}, **_rule_views(judge))
    reason = reason_of(d.key, d.top, d.manual)
    # 데이터 완전성 가드 — 지금 가진 확정 봉이 트리가 쓰는 가장 긴 창(필요 워밍업)보다 짧으면 등급은 ❔(불완전
    #   데이터, 판정 보류)로 떨어져 있다(grade_key). 사유를 '모르고 매매 금지'로 분명히 적는다(✅/🚫 확신 금지).
    if d.incomplete:
        reason = "불완전 데이터(판정 보류) — 확정 봉 %d개 < 필요 워밍업 %d개, 창이 덜 차 신뢰불가" % (d.confirmed, d.warmup)
    v = dict(base, date=d.date, close=d.close,
             chg=(d.close / d.prev_close - 1) * 100 if d.prev_close else None,
             key=d.key, grade=d.grade, reason=reason, gates=d.views,
             opt=d.opt, pes=d.pes, **_rule_views(judge, d.amount))
    pos = [dict(_holding_view(hs), entry_date=x["entry_date"], entry_px=x["entry_px"], filled=x.get("filled", 1))
           for hs, x in zip(d.holdings, mine)]
    if pos:
        v["positions"] = pos
    return v


def _holding_view(hs):
    """보유 하나(HoldingStatus) → {ret, days, sells:[{label, ref, sell, v, view}], next_tranche:{label, ref, frac, v, view}|None}."""
    if hs.error:
        return {"error": hs.error}
    out = {"ret": hs.ret, "days": hs.days,
           "sells": [{"label": r.label, "ref": r.ref, "sell": sell_text(r.qty, r.repeat), "v": v, "view": view}
                     for r, v, view in hs.sells]}
    nt = hs.next_tranche
    out["next_tranche"] = None if nt is None else {
        "label": nt[0].label, "ref": nt[0].ref, "frac": nt[0].qty.x, "v": nt[1], "view": nt[2]}
    return out


# ------------------------------------------------------------------ 책 하나
def render(slug, asof=None, answers=None):
    """asof = 관측 시각(UTC datetime). None 이면 지금 — 장중(tf="1m") 조건을 이 시점 이하로 자른다.
    answers = 화면에서 사람이 답한 수동 {Cond.answer_key: 참/거짓} — 판단자가 그 답으로 등급·조건 값·금액을 낸다
    (서버 권위 — 화면은 다시 계산하지 않는다). None 이면 답 없는 판정, 주면 top["answers"] 로 되돌려 준다.

    판정(Judge.decisions)과 모양 빚기(_format)를 쪼개 둔다 — 라이브 2단 pub-sub(entry/live)에서 신호
    핸들러가 판정 사실을 내 verdict_bus 에 올리면, 화면 소비자가 그 사실로 _format 만 부른다(한 번 계산)."""
    book = Judge.open(slug)
    if book is None:
        return _format(slug, None, {}, [], answers=answers)
    prices = book.prices()
    return _format(slug, book, prices, book.decisions(prices, asof=asof, answers=answers), answers=answers)


def _format(slug, book, prices, decisions, answers=None):
    """판정 사실(Judge.decisions 의 결과)을 top(화면·알림·/api/verdict 가 소비하는 dict)으로 빚는다 —
    라이브 2단 pub-sub 의 화면 소비자가 verdict_bus 에서 받은 사실로 이걸 부른다(같은 모양을 라이브·배치가 공유)."""
    now = datetime.now(timezone.utc).astimezone()
    top = {"slug": slug, "title": book_title(slug), "ts": now.isoformat(), "source": SOURCE,
           "verdicts": [], "refs": {}, "missing": {}, "cash": None,
           # 등급 글자표(키→라벨)를 실어보낸다 — 화면이 따로 복붙하지 않고 이걸 받아 쓴다(단일 출처).
           "grades": Grade.GRADES,
           # 동사 셋(화면 머리글·판정 JSON 키) — Cond.VERBS 가 정본이다. 화면은 복붙하지 않고 이걸 받아 쓴다.
           "verbs": list(Cond.VERBS),
           # 매도 정책 "none"(책에 매도 규칙 없음) 문구 — 정본 consumers/backtest/trades.NO_EXIT_NOTE(화면이 받아 쓴다).
           "no_exit_note": NO_EXIT_NOTE}
    if book is None:
        top["error"] = "조건 트리 없음 — books/%s/tree.json 이 있어야 판정한다" % slug
        return top
    weights, all_known = [], True
    for _p, d, judge, mine in decisions:
        v = product_verdict(judge, d, mine)
        top["verdicts"].append(v)
        sz = v.get("size") or {}
        if sz.get("weight_set"):
            if sz.get("weight") is None:
                all_known = False
            else:
                weights.append(sz["weight"])
    if weights and all_known:
        top["cash"] = max(0.0, 100.0 - sum(weights))
    top["date"] = max((v.get("date") or "" for v in top["verdicts"]), default=None)
    top["refs"] = book.coverage()
    top["missing"] = {s: md_feed.requested().get(s, "-") for s in Judge.missing(prices)}
    if answers is not None:
        top["answers"] = answers
    if any(mine for _p, _d, _j, mine in decisions):
        top["positions_note"] = "내 포지션(books/%s/positions.json) 기준 — 로컬 화면에서만 쓴다" % slug
    return top


# ------------------------------------------------------------------ 출력 텍스트 / 알림
def build_text(top):
    now = datetime.fromisoformat(top["ts"])
    L = ["📈 %s  (%s KST · %s 종가 기준)" % (top.get("title") or top["slug"], now.strftime("%Y-%m-%d %H:%M"),
                                         top.get("date") or "-")]
    if top.get("error"):
        L.append("❔ " + top["error"])
        return "\n".join(L)
    L.append("─" * 30)
    for v in top["verdicts"]:
        L.append("%s  %s" % (v["prod"], v["grade"]))
        L.append("   %s" % v["reason"])
        sz = v.get("size") or {}
        if sz.get("weight") is not None:
            L.append("   비중 %.0f%%" % sz["weight"])
        elif sz.get("weight_range"):
            L.append("   비중 확인 필요: %s%%" % " / ".join("%.0f" % x for x in sz["weight_range"]))
        for ps in v.get("positions") or []:
            hit = [e["label"] for e in ps.get("sells", []) if e.get("v") is True]
            L.append("   보유(%s, %+.1f%%) 매도 신호: %s" % (ps.get("entry_date"), ps.get("ret") or 0,
                                                     " · ".join(hit) if hit else "없음"))
    if top.get("cash") is not None:
        L.append("현금 %.0f%%" % top["cash"])
    if top.get("missing"):
        L.append("⚠ 시세 없음(수집 요청): " + ", ".join("%s #%s" % kv for kv in top["missing"].items()))
    L.append("─" * 30)
    L.append("※ 관측 시점(asof) 기준 판정 — 종가 조건은 마지막 확정 일봉, 장중 조건은 그 시점 분봉. "
             "🟡 는 수동(장중 분봉 미연결·저자 미명시) 조건을 직접 확인한 뒤 진입. 규칙 출처 = 저자 명시.")
    return "\n".join(L)


# 알림 발신(send_telegram/send_desktop)은 소비층 consumers/notify 가 맡는다 —
# 네트워크 코드(urllib)는 그 한 파일에만 허용된다(verify/rules.py ALLOW 의 명시 예외).
def _cli():
    argv = sys.argv[1:]
    slug = next((a for a in argv if not a.startswith("-")), None)
    if not slug:
        print("사용법: python -m consumers.display.verdict_view <slug> [--json] [--no-send]", file=sys.stderr)
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
