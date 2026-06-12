#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/finance-news-digest}"
MARKER="# finance-news-digest"
DEEP_MARKER="# finance-deep-reads"
REDDIT_MARKER="# finance-reddit-digest"
mkdir -p "$PROJECT_ROOT/var/log"

if command -v flock >/dev/null 2>&1; then
  COMMAND="/usr/bin/flock -n $PROJECT_ROOT/var/run.lock $PROJECT_ROOT/scripts/run-daily.sh"
else
  COMMAND="$PROJECT_ROOT/scripts/run-daily.sh"
fi
if command -v flock >/dev/null 2>&1; then
  DEEP_COMMAND="/usr/bin/flock -n $PROJECT_ROOT/var/deep-run.lock $PROJECT_ROOT/scripts/run-deep-reads.sh"
else
  DEEP_COMMAND="$PROJECT_ROOT/scripts/run-deep-reads.sh"
fi
if command -v flock >/dev/null 2>&1; then
  REDDIT_COMMAND="/usr/bin/flock -n $PROJECT_ROOT/var/reddit-run.lock $PROJECT_ROOT/scripts/run-reddit-digest.sh"
else
  REDDIT_COMMAND="$PROJECT_ROOT/scripts/run-reddit-digest.sh"
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -vF "$DEEP_MARKER" | grep -vF "$REDDIT_MARKER" > "$tmp" || true
printf '0 4 * * * %s >> %s/var/log/cron.log 2>&1 %s\n' \
  "$COMMAND" "$PROJECT_ROOT" "$MARKER" >> "$tmp"
printf '0 5 * * 0 %s >> %s/var/log/deep-reads.log 2>&1 %s\n' \
  "$DEEP_COMMAND" "$PROJECT_ROOT" "$DEEP_MARKER" >> "$tmp"
printf '30 4 * * * %s >> %s/var/log/reddit-digest.log 2>&1 %s\n' \
  "$REDDIT_COMMAND" "$PROJECT_ROOT" "$REDDIT_MARKER" >> "$tmp"
crontab "$tmp"
crontab -l | grep -E 'finance-news-digest|finance-deep-reads|finance-reddit-digest'
