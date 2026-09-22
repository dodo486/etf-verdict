#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""스케줄 실행 러너 — macOS / Windows / Linux 공용.

run.sh / run_intraday.sh(bash + /opt/homebrew/bin/python3 하드코딩)를 대체한다.
파이썬은 항상 '지금 이 스크립트를 돌린 인터프리터'(sys.executable)를 쓰므로
homebrew·python.org·Microsoft Store 어느 설치본이든 그대로 동작한다.

사용법
  python run.py daily        # EOD 판정 → 발행 (장 마감 후, 기존 run.sh)
  python run.py intraday     # 장중 판정 → 발행 (개장+31분, 기존 run_intraday.sh)
  python run.py publish      # 재판정 없이 현재 JSON으로 다시 발행만

옵션
  --no-git     발행 후 git commit/push 생략
  --no-push    commit 은 하되 push 는 생략
  --quiet      콘솔 출력 최소화(로그 파일에는 그대로 남음)

경로·크레덴셜은 paths.py 규칙을 따른다. kis.env / telegram.env 가 BASE에 있으면
자동으로 환경변수에 주입한다(없으면 그냥 건너뜀).
"""
import os
import subprocess
import sys
from datetime import datetime

import paths
from paths import BASE, PUBLIC, LOGS, ensure_dir, load_env_file, write_text

PY = sys.executable or "python3"


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

    def step(self, script, args=(), capture_to=None, required=True):
        """BASE 안의 파이썬 스크립트 하나 실행.

        capture_to 가 있으면 stdout 을 그 파일에 UTF-8로 저장한다
        (bash의 `> latest-verdict.json` 리다이렉트 대체 — Windows 콘솔
        코드페이지를 타지 않도록 파이프에서 직접 디코드한다).
        """
        cmd = [PY, os.path.join(BASE, script)] + list(args)
        self.say("실행: %s %s" % (script, " ".join(args)))
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        try:
            p = subprocess.run(cmd, cwd=BASE, env=env, capture_output=True)
        except Exception as e:
            self.say("  !! 실행 실패: %s" % e)
            if required:
                self.failed.append(script)
            return False

        out = p.stdout.decode("utf-8", "replace")
        err = p.stderr.decode("utf-8", "replace")
        if err.strip():
            self.say("  stderr: %s" % err.strip()[:800])
        if p.returncode != 0:
            self.say("  !! 종료코드 %d" % p.returncode)
            if required:
                self.failed.append(script)
            return False

        if capture_to:
            if not out.strip():
                self.say("  !! 출력이 비어 %s 를 덮지 않음" % os.path.basename(capture_to))
                if required:
                    self.failed.append(script)
                return False
            write_text(capture_to, out)
            self.say("  → %s (%d bytes)" % (os.path.basename(capture_to), len(out)))
        elif out.strip() and not self.quiet:
            tail = out.strip().splitlines()[-3:]
            for t in tail:
                self.say("  %s" % t)
        return True


def git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)


def publish_git(r, do_push=True):
    """PUBLIC 이 git 리포면 커밋(+푸시). origin 이 없으면 조용히 건너뛴다."""
    if not os.path.isdir(os.path.join(PUBLIC, ".git")):
        r.say("git: %s 는 리포가 아님 — 건너뜀" % PUBLIC)
        return
    has_origin = git(["remote", "get-url", "origin"], PUBLIC).returncode == 0

    st = git(["status", "--porcelain"], PUBLIC)
    if not st.stdout.strip():
        r.say("git: 변경 없음")
        return

    stamp = datetime.now().strftime("%Y-%m-%d" if r.mode == "daily" else "%Y-%m-%d %H:%M")
    msg = ("auto: %s 판정 갱신" if r.mode == "daily" else "auto(장중): %s 진입조건 갱신") % stamp

    git(["add", "-A"], PUBLIC)
    c = git(["-c", "user.name=조혜영", "-c", "user.email=dodo486@users.noreply.github.com",
             "commit", "-qm", msg], PUBLIC)
    if c.returncode != 0:
        r.say("git: 커밋 실패 — %s" % (c.stderr or c.stdout).strip()[:300])
        return
    r.say("git: 커밋 완료 — %s" % msg)

    if not do_push:
        r.say("git: --no-push 지정 — 푸시 생략")
        return
    if not has_origin:
        r.say("git: origin 없음 — 푸시 생략")
        return
    br = git(["rev-parse", "--abbrev-ref", "HEAD"], PUBLIC).stdout.strip() or "main"
    p = git(["push", "-q", "origin", br], PUBLIC)
    r.say("git: 푸시 %s" % ("완료 (%s)" % br if p.returncode == 0
                            else "실패 — %s" % (p.stderr or "").strip()[:300]))


def main(argv):
    modes = [a for a in argv if not a.startswith("-")]
    mode = modes[0] if modes else "daily"
    if mode not in ("daily", "intraday", "publish"):
        print(__doc__)
        return 2

    quiet = "--quiet" in argv
    no_git = "--no-git" in argv
    no_push = "--no-push" in argv

    for envfile in ("kis.env", "telegram.env"):
        loaded = load_env_file(os.path.join(BASE, envfile))
        if loaded and not quiet:
            print("%s 로드 (%d개 키)" % (envfile, len(loaded)))

    r = Runner(mode, quiet)
    r.say("=== %s 시작 · %s · BASE=%s · PUBLIC=%s" % (mode, sys.platform, BASE, PUBLIC))

    latest = os.path.join(BASE, "latest-verdict.json")

    if mode == "daily":
        # 1) 알림 포함 본 실행 (텔레그램/데스크톱)
        r.step("etf_daily_verdict.py")
        # 2) 발행용 JSON (알림 없이 stdout → 파일)
        r.step("etf_daily_verdict.py", ["--json", "--no-send"], capture_to=latest)
    elif mode == "intraday":
        # 장중 KIS 판정 → kis-intraday.json
        r.step("etf_intraday_verdict.py")
        # EOD JSON도 같이 갱신(장중 병합 대상)
        r.step("etf_daily_verdict.py", ["--json", "--no-send"], capture_to=latest)

    if not os.path.exists(latest):
        r.say("!! latest-verdict.json 없음 — 발행 중단")
        return 1

    r.step("publish_pages.py")
    r.step("build_home.py", required=False)

    # 저자 원문이 바뀌지 않았는지 매 발행마다 확인한다.
    # (책 = 사양, 코드 = 구현. 구현에 맞춰 원문을 고치는 사고를 기계로 막는다)
    if not r.step("verify_source_integrity.py", required=False):
        r.say("!! 저자 원문이 바뀐 것으로 보입니다 — verify_source_integrity.py 확인 필요")

    # '✅ 반영' 배지가 사실인지도 대조한다. 배지는 사람이 적은 주장이라 검증이 없으면
    # 구현이 빠져도 ✅로 남는다(5-2 '2거래일 유지' 사고).
    if not r.step("verify_coverage.py", required=False):
        r.say("!! 커버리지 배지와 구현이 어긋납니다 — verify_coverage.py 확인 필요")

    if no_git:
        r.say("git: --no-git 지정 — 건너뜀")
    else:
        publish_git(r, do_push=not no_push)

    if r.failed:
        r.say("=== 실패 단계: %s" % ", ".join(r.failed))
        return 1
    r.say("=== %s 완료" % mode)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
