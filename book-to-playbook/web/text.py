# -*- coding: utf-8 -*-
"""식 → 글 낱말(화면층, 책 무관) — 트리 식을 사람 말로 옮길 때 쓰는 낱말·표 한 곳.

두 글이 이 낱말을 같이 쓴다(문장 모양은 각자 — 낱말·표는 여기서만):
  · web/explain   조건 설명의 짧은 피연산자 이름(측정 증거 '종가 · 20일 최고 · 수익률(%)')·단위 힌트
  · web/raw_tree  원시 트리 보기의 전체 글('X 종가(3일 전) > 20일최고(…)')
"""
from tree.gateway import UNKNOWN

PX = {"open": "시가", "high": "고가", "low": "저가", "close": "종가", "volume": "거래량"}   # 시세 필드
INTRADAY_TF = ("1m", "5m")                                   # 장중 분봉(확정 일봉과 구분)
WINDOW = {"highest": "최고", "lowest": "최저", "sum": "합계"}   # k일 창
SINCE = {"minsince": "최저", "maxsince": "최고"}               # 신호 이후
EXTREME = {"max": "최대", "min": "최소"}                       # 둘 중
ARITH_SYM = {"add": " + ", "sub": " − ", "mul": " × ", "div": " ÷ "}
CMP_SYM = {"gt": ">", "ge": "≥", "lt": "<", "le": "≤"}
# 포지션 값 — (짧은 이름(설명), 글 이름(원시 트리), 단위 힌트)
POS = {"ret": ("수익률(%)", "보유수익률%", "%"), "days": ("보유일", "보유일", "일"),
       "maxret": ("최고수익(%)", "최고수익%", "%"), "minret": ("최저수익(%)", "최저수익%", "%"),
       "filled": ("산 횟수", "산 횟수", "회"), "sold": ("판 비율", "판 비율", "")}
POS_UNKNOWN = "포지션"                                       # 모르는 포지션 값(짧은 이름)
BARSSINCE_UNIT = "일"
DIV_UNIT = "배"


def intraday(node):
    """장중 분봉 잎이면 "장중 " 머리말."""
    return "장중 " if node.get("tf", "1d") in INTRADAY_TF else ""


def px_name(field):
    return PX.get(field, field)


def short_n(k):
    """창 길이·lag 자리 숫자(짧게) — 저자가 안 준 숫자는 "?"."""
    return "?" if k == UNKNOWN else "%d" % k


def prose_n(x):
    """식 안 숫자(글) — 저자가 안 준 숫자는 "?(미명시)"."""
    return "?(미명시)" if x == UNKNOWN else str(x)


def ago(n):
    """lag 말투 — n(이미 글자)일 전."""
    return "%s일 전" % n


def pos_rule(node):
    """포지션 값의 규칙 꼬리표 — 산 횟수(1차) 의 '(1차)'."""
    return "(%s)" % node["rule"] if node.get("rule") else ""


def pos_short(key):
    return POS[key][0] if key in POS else POS_UNKNOWN


def pos_prose(key):
    return POS[key][1] if key in POS else key


def pos_unit(key):
    return POS[key][2] if key in POS else "%"
