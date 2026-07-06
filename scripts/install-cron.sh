#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/finance-news-digest}"
MARKER="# finance-news-digest"
DEEP_MARKER="# finance-deep-reads"
REDDIT_MARKER="# finance-reddit-digest"
CSI300_MARKER="# finance-csi300-analysis"
CSI500_MARKER="# finance-csi500-analysis"
CSI1000_MARKER="# finance-csi1000-analysis"
SECTOR_HOTSPOTS_MARKER="# finance-sector-hotspots"
US_SECTOR_HOTSPOTS_MARKER="# finance-us-sector-hotspots"
NATIONAL_TEAM_ETF_MARKER="# finance-national-team-etf-weekly"
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
if command -v flock >/dev/null 2>&1; then
  CSI300_COMMAND="/usr/bin/flock -n $PROJECT_ROOT/var/csi300-run.lock $PROJECT_ROOT/scripts/run-csi300-analysis.sh"
else
  CSI300_COMMAND="$PROJECT_ROOT/scripts/run-csi300-analysis.sh"
fi
if command -v flock >/dev/null 2>&1; then
  CSI500_COMMAND="/usr/bin/flock -n $PROJECT_ROOT/var/csi500-run.lock $PROJECT_ROOT/scripts/run-csi500-analysis.sh"
else
  CSI500_COMMAND="$PROJECT_ROOT/scripts/run-csi500-analysis.sh"
fi
if command -v flock >/dev/null 2>&1; then
  CSI1000_COMMAND="/usr/bin/flock -n $PROJECT_ROOT/var/csi1000-run.lock $PROJECT_ROOT/scripts/run-csi1000-analysis.sh"
else
  CSI1000_COMMAND="$PROJECT_ROOT/scripts/run-csi1000-analysis.sh"
fi
if command -v flock >/dev/null 2>&1; then
  SECTOR_HOTSPOTS_COMMAND="/usr/bin/flock -n $PROJECT_ROOT/var/sector-hotspots-run.lock $PROJECT_ROOT/scripts/run-sector-hotspots.sh"
else
  SECTOR_HOTSPOTS_COMMAND="$PROJECT_ROOT/scripts/run-sector-hotspots.sh"
fi
if command -v flock >/dev/null 2>&1; then
  US_SECTOR_HOTSPOTS_COMMAND="/usr/bin/flock -n $PROJECT_ROOT/var/us-sector-hotspots-run.lock $PROJECT_ROOT/scripts/run-us-sector-hotspots.sh"
else
  US_SECTOR_HOTSPOTS_COMMAND="$PROJECT_ROOT/scripts/run-us-sector-hotspots.sh"
fi
if command -v flock >/dev/null 2>&1; then
  NATIONAL_TEAM_ETF_COMMAND="/usr/bin/flock -n $PROJECT_ROOT/var/national-team-etf-run.lock $PROJECT_ROOT/scripts/run-national-team-etf-weekly.sh"
else
  NATIONAL_TEAM_ETF_COMMAND="$PROJECT_ROOT/scripts/run-national-team-etf-weekly.sh"
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
crontab -l 2>/dev/null \
  | grep -vF "$MARKER" \
  | grep -vF "$DEEP_MARKER" \
  | grep -vF "$REDDIT_MARKER" \
  | grep -vF "$CSI300_MARKER" \
  | grep -vF "$CSI500_MARKER" \
  | grep -vF "$CSI1000_MARKER" \
  | grep -vF "$SECTOR_HOTSPOTS_MARKER" \
  | grep -vF "$US_SECTOR_HOTSPOTS_MARKER" \
  | grep -vF "$NATIONAL_TEAM_ETF_MARKER" \
  | grep -v 'run-csi300-analysis.sh' \
  | grep -v 'run-csi500-analysis.sh' \
  | grep -v 'run-csi1000-analysis.sh' \
  | grep -v 'run-sector-hotspots.sh' \
  | grep -v 'run-us-sector-hotspots.sh' \
  | grep -v 'csi300-analysis.log' \
  | grep -v 'csi500-analysis.log' \
  | grep -v 'csi1000-analysis.log' \
  | grep -v 'sector-hotspots.log' \
  | grep -v 'us-sector-hotspots.log' \
  | grep -v 'run-national-team-etf-weekly.sh' \
  | grep -v 'national-team-etf-weekly.log' > "$tmp" || true
printf '0 4 * * * %s >> %s/var/log/cron.log 2>&1 %s\n' \
  "$COMMAND" "$PROJECT_ROOT" "$MARKER" >> "$tmp"
printf '0 5 * * 0 %s >> %s/var/log/deep-reads.log 2>&1 %s\n' \
  "$DEEP_COMMAND" "$PROJECT_ROOT" "$DEEP_MARKER" >> "$tmp"
printf '30 4 * * * %s >> %s/var/log/reddit-digest.log 2>&1 %s\n' \
  "$REDDIT_COMMAND" "$PROJECT_ROOT" "$REDDIT_MARKER" >> "$tmp"
printf '0 7 * * 2-6 %s >> %s/var/log/us-sector-hotspots.log 2>&1 %s\n' \
  "$US_SECTOR_HOTSPOTS_COMMAND" "$PROJECT_ROOT" "$US_SECTOR_HOTSPOTS_MARKER" >> "$tmp"
printf '30 15 * * 1-5 %s >> %s/var/log/csi300-analysis.log 2>&1 %s\n' \
  "$CSI300_COMMAND" "$PROJECT_ROOT" "$CSI300_MARKER" >> "$tmp"
printf '35 15 * * 1-5 %s >> %s/var/log/csi500-analysis.log 2>&1 %s\n' \
  "$CSI500_COMMAND" "$PROJECT_ROOT" "$CSI500_MARKER" >> "$tmp"
printf '40 15 * * 1-5 %s >> %s/var/log/csi1000-analysis.log 2>&1 %s\n' \
  "$CSI1000_COMMAND" "$PROJECT_ROOT" "$CSI1000_MARKER" >> "$tmp"
printf '0 16 * * 1-5 %s >> %s/var/log/sector-hotspots.log 2>&1 %s\n' \
  "$SECTOR_HOTSPOTS_COMMAND" "$PROJECT_ROOT" "$SECTOR_HOTSPOTS_MARKER" >> "$tmp"
printf '10 9 * * 6 %s >> %s/var/log/national-team-etf-weekly.log 2>&1 %s\n' \
  "$NATIONAL_TEAM_ETF_COMMAND" "$PROJECT_ROOT" "$NATIONAL_TEAM_ETF_MARKER" >> "$tmp"
crontab "$tmp"
crontab -l | grep -E 'finance-news-digest|finance-deep-reads|finance-reddit-digest|finance-csi[0-9]+-analysis|finance-sector-hotspots|finance-us-sector-hotspots|finance-national-team-etf-weekly'
