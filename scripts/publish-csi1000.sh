#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/home/ME/finance-news-digest}"
PUBLISH_BRANCH="${PUBLISH_BRANCH:-main}"
export PATH="$HOME/.local/bin:$PATH"
cd "$PROJECT_ROOT"

# Find latest csi1000 report (exclude latest.md)
LATEST_MD="$(ls -t published/csi1000/*.md 2>/dev/null | grep -v latest | head -1)"
if [[ -z "$LATEST_MD" || ! -f "$LATEST_MD" ]]; then
  echo "publish-csi1000: no report found in published/csi1000/" >&2
  exit 1
fi

REPORT_DATE="$(basename "$LATEST_MD" .md)"

# Update latest.md
cp "$LATEST_MD" "published/csi1000/latest.md"

if git remote get-url origin >/dev/null 2>&1; then
  git pull --rebase --autostash origin "$PUBLISH_BRANCH"
fi

git add "published/csi1000/${REPORT_DATE}.md" published/csi1000/latest.md
if git diff --cached --quiet -- "published/csi1000/${REPORT_DATE}.md" published/csi1000/latest.md; then
  echo "publish-csi1000: report is unchanged"
  exit 0
fi

git commit --only "published/csi1000/${REPORT_DATE}.md" published/csi1000/latest.md \
  -m "Publish CSI1000 analysis ${REPORT_DATE}"
git push origin "HEAD:$PUBLISH_BRANCH"
echo "Published CSI1000 report for $REPORT_DATE"
