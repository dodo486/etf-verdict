#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""스케줄 실행 러너 — macOS / Windows / Linux 공용.

run.sh(bash + /opt/homebrew/bin/python3 하드코딩)를 대체한다.
파이썬은 항상 '지금 이 스크립트를 돌린 인터프리터'(sys.executable)를 쓰므로
homebrew·python.org·Microsoft Store 어느 설치본이든 그대로 동작한다.

사용법
  python run.py daily        # 판정(체크리스트 = 조건 트리) → 백테스트 → 발행 (장 마감 후)
  python run.py watch        # 저자가 말한 시각(트리의 at — 예: 개장 10분 전)마다 기다렸다 판정 → 발행
                             #   그날 미국 정규장 개장 기준으로 계산한다(서머타임 자동). 매일 밤 한 번 띄우면 된다.
  python run.py publish      # 재판정 없이 현재 JSON으로 다시 발행만

옵션
  --no-git     발행 후 git commit/push 생략
  --no-push    commit 은 하되 push 는 생략
  --quiet      콘솔 출력 최소화(로그 파일에는 그대로 남음)

경로·크레덴셜은 shared/paths.py 규칙을 따른다. telegram.env 가 BASE에 있으면
자동으로 환경변수에 주입한다(없으면 그냥 건너뜀).

