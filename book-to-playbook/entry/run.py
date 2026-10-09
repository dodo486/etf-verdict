#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""스케줄 실행 러너 — macOS / Windows / Linux 공용.

run.sh(bash + /opt/homebrew/bin/python3 하드코딩)를 대체한다.
파이썬은 항상 '지금 이 스크립트를 돌린 인터프리터'(sys.executable)를 쓰므로
homebrew·python.org·Microsoft Store 어느 설치본이든 그대로 동작한다.

사용법
  python -m entry.run daily        # 판정(체크리스트 = 조건 트리) → 알림 → 백테스트 (장 마감 후). 화면은 라이브 서버가 맡는다.
  python -m entry.run watch [--every N]  # asof=지금 기준으로 N분(기본 5)마다 재판정(백테스트 제외).
                             #   장중 조건은 asof(관측 시점) 기준 분봉을 본다 — 분봉이 연결되면 그대로 살아난다.
  python -m entry.run check [--no-verify-tree] [--parity]  # 검사만 전부(CHECKS 한 목록) — 요약 + 종료코드
  python -m entry.serve        # 화면 보기 — 셸(책목록)+모든 책을 실시간 서빙(정적 스냅샷 폐지)

옵션
  --quiet      콘솔 출력 최소화(로그 파일에는 그대로 남음)
  --no-verify-tree  CHECKS 의 "tree" 태그(트리 검수·원시함수·구간③·화면 설명) 생략 — 트리를
                    만들 때 한 번 검수하면 되는 것이라, 트리가 더 안 바뀌면 끈다("gate" 태그 — 코드 규칙·
                    본문 해시·책 계약·책 페이지 — 는 항상 돈다). 트리 완성 전에는 켜 두는 것이 안전하다.
  --parity     (check 만) "opt" 태그 — 신호 패리티(verify.verify_trading --parity)도 돈다(시세 필요).

경로·크레덴셜은 shared/paths.py 규칙을 따른다. telegram.env · local.env 가 BASE에 있으면
자동으로 환경변수에 주입한다(없으면 그냥 건너뜀). 스케줄러로 돌릴 때 jhts 시세 패키지 경로는
local.env 의 PYTHONPATH 로 준다(local.env.example 참고).

팀 구조: 실행 대상은 전부 패키지 모듈(python -m <팀>.<모듈>)이다 — playbook(구간①)
· checklist(구간②) · trading(구간③ 판정·백테스트·장중) · web(화면) · shared(공통).
"""
import os
import subprocess
import sys
from collections import namedtuple
from datetime import datetime

from shared import paths
from shared.paths import BASE, LOGS, ensure_dir, load_env_file, write_text

PY = sys.executable or "python3"

# ---- 검사 목록 — 한 곳. 모든 모드(daily·verdict·check)가 여기서 태그로 고른다(모드마다 목록을 복붙하지 않는다).
#   tag   "gate" 트리와 무관한 코드·발행물 점검 — 항상 돈다
#         "tree" 트리 검수·원시 연산·구간③·화면 설명 — --no-verify-tree 면 건너뛴다
#         "opt"  시세로 오래 도는 선택 검사 — run check --parity 일 때만
#   warn2 종료코드 2 를 '경고(발행은 막지 않음)'로 보나. 아니면 0 외에는 전부 정지.
Check = namedtuple("Check", "module args tag warn2 what")
CHECKS = [
    Check("verify.verify_code", (), "gate", False, "코드 규칙 — 폴더 경계·주인 표"),
    Check("verify.verify_source_integrity", (), "gate", False, "플레이북 본문 해시"),
    Check("verify.verify_tree", ("--contract",), "gate", False, "책 계약 — 소절 인덱스·트리 문법·ref"),
    Check("verify.verify_view", ("--pages",), "gate", False, "책 페이지 — 구획·UI 사본"),
    Check("verify.verify_primitives", (), "tree", True, "원시함수 계산"),
    Check("verify.verify_trading", (), "tree", True, "거래 시뮬레이터·실전 경로"),
    Check("verify.verify_view", (), "tree", True, "화면 설명 구조"),
    Check("verify.verify_tree", (), "tree", True, "규칙 동작(트리 없음·미심판 불일치·원문 사례 불일치 등)"),
    Check("verify.verify_trading", ("--parity",), "opt", False, "신호 패리티 — 백테스트 == 실시간(일봉)"),
]


def select_checks(no_tree=False, opt=False):
    """태그로 고른 CHECKS 부분집합(순서 그대로)."""
    tags = {"gate"} | (set() if no_tree else {"tree"}) | ({"opt"} if opt else set())
    return [c for c in CHECKS if c.tag in tags]


def check_name(c):
    return " ".join((c.module,) + tuple(c.args))


def run_check(c):
    """검사 하나 실행(python -m <모듈> <인자>, cwd=BASE) → (종료코드, stdout, stderr). 등급 판단은 grade_of."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        p = subprocess.run([PY, "-m", c.module] + list(c.args), cwd=BASE, env=env, capture_output=True)
    except Exception as e:  # noqa: BLE001
        return 1, "", str(e)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def grade_of(c, code):
    """종료코드 → "pass" · "warn" · "stop"."""
    if code == 0:
        return "pass"
    return "warn" if (code == 2 and c.warn2) else "stop"


