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
        self.failed 에 쌓아 발행을 막는다. 검사기 넷은 등급이 갈린다
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

    stamp = datetime.now().strftime("%Y-%m-%d" if r.mode == "daily" else "%Y-%m-%d %H:%M")
    msg = ("auto: %s 판정 갱신" if r.mode == "daily" else "auto(장중): %s 진입조건 갱신") % stamp

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


# ---------------------------------------------------------------- 검증 추이 기록
# logs/verify-history.jsonl — 발행마다 한 줄. 숫자는 verify_contract.py /
# verify_rules_vs_spec.py 가 --json 으로 이미 계산해 낸 것을 그대로 옮긴다.
# 여기서 다시 세지 않는다 — 두 곳의 셈이 갈리면 그게 오늘 하루 종일 잡은 실패 양식이다.
HISTORY_FIELDS = ("gap", "violations", "exempt", "leaks", "fabrications", "qualitative")  # 악화(값 증가)를 감시하는 항목


def verify_json_stats(module):
    """검사기를 --json 모드로 한 번 더 돌려 숫자만 받는다. 등급(통과/경고/정지) 판단에는
    이 결과를 쓰지 않는다 — 그건 main() 이 일반 실행(verify())의 종료코드로 이미 끝냈다.
    이 호출은 순수하게 추이 기록용 숫자 채집이다."""
    cmd = [PY, "-m", module, "--json"]
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
    (cron.log·publish.log·<slug>-*.txt 와 같은 취급 — 발행마다 갱신되는 운영 로그는
    환경마다 새로 쌓이는 것이지 버전관리 대상이 아니다). 그래서 이 파일도 커밋
    대상으로 새로 옮기지 않는다 — 기존 로그들과 다르게 취급할 근거가 없다.
    """
    contract_stats = verify_json_stats("verify_contract")      # {slug: {reflected,gap,mindset,rules,ref_missing,spec_items,exempt,leaks}}
    rvs_stats = verify_json_stats("verdict.verify_rules_vs_spec")      # {slug: violations|null}
    fab_stats = verify_json_stats("playbook.verify_source_fabrication")  # {slug: {claims,orphans,ungrounded,fabrications}|null 값들}

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
    # live:true 인 책의 engine.daily / engine.intraday 를 순서대로 실행.
    live = paths.live_slugs()
    if not live:
        r.say("!! books.json 에 live:true 책이 없음 — 시세 엔진 건너뜀")
    if mode == "daily":
        for slug in live:
            daily = paths.book_engine(slug, "daily")
            if not daily:
                r.say("!! %s: engine.daily 없음 — 건너뜀" % slug); continue
            r.step(daily, [slug])                                              # 1) 알림 포함 본 실행
            r.step(daily, [slug, "--json", "--no-send"], capture_to=latest_path(slug))  # 2) 발행용 JSON
    elif mode == "intraday":
        for slug in live:
            intraday = paths.book_engine(slug, "intraday")
            daily = paths.book_engine(slug, "daily")
            if intraday:
                r.step(intraday, [slug])                               # 장중 판정
            if daily:
                r.step(daily, [slug, "--json", "--no-send"], capture_to=latest_path(slug))  # EOD 병합 대상

    have = [s for s in live if os.path.exists(latest_path(s))]
    if live and not have:
        if os.path.exists(os.path.join(BASE, "latest-verdict.json")):
            r.say("!! 책별 판정 파일 없음 — 구버전 latest-verdict.json 폴백으로 발행")
        else:
            r.say("!! latest-verdict-<slug>.json 이 하나도 없음 — 발행 중단")
            return 1
    for s in live:
        if s not in have:
            r.say("!! %s: latest-verdict-%s.json 없음 — 지난 스냅샷/구파일로 발행됨" % (s, s))

    r.step("publish.publish_pages")
    r.step("publish.build_home", required=False)

    # ---- 검사 6종 — 반드시 여기(publish/build_home 직후 · git 커밋/푸시 이전)에서 돈다.
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
    # 순서(사람이 읽는 로그 기준, 판정에는 영향 없음 — 서로 독립):
    #   팀 경계(코드 구조가 맞는가)가 맨 앞 —

    #   원문 무결(있는 그대로인가) → 원문 창작(플레이북이 저자에게 없는 걸 안 돌렸나)
    #   → 커버리지(반영 주장이 맞는가) → 계약(형식을 갖췄는가) → 규칙↔수집(층 사이가 맞는가)
    # 원문 창작은 입력(책→플레이북) 쪽 근거 검사라 원문 무결 바로 뒤에 온다.
    # 앞이 깨지면 뒤의 결과도 그 위에서 흔들리므로, 좁은 것부터 넓은 것 순.
    checks = ["verify_teams", "playbook.verify_source_integrity",
              "playbook.verify_source_fabrication", "checklist.verify_coverage",
              "verify_contract", "verdict.verify_rules_vs_spec",
              "verdict.verify_metric_semantics", "verify_editable_auto"]
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
    if codes["verify_teams"] != 0:
        blocking.append("verify_teams — 팀 경계/jhts 단일창구 위반")
    if codes["playbook.verify_source_integrity"] != 0:
        blocking.append("playbook.verify_source_integrity — 저자 원문이 바뀜")
    if codes["playbook.verify_source_fabrication"] == 1:
        blocking.append("playbook.verify_source_fabrication — 플레이북이 책에 없는 걸 지어냄(창작)")
    elif codes["playbook.verify_source_fabrication"] == 2:
        r.say("!! playbook.verify_source_fabrication: 검사 불가(경고) — 발행은 막지 않음")
    if codes["checklist.verify_coverage"] != 0:
        blocking.append("checklist.verify_coverage — 커버리지 배지가 거짓")
    if codes["verify_contract"] == 1:
        blocking.append("verify_contract — 규칙 누출(JSON 밖 규칙)")
    elif codes["verify_contract"] == 2:
        r.say("!! verify_contract: 계약 미충족(경고) — 발행은 막지 않음")
    if codes.get("verify_editable_auto", 0) != 0:
        blocking.append("verify_editable_auto — 자동판정 체크박스가 파이프라인 밖 하드코딩(editable 위험)")
    if codes["verdict.verify_rules_vs_spec"] == 1:
        blocking.append("verdict.verify_rules_vs_spec — 체크리스트↔수집요청 위반(누락/창작)")
    elif codes["verdict.verify_rules_vs_spec"] == 2:
        r.say("!! verdict.verify_rules_vs_spec: 검사 불가(경고) — 발행은 막지 않음")
    if codes.get("verdict.verify_metric_semantics", 0) != 0:
        r.say("!! verdict.verify_metric_semantics: 계산기 어긋남 감지 — 런타임에서 "
              "자동교체(🤖)/격리(🚧)로 안전 처리됨(틀린 값은 안 나감). 발행은 막지 않음.")

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
