#!/bin/bash
# macOS / Linux 래퍼 — 실제 동작은 run.py(OS 중립)가 한다.
# launchd/cron 에서 이 파일을 그대로 호출하면 된다.
#   ./run.sh            (EOD)
#   ./run.sh intraday   (장중)
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 파이썬 고르기: 지정값 우선, 없으면 후보를 실제로 실행해 보고 되는 것만 채택.
# (단순히 command -v 로 잡으면 동작하지 않는 스텁을 고를 수 있다)
PY="${BOOK_TO_PLAYBOOK_PYTHON:-}"
if [ -z "$PY" ]; then
  for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)' >/dev/null 2>&1; then
      PY="$c"; break
    fi
  done
fi
if [ -z "$PY" ]; then
  echo "python3(3.7+)을 찾지 못했습니다. BOOK_TO_PLAYBOOK_PYTHON 에 경로를 지정하세요." >&2
  exit 1
fi

if [ "$#" -eq 0 ]; then set -- daily; fi
exec "$PY" "$DIR/run.py" "$@"
