#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/home/ME/finance-news-digest}"
PUBLISH_BRANCH="${PUBLISH_BRANCH:-main}"
export PATH="$HOME/.local/bin:$PATH"
cd "$PROJECT_ROOT"

LATEST_MD="$(ls -t published/national-team-etf/*.md 2>/dev/null | grep -v '/latest.md$' | head -1)"
if [[ -z "$LATEST_MD" || ! -f "$LATEST_MD" ]]; then
  echo "publish-national-team-etf-weekly: no report found in published/national-team-etf/" >&2
  exit 1
fi

REPORT_DATE="$(basename "$LATEST_MD" .md)"
cp "$LATEST_MD" "published/national-team-etf/latest.md"

if git remote get-url origin >/dev/null 2>&1; then
  git pull --rebase --autostash origin "$PUBLISH_BRANCH"
fi

git add "published/national-team-etf/${REPORT_DATE}.md" published/national-team-etf/latest.md
if git diff --cached --quiet -- "published/national-team-etf/${REPORT_DATE}.md" published/national-team-etf/latest.md; then
  echo "publish-national-team-etf-weekly: report is unchanged"
  exit 0
fi

git commit --only "published/national-team-etf/${REPORT_DATE}.md" published/national-team-etf/latest.md \
  -m "Publish national team ETF weekly ${REPORT_DATE}"
git push origin "HEAD:$PUBLISH_BRANCH"
echo "Published national team ETF weekly report for $REPORT_DATE"
