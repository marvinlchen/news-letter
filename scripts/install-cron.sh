#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/finance-news-digest}"
MARKER="# finance-news-digest"
mkdir -p "$PROJECT_ROOT/var/log"

if command -v flock >/dev/null 2>&1; then
  COMMAND="/usr/bin/flock -n $PROJECT_ROOT/var/run.lock $PROJECT_ROOT/scripts/run-daily.sh"
else
  COMMAND="$PROJECT_ROOT/scripts/run-daily.sh"
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
crontab -l 2>/dev/null | grep -vF "$MARKER" > "$tmp" || true
printf '20 0 * * * %s >> %s/var/log/cron.log 2>&1 %s\n' \
  "$COMMAND" "$PROJECT_ROOT" "$MARKER" >> "$tmp"
crontab "$tmp"
crontab -l | grep -F "$MARKER"
