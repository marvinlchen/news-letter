#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/home/ME/finance-news-digest}"
PUBLISH_BRANCH="${PUBLISH_BRANCH:-main}"
export PATH="$HOME/.local/bin:$PATH"
cd "$PROJECT_ROOT"

# Find latest csi300 report (exclude latest.md)
LATEST_MD="$(ls -t published/csi300/*.md 2>/dev/null | grep -v latest | head -1)"
if [[ -z "$LATEST_MD" || ! -f "$LATEST_MD" ]]; then
  echo "publish-csi300: no report found in published/csi300/" >&2
  exit 1
fi

REPORT_DATE="$(basename "$LATEST_MD" .md)"

# Update latest.md symlink or copy
cp "$LATEST_MD" "published/csi300/latest.md"

if git remote get-url origin >/dev/null 2>&1; then
  git pull --rebase --autostash origin "$PUBLISH_BRANCH"
fi

git add "published/csi300/${REPORT_DATE}.md" published/csi300/latest.md
if git diff --cached --quiet; then
  echo "publish-csi300: report is unchanged"
  exit 0
fi

git commit -m "Publish CSI300 analysis ${REPORT_DATE}"
git push origin "HEAD:$PUBLISH_BRANCH"
echo "Published CSI300 report for $REPORT_DATE"
