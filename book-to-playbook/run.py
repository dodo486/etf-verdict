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
import json
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

    def verify(self, script, args=()):
        """검사기(verify_*.py) 전용 실행 — 종료코드를 그대로 돌려준다.

        step() 은 성공/실패(True/False) 하나만 알려주고, 실패 시 곧바로
        self.failed 에 쌓아 발행을 막는다. 검사기 넷은 등급이 갈린다
        (0=통과 · 1=발행 정지 · 2=경고뿐 — 스크립트마다 1/2 의 뜻은 main() 의
        등급표를 따른다). 그 등급 판단은 여기가 아니라 호출부(main)가 한다 —
        그래서 이 메서드는 self.failed 를 건드리지 않고 (종료코드, stdout, stderr)
        셋을 그대로 돌려준다.
        """
        cmd = [PY, os.path.join(BASE, script)] + list(args)
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


# ---------------------------------------------------------------- 검증 추이 기록
# logs/verify-history.jsonl — 발행마다 한 줄. 숫자는 verify_contract.py /
# verify_rules_vs_spec.py 가 --json 으로 이미 계산해 낸 것을 그대로 옮긴다.
# 여기서 다시 세지 않는다 — 두 곳의 셈이 갈리면 그게 오늘 하루 종일 잡은 실패 양식이다.
HISTORY_FIELDS = ("gap", "violations", "exempt", "leaks", "fabrications")  # 악화(값 증가)를 감시하는 항목


def verify_json_stats(script):
    """검사기를 --json 모드로 한 번 더 돌려 숫자만 받는다. 등급(통과/경고/정지) 판단에는
    이 결과를 쓰지 않는다 — 그건 main() 이 일반 실행(verify())의 종료코드로 이미 끝냈다.
    이 호출은 순수하게 추이 기록용 숫자 채집이다."""
    cmd = [PY, os.path.join(BASE, script), "--json"]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        p = subprocess.run(cmd, cwd=BASE, env=env, capture_output=True, timeout=60)
        out = p.stdout.decode("utf-8", "replace").strip()
        line = out.splitlines()[-1] if out else ""
        return json.loads(line) if line else {}
    except Exception:
        return {}


def history_path():
    return os.path.join(LOGS, "verify-history.jsonl")


def load_last_history():
    """추이 파일의 마지막 줄(직전 회차) — 악화 비교의 기준."""
    p = history_path()
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            lines = [ln for ln in f if ln.strip()]
        return json.loads(lines[-1]) if lines else None
    except Exception:
        return None


