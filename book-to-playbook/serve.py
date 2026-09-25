#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""etf-verdict 로컬 실시간 서버 — 정적 스냅샷(GitHub Pages)은 그대로 두고
같은 페이지를 '살아 움직이게' 얹는 점진적 향상(progressive enhancement) 계층.

두 모드, 한 파일:
  · GitHub Pages(정적)      → publish_pages.py 가 구운 스냅샷을 그대로 본다(서버 없음).
  · 이 서버(python3 serve.py) → 같은 etf-playbook.html 을 열면 /api/verdict 를
    폴링(또는 /events SSE 수신)해 값이 실시간으로 갱신된다.

엔드포인트
  GET /api/verdict   판정 JSON(라이브). etf_daily_verdict.py --json 을 그대로 재사용해
                     계산하고, 짧은 TTL 캐시(기본 8초)로 잦은 폴링이 야후를 두드리지
                     않게 막는다. CORS 허용(Access-Control-Allow-Origin: *).
  GET /events        SSE — ~15초마다 tick 을 밀어준다(캐시 무효화 후 최신 ts 동봉).
                     브라우저가 tick 을 받으면 /api/verdict 를 한 번 더 당겨 다시 그린다.
  GET / , /index.html  최신 판정을 #verdict-data 에 구워 넣은 etf 페이지(루트로 바로 열림).
  기타 정적 파일       BASE 디렉터리에서 그대로 서빙(폰트·이미지 등).

바인딩은 0.0.0.0(테일스케일/LAN 에서 폰으로 접속 가능). 포트는 ETF_VERDICT_PORT
환경변수(기본 8799).