def log_path(mode):
    ensure_dir(LOGS)
    return os.path.join(LOGS, "cron.log" if mode == "daily" else "%s.log" % mode)


class Runner:
    def __init__(self, mode, quiet=False):
        self.mode = mode
        self.quiet = quiet
        self.logf = log_path(mode)
        self.failed = []

    def say(self, msg):
        line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
        if not self.quiet:
            print(line)
        try:
            with open(self.logf, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def step(self, module, args=(), capture_to=None, required=True):
        """팀 패키지 모듈 하나 실행(python -m <팀>.<모듈>, cwd=BASE).

        capture_to 가 있으면 stdout 을 그 파일에 UTF-8로 저장한다
        (bash의 `> 파일` 리다이렉트 대체 — Windows 콘솔
        코드페이지를 타지 않도록 파이프에서 직접 디코드한다).
        """
        cmd = [PY, "-m", module] + list(args)
        self.say("실행: %s %s" % (module, " ".join(args)))
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        try:
            p = subprocess.run(cmd, cwd=BASE, env=env, capture_output=True)
        except Exception as e:
            self.say("  !! 실행 실패: %s" % e)
            if required:
                self.failed.append(module)
            return False

        out = p.stdout.decode("utf-8", "replace")
        err = p.stderr.decode("utf-8", "replace")
        if err.strip():
            self.say("  stderr: %s" % err.strip()[:800])
        if p.returncode != 0:
            self.say("  !! 종료코드 %d" % p.returncode)
            if required:
                self.failed.append(module)
            return False

        if capture_to:
            if not out.strip():
                self.say("  !! 출력이 비어 %s 를 덮지 않음" % os.path.basename(capture_to))
                if required:
                    self.failed.append(module)
                return False
            write_text(capture_to, out)
            self.say("  → %s (%d bytes)" % (os.path.basename(capture_to), len(out)))
        elif out.strip() and not self.quiet:
            tail = out.strip().splitlines()[-3:]
            for t in tail:
                self.say("  %s" % t)
        return True


def main(argv):
    modes = [a for a in argv if not a.startswith("-")]
    mode = modes[0] if modes else "daily"
    if mode == "watch":
        from entry.watch import watch                 # 장중 주기 재판정 루프(구간③) — 한 회차 = 이 러너의 verdict 모드
        return watch(argv, lambda rest: main(["verdict"] + rest))
    if mode == "check":
        return check_main(argv)
    if mode not in ("daily", "verdict"):
        print(__doc__)
        return 2

    quiet = "--quiet" in argv
    # 트리 검수(verify_tree)·원시함수 검사(verify_primitives) 등 "tree" 태그는 트리를 '만들 때' 한 번 하면
    # 되는 것이라(python -m verify.verify_tree <slug>), 트리가 더 안 바뀌면 daily 가 매번 다시 돌 필요가
    # 없다. --no-verify-tree 로 끈다("gate" 태그 — 코드 규칙·본문 해시·책 계약·책 페이지 — 는 항상 돈다).
    no_verify_tree = "--no-verify-tree" in argv

    # telegram.env(알림 크레덴셜) · local.env(이 컴퓨터 설정 — 예: PYTHONPATH=<jhts 경로>). 둘 다 커밋하지 않는다.
    for envfile in ("telegram.env", "local.env"):
        loaded = load_env_file(os.path.join(BASE, envfile))
        if loaded and not quiet:
            print("%s 로드 (%d개 키)" % (envfile, len(loaded)))

    r = Runner(mode, quiet)
    r.say("=== %s 시작 · %s · BASE=%s" % (mode, sys.platform, BASE))

    # 어느 엔진을 돌릴지는 books.json 에서 온다(코드에 특정 책을 박지 않는다).
    live = paths.live_slugs()
    if not live:
        r.say("!! books.json 에 live:true 책이 없음 — 시세 엔진 건너뜀")
    if mode in ("daily", "verdict"):
        for slug in live:
            daily = paths.book_engine(slug, "daily")
            if not daily:
                r.say("!! %s: engine.daily 없음 — 건너뜀" % slug); continue
            r.step(daily, [slug])                                              # 알림 포함 본 실행 — 화면은 라이브 서버가 맡는다
            # 책 페이지 '백테스트' 탭 데이터(1년·3년) — 장 마감 후(daily)만. 실패해도 막지 않는다.
            if mode == "daily":
                r.step("consumers.display.backtest_page", [slug], required=False)

    # 정적 발행(GitHub Pages)은 폐지됐다 — 화면은 라이브 서버(entry.serve)가 매 요청 엔진을
    # 새로 돌려 그린다(오래된 값이 '지금 값'처럼 안 보이게). 파일로 굽지도, 레포에 push 하지도 않는다.

    # ---- 검사 — 판정·백테스트 뒤에 돈다. 목록은 CHECKS 한 곳(태그로 고름).
    if no_verify_tree:
        r.say("--no-verify-tree: 트리 검수·원시함수 검사 생략(트리 생성 단계에서 이미 검수한 것으로 봄)")
    blocking = []
    for c in select_checks(no_tree=no_verify_tree):
        name = check_name(c)
        code, out, err = run_check(c)
        for t in out.strip().splitlines()[-6:]:
            r.say("  [%s] %s" % (name, t))
        if err.strip():
            r.say("  [%s] stderr: %s" % (name, err.strip()[:400]))
        r.say("  [%s] 종료코드 %d" % (name, code))
        g = grade_of(c, code)
        if g == "warn":
            r.say("!! %s: 경고 — 발행은 막지 않음" % name)
        elif g == "stop":
            blocking.append("%s — %s" % (name, c.what) if code in (1, 2) else "%s — 비정상 종료(%d)" % (name, code))

    if blocking:
        r.say("=== 발행 정지 — 아래 검사가 실패했습니다:")
        for b in blocking:
            r.say("    - %s" % b)
        r.failed.extend(blocking)

    if r.failed:
        r.say("=== 실패 단계: %s" % ", ".join(r.failed))
        return 1
    r.say("=== %s 완료" % mode)
    return 0


def check_main(argv):
    """검사만 전부 — CHECKS 에서 태그로 고르고 한 줄씩 요약. 정지 있으면 1, 경고만이면 0(daily 와 같은 등급)."""
    for envfile in ("telegram.env", "local.env"):
        load_env_file(os.path.join(BASE, envfile))
    chosen = select_checks(no_tree="--no-verify-tree" in argv, opt="--parity" in argv)
    cnt = {"pass": 0, "warn": 0, "stop": 0}
    mark = {"pass": "✅", "warn": "⚠", "stop": "❌"}
    for c in chosen:
        code, out, err = run_check(c)
        g = grade_of(c, code)
        cnt[g] += 1
        lines = out.strip().splitlines()
        last = lines[-1].strip() if lines else (err.strip().splitlines() or [""])[-1]
        print("  %s %-42s %s" % (mark[g], check_name(c), last[:140]))
        if g == "stop":
            print("      └ %s · 종료코드 %d" % (c.what, code))
    print("검사 %d개 · 통과 %d · 경고 %d · 정지 %d" % (len(chosen), cnt["pass"], cnt["warn"], cnt["stop"]))
    return 1 if cnt["stop"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