팀 구조: 실행 대상은 전부 패키지 모듈(python -m <팀>.<모듈>)이다 — playbook(구간①)
· checklist(구간②) · verdict(구간③) · publish(발행층) · shared(공통).
"""
import json
import os
import subprocess
import sys
from datetime import datetime

from shared import paths
from shared.paths import BASE, PUBLIC, LOGS, ensure_dir, load_env_file, write_text

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

    def step(self, module, args=(), capture_to=None, required=True):
        """팀 패키지 모듈 하나 실행(python -m <팀>.<모듈>, cwd=BASE).

        capture_to 가 있으면 stdout 을 그 파일에 UTF-8로 저장한다
        (bash의 `> latest-verdict.json` 리다이렉트 대체 — Windows 콘솔
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

    def verify(self, module, args=()):
        """검사기(verify_*.py) 전용 실행 — 종료코드를 그대로 돌려준다.

        step() 은 성공/실패(True/False) 하나만 알려주고, 실패 시 곧바로
        self.failed 에 쌓아 발행을 막는다. 검사기는 등급이 갈린다
        (0=통과 · 1=발행 정지 · 2=경고뿐 — 스크립트마다 1/2 의 뜻은 main() 의
        등급표를 따른다). 그 등급 판단은 여기가 아니라 호출부(main)가 한다 —
        그래서 이 메서드는 self.failed 를 건드리지 않고 (종료코드, stdout, stderr)
        셋을 그대로 돌려준다.
        """
        cmd = [PY, "-m", module] + list(args)
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        try:
            p = subprocess.run(cmd, cwd=BASE, env=env, capture_output=True)
        except Exception as e:
            self.say("  !! 실행 실패: %s" % e)
            return 1, "", str(e)
        out = p.stdout.decode("utf-8", "replace")
        err = p.stderr.decode("utf-8", "replace")
        return p.returncode, out, err


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

    msg = "auto: %s 판정 갱신" % datetime.now().strftime("%Y-%m-%d")

    git(["add", "-A"], PUBLIC)
    # 커밋 신원은 이 저장소의 git 설정(user.name/email)을 그대로 쓴다 — 코드에 박지 않는다.
    c = git(["commit", "-qm", msg], PUBLIC)
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
    if mode == "watch":
        return watch(argv)
    if mode not in ("daily", "publish", "verdict"):
        print(__doc__)
        return 2

    quiet = "--quiet" in argv
    no_git = "--no-git" in argv
    no_push = "--no-push" in argv

    for envfile in ("telegram.env",):
        loaded = load_env_file(os.path.join(BASE, envfile))
        if loaded and not quiet:
            print("%s 로드 (%d개 키)" % (envfile, len(loaded)))

    r = Runner(mode, quiet)
    r.say("=== %s 시작 · %s · BASE=%s · PUBLIC=%s" % (mode, sys.platform, BASE, PUBLIC))

    # 판정 JSON은 책마다 분리 저장한다(latest-verdict-<slug>.json). 한 파일을
    # 돌려쓰면 live 2권째부터 마지막 책의 판정이 모든 페이지에 병합된다.
    def latest_path(slug):
        return os.path.join(BASE, "latest-verdict-%s.json" % slug)

    # 어느 엔진을 돌릴지는 books.json 에서 온다(코드에 특정 책을 박지 않는다).
    live = paths.live_slugs()
    if not live:
        r.say("!! books.json 에 live:true 책이 없음 — 시세 엔진 건너뜀")
    if mode in ("daily", "verdict"):
        for slug in live:
            daily = paths.book_engine(slug, "daily")
            if not daily:
                r.say("!! %s: engine.daily 없음 — 건너뜀" % slug); continue
            r.step(daily, [slug])                                              # 1) 알림 포함 본 실행
            r.step(daily, [slug, "--json", "--no-send"], capture_to=latest_path(slug))  # 2) 발행용 JSON
            # 3) 책 페이지 '백테스트' 탭 데이터(1년·3년) — 장 마감 후(daily)만. 실패해도 판정 발행은 막지 않는다.
            if mode == "daily":
                r.step("verdict.backtest", [slug, "--page"], required=False)

    missing = [s for s in live if not os.path.exists(latest_path(s))]
    if missing:
        r.say("!! 판정 파일 없음: %s — 발행 중단(run.py daily 를 먼저)" % ", ".join(missing))
        return 1

    r.step("publish.publish_pages")
    r.step("publish.build_home", required=False)

    # ---- 검사 3종 — 반드시 여기(publish/build_home 직후 · git 커밋/푸시 이전)에서 돈다.
    #
    # 왜 이 위치인가: 구조 게이트의 원문 무결 검사는 PUBLIC/<slug>/index.html(방금 위에서 새로
    # 쓴 배포본)을 작업본보다 우선 읽는다. publish 후 · git 커밋 전이면 "방금 만든 페이지"를
    # 검사하면서도, 걸렸을 때 그 페이지가 아직 공개 사이트로 안 나간 상태다.
    #
    #   ① verify_structure          형식·구조(팀 경계·플레이북 본문 해시·책 계약)
    #   ② verdict.verify_primitives 조건 트리 원시 연산이 계산을 맞게 하나(실행 검사)
    #   ③ checklist.verify_tree     체크리스트가 원문 뜻대로 동작하나(이중 추출·원문 사례·발화 통계·비중 합)
    # 등급: 0 통과 · 1 정지 · 2 경고.
    checks = ["verify_structure", "verdict.verify_primitives", "checklist.verify_tree"]
    codes = {}
    for script in checks:
        code, out, err = r.verify(script)
        codes[script] = code
        for t in out.strip().splitlines()[-6:]:
            r.say("  [%s] %s" % (script, t))
        if err.strip():
            r.say("  [%s] stderr: %s" % (script, err.strip()[:400]))
        r.say("  [%s] 종료코드 %d" % (script, code))

    blocking = []
    labels = {"verify_structure": "형식·구조 위반",
              "verdict.verify_primitives": "원시함수 계산 오류",
              "checklist.verify_tree": "규칙 동작 검사 실패(트리 없음·미심판 불일치·원문 사례 불일치 등)"}
    for script in checks:
        if codes[script] == 1:
            blocking.append("%s — %s" % (script, labels[script]))
        elif codes[script] == 2:
            r.say("!! %s: 경고 — 발행은 막지 않음" % script)
        elif codes[script] != 0:
            blocking.append("%s — 비정상 종료(%d)" % (script, codes[script]))

    if blocking:
        r.say("=== 발행 정지 — 아래 검사가 실패해 git 커밋/푸시를 하지 않습니다:")
        for b in blocking:
            r.say("    - %s" % b)
        r.failed.extend(blocking)
    elif no_git:
        r.say("git: --no-git 지정 — 건너뜀")
    else:
        publish_git(r, do_push=not no_push)

    if r.failed:
        r.say("=== 실패 단계: %s" % ", ".join(r.failed))
        return 1
    r.say("=== %s 완료" % mode)
    return 0


def watch(argv):
    """저자가 말한 시각마다 판정 — 라이브 책 트리의 at(개장 기준 분)을 모아, 오늘 미국 정규장 개장 기준 그 시각
    (+1분: 1분봉이 닫히고 들어오는 여유)까지 기다렸다가 판정→발행(백테스트 제외)을 돈다. 주말이면 그냥 끝난다."""
    import time
    from datetime import timedelta, timezone
    from shared import cond, tree_grade
    offs = set()
    for slug in paths.live_slugs():
        t = tree_grade.load_tree(slug)
        if t:
            offs.update(cond.at_offsets(t))
    now = datetime.now(timezone.utc)
    et_day = (now - timedelta(hours=5)).strftime("%Y%m%d")    # 뉴욕 날짜(대략) — 개장 시각은 et_to_utc 가 정확히
    if datetime.strptime(et_day, "%Y%m%d").weekday() >= 5:
        print("watch: 오늘은 미국 정규장이 없다 — 끝")
        return 0
    rest = [a for a in argv if a != "watch"]
    code = 0
    for off in sorted(offs):
        due = cond.et_to_utc(et_day, *cond.US_OPEN_ET) + timedelta(minutes=off + 1)
        wait = (due - datetime.now(timezone.utc)).total_seconds()
        if wait < -600:
            print("watch: 개장 %+d분 시각은 이미 지남 — 건너뜀" % off)
            continue
        print("watch: 개장 %+d분 판정 — %s(현지 %s)까지 %.0f분 대기"
              % (off, due.strftime("%H:%M UTC"), due.astimezone().strftime("%H:%M"), max(0, wait) / 60))
        if wait > 0:
            time.sleep(wait)
        code = main(["verdict"] + rest) or code
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