설계 메모: 판정 계산부(compute_verdict)를 HTTP 배관과 분리해 둔다. 나중에
서버리스 함수로 그대로 들어낼 수 있도록 '판정을 만드는 순수 호출부'만 떼어 둔 것.
"""
import http.server
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable or "python3"
PORT = int(os.environ.get("ETF_VERDICT_PORT", "8799"))
HOST = os.environ.get("ETF_VERDICT_HOST", "0.0.0.0")
CACHE_TTL = float(os.environ.get("ETF_VERDICT_TTL", "8"))   # 초 — 잦은 폴링이 야후를 안 두드리게
SSE_TICK = float(os.environ.get("ETF_VERDICT_TICK", "15"))  # 초 — SSE tick 주기

# 어느 책을 라이브로 띄울지는 books.json 에서 온다(코드에 특정 책을 박지 않는다).
# BOOK_SLUG 로 덮어쓸 수 있고, 기본은 첫 live 책.
from paths import default_slug, book_engine, playbook_src   # noqa: E402
SLUG = os.environ.get("BOOK_SLUG") or default_slug()
PAGE_SRC = playbook_src(SLUG)
DAILY_ENGINE = book_engine(SLUG, "daily")
VERDICT_RE = re.compile(
    r'(<script type="application/json" id="verdict-data">)(.*?)(</script>)', re.S)

# ------------------------------------------------------------------ 판정 계산부
# (HTTP 배관과 분리 — 서버리스 함수로 그대로 이관 가능한 순수 호출부)
_cache_lock = threading.Lock()
_cache = {"data": None, "ts": 0.0, "err": None}


def _run_verdict():
    """etf_daily_verdict.py --json 을 한 프로세스로 돌려 판정 dict 를 받는다.

    로직을 복제하지 않고 **같은 스크립트의 --json 경로를 재사용**한다(run.py 가
    latest-verdict.json 을 만들 때와 동일한 호출). 새 프로세스라 매번 md_feed(야후)로
    새로 시세를 받는다. 텔레그램/데스크톱 알림은 --no-send 로 끈다.
    """
    if not DAILY_ENGINE:
        raise RuntimeError("%s 책에 시세 엔진(engine.daily)이 없습니다 — books.json 확인" % SLUG)
    cmd = [PY, os.path.join(BASE, DAILY_ENGINE), "--json", "--no-send"]
    p = subprocess.run(cmd, cwd=BASE, capture_output=True, timeout=90)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or b"").decode("utf-8", "replace")[:400]
                           or "verdict 계산 실패(코드 %d)" % p.returncode)
    data = json.loads(p.stdout.decode("utf-8"))
    # 라이브 모드임을 프런트가 알 수 있게 소스 라벨을 동봉(정직한 신선도 표기용)
    data["source"] = "야후(marketdata)"
    data["live"] = True
    # 서버는 EOD 판정만 계산한다(장중 KIS 자동판정은 M2에서 제거됨).
    # 프런트의 장중 뱃지가 '수집 실패'로 오해하지 않도록 대기 상태로 표시.
    data.setdefault("intraday_state", "pending")
    return data


def compute_verdict(force=False):
    """TTL 캐시가 살아 있으면 캐시를, 아니면 새로 계산해 (data, from_cache) 반환.

    서버리스로 옮길 때는 이 함수 하나만 들어내면 된다(캐시는 프로세스 지역 캐시라
    서버리스에선 무해하게 매번 계산으로 동작한다)."""
    now = time.time()
    with _cache_lock:
        fresh = (not force and _cache["data"] is not None
                 and (now - _cache["ts"]) < CACHE_TTL)
        if fresh:
            return _cache["data"], True
    # 캐시 계산은 락 밖에서(수 초 걸리는 네트워크 호출 동안 다른 요청 안 막게)
    data = _run_verdict()
    with _cache_lock:
        _cache["data"] = data
        _cache["ts"] = time.time()
        _cache["err"] = None
    return data, False


def render_page():
    """최신 판정을 #verdict-data 에 구워 넣은 etf 페이지 HTML.

    서버 루트(/)를 바로 열어도 최신값이 보이도록. 폴링/SSE 코드는 페이지 안에
    이미 들어 있어(정적 스냅샷과 동일 파일) 이후엔 스스로 갱신한다.
    """
    html = open(PAGE_SRC, encoding="utf-8").read()
    # 발행 파이프라인과 동일하게 조립한다 — #rules(체크리스트 데이터)·공유 UI(ui/*.js)·
    # 좌측 책 레일(nav)을 여기서 얹는다. 특히 rules 를 주입하지 않으면 페이지에 구워진
    # 옛 #rules 사본(드리프트)이 서빙돼 최신 books/etf/rules.json 의 병합·수정이 안 보인다.
    try:
        from inject_rules import inject as _inject_rules
        html = _inject_rules(html, SLUG)
    except Exception:
        pass
    try:
        from inject_ui import inject as _inject_ui
        html = _inject_ui(html)
    except Exception:
        pass
    # 지표 레지스트리 주입 — 체크리스트가 mtype 으로 🤖자동/🚧미구현/✋직접을 구분해 보이게 한다.
    try:
        import re as _re
        _reg = open(os.path.join(BASE, "metric_registry.json"), encoding="utf-8").read()
        html = _re.sub(r'(<script type="application/json" id="metric-registry">).*?(</script>)',
                       lambda m: m.group(1) + _reg + m.group(2), html, count=1, flags=_re.S)
    except Exception:
        pass
    try:
        import inject_nav
        html = inject_nav.inject(html, SLUG)
    except Exception:
        pass
    try:
        data, _ = compute_verdict()
        blob = json.dumps(data, ensure_ascii=False)
        html = VERDICT_RE.sub(lambda m: m.group(1) + "\n" + blob + "\n" + m.group(3), html)
    except Exception:
        # 계산 실패해도 스냅샷 페이지는 그대로 내보낸다(프런트가 폴링으로 재시도).
        pass
    return html.encode("utf-8")


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
        if route in ("/", "/index.html", "/%s/" % SLUG, "/%s/index.html" % SLUG):
            return self._serve_page()
        return super().do_GET()

    def _serve_page(self):
        try:
            body = render_page()
        except Exception as ex:
            body = ("페이지 렌더 실패: %s" % ex).encode("utf-8")
            return self._send(body, "text/plain; charset=utf-8", 500)
        self._send(body, "text/html; charset=utf-8")

    def _serve_verdict(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        force = "force" in qs
        try:
            data, cached = compute_verdict(force=force)
            data = dict(data)
            data["_cached"] = cached
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send(body, "application/json; charset=utf-8")
        except Exception as ex:
            body = json.dumps({"error": str(ex)}, ensure_ascii=False).encode("utf-8")
            self._send(body, "application/json; charset=utf-8", 500)

    def _serve_sse(self):
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
                data, _ = compute_verdict()
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
    """첫 요청 전에 판정을 한 번 데워 첫 클릭 지연(수 초 콜드 페치)을 없앤다."""
    try:
        compute_verdict()
    except Exception:
        pass


if __name__ == "__main__":
    os.chdir(BASE)
    print("%s 로컬 실시간 서버" % SLUG)
    print("  로컬:      http://127.0.0.1:%d/" % PORT)
    print("  LAN/폰:    http://<이 컴퓨터 IP 또는 테일스케일 MagicDNS>:%d/" % PORT)
    print("  판정 JSON: http://127.0.0.1:%d/api/verdict" % PORT)
    print("  (종료: Ctrl+C)")
    threading.Thread(target=_warm, daemon=True).start()
    with http.server.ThreadingHTTPServer((HOST, PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n종료")
