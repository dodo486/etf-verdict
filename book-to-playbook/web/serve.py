#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""book-to-playbook 로컬 실시간 서버 — 화면을 보는 유일한 경로(정적 스냅샷은 폐지됨).

한 주소로 고정이다. books.json 에 어떤 책이 들어와도 **서버 재시작 없이** 바로 잡힌다
(_slugs()·render_shell 이 매 요청 books.json 을 새로 읽는다). 매 요청 엔진을 새로 돌려
그리므로 오래된 값이 '지금 값'처럼 보일 여지가 없다.

엔드포인트
  GET /                셸(책 선택) — 좌측 책목록 + 본문 iframe. 책을 눌러도 셸은 그대로, 본문만 바뀐다.
  GET /<slug>/         그 책 페이지 — 요청 시점 라이브 판정을 구워 넣는다(assemble).
  GET /api/verdict?slug=<책>  판정 JSON(라이브). 엔진(books.json engine.daily) --json 재사용 + 짧은
                     TTL 캐시(기본 8초, 책별)로 잦은 폴링이 시세 창구를 안 두드리게. CORS 허용.
  GET /events?slug=<책>       SSE — ~15초마다 tick(브라우저가 받으면 /api/verdict 를 다시 당겨 재렌더).
  기타 정적 파일       BASE 디렉터리에서 그대로 서빙(폰트·이미지 등).

바인딩은 0.0.0.0(테일스케일/LAN 에서 폰으로 접속 가능). 포트는 PLAYBOOK_PORT 환경변수(기본 8799).

