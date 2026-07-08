#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/home/ME/finance-news-digest}"
PUBLISH_BRANCH="${PUBLISH_BRANCH:-main}"
export PATH="$HOME/.local/bin:$PATH"
cd "$PROJECT_ROOT"

LATEST_MD="$(ls -t published/stock-pool/*.md 2>/dev/null | grep -v '/latest.md$' | head -1)"
if [[ -z "$LATEST_MD" || ! -f "$LATEST_MD" ]]; then
  echo "publish-stock-pool: no report found in published/stock-pool/" >&2
  exit 1
fi

REPORT_DATE="$(basename "$LATEST_MD" .md)"
cp "$LATEST_MD" "published/stock-pool/latest.md"

if git remote get-url origin >/dev/null 2>&1; then
  git pull --rebase --autostash origin "$PUBLISH_BRANCH"
fi

git add "published/stock-pool/${REPORT_DATE}.md" published/stock-pool/latest.md
if git diff --cached --quiet -- "published/stock-pool/${REPORT_DATE}.md" published/stock-pool/latest.md; then
  echo "publish-stock-pool: report is unchanged"
  exit 0
fi

git commit --only "published/stock-pool/${REPORT_DATE}.md" published/stock-pool/latest.md \
  -m "Publish stock pool news ${REPORT_DATE}"
git push origin "HEAD:$PUBLISH_BRANCH"
echo "Published stock pool news report for $REPORT_DATE"
