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
update_status_publish_commit() {
  local commit="$1"
  python3 - "$PROJECT_ROOT" csi300 "$REPORT_DATE" "$commit" <<'PY'
import json
import sys
from pathlib import Path

root, index, report_date, commit = sys.argv[1:5]
status_dir = Path(root) / "var" / "csi-status" / index
for path in (status_dir / f"{report_date}.json", status_dir / "latest.json"):
    if not path.exists():
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    data["publish_commit"] = commit
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

# Update latest.md symlink or copy
cp "$LATEST_MD" "published/csi300/latest.md"

if git remote get-url origin >/dev/null 2>&1; then
  git pull --rebase --autostash origin "$PUBLISH_BRANCH"
fi

git add "published/csi300/${REPORT_DATE}.md" published/csi300/latest.md
if git diff --cached --quiet -- "published/csi300/${REPORT_DATE}.md" published/csi300/latest.md; then
  echo "publish-csi300: report is unchanged"
  update_status_publish_commit "$(git rev-parse HEAD)"
  exit 0
fi

git commit --only "published/csi300/${REPORT_DATE}.md" published/csi300/latest.md \
  -m "Publish CSI300 analysis ${REPORT_DATE}"
git push origin "HEAD:$PUBLISH_BRANCH"
update_status_publish_commit "$(git rev-parse HEAD)"
echo "Published CSI300 report for $REPORT_DATE"
