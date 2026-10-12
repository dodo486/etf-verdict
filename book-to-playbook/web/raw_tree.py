#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""원시 트리 보기 — 트리(v3 규칙 목록)를 **판정 로직 안 거치고** 1:1 로 글(HTML)로 옮긴다. 추출 충실성 검증 전용.

왜 있나
  판정 화면(verdict_view → checklist-ui)은 트리를 동사별로 **재배치**하고 등급을 계산해 보여준다. 그래서 "화면이 이상한 게
  트리가 잘못 뽑혀서인지 화면 로직 탓인지"를 가릴 수 없다. 이 보기는 그 반대다 — 재배치·등급·펼치기 없이 규칙을 원문
  소절(ref)마다 그대로 보여준다(플레이북 소절 헤딩의 '🌲 규칙' 토글).

  트리는 판단자에게 묻는다 — judge.tree.cards()(출입구 TreeGateway.cards 의 규칙 카드: 적힌 그대로). 파일 키를 직접 만지지 않는다.
  식 → 글 문장 모양(모두{}·«이름»·(k일 전) 등)은 여기, 낱말·표(종가·보유일·≥ 등)는 web/text 한 곳."""
import re

from tree.gateway import CondError, META, _op_of
from web import text


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _e(n):
    """값·조건 노드 → 글(순수 텍스트). 노드 레벨 on 은 e() 가 덧붙인다."""
    if isinstance(n, bool):
        return str(n)
    if not isinstance(n, dict):
        return text.prose_n(n)
    if set(n) - set(META) == {"rule"}:
        return "«%s»" % n["rule"]
    try:
        op = _op_of(n)
    except CondError:
        return "(알 수 없는 식 %s)" % ",".join(sorted(n))
    v = n[op]
    if op == "manual":
        return "✋" + str(v)
    if op == "px":
        return text.intraday(n) + "%s %s" % (n.get("sym", "(티커 없음)"), text.px_name(v))
    if op == "lag":
        return e(v[0]) + "(%s)" % text.ago(text.prose_n(v[1]))
    if op == "abs":
        return "|" + e(v) + "|"
    if op in text.ARITH_SYM:
        return "(" + e(v[0]) + text.ARITH_SYM[op] + e(v[1]) + ")"
    if op in text.EXTREME:
        return text.EXTREME[op] + "(" + e(v[0]) + ", " + e(v[1]) + ")"
    if op in text.WINDOW:
        return "%s일%s(" % (text.prose_n(v[1]), text.WINDOW[op]) + e(v[0]) + ")"
    if op == "barssince":
        return "마지막참이후일수[" + e(v) + "]"
    if op == "valuewhen":
        return "[" + e(v[0]) + "] 마지막 참인 날의 " + e(v[1])
    if op in ("minsince", "maxsince"):
        return "[" + e(v[0]) + "] 이후 " + text.SINCE[op] + "(" + e(v[1]) + ")"
    if op == "case":
        parts = ["%s이면 %s" % (e(c), e(x)) for c, x in v] + ["아니면 " + e(n["else"])]
        return "조건별{ " + " · ".join(parts) + " }"
    if op == "pos":
        return text.pos_prose(v) + text.pos_rule(n)
    if op in text.CMP_SYM:
        return e(v[0]) + " " + text.CMP_SYM[op] + " " + e(v[1])
    if op == "all":
        return "모두{ " + " · ".join(e(x) for x in v) + " }"
    if op == "any":
        return "하나이상{ " + " · ".join(e(x) for x in v) + " }"
    if op == "atleast":
        return "%s개이상{ " % text.prose_n(v) + " · ".join(e(x) for x in n["of"]) + " }"
    if op == "not":
        return "아님(" + e(v) + ")"
    return "(알 수 없는 연산 %s)" % op          # 지운 연산 등 — 숨기지 않고 드러낸다


def e(n):
    """글 + 노드 레벨 on(상품 델타) 표면화."""
    s = _e(n)
    if isinstance(n, dict) and n.get("on"):
        s += " `{%s}`" % ",".join(n["on"])
    return s


def _prose_html(node):
    """글을 HTML 로 — `{..}`(노드 on)·«..»(참조)를 칩으로 강조."""
    out = _esc(e(node))
    out = re.sub(r"`\{([^}]*)\}`", r"<span class='rt-on'>{\1}</span>", out)
    return re.sub(r"«([^»]*)»", r"<span class='rt-ref'>«\1»</span>", out)


PANEL_CSS = """
.pb-rt-btn{margin-left:8px;font-size:11px;padding:2px 8px;border:1px solid var(--line,#ccc);border-radius:10px;background:transparent;color:var(--mute,#888);cursor:pointer;vertical-align:middle}
.pb-rt-btn:hover{color:inherit;border-color:var(--accent,#888)}
.pb-rt-btn.on{background:var(--accent,#3fae7a);color:#fff;border-color:transparent}
.rtx{margin:6px 0 14px}
.rtx .rt-rule{border:1px solid var(--line,#e2e2e2);border-radius:10px;padding:9px 13px;margin:6px 0;background:var(--surface-2,rgba(127,127,127,.06))}
.rtx .rt-rule.cond{border-style:dashed}
.rtx .rt-rule.skip{opacity:.75}
.rtx .rt-lab{font-weight:700}
.rtx .rt-meta{color:var(--mute,#999);font-size:12px;font-weight:400;margin-left:6px}
.rtx .rt-kind{font-size:11px;padding:1px 6px;border-radius:999px;background:var(--line,#eee);color:var(--mute,#666);margin-left:6px}
.rtx .rt-do{display:inline-block;font-weight:700;margin:6px 8px 0 0}
.rtx .rt-qty{color:var(--accent,#3fae7a);font-weight:600}
.rtx .rt-cond{display:block;margin:2px 0 0 0;line-height:1.7}
.rtx .rt-on,.rtx .rt-all{font-size:11px;padding:0 5px;border-radius:5px;background:rgba(63,174,122,.16);color:var(--accent,#2e8b5f)}
.rtx .rt-all{background:rgba(120,120,120,.16);color:var(--mute,#777)}
.rtx .rt-ref{color:var(--head,inherit)}
.rtx .rt-why,.rtx .rt-n{color:var(--mute,#888);font-size:12px;margin-top:4px;font-style:italic}
"""


def _ref_str(ref):
    return ref if isinstance(ref, str) else "·".join(ref) if isinstance(ref, list) else ""


def _ref_tokens(ref):
    """규칙이 단 ref 를 소절 키(x-y) 목록으로 — '7-5·4-3' → ['7-5', '4-3']."""
    return [t.strip() for t in _ref_str(ref).replace(",", "·").split("·") if "-" in t]


def _on_tag(on):
    return (" <span class='rt-on'>{%s}</span>" % _esc(",".join(on)) if on
            else " <span class='rt-all'>{공통·전상품}</span>")


def _card_html(c):
    head = "<span class='rt-meta'>원문 %s</span>%s</div>" % (_esc(_ref_str(c.ref)), _on_tag(c.on))
    tail = ("<div class='rt-n'>note: %s</div>" % _esc(c.note) if c.note else "") + \
           ("<div class='rt-why'>why: %s</div>" % _esc(c.why) if c.why else "")
    if c.branches:
        body = []
        for b in c.branches:
            q = ""
            if b.qty is not None:
                of, x = b.qty                       # 적힌 그대로(변환하지 않는다 — 물량 변환은 judge.to_units)
                q = " <span class='rt-qty'>[qty %s %s]</span>" % (_esc(of), _esc(e(x)))
            rep = " <span class='rt-kind'>반복</span>" if b.repeat else ""
            when = _prose_html(b.when) if b.when is not None else "(조건 없음)"
            body.append("<div><span class='rt-do'>%s%s%s</span><span class='rt-cond'>%s</span></div>"
                        % (_esc(b.do), q, rep, when))
        return "<div class='rt-rule'><div class='rt-lab'>%s%s%s%s</div>" % (_esc(c.label), head, "".join(body), tail)
    if c.skip:
        return ("<div class='rt-rule skip'><div class='rt-lab'>%s<span class='rt-kind'>skip</span>%s"
                "<div class='rt-cond'>✋ %s</div>%s</div>" % (_esc(c.label), head, _esc(c.skip), tail))
    return ("<div class='rt-rule cond'><div class='rt-lab'>«%s»<span class='rt-kind'>이름 조건</span>%s"
            "<div class='rt-cond'>정의: %s</div>%s</div>" % (_esc(c.label), head, _prose_html(c.value or {}), tail))


def render_by_ref(judge):
    """{소절 ref: 그 소절을 근거로 단 규칙들의 HTML} — 플레이북 소절 밑에 붙이는 조각. 한 규칙이 소절 여럿을 ref 로
    들면 그 소절마다 나온다."""
    out = {}
    for c in judge.tree.cards():
        html = _card_html(c)
        for ref in _ref_tokens(c.ref):
            out.setdefault(ref, []).append(html)
    return {k: "".join(v) for k, v in out.items()}
