#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""스케줄 실행 러너 — macOS / Windows / Linux 공용.

run.sh(bash + /opt/homebrew/bin/python3 하드코딩)를 대체한다.
파이썬은 항상 '지금 이 스크립트를 돌린 인터프리터'(sys.executable)를 쓰므로
homebrew·python.org·Microsoft Store 어느 설치본이든 그대로 동작한다.

사용법
  python run.py daily        # 판정(체크리스트 = 조건 트리) → 알림 → 백테스트 (장 마감 후). 화면은 라이브 서버가 맡는다.
  python run.py watch [--every N]  # asof=지금 기준으로 N분(기본 5)마다 재판정(백테스트 제외).
                             #   장중 조건은 asof(관측 시점) 기준 분봉을 본다 — 분봉이 연결되면 그대로 살아난다.
  python -m publish.serve    # 화면 보기 — 셸(책목록)+모든 책을 실시간 서빙(정적 스냅샷 폐지)

옵션
  --quiet      콘솔 출력 최소화(로그 파일에는 그대로 남음)
  --no-verify-tree  트리 검수(verify_tree)·원시함수 검사(verify_primitives) 생략 — 트리를
                    만들 때 한 번 검수하면 되는 것이라, 트리가 더 안 바뀌면 끈다(발행물 점검
                    verify_structure 는 항상 돈다). 트리 완성 전에는 켜 두는 것이 안전하다.

경로·크레덴셜은 shared/paths.py 규칙을 따른다. telegram.env · local.env 가 BASE에 있으면
자동으로 환경변수에 주입한다(없으면 그냥 건너뜀). 스케줄러로 돌릴 때 jhts 시세 패키지 경로는
local.env 의 PYTHONPATH 로 준다(local.env.example 참고).

팀 구조: 실행 대상은 전부 패키지 모듈(python -m <팀>.<모듈>)이다 — playbook(구간①)
· checklist(구간②) · verdict(구간③) · operations(구간④ 계산기) · publish(발행층) · shared(공통).
"""
import json
import os
import subprocess
import sys
from datetime import datetime

from shared import paths
from shared.paths import BASE, LOGS, ensure_dir, load_env_file, write_text

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


def main(argv):
    modes = [a for a in argv if not a.startswith("-")]
    mode = modes[0] if modes else "daily"
    if mode == "watch":
        return watch(argv)
    if mode not in ("daily", "verdict"):
        print(__doc__)
        return 2

    quiet = "--quiet" in argv
    # 트리 검수(verify_tree)·원시함수 검사(verify_primitives)는 트리를 '만들 때' 한 번 하면 되는
    # 것이라(python -m checklist.verify_tree <slug>), 트리가 더 안 바뀌면 daily 가 매번 다시 돌 필요가
    # 없다. --no-verify-tree 로 그 둘을 끈다(발행물 점검 verify_structure 는 트리와 무관해 항상 돈다).
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
                r.step("operations.backtest", [slug, "--page"], required=False)

    # 정적 발행(GitHub Pages)은 폐지됐다 — 화면은 라이브 서버(publish.serve)가 매 요청 엔진을
    # 새로 돌려 그린다(오래된 값이 '지금 값'처럼 안 보이게). 파일로 굽지도, 레포에 push 하지도 않는다.

    # ---- 검사 3종 — 판정·백테스트 뒤에 돈다.
    #
    #   ① verify_structure          형식·구조(팀 경계·플레이북 본문 해시·책 계약)
    #   ② verdict.verify_primitives 조건 트리 원시 연산이 계산을 맞게 하나(실행 검사)
    #   ③ checklist.verify_tree     체크리스트가 원문 뜻대로 동작하나(이중 추출·원문 사례·발화 통계·비중 합)
    # 등급: 0 통과 · 1 정지 · 2 경고.
    checks = ["verify_structure"]   # 발행물·구조 점검 — 트리와 무관, 항상 돈다
    if not no_verify_tree:
        checks += ["verdict.verify_primitives", "checklist.verify_tree"]
    else:
        r.say("--no-verify-tree: 트리 검수·원시함수 검사 생략(트리 생성 단계에서 이미 검수한 것으로 봄)")
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
        r.say("=== 발행 정지 — 아래 검사가 실패했습니다:")
        for b in blocking:
            r.say("    - %s" % b)
        r.failed.extend(blocking)

    if r.failed:
        r.say("=== 실패 단계: %s" % ", ".join(r.failed))
        return 1
    r.say("=== %s 완료" % mode)
    return 0


def watch(argv):
    """asof=지금 기준으로 주기적으로 재판정→발행(백테스트 제외)한다. 장중(tf="1m") 조건은 asof(관측 시점)
    이하 마지막 분봉을 본다 — 분봉이 연결되면 그대로 자동으로 살아나고, 그 전엔 None→manual(🟡)로 떨어진다.

    옛 watch 는 저자가 말한 '아침 고정 시각'까지 기다리는 용도였다 — asof 모델에선 그 고정 시점 개념이 없어
    '지금 기준 주기 평가'로 바뀌었다. --every N 으로 간격(분, 기본 5)을, --cycles K 로 횟수(기본 무한)를 준다."""
    import time
    rest = [a for a in argv if a != "watch" and a not in ("--every", "--cycles")]
    every = int(argv[argv.index("--every") + 1]) if "--every" in argv else 5
    cycles = int(argv[argv.index("--cycles") + 1]) if "--cycles" in argv else None
    code, n = 0, 0
    while cycles is None or n < cycles:
        n += 1
        print("watch: asof=지금 %d회차 판정 — %s" % (n, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        code = main(["verdict"] + rest) or code
        if cycles is not None and n >= cycles:
            break
        time.sleep(max(1, every) * 60)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
