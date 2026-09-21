#!/bin/bash
DIR="$HOME/.claude/skills/book-to-playbook"
PY=/opt/homebrew/bin/python3
[ -f "$DIR/telegram.env" ] && set -a && . "$DIR/telegram.env" && set +a
"$PY" "$DIR/etf_daily_verdict.py" >> "$DIR/logs/cron.log" 2>&1
"$PY" "$DIR/etf_daily_verdict.py" --json --no-send > "$DIR/latest-verdict.json" 2>/dev/null
"$PY" "$DIR/publish_pages.py"; "$PY" "$DIR/build_home.py" >> "$DIR/logs/cron.log" 2>&1
if git -C "$DIR/public" remote get-url origin >/dev/null 2>&1; then
  cd "$DIR/public"
  git add -A
  git -c user.name="조혜영" -c user.email="dodo486@users.noreply.github.com" commit -qm "auto: $(date +%F) 판정 갱신" 2>/dev/null && git push -q origin main 2>>"$DIR/logs/cron.log" || true
fi
