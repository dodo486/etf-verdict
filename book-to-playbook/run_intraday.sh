#!/bin/bash
DIR="$HOME/.claude/skills/book-to-playbook"
PY=/opt/homebrew/bin/python3
"$PY" "$DIR/etf_intraday_verdict.py" >> "$DIR/logs/intraday.log" 2>&1
"$PY" "$DIR/etf_daily_verdict.py" --json --no-send > "$DIR/latest-verdict.json" 2>/dev/null
"$PY" "$DIR/publish_pages.py"; "$PY" "$DIR/build_home.py" >> "$DIR/logs/intraday.log" 2>&1
if git -C "$DIR/public" remote get-url origin >/dev/null 2>&1; then
  cd "$DIR/public"; git add -A
  git -c user.name="조혜영" -c user.email="dodo486@users.noreply.github.com" commit -qm "auto(장중): $(date +%F\ %H:%M) 진입조건 갱신" 2>/dev/null && git push -q origin main 2>>"$DIR/logs/intraday.log" || true
fi