def record_verify_history(r, mode):
    """발행마다 검증 숫자를 logs/verify-history.jsonl 에 한 줄 append.

    커밋 대상 여부: logs/ 는 book-to-playbook/.gitignore 에 이미 있다
    (cron.log·publish.log·etf-*.txt 와 같은 취급 — 발행마다 갱신되는 운영 로그는
    환경마다 새로 쌓이는 것이지 버전관리 대상이 아니다). 그래서 이 파일도 커밋
    대상으로 새로 옮기지 않는다 — 기존 로그들과 다르게 취급할 근거가 없다.
    """
    contract_stats = verify_json_stats("verify_contract.py")      # {slug: {reflected,gap,mindset,rules,ref_missing,spec_items,exempt,leaks}}
    rvs_stats = verify_json_stats("verify_rules_vs_spec.py")      # {slug: violations|null}
    fab_stats = verify_json_stats("verify_source_fabrication.py")  # {slug: {claims,orphans,ungrounded,fabrications}|null 값들}

    books = {}
    for slug in set(contract_stats) | set(rvs_stats) | set(fab_stats):
        entry = dict(contract_stats.get(slug) or {})
        entry["violations"] = rvs_stats.get(slug)
        # 창작 검사 숫자(fabrications 등)를 그대로 옮긴다. 검사 불가 책은 None 이 담겨
        # 온다 — 0(돌았고 없음)과 구분된다. 여기서 다시 세지 않는다.
        entry.update(fab_stats.get(slug) or {})
        books[slug] = entry

    prev_books = (load_last_history() or {}).get("books") or {}
    worsened = []
    for slug, cur in books.items():
        pv = prev_books.get(slug) or {}
        for f in HISTORY_FIELDS:
            a, b = pv.get(f), cur.get(f)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) and b > a:
                worsened.append("%s.%s %s→%s" % (slug, f, a, b))

    record = {"ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "mode": mode, "books": books}
    ensure_dir(LOGS)
    with open(history_path(), "a", encoding="utf-8", newline="") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    r.say("추이 기록: %s (책 %d권)" % (os.path.basename(history_path()), len(books)))

    if worsened:
        r.say("!! 직전 회차 대비 악화: %s" % ", ".join(worsened))


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

    # ---- 검사 5종 — 반드시 여기(publish/build_home 직후 · git 커밋/푸시 이전)에서 돈다.
    #
    # 왜 이 위치인가: 검사기 넷은 모두 PUBLIC/<slug>/index.html(방금 위에서 새로 쓴
    # 배포본)을 작업본보다 **우선** 읽는다.
    #   · publish 전에 돌리면 아직 안 바뀐 어제 배포본을 검사한다 — 낡은 결과다.
    #     (verify_source_integrity 의 stale 가드가 이걸 그 자체로 실패 처리한다)
    #   · publish 후 · git 커밋 전에 돌리면 "방금 만든 페이지"를 검사하면서도,
    #     걸렸을 때 그 페이지가 아직 git 에 올라가지 않은 상태다 — 공개 사이트로는
    #     안 나간다. 그래서 publish_pages/build_home 다음 · publish_git 이전인
    #     지금 위치가 유일하게 맞다.
    #
    # 다섯의 순서(사람이 읽는 로그 기준, 판정에는 영향 없음 — 서로 독립):
    #   원문 무결(있는 그대로인가) → 원문 창작(플레이북이 저자에게 없는 걸 안 돌렸나)
    #   → 커버리지(반영 주장이 맞는가) → 계약(형식을 갖췄는가) → 규칙↔수집(층 사이가 맞는가)
    # 원문 창작은 입력(책→플레이북) 쪽 근거 검사라 원문 무결 바로 뒤에 온다.
    # 앞이 깨지면 뒤의 결과도 그 위에서 흔들리므로, 좁은 것부터 넓은 것 순.
    checks = ["verify_source_integrity.py", "verify_source_fabrication.py",
              "verify_coverage.py", "verify_contract.py", "verify_rules_vs_spec.py"]
    codes = {}
    for script in checks:
        code, out, err = r.verify(script)
        codes[script] = code
        for t in out.strip().splitlines()[-4:]:
            r.say("  [%s] %s" % (script, t))
        if err.strip():
            r.say("  [%s] stderr: %s" % (script, err.strip()[:400]))
        r.say("  [%s] 종료코드 %d" % (script, code))

    # ---- 등급 — 거짓(blocking)과 아직 못 채운 것(warning)을 나눈다.
    #   verify_source_integrity / verify_coverage: 단일 등급. 0=통과, 그 외=발행 정지.
    #   verify_contract / verify_rules_vs_spec: 자체적으로 0=통과·1=발행 정지(위반/누출)·
    #     2=경고뿐(계약 미충족/검사 불가) 를 낸다 — 각 스크립트의 등급표 참고.
    blocking = []
    if codes["verify_source_integrity.py"] != 0:
        blocking.append("verify_source_integrity.py — 저자 원문이 바뀜")
    if codes["verify_source_fabrication.py"] == 1:
        blocking.append("verify_source_fabrication.py — 플레이북이 책에 없는 걸 지어냄(창작)")
    elif codes["verify_source_fabrication.py"] == 2:
        r.say("!! verify_source_fabrication.py: 검사 불가(경고) — 발행은 막지 않음")
    if codes["verify_coverage.py"] != 0:
        blocking.append("verify_coverage.py — 커버리지 배지가 거짓")
    if codes["verify_contract.py"] == 1:
        blocking.append("verify_contract.py — 규칙 누출(JSON 밖 규칙)")
    elif codes["verify_contract.py"] == 2:
        r.say("!! verify_contract.py: 계약 미충족(경고) — 발행은 막지 않음")
    if codes["verify_rules_vs_spec.py"] == 1:
        blocking.append("verify_rules_vs_spec.py — 체크리스트↔수집요청 위반(누락/창작)")
    elif codes["verify_rules_vs_spec.py"] == 2:
        r.say("!! verify_rules_vs_spec.py: 검사 불가(경고) — 발행은 막지 않음")

    # ---- 추이 기록 — 통과든 실패든 항상 남긴다(오늘의 실패도 내일 비교할 기준이 된다)
    try:
        record_verify_history(r, mode)
    except Exception as e:
        r.say("!! 추이 기록 실패: %s" % e)

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


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
