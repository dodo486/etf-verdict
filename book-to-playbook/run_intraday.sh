#!/bin/bash
# macOS / Linux 래퍼 (장중) — run.sh 와 동일 경로로 run.py intraday 호출.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$DIR/run.sh" intraday "$@"