설계 메모: 판정 계산부(compute_verdict)를 HTTP 배관과 분리해 둔다 — 서버리스로 그대로 이관 가능하게."""
import http.server
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse

PY = sys.executable or "python3"
PORT = int(os.environ.get("PLAYBOOK_PORT", "8799"))
HOST = os.environ.get("PLAYBOOK_HOST", "0.0.0.0")
CACHE_TTL = float(os.environ.get("PLAYBOOK_TTL", "8"))   # 초 — 잦은 폴링이 시세 창구를 안 두드리게
SSE_TICK = float(os.environ.get("PLAYBOOK_TICK", "15"))  # 초 — SSE tick 주기

# 어느 책을 라이브로 띄울지는 books.json 에서 온다(코드에 특정 책을 박지 않는다).
# BOOK_SLUG 로 덮어쓸 수 있고, 기본은 첫 live 책.
from shared.paths import BASE, default_slug, book_engine, live_slugs, load_manifest   # noqa: E402
DEFAULT_SLUG = os.environ.get("BOOK_SLUG") or (live_slugs() or [default_slug()])[0]


def _slugs():
    """지금 books.json 에 있는 라이브 책 전부 — 매 요청 새로 읽는다. 책을 추가하면 서버 재시작 없이
    바로 셸 목록·라우팅·API 에 잡힌다(한 주소 고정, 어떤 책이 들어와도)."""
    return live_slugs() or [DEFAULT_SLUG]

# ------------------------------------------------------------------ 판정 계산부
# (HTTP 배관과 분리 — 서버리스 함수로 그대로 이관 가능한 순수 호출부)
_cache_lock = threading.Lock()
_cache = {}                       # slug -> {"data":..., "ts":...}  (책마다 따로 캐시)


def _run_verdict(slug):
    """엔진(books.json engine.daily) --json 을 한 프로세스로 돌려 판정 dict 를 받는다 — 매번 새 시세로.

    로직을 복제하지 않고 **같은 엔진 모듈의 --json 경로를 재사용**한다. 텔레그램/데스크톱 알림은
    --no-send 로 끈다. 라이브 전용이라 정적 스냅샷 파일(latest-verdict)은 읽지도 쓰지도 않는다."""
    daily = book_engine(slug, "daily")
    if not daily:
        raise RuntimeError("%s 책에 시세 엔진(engine.daily)이 없습니다 — books.json 확인" % slug)
    cmd = [PY, "-m", daily, slug, "--json", "--no-send"]
    p = subprocess.run(cmd, cwd=BASE, capture_output=True, timeout=90)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or b"").decode("utf-8", "replace")[:400]
                           or "verdict 계산 실패(코드 %d)" % p.returncode)
    data = json.loads(p.stdout.decode("utf-8"))
    data["live"] = True          # 라이브 모드임을 프런트가 알 수 있게(정직한 신선도 표기용)
    return data


def compute_verdict(slug, force=False):
    """책 slug 의 판정 — TTL 캐시가 살아 있으면 캐시를, 아니면 새로 계산해 (data, from_cache) 반환."""
    now = time.time()
    with _cache_lock:
        c = _cache.get(slug)
        if not force and c and (now - c["ts"]) < CACHE_TTL:
            return c["data"], True
    data = _run_verdict(slug)                 # 락 밖에서(수 초 걸리는 호출이 다른 요청 안 막게)
    with _cache_lock:
        _cache[slug] = {"data": data, "ts": time.time()}
    return data, False


def render_page(slug):
    """책 slug 페이지 HTML — 요청 시점의 라이브 판정(내 포지션 포함)을 구워 넣는다. 조립은 assemble 하나로.
    판정 계산이 실패해도 페이지는 내보낸다(프런트가 폴링으로 재시도)."""
    from web.book_page import assemble
    try:
        data, _ = compute_verdict(slug)
    except Exception:
        data = None
    return assemble(slug, data).encode("utf-8")


def render_shell():
    """책 선택 셸(홈) — books.json 의 모든 책을 좌측 목록에, 본문은 /<slug>/ 를 라이브로 띄운다."""
    from web.build_home import render_home
    return render_home(load_manifest()).encode("utf-8")


# ------------------------------------------------------------------ HTTP 배관
class Handler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"   # SSE keep-alive

    def __init__(self, *a, **k):
        super().__init__(*a, directory=BASE, **k)

    def log_message(self, *a):   # 콘솔 조용히
        pass

    def handle_one_request(self):
        # 브라우저/curl 이 keep-alive 소켓을 갑자기 닫을 때 나는 ConnectionReset
        # 트레이스백을 삼킨다(정상 종료 — 스팸 방지).
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True

    # ---- 응답 헬퍼 ----
    def _send(self, body, ctype, code=200, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        route = urllib.parse.urlparse(self.path).path
        if route == "/api/verdict":
            return self._serve_verdict()
        if route == "/events":
            return self._serve_sse()
        if route in ("/", "/index.html"):
            return self._serve_shell()
        m = re.match(r"^/([^/]+)/(?:index\.html)?$", route)
        if m and m.group(1) in _slugs():
            return self._serve_page(m.group(1))
        return super().do_GET()

    def _serve_shell(self):
        try:
            body = render_shell()
        except Exception as ex:
            return self._send(("셸 렌더 실패: %s" % ex).encode("utf-8"), "text/plain; charset=utf-8", 500)
        self._send(body, "text/html; charset=utf-8")

    def _serve_page(self, slug):
        try:
            body = render_page(slug)
        except Exception as ex:
            body = ("페이지 렌더 실패: %s" % ex).encode("utf-8")
            return self._send(body, "text/plain; charset=utf-8", 500)
        self._send(body, "text/html; charset=utf-8")

    def _serve_verdict(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        force = "force" in qs
        slug = (qs.get("slug") or [DEFAULT_SLUG])[0]
        if slug not in _slugs():
            slug = DEFAULT_SLUG
        try:
            data, cached = compute_verdict(slug, force=force)
            data = dict(data)
            data["_cached"] = cached
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send(body, "application/json; charset=utf-8")
        except Exception as ex:
            body = json.dumps({"error": str(ex)}, ensure_ascii=False).encode("utf-8")
            self._send(body, "application/json; charset=utf-8", 500)

    def _serve_sse(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        slug = (qs.get("slug") or [DEFAULT_SLUG])[0]
        if slug not in _slugs():
            slug = DEFAULT_SLUG
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self.wfile.write(b"retry: 5000\ndata: hello\n\n")
            self.wfile.flush()
        except Exception:
            return
        last_ts = None
        beat = 0
        while True:
            time.sleep(SSE_TICK)
            try:
                data, _ = compute_verdict(slug)
                ts = data.get("ts")
                payload = json.dumps({"ts": ts}, ensure_ascii=False)
                self.wfile.write(("data: %s\n\n" % payload).encode("utf-8"))
                self.wfile.flush()
                last_ts = ts
                beat = 0
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                break   # 브라우저가 닫음 — 스레드 종료(EventSource 자동 재접속)
            except Exception:
                beat += 1
                try:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                except OSError:
                    break


def _warm():
    """첫 요청 전에 기본 책을 한 번 데워 첫 클릭 지연(수 초 콜드 페치)을 없앤다."""
    try:
        compute_verdict(DEFAULT_SLUG)
    except Exception:
        pass


if __name__ == "__main__":
    os.chdir(BASE)
    print("로컬 실시간 서버 — 책: %s" % ", ".join(_slugs()))
    print("  로컬:      http://127.0.0.1:%d/  (셸 · 책 전환)" % PORT)
    print("  LAN/폰:    http://<이 컴퓨터 IP 또는 테일스케일 MagicDNS>:%d/" % PORT)
    print("  판정 JSON: http://127.0.0.1:%d/api/verdict?slug=<책>" % PORT)
    print("  (종료: Ctrl+C)")
    threading.Thread(target=_warm, daemon=True).start()
    with http.server.ThreadingHTTPServer((HOST, PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n종료")
